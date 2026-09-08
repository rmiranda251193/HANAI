import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.ai.exceptions import AIError
from apps.ai.requests import LessonGenerationRequest, LessonReviewRequest
from apps.ai.services import generate_lesson_draft, review_lesson_draft
from apps.assessments.models import Assessment, QuestionBankItem
from apps.physics.models import MisconceptionRecoveryPath, PhysicsConcept, PhysicsSimulation
from apps.provenance.models import GeneratedLessonDraft, PersistedReviewIssue, ProvenanceEvent
from apps.provenance.services import (
    LessonFinalizationError,
    ReviewDecisionError,
    ReviewWorkflowError,
    finalize_lesson_from_review,
    get_lesson_history,
    persist_generated_lesson_draft,
    persist_lesson_draft_review,
    record_event,
    record_review_issue_decision,
)
from apps.students.practice_services import AnswerValidationError, PracticeError
from apps.teachers.access import teacher_required

from .authoring_services import (
    LessonAuthoringError,
    LessonPublishError,
    build_lesson_preview,
    create_activity,
    delete_activity,
    lesson_activities,
    move_activity,
    practice_question_view,
    publish_lesson,
    record_practice_activity_answer,
    set_learning_objectives,
    set_lesson_concepts,
    update_activity,
    update_lesson_basics,
    validate_lesson_for_publish,
)
from .forms import LessonForm
from .models import Lesson, LessonActivity


logger = logging.getLogger(__name__)


GENERATION_ERROR_MESSAGE = (
    "AI generation could not be completed. Please check the AI configuration and try again."
)
REVIEW_ERROR_MESSAGE = (
    "AI review could not be completed. Please check the AI configuration and try again."
)


def _render_lesson_detail(
    request,
    lesson,
    *,
    generated_lesson_draft: GeneratedLessonDraft | None = None,
    **extra_context,
):
    """Render one persisted AI draft and its review state alongside a lesson."""

    generated_lesson_draft = generated_lesson_draft or lesson.ai_drafts.first()
    context = {
        "lesson": lesson,
        "lesson_history": get_lesson_history(lesson),
    }

    if generated_lesson_draft is not None:
        context["generated_lesson_draft"] = generated_lesson_draft
        context["generated_draft"] = generated_lesson_draft.as_lesson_draft()
        lesson_review = generated_lesson_draft.reviews.first()
        if lesson_review is not None:
            review_issues = list(
                lesson_review.issues.select_related("decision_record").all()
            )
            context.update(
                {
                    "lesson_review": lesson_review,
                    "review_issues": review_issues,
                    "all_review_issues_decided": all(
                        issue.status != PersistedReviewIssue.Status.PENDING
                        for issue in review_issues
                    ),
                }
            )

    context.update(extra_context)
    return render(request, "lessons/detail.html", context)


def _current_teacher(request):
    return request.user if getattr(request.user, "is_authenticated", False) else None


def lesson_list(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")
    return render(request, "lessons/list.html", {"lessons": lessons})


def lesson_create(request):
    form = LessonForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            lesson = form.save(commit=False)
            # Attribute ownership when a real teacher account creates the
            # lesson; anonymous/local creation keeps created_by = None and stays
            # editable by any teacher (backward compatible).
            teacher = _current_teacher(request)
            if teacher is not None:
                lesson.created_by = teacher
            lesson.save()
            form.save_m2m()
            record_event(
                lesson,
                ProvenanceEvent.EventType.LESSON_CREATED,
                source="teacher",
                actor=teacher,
                metadata={
                    "title": lesson.title,
                    "topic": lesson.topic,
                    "grade_level": lesson.grade_level,
                    "duration_minutes": lesson.duration_minutes,
                    "learning_objectives": list(lesson.learning_objectives),
                    "common_misconceptions": list(lesson.common_misconceptions),
                    "physics_concepts": list(
                        lesson.physics_concepts.values_list("name", flat=True)
                    ),
                },
            )
        return redirect("lessons:detail", slug=lesson.slug)

    return render(request, "lessons/form.html", {"form": form})


def lesson_detail(request, slug):
    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    return _render_lesson_detail(request, lesson)


@require_POST
def lesson_generate(request, slug):
    """Generate a review-only lesson draft without changing the Lesson."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )

    try:
        generation_request = LessonGenerationRequest.from_lesson(lesson)
        generation_result = generate_lesson_draft(generation_request)
        generated_lesson_draft = persist_generated_lesson_draft(
            lesson, generation_result
        )
    except (AIError, ValueError) as exc:
        logger.warning(
            "AI lesson generation failed for lesson %s (%s).",
            lesson.pk,
            exc.__class__.__name__,
        )
        return _render_lesson_detail(
            request, lesson, generation_error=GENERATION_ERROR_MESSAGE
        )
    except Exception:
        logger.exception("Unexpected AI lesson generation failure for lesson %s.", lesson.pk)
        return _render_lesson_detail(
            request, lesson, generation_error=GENERATION_ERROR_MESSAGE
        )

    return _render_lesson_detail(
        request,
        lesson,
        generated_lesson_draft=generated_lesson_draft,
        workflow_message="AI draft saved for teacher review.",
    )


@require_POST
def lesson_review(request, slug, draft_id):
    """Run and persist the first AI review for an immutable generated draft."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    generated_lesson_draft = get_object_or_404(
        GeneratedLessonDraft,
        pk=draft_id,
        lesson=lesson,
    )

    if generated_lesson_draft.reviews.exists():
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            review_error="This AI draft already has saved review findings.",
        )

    try:
        review_request = LessonReviewRequest.from_lesson(
            lesson,
            generated_lesson_draft.as_lesson_draft(),
        )
        review_result = review_lesson_draft(review_request)
        persist_lesson_draft_review(generated_lesson_draft, review_result)
    except (AIError, ValueError, ReviewWorkflowError) as exc:
        logger.warning(
            "AI lesson review failed for lesson %s (%s).",
            lesson.pk,
            exc.__class__.__name__,
        )
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            review_error=REVIEW_ERROR_MESSAGE,
        )
    except Exception:
        logger.exception("Unexpected AI lesson review failure for lesson %s.", lesson.pk)
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            review_error=REVIEW_ERROR_MESSAGE,
        )

    return _render_lesson_detail(
        request,
        lesson,
        generated_lesson_draft=generated_lesson_draft,
        workflow_message="AI review findings are ready for your decisions.",
    )


@require_POST
def lesson_review_issue_decision(request, slug, draft_id, issue_id):
    """Persist one teacher decision without changing the source AI issue."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    generated_lesson_draft = get_object_or_404(
        GeneratedLessonDraft,
        pk=draft_id,
        lesson=lesson,
    )
    issue = get_object_or_404(
        PersistedReviewIssue,
        pk=issue_id,
        review__draft=generated_lesson_draft,
    )

    try:
        record_review_issue_decision(
            issue,
            request.POST.get("decision", ""),
            teacher_note=request.POST.get("teacher_note", ""),
            edited_text=request.POST.get("edited_text", ""),
            teacher=_current_teacher(request),
        )
    except ReviewDecisionError as exc:
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            decision_error=str(exc),
        )
    except Exception:
        logger.exception(
            "Unexpected review decision failure for lesson %s.", lesson.pk
        )
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            decision_error="Your review decision could not be saved. Please try again.",
        )

    return _render_lesson_detail(
        request,
        lesson,
        generated_lesson_draft=generated_lesson_draft,
        workflow_message="Your review decision was saved.",
    )


@require_POST
def lesson_finalize(request, slug, draft_id, review_id):
    """Create approved lesson content only after the teacher resolves findings."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    generated_lesson_draft = get_object_or_404(
        GeneratedLessonDraft,
        pk=draft_id,
        lesson=lesson,
    )
    review = get_object_or_404(
        generated_lesson_draft.reviews,
        pk=review_id,
    )

    try:
        finalize_lesson_from_review(review, teacher=_current_teacher(request))
    except LessonFinalizationError as exc:
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            finalization_error=str(exc),
        )
    except Exception:
        logger.exception("Unexpected lesson finalization failure for lesson %s.", lesson.pk)
        return _render_lesson_detail(
            request,
            lesson,
            generated_lesson_draft=generated_lesson_draft,
            finalization_error="The lesson could not be finalized. Please try again.",
        )

    return _render_lesson_detail(
        request,
        lesson,
        generated_lesson_draft=generated_lesson_draft,
        workflow_message=(
            "Lesson content was finalized from your approved and edited review decisions."
        ),
    )


# --- Teacher lesson builder (Step 26) ---------------------------------
#
# These views are gated by the existing teacher mechanism (``teacher_required``
# -> any is_staff user). Every state-changing action is POST + CSRF, resolves
# the lesson server-side, and -- for a lesson that has an owner -- refuses a
# different teacher. Reads (builder page, preview) never mutate anything.


def _lesson_for_build(slug):
    return get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"), slug=slug
    )


def _require_lesson_owner(request, lesson):
    """A lesson with an owner may only be edited by that owner.

    Legacy / locally-created lessons (``created_by is None``) stay editable by
    any teacher so existing content is never stranded.
    """

    if lesson.created_by_id is not None and lesson.created_by_id != getattr(
        request.user, "id", None
    ):
        raise PermissionDenied("This lesson belongs to another teacher.")


def _build_context(request, lesson, **extra):
    activities = lesson_activities(lesson)
    context = {
        "lesson": lesson,
        "activities": activities,
        "activity_types": LessonActivity.ActivityType.choices,
        "concepts": PhysicsConcept.objects.filter(is_active=True).order_by("topic", "name"),
        "selected_concept_ids": set(
            lesson.physics_concepts.values_list("pk", flat=True)
        ),
        "simulations": PhysicsSimulation.objects.filter(is_active=True)
        .select_related("concept")
        .order_by("title"),
        "questions": QuestionBankItem.objects.filter(is_active=True).order_by("key"),
        "assessments": Assessment.objects.filter(
            status=Assessment.Status.PUBLISHED
        ).order_by("title"),
        "recovery_paths": MisconceptionRecoveryPath.objects.filter(is_active=True)
        .select_related("misconception")
        .order_by("title"),
        "publish_reasons": validate_lesson_for_publish(lesson, activities=activities),
        "can_edit": lesson.created_by_id in (None, getattr(request.user, "id", None)),
        "lesson_history": get_lesson_history(lesson),
    }
    context.update(extra)
    return context


@teacher_required
def lesson_build(request, slug):
    """The multi-section lesson builder. Read-only (GET)."""

    lesson = _lesson_for_build(slug)
    return render(request, "lessons/build.html", _build_context(request, lesson))


def _authoring_post(request, slug, action, *, success):
    """Shared POST wrapper: owner check, run ``action(lesson)``, PRG or re-render."""

    lesson = _lesson_for_build(slug)
    try:
        _require_lesson_owner(request, lesson)
        action(lesson)
    except (PermissionDenied, Http404):
        raise
    except LessonAuthoringError as exc:
        lesson.refresh_from_db()
        return render(
            request,
            "lessons/build.html",
            _build_context(request, lesson, authoring_error=str(exc)),
        )
    except Exception:
        logger.exception("Unexpected lesson authoring failure for lesson %s.", lesson.pk)
        lesson.refresh_from_db()
        return render(
            request,
            "lessons/build.html",
            _build_context(
                request,
                lesson,
                authoring_error="That change could not be saved. Please try again.",
            ),
        )
    return redirect(f"{reverse('lessons:build', args=[lesson.slug])}?ok={success}")


@require_POST
@teacher_required
def lesson_update_basics(request, slug):
    return _authoring_post(
        request,
        slug,
        lambda lesson: update_lesson_basics(
            lesson=lesson,
            teacher=_current_teacher(request),
            title=request.POST.get("title", ""),
            topic=request.POST.get("topic", ""),
            grade_level=request.POST.get("grade_level", ""),
            duration_minutes=request.POST.get("duration_minutes", ""),
            description=request.POST.get("description", ""),
        ),
        success="basics",
    )


@require_POST
@teacher_required
def lesson_update_objectives(request, slug):
    return _authoring_post(
        request,
        slug,
        lambda lesson: set_learning_objectives(
            lesson=lesson,
            teacher=_current_teacher(request),
            raw_objectives=request.POST.getlist("objective"),
        ),
        success="objectives",
    )


@require_POST
@teacher_required
def lesson_update_concepts(request, slug):
    return _authoring_post(
        request,
        slug,
        lambda lesson: set_lesson_concepts(
            lesson=lesson,
            teacher=_current_teacher(request),
            concept_ids=request.POST.getlist("concept"),
        ),
        success="concepts",
    )


@require_POST
@teacher_required
def lesson_activity_add(request, slug):
    return _authoring_post(
        request,
        slug,
        lambda lesson: create_activity(
            lesson=lesson,
            teacher=_current_teacher(request),
            activity_type=request.POST.get("activity_type", ""),
            title=request.POST.get("title", ""),
            instructions=request.POST.get("instructions", ""),
            reference_id=request.POST.get("reference_id", ""),
            tutor_focus=request.POST.get("tutor_focus", ""),
        ),
        success="activity_added",
    )


@require_POST
@teacher_required
def lesson_activity_edit(request, slug, activity_id):
    return _authoring_post(
        request,
        slug,
        lambda lesson: update_activity(
            activity=get_object_or_404(LessonActivity, pk=activity_id, lesson=lesson),
            teacher=_current_teacher(request),
            title=request.POST.get("title", ""),
            instructions=request.POST.get("instructions", ""),
            reference_id=request.POST.get("reference_id", ""),
            tutor_focus=request.POST.get("tutor_focus", ""),
        ),
        success="activity_updated",
    )


@require_POST
@teacher_required
def lesson_activity_delete(request, slug, activity_id):
    return _authoring_post(
        request,
        slug,
        lambda lesson: delete_activity(
            activity=get_object_or_404(LessonActivity, pk=activity_id, lesson=lesson),
            teacher=_current_teacher(request),
        ),
        success="activity_deleted",
    )


@require_POST
@teacher_required
def lesson_activity_move(request, slug, activity_id):
    return _authoring_post(
        request,
        slug,
        lambda lesson: move_activity(
            activity=get_object_or_404(LessonActivity, pk=activity_id, lesson=lesson),
            teacher=_current_teacher(request),
            direction=request.POST.get("direction", ""),
        ),
        success="activity_moved",
    )


@teacher_required
def lesson_preview(request, slug):
    """Read-only teacher preview of the student learning sequence."""

    lesson = _lesson_for_build(slug)
    return render(
        request,
        "lessons/preview.html",
        {
            "lesson": lesson,
            "preview_activities": build_lesson_preview(lesson),
            "objectives": [
                o for o in (lesson.learning_objectives or []) if str(o).strip()
            ],
        },
    )


@require_POST
@teacher_required
def lesson_publish(request, slug):
    lesson = _lesson_for_build(slug)
    try:
        _require_lesson_owner(request, lesson)
        publish_lesson(lesson=lesson, teacher=_current_teacher(request))
    except PermissionDenied:
        raise
    except LessonPublishError as exc:
        lesson.refresh_from_db()
        return render(
            request,
            "lessons/build.html",
            _build_context(request, lesson, publish_errors=exc.reasons),
        )
    except Exception:
        logger.exception("Unexpected lesson publish failure for lesson %s.", lesson.pk)
        lesson.refresh_from_db()
        return render(
            request,
            "lessons/build.html",
            _build_context(
                request,
                lesson,
                authoring_error="The lesson could not be published. Please try again.",
            ),
        )
    return redirect(f"{reverse('lessons:build', args=[lesson.slug])}?ok=published")


# --- Student-facing practice activity (reuses the existing evaluators) ---


def student_activity_practice(request, slug, activity_id):
    """Answer one practice-activity question. Reuses the pure evaluators.

    No new grading engine and no new question store: correctness comes from
    ``apps.students.practice_services`` and the recorded evidence is a normal
    ``LearningEvidence(kind=PRACTICE_ATTEMPTED)`` row.
    """

    from apps.students.views import _current_student

    lesson = get_object_or_404(Lesson, slug=slug, status=Lesson.Status.PUBLISHED)
    activity = get_object_or_404(
        LessonActivity.objects.select_related("question", "question__concept"),
        pk=activity_id,
        lesson=lesson,
        activity_type=LessonActivity.ActivityType.PRACTICE,
    )
    if activity.question_id is None or not activity.question.is_active:
        raise Http404("This practice question is not available.")

    student = _current_student(request)
    feedback = None
    error = ""
    if request.method == "POST":
        try:
            feedback = record_practice_activity_answer(
                student=student,
                lesson=lesson,
                activity=activity,
                submitted_answer=request.POST.get("answer", ""),
            )
        except (AnswerValidationError, PracticeError, LessonAuthoringError) as exc:
            error = str(exc)
        except Exception:
            logger.exception(
                "Unexpected practice-activity failure for activity %s.", activity.pk
            )
            error = "Your answer could not be recorded. Please try again."

    return render(
        request,
        "lessons/student_activity_practice.html",
        {
            "lesson": lesson,
            "activity": activity,
            "question": practice_question_view(activity.question),
            "feedback": feedback,
            "practice_error": error,
        },
    )
