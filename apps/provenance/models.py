from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class GeneratedLessonDraft(models.Model):
    """Immutable snapshot of one AI-generated lesson draft.

    The snapshot is intentionally separate from ``Lesson.content`` so a
    teacher can review, decide on findings, and finalize explicitly.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.CASCADE,
        related_name="ai_drafts",
    )
    draft_data = models.JSONField(
        help_text="Validated structured AI lesson draft preserved without mutation."
    )
    provider_name = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_ai_lesson_drafts",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AI draft for {self.lesson} ({self.created_at:%Y-%m-%d %H:%M})"

    def as_lesson_draft(self):
        """Rehydrate the stored, validated payload for review or finalization."""

        from apps.ai.schemas import LessonDraft

        return LessonDraft.from_dict(self.draft_data)


class LessonDraftReview(models.Model):
    """One persisted AI review run for an immutable generated draft."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    draft = models.ForeignKey(
        GeneratedLessonDraft,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    overall_summary = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AI review for {self.draft}"


class PersistedReviewIssue(models.Model):
    """Immutable AI finding with a separate teacher-controlled decision state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        EDITED = "edited", "Edited"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        LessonDraftReview,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    category = models.CharField(max_length=32)
    severity = models.CharField(max_length=16)
    issue = models.TextField()
    explanation = models.TextField()
    affected_section = models.CharField(max_length=100)
    suggested_revision = models.TextField()
    confidence = models.CharField(max_length=16)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.get_severity_display()} review issue: {self.issue[:60]}"


class ReviewIssueDecision(models.Model):
    """Teacher response kept separate from the original AI review finding."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.OneToOneField(
        PersistedReviewIssue,
        on_delete=models.CASCADE,
        related_name="decision_record",
    )
    decision = models.CharField(
        max_length=16,
        choices=(
            (PersistedReviewIssue.Status.ACCEPTED, "Accepted"),
            (PersistedReviewIssue.Status.EDITED, "Edited"),
            (PersistedReviewIssue.Status.REJECTED, "Rejected"),
        ),
    )
    teacher_note = models.TextField(blank=True)
    edited_text = models.TextField(blank=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_review_issue_decisions",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self) -> str:
        return f"{self.get_decision_display()} decision for {self.issue}"
