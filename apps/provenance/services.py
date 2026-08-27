from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.ai.services import LessonGenerationResult
from apps.ai.schemas import LessonReviewResult
from apps.lessons.models import Lesson

from .models import (
    GeneratedLessonDraft,
    LessonDraftReview,
    PersistedReviewIssue,
    ReviewIssueDecision,
)


class ReviewWorkflowError(Exception):
    """Base error for the teacher-controlled review workflow."""


class ReviewAlreadyExistsError(ReviewWorkflowError):
    """The immutable generated draft already has its saved review."""


class ReviewDecisionError(ReviewWorkflowError):
    """A requested teacher decision is invalid for this review issue."""


class LessonFinalizationError(ReviewWorkflowError):
    """The selected draft cannot be finalized safely yet."""


FINALIZED_DRAFT_SECTIONS = (
    "overview",
    "explanation",
    "worked_examples",
    "activities",
    "assessment_questions",
    "teacher_notes",
)


@transaction.atomic
def persist_generated_lesson_draft(
    lesson: Lesson,
    result: LessonGenerationResult,
) -> GeneratedLessonDraft:
    """Persist a new immutable AI draft without modifying the lesson itself."""

    return GeneratedLessonDraft.objects.create(
        lesson=lesson,
        draft_data=result.draft.to_dict(),
        provider_name=result.provider_name,
        model=result.model,
        prompt_version=result.prompt_version,
        created_at=result.created_at,
    )


@transaction.atomic
def persist_lesson_draft_review(
    draft: GeneratedLessonDraft,
    result: LessonReviewResult,
) -> LessonDraftReview:
    """Persist one validated review and its immutable issue findings."""

    locked_draft = GeneratedLessonDraft.objects.select_for_update().get(pk=draft.pk)
    if locked_draft.reviews.exists():
        raise ReviewAlreadyExistsError("This AI draft has already been reviewed.")

    review = LessonDraftReview.objects.create(
        draft=locked_draft,
        overall_summary=result.overall_summary,
    )
    PersistedReviewIssue.objects.bulk_create(
        [
            PersistedReviewIssue(
                review=review,
                category=issue.category,
                severity=issue.severity,
                issue=issue.issue,
                explanation=issue.explanation,
                affected_section=issue.affected_section,
                suggested_revision=issue.suggested_revision,
                confidence=issue.confidence,
            )
            for issue in result.issues
        ]
    )
    return review


@transaction.atomic
def record_review_issue_decision(
    issue: PersistedReviewIssue,
    decision: str,
    *,
    teacher_note: str = "",
    edited_text: str = "",
    teacher=None,
) -> PersistedReviewIssue:
    """Record one terminal teacher decision while preserving AI source text."""

    valid_decisions = {
        PersistedReviewIssue.Status.ACCEPTED,
        PersistedReviewIssue.Status.EDITED,
        PersistedReviewIssue.Status.REJECTED,
    }
    decision = (decision or "").strip().lower()
    teacher_note = (teacher_note or "").strip()
    edited_text = (edited_text or "").strip()

    if decision not in valid_decisions:
        raise ReviewDecisionError("Choose accept, edit, or reject for this review issue.")
    if decision == PersistedReviewIssue.Status.EDITED and not edited_text:
        raise ReviewDecisionError("An edited decision requires a teacher revision.")

    locked_issue = PersistedReviewIssue.objects.select_for_update().get(pk=issue.pk)
    if locked_issue.status != PersistedReviewIssue.Status.PENDING:
        raise ReviewDecisionError("This review issue has already received a decision.")

    ReviewIssueDecision.objects.create(
        issue=locked_issue,
        decision=decision,
        teacher_note=teacher_note,
        edited_text=edited_text,
        teacher=teacher if getattr(teacher, "is_authenticated", False) else None,
    )
    locked_issue.status = decision
    locked_issue.save(update_fields=["status"])
    return locked_issue


def build_teacher_approved_content(
    draft: GeneratedLessonDraft,
    issues: list[PersistedReviewIssue],
) -> dict:
    """Create an explicit, safe merge of a draft and teacher decisions.

    Natural-language review suggestions do not identify machine-safe patches, so
    they are never silently applied to a draft section. The teacher's accepted
    or edited revision is recorded explicitly; rejected suggestions are omitted.
    """

    source = draft.as_lesson_draft().to_dict()
    content = {section: source[section] for section in FINALIZED_DRAFT_SECTIONS}
    teacher_approved_revisions: list[dict[str, str]] = []

    for issue in issues:
        if issue.status == PersistedReviewIssue.Status.REJECTED:
            continue

        decision = issue.decision_record
        revision_text = (
            decision.edited_text
            if issue.status == PersistedReviewIssue.Status.EDITED
            else issue.suggested_revision
        )
        revision = {
            "issue_id": str(issue.pk),
            "affected_section": issue.affected_section,
            "decision": issue.status,
            "content": revision_text,
        }
        if decision.teacher_note:
            revision["teacher_note"] = decision.teacher_note
        teacher_approved_revisions.append(revision)

    if teacher_approved_revisions:
        content["teacher_approved_revisions"] = teacher_approved_revisions
    return content


@transaction.atomic
def finalize_lesson_from_review(
    review: LessonDraftReview,
    *,
    teacher=None,
) -> Lesson:
    """Finalize approved content without publishing or mutating source records."""

    locked_review = (
        LessonDraftReview.objects.select_for_update()
        .select_related("draft__lesson")
        .get(pk=review.pk)
    )
    locked_draft = GeneratedLessonDraft.objects.select_for_update().get(
        pk=locked_review.draft_id
    )
    issues = list(
        PersistedReviewIssue.objects.select_for_update()
        .select_related("decision_record")
        .filter(review=locked_review)
    )
    pending_issues = [
        issue
        for issue in issues
        if issue.status == PersistedReviewIssue.Status.PENDING
    ]
    if pending_issues:
        raise LessonFinalizationError(
            "Resolve every review issue before finalizing this lesson."
        )

    lesson = Lesson.objects.select_for_update().get(pk=locked_draft.lesson_id)
    lesson.content = build_teacher_approved_content(locked_draft, issues)
    lesson.ai_generated = True
    lesson.ai_model = locked_draft.model
    lesson.ai_version = locked_draft.prompt_version
    lesson.save(
        update_fields=["content", "ai_generated", "ai_model", "ai_version", "updated_at"]
    )

    locked_draft.finalized_at = timezone.now()
    locked_draft.finalized_by = (
        teacher if getattr(teacher, "is_authenticated", False) else None
    )
    locked_draft.save(update_fields=["finalized_at", "finalized_by"])
    return lesson
