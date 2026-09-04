"""Physics question bank and structured assessments.

Three layers, kept separate on purpose (see the module docstring in
``services.py``):

    QuestionBankItem   -- a reusable, deterministically-gradeable question
    Assessment / AssessmentQuestion -- an ordered, published set of questions
    AssessmentAttempt / AssessmentAnswer -- what one student actually did

A question's trusted answer definition (``expected_value`` / ``tolerance`` /
``correct_choice``) is authoritative and server-only. It is never sent to the
browser as ground truth and never trusted from a POST; evaluation reuses the
existing Step 18 evaluators in ``apps.students.practice_services`` rather than
re-implementing grading here.

This module does not touch ``Lesson.problems`` or the existing practice
engine -- both continue to work unchanged. See ``services.py`` for how a
question is (or is not) linked back to a lesson.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class QuestionBankItem(models.Model):
    """One reusable Physics question with a stable, teacher-assigned key."""

    class QuestionType(models.TextChoices):
        NUMERIC = "numeric", "Numeric"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    key = models.SlugField(
        max_length=120,
        unique=True,
        help_text=(
            "Stable identifier, unique across the whole question bank -- "
            "never a positional index like 'q1'."
        ),
    )
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    prompt = models.TextField()
    concept = models.ForeignKey(
        "physics.PhysicsConcept",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="question_bank_items",
        help_text="Optional link into the Physics concept graph.",
    )
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        help_text="Describes the question, not the student.",
    )

    # Multiple-choice only.
    choices = models.JSONField(default=list, blank=True)
    correct_choice = models.PositiveSmallIntegerField(null=True, blank=True)

    # Numeric only.
    expected_value = models.FloatField(null=True, blank=True)
    expected_unit = models.CharField(max_length=40, blank=True, default="")
    tolerance = models.FloatField(null=True, blank=True)

    hint = models.TextField(blank=True, default="")
    explanation = models.TextField(blank=True, default="")

    is_active = models.BooleanField(
        default=True,
        help_text="Inactive questions are hidden from new assessments; past attempts are unaffected.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_bank_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["question_type", "is_active"]),
            models.Index(fields=["concept", "is_active"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return self.key


class Assessment(models.Model):
    """A titled, ordered set of question-bank questions a teacher publishes."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="Stable, student-safe identifier used in learning-evidence records.",
    )
    description = models.TextField(blank=True, default="")
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments",
    )
    concept = models.ForeignKey(
        "physics.PhysicsConcept",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    questions = models.ManyToManyField(
        QuestionBankItem, through="AssessmentQuestion", related_name="assessments"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["concept", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "assessment"
            slug = base
            suffix = 2
            while Assessment.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{suffix}"[:220]
                suffix += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED


class AssessmentQuestion(models.Model):
    """One question at one deterministic position within one assessment."""

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="assessment_questions"
    )
    question = models.ForeignKey(
        QuestionBankItem, on_delete=models.PROTECT, related_name="assessment_questions"
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "question"], name="uniq_assessment_question"
            )
        ]
        indexes = [models.Index(fields=["assessment", "position"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.assessment_id}:{self.question_id}"


class AssessmentAttempt(models.Model):
    """One student's single pass at one assessment. Status is derived, not stored."""

    student = models.ForeignKey(
        "students.StudentProfile", on_delete=models.CASCADE, related_name="assessment_attempts"
    )
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "assessment"], name="uniq_student_assessment_attempt"
            )
        ]
        indexes = [
            models.Index(fields=["student", "assessment"]),
            models.Index(fields=["assessment", "started_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.student_id}:{self.assessment_id}"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


class AssessmentAnswer(models.Model):
    """One student's answer to one question within one attempt. Never overwritten."""

    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name="answers")
    assessment_question = models.ForeignKey(
        AssessmentQuestion, on_delete=models.PROTECT, related_name="answers"
    )
    evidence = models.ForeignKey(
        "students.LearningEvidence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessment_answers",
    )
    answer_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(null=True, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attempted_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "assessment_question"], name="uniq_attempt_question_answer"
            )
        ]
        indexes = [models.Index(fields=["attempt", "attempted_at"])]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.attempt_id}:{self.assessment_question_id}"
