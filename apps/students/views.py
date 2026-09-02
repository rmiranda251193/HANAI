import logging

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ai.exceptions import AIError
from apps.lessons.models import Lesson
from apps.teachers.services import (
    RecommendationError,
    RecommendationNotFound,
    count_pending_recommendations,
    dismiss_recommendation,
    list_student_recommendations,
    open_recommendation,
)

from .exceptions import EmptyTutorMessageError, MisconceptionDecisionError, TutorError
from .misconception_services import apply_teacher_decision
from .models import (
    ExperimentAttempt,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from .pattern_services import build_student_learning_patterns
from .practice_services import (
    AnswerValidationError,
    PracticeError,
    build_practice_feedback,
    build_practice_page,
    record_practice_attempt,
)
from .progress_services import build_student_learning_progress
from .requests import ExperimentContext
from .services import run_tutor_turn

logger = logging.getLogger(__name__)

GUEST_DISPLAY_NAME = "Guest learner"

TUTOR_ERROR_MESSAGE = (
    "The tutor could not respond right now. Please check the AI configuration and try again."
)
EMPTY_QUESTION_MESSAGE = "Type a question before sending it to the tutor."
EMPTY_ATTEMPT_MESSAGE = "Write your attempt before sending it to the tutor."
DECISION_SAVED_MESSAGE = "Your decision was recorded."


def _current_student(request) -> StudentProfile:
    """Return the acting student profile.

    TODO(auth): once student login exists, always resolve this from
    ``request.user`` and drop the shared guest profile.
    """

    user = request.user if getattr(request.user, "is_authenticated", False) else None
    if user is not None:
        profile, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults={"display_name": user.get_username() or "Student"},
        )
        return profile

    profile, _ = StudentProfile.objects.get_or_create(
        user=None,
        defaults={"display_name": GUEST_DISPLAY_NAME},
    )
    return profile


def _current_teacher(request):
    """The acting teacher, or None in local development without auth.

    TODO(auth): require an authenticated teacher for the insight decision views.
    """

    return request.user if getattr(request.user, "is_authenticated", False) else None


def _active_session(student: StudentProfile, lesson: Lesson) -> TutorSession:
    session = (
        TutorSession.objects.filter(
            student=student,
            lesson=lesson,
            status=TutorSession.Status.ACTIVE,
        )
        .order_by("-started_at")
        .first()
    )
    if session is None:
        session = TutorSession.objects.create(student=student, lesson=lesson)
    return session


def _practice_problems(lesson: Lesson) -> list[str]:
    problems: list[str] = []
    for item in lesson.problems or []:
        if isinstance(item, str) and item.strip():
            problems.append(item.strip())
        elif isinstance(item, dict):
            text = (
                item.get("problem")
                or item.get("question")
                or item.get("prompt")
                or item.get("text")
            )
            if isinstance(text, str) and text.strip():
                problems.append(text.strip())

    if not problems:
        topic = lesson.topic or "physics"
        problems.append(
            f"In your own words, outline the steps you would take to solve a typical "
            f"{topic} problem, and name the equation that connects the quantities involved."
        )
    return problems


def _clamp_index(raw_value, items: list) -> int:
    try:
        index = int(raw_value)
    except (TypeError, ValueError):
        return 0
    if index < 0 or index >= len(items):
        return 0
    return index


def _experiment_attempt_for(student: StudentProfile, raw_id):
    """Load an experiment attempt by id, only if it belongs to this student."""

    try:
        attempt_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return (
        ExperimentAttempt.objects.filter(pk=attempt_id, student=student)
        .select_related("simulation")
        .first()
    )


def student_home(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")[:6]
    return render(request, "students/home.html", {"lessons": lessons})


def student_lessons(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")
    return render(request, "students/lessons.html", {"lessons": lessons})


def student_progress(request):
    """A scientific learning journal for the current student only.

    The student is always resolved from the existing session mechanism; a
    ``?student_id=`` (or any other) query parameter is never used as authority.
    """

    student = _current_student(request)
    context = build_student_learning_progress(student=student)
    context["student"] = student
    context["recommendations_pending"] = count_pending_recommendations(student)
    return render(request, "students/progress.html", context)


def learning_patterns(request):
    """A factual synthesis of the current student's recent Physics activity.

    Deterministic and read-only: the same records always produce the same
    patterns, and no AI provider is involved. The student is resolved from the
    session only -- ``?student_id=`` is never authority.
    """

    student = _current_student(request)
    context = build_student_learning_patterns(student=student)
    context["student"] = student
    return render(request, "students/learning.html", context)


def student_recommendations(request):
    """The current student's own recommendation inbox. No cross-student access."""

    student = _current_student(request)
    data = list_student_recommendations(student=student)
    return render(
        request,
        "students/recommendations.html",
        {
            "student": student,
            "pending": data["pending"],
            "history": data["history"],
        },
    )


@require_POST
def recommendation_open(request, intervention_id):
    """Record pending -> opened, then redirect to the server-chosen destination."""

    student = _current_student(request)
    try:
        destination = open_recommendation(
            intervention_id=intervention_id, student=student
        )
    except RecommendationNotFound:
        raise Http404("That recommendation is not available.")
    return redirect(destination or "students:recommendations")


@require_POST
def recommendation_dismiss(request, intervention_id):
    """Let the student dismiss one of their own pending/opened recommendations."""

    student = _current_student(request)
    try:
        dismiss_recommendation(intervention_id=intervention_id, student=student)
    except RecommendationNotFound:
        raise Http404("That recommendation is not available.")
    except RecommendationError as exc:
        data = list_student_recommendations(student=student)
        return render(
            request,
            "students/recommendations.html",
            {
                "student": student,
                "pending": data["pending"],
                "history": data["history"],
                "recommendation_error": str(exc),
            },
        )
    return redirect("students:recommendations")


def tutor_view(request, slug):
    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    student = _current_student(request)
    session = _active_session(student, lesson)

    practice_problems = _practice_problems(lesson)
    problem_index = _clamp_index(
        request.POST.get("problem_index")
        if request.method == "POST"
        else request.GET.get("problem"),
        practice_problems,
    )

    # A GET ``prefill`` lets another page (e.g. the Physics Lab) hand the student
    # a starting message. It only pre-fills the textarea; nothing is sent until
    # the student presses Send, so this never creates a turn on its own.
    initial_question = ""
    if request.method == "GET":
        initial_question = request.GET.get("prefill", "")[:2000]

    # An ``experiment`` id (from the Physics Lab "Ask the Tutor" link) attaches
    # the deterministic experiment values + prediction/observation/explanation
    # to the tutor turn as structured context.
    experiment_attempt = _experiment_attempt_for(
        student,
        request.GET.get("experiment")
        if request.method == "GET"
        else request.POST.get("experiment"),
    )

    context = {
        "lesson": lesson,
        "session": session,
        "initial_question": initial_question,
        "experiment_attempt": experiment_attempt,
        "practice_problem": practice_problems[problem_index],
        "practice_problem_index": problem_index,
        "practice_problem_count": len(practice_problems),
    }

    if request.method == "POST":
        action = request.POST.get("action", "ask")
        experiment_context = (
            ExperimentContext.from_attempt(experiment_attempt)
            if experiment_attempt is not None
            else None
        )
        try:
            if action == "practice":
                attempt = request.POST.get("attempt", "")
                if not attempt.strip():
                    context["tutor_error"] = EMPTY_ATTEMPT_MESSAGE
                else:
                    run_tutor_turn(
                        session,
                        practice_problem=practice_problems[problem_index],
                        student_attempt=attempt,
                    )
                    context["workflow_message"] = "The tutor reviewed your attempt below."
            else:
                question = request.POST.get("question", "")
                if not question.strip():
                    context["tutor_error"] = EMPTY_QUESTION_MESSAGE
                else:
                    run_tutor_turn(
                        session,
                        student_question=question,
                        experiment=experiment_context,
                    )
                    context["workflow_message"] = "Your tutor replied below."
        except EmptyTutorMessageError as exc:
            context["tutor_error"] = str(exc)
        except (AIError, TutorError, ValueError) as exc:
            logger.warning(
                "Tutor turn failed for lesson %s (%s).",
                lesson.pk,
                exc.__class__.__name__,
            )
            context["tutor_error"] = TUTOR_ERROR_MESSAGE
        except Exception:
            logger.exception("Unexpected tutor failure for lesson %s.", lesson.pk)
            context["tutor_error"] = TUTOR_ERROR_MESSAGE

    conversation = list(session.messages.all())
    context["conversation"] = conversation
    context["latest_tutor_message"] = next(
        (m for m in reversed(conversation) if m.role == TutorMessage.Role.TUTOR),
        None,
    )
    return render(request, "students/tutor.html", context)


PRACTICE_RECORD_ERROR = "Your answer could not be recorded. Please try again."


def practice_view(request, slug):
    """Deterministic Physics practice for one lesson and the current student.

    Every question and its expected answer are resolved on the server from
    trusted lesson data. The POST carries only ``question_key`` and ``answer``;
    any other field (``expected_answer``, ``is_correct``, ``student_id`` ...) is
    ignored. The acting student always comes from the session.
    """

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"), slug=slug
    )
    student = _current_student(request)
    session = _active_session(student, lesson)

    current_key = (request.GET.get("q") or "").strip() or None
    last_feedback = None
    error = ""

    if request.method == "POST":
        current_key = (request.POST.get("question_key") or "").strip() or None
        try:
            attempt = record_practice_attempt(
                student=student,
                lesson=lesson,
                question_key=current_key or "",
                submitted_answer=request.POST.get("answer", ""),
                session=session,
            )
        except (AnswerValidationError, PracticeError) as exc:
            error = str(exc)
        except Exception:
            logger.exception("Unexpected practice failure for lesson %s.", lesson.pk)
            error = PRACTICE_RECORD_ERROR
        else:
            current_key = attempt.question_key
            last_feedback = build_practice_feedback(attempt, lesson=lesson)

    context = build_practice_page(
        lesson=lesson,
        student=student,
        current_key=current_key,
        last_feedback=last_feedback,
        error=error,
    )
    context["student"] = student
    return render(request, "students/practice.html", context)


# --- Teacher-facing insight views -------------------------------------------------


def _lesson_observations(lesson: Lesson):
    concept_ids = list(lesson.physics_concepts.values_list("pk", flat=True))
    query = (
        StudentMisconception.objects.select_related(
            "student", "misconception", "misconception__physics_concept"
        )
        .prefetch_related("evidence")
        .order_by("status", "-last_observed_at")
    )
    if concept_ids:
        query = query.filter(misconception__physics_concept_id__in=concept_ids)
    else:
        query = query.none()
    return list(query)


def _lesson_experiments(lesson: Lesson):
    """Physics Lab experiment evidence tied to this lesson or its concepts.

    Each row carries whether the student took it to the tutor and the most
    recent *possible* misconception on the same concept (title, never a code).
    """

    from types import SimpleNamespace

    from django.db.models import Q

    concept_ids = list(lesson.physics_concepts.values_list("pk", flat=True))
    condition = Q(lesson=lesson)
    if concept_ids:
        condition |= Q(simulation__concept_id__in=concept_ids)

    attempts = (
        ExperimentAttempt.objects.filter(condition)
        .exclude(prediction="", observation="", explanation="")
        .select_related("student", "simulation", "simulation__concept")
        .order_by("-started_at")[:25]
    )

    rows = []
    for attempt in attempts:
        tutor_feedback = bool(
            attempt.session_id
            and TutorMessage.objects.filter(
                session_id=attempt.session_id, role=TutorMessage.Role.TUTOR
            ).exists()
        )
        misconception = (
            StudentMisconception.objects.filter(
                student=attempt.student,
                misconception__physics_concept=attempt.simulation.concept,
            )
            .exclude(status=StudentMisconception.Status.DISMISSED)
            .select_related("misconception")
            .order_by("-last_observed_at")
            .first()
        )
        rows.append(
            SimpleNamespace(
                attempt=attempt,
                tutor_feedback=tutor_feedback,
                misconception=misconception,
            )
        )
    return rows


def _render_insights(request, lesson: Lesson, **extra_context):
    observations = _lesson_observations(lesson)
    context = {
        "lesson": lesson,
        "observations": observations,
        "experiments": _lesson_experiments(lesson),
        "candidate_status": StudentMisconception.Status.CANDIDATE,
        "has_candidates": any(
            obs.status == StudentMisconception.Status.CANDIDATE for obs in observations
        ),
    }
    context.update(extra_context)
    return render(request, "students/insights.html", context)


def lesson_insights(request, slug):
    """Teacher view of *possible* misconceptions for this lesson's concepts."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"), slug=slug
    )
    return _render_insights(request, lesson)


@require_POST
def misconception_decision(request, slug, observation_id):
    """Record an explicit teacher decision on one observation."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"), slug=slug
    )
    observation = get_object_or_404(StudentMisconception, pk=observation_id)

    try:
        apply_teacher_decision(
            observation,
            request.POST.get("decision", ""),
            teacher=_current_teacher(request),
            note=request.POST.get("note", ""),
        )
    except MisconceptionDecisionError as exc:
        return _render_insights(request, lesson, decision_error=str(exc))
    except Exception:
        logger.exception(
            "Unexpected misconception decision failure for lesson %s.", lesson.pk
        )
        return _render_insights(
            request,
            lesson,
            decision_error="Your decision could not be saved. Please try again.",
        )

    return _render_insights(
        request, lesson, workflow_message=DECISION_SAVED_MESSAGE
    )
