import logging

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.ai.exceptions import AIError
from apps.lessons.models import Lesson

from .exceptions import EmptyTutorMessageError, MisconceptionDecisionError, TutorError
from .misconception_services import apply_teacher_decision
from .models import StudentMisconception, StudentProfile, TutorMessage, TutorSession
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


def student_home(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")[:6]
    return render(request, "students/home.html", {"lessons": lessons})


def student_lessons(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")
    return render(request, "students/lessons.html", {"lessons": lessons})


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

    context = {
        "lesson": lesson,
        "session": session,
        "initial_question": initial_question,
        "practice_problem": practice_problems[problem_index],
        "practice_problem_index": problem_index,
        "practice_problem_count": len(practice_problems),
    }

    if request.method == "POST":
        action = request.POST.get("action", "ask")
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
                    run_tutor_turn(session, student_question=question)
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


def _render_insights(request, lesson: Lesson, **extra_context):
    observations = _lesson_observations(lesson)
    context = {
        "lesson": lesson,
        "observations": observations,
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
