from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.ai.services import LessonGenerationResult
from apps.ai.schemas import LessonReviewResult
from apps.lessons.models import Lesson

from .models import (
    GeneratedLessonDraft,
    LessonDraftReview,
    PersistedReviewIssue,
    ProvenanceEvent,
    ReviewIssueDecision,
)

SECRET_METADATA_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "token",
    "authorization",
    "credential",
    "private_key",
    "access_key",
)

PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "fake": "Fake",
    "ollama": "Ollama",
}

DECISION_EVENT_TYPES = {
    PersistedReviewIssue.Status.ACCEPTED: ProvenanceEvent.EventType.TEACHER_ACCEPTED,
    PersistedReviewIssue.Status.EDITED: ProvenanceEvent.EventType.TEACHER_EDITED,
    PersistedReviewIssue.Status.REJECTED: ProvenanceEvent.EventType.TEACHER_REJECTED,
}


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


@dataclass(frozen=True)
class HistoryEntry:
    """Template-ready presentation of one persisted provenance event."""

    event_type: str
    title: str
    source_label: str
    created_at: datetime
    details: tuple[str, ...]


def _is_secret_metadata_key(key: str) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(fragment in normalized for fragment in SECRET_METADATA_KEY_FRAGMENTS)


def sanitize_provenance_metadata(value):
    """Drop secret-like keys so API keys never enter the audit trail."""

    if isinstance(value, dict):
        return {
            key: sanitize_provenance_metadata(item)
            for key, item in value.items()
            if not _is_secret_metadata_key(key)
        }
    if isinstance(value, list):
        return [sanitize_provenance_metadata(item) for item in value]
    return value


def _authenticated_actor(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def _provider_label(name: str) -> str:
    return PROVIDER_DISPLAY_NAMES.get((name or "").strip().lower(), name)


def _quoted(text: str) -> str:
    return f'"{text.strip()}"'


def history_entry_for(event: ProvenanceEvent) -> HistoryEntry:
    """Turn one stored event into the lesson-history display record."""

    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    details: list[str] = []
    source_label = ""

    if event.event_type == ProvenanceEvent.EventType.LESSON_CREATED:
        source_label = "Teacher"
    elif event.event_type == ProvenanceEvent.EventType.AI_DRAFT_GENERATED:
        source_label = _provider_label(metadata.get("provider") or event.source)
        model = metadata.get("model")
        prompt_version = metadata.get("prompt_version")
        if model:
            details.append(f"Model: {model}")
        if prompt_version:
            details.append(f"Prompt: {prompt_version}")
    elif event.event_type == ProvenanceEvent.EventType.AI_REVIEW_COMPLETED:
        count = metadata.get("finding_count", 0)
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 0
        details.append("1 finding" if count == 1 else f"{count} findings")
    elif event.event_type == ProvenanceEvent.EventType.TEACHER_ACCEPTED:
        source_label = "Teacher"
        note = metadata.get("teacher_note") or metadata.get("issue") or ""
        if note:
            details.append(_quoted(str(note)))
    elif event.event_type == ProvenanceEvent.EventType.TEACHER_EDITED:
        source_label = "Teacher"
        revision = metadata.get("teacher_revision") or metadata.get("issue") or ""
        if revision:
            details.append(_quoted(str(revision)))
    elif event.event_type == ProvenanceEvent.EventType.TEACHER_REJECTED:
        source_label = "Teacher"
        note = metadata.get("teacher_note") or metadata.get("issue") or ""
        if note:
            details.append(_quoted(str(note)))
    elif event.event_type == ProvenanceEvent.EventType.LESSON_FINALIZED:
        source_label = "Teacher"
        version = metadata.get("version")
        if version:
            details.append(f"Version: {version}")

    return HistoryEntry(
        event_type=event.event_type,
        title=event.get_event_type_display(),
        source_label=source_label,
        created_at=event.created_at,
        details=tuple(details),
    )


@transaction.atomic
def record_event(
    lesson: Lesson,
    event_type: str,
    *,
    metadata: dict | None = None,
    source: str = "",
    actor=None,
) -> ProvenanceEvent:
    """Persist one audit event for a lesson without storing secrets."""

    if event_type not in ProvenanceEvent.EventType.values:
        raise ValueError(f"Unsupported provenance event type: {event_type}")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("Provenance metadata must be a JSON object.")

    return ProvenanceEvent.objects.create(
        lesson=lesson,
        event_type=event_type,
        source=(source or "").strip(),
        actor=_authenticated_actor(actor),
        metadata=sanitize_provenance_metadata(metadata),
    )


def get_lesson_history(lesson: Lesson) -> list[HistoryEntry]:
    """Return persisted history in chronological order for the lesson UI."""

    events = ProvenanceEvent.objects.filter(lesson=lesson)
    return [history_entry_for(event) for event in events]


@transaction.atomic
def persist_generated_lesson_draft(
    lesson: Lesson,
    result: LessonGenerationResult,
) -> GeneratedLessonDraft:
    """Persist a new immutable AI draft without modifying the lesson itself."""

    draft = GeneratedLessonDraft.objects.create(
        lesson=lesson,
        draft_data=result.draft.to_dict(),
        provider_name=result.provider_name,
        model=result.model,
        prompt_version=result.prompt_version,
        created_at=result.created_at,
    )
    record_event(
        lesson,
        ProvenanceEvent.EventType.AI_DRAFT_GENERATED,
        source=result.provider_name,
        metadata={
            "provider": result.provider_name,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "draft_id": str(draft.pk),
        },
    )
    return draft


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
    record_event(
        locked_draft.lesson,
        ProvenanceEvent.EventType.AI_REVIEW_COMPLETED,
        source=locked_draft.provider_name,
        metadata={
            "draft_id": str(locked_draft.pk),
            "review_id": str(review.pk),
            "finding_count": len(result.issues),
            "overall_summary": result.overall_summary,
        },
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

    locked_issue = (
        PersistedReviewIssue.objects.select_for_update()
        .select_related("review__draft__lesson")
        .get(pk=issue.pk)
    )
    if locked_issue.status != PersistedReviewIssue.Status.PENDING:
        raise ReviewDecisionError("This review issue has already received a decision.")

    actor = _authenticated_actor(teacher)
    ReviewIssueDecision.objects.create(
        issue=locked_issue,
        decision=decision,
        teacher_note=teacher_note,
        edited_text=edited_text,
        teacher=actor,
    )
    locked_issue.status = decision
    locked_issue.save(update_fields=["status"])

    metadata = {
        "issue_id": str(locked_issue.pk),
        "issue": locked_issue.issue,
    }
    if teacher_note:
        metadata["teacher_note"] = teacher_note
    if decision == PersistedReviewIssue.Status.EDITED:
        metadata["original_suggestion"] = locked_issue.suggested_revision
        metadata["teacher_revision"] = edited_text

    record_event(
        locked_issue.review.draft.lesson,
        DECISION_EVENT_TYPES[decision],
        source="teacher",
        actor=actor,
        metadata=metadata,
    )
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

    actor = _authenticated_actor(teacher)
    locked_draft.finalized_at = timezone.now()
    locked_draft.finalized_by = actor
    locked_draft.save(update_fields=["finalized_at", "finalized_by"])
    record_event(
        lesson,
        ProvenanceEvent.EventType.LESSON_FINALIZED,
        source="teacher",
        actor=actor,
        metadata={
            "version": locked_draft.prompt_version,
            "draft_id": str(locked_draft.pk),
            "review_id": str(locked_review.pk),
            "model": locked_draft.model,
        },
    )
    return lesson
