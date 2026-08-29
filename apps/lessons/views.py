import logging

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ai.exceptions import AIError
from apps.ai.requests import LessonGenerationRequest, LessonReviewRequest
from apps.ai.services import generate_lesson_draft, review_lesson_draft
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

from .forms import LessonForm
from .models import Lesson


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
            lesson = form.save()
            record_event(
                lesson,
                ProvenanceEvent.EventType.LESSON_CREATED,
                source="teacher",
                actor=_current_teacher(request),
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
