from __future__ import annotations

from django.conf import settings
from django.db import models


class StudentProfile(models.Model):
    """Minimal learner identity for the Physics tutor.

    ``user`` is optional so local development works before student
    authentication exists. When a login system is added, every profile
    should be linked to a real user and the guest fallback removed.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="student_profile",
    )
    display_name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class TutorSession(models.Model):
    """One student's tutoring conversation for a single lesson.

    A student may open many sessions for the same lesson over time.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="tutor_sessions",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.CASCADE,
        related_name="tutor_sessions",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["student", "lesson", "status"]),
        ]

    def __str__(self) -> str:
        return f"Tutor session for {self.lesson} ({self.get_status_display()})"


class TutorMessage(models.Model):
    """One turn in a tutoring conversation, ordered oldest to newest."""

    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        TUTOR = "tutor", "Tutor"
        SYSTEM = "system", "System"

    session = models.ForeignKey(
        TutorSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    mode = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Structured tutor response mode, when the message is from the tutor.",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured tutor fields (hint, next_question, needs_student_attempt).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_role_display()}: {self.content[:60]}"


class LearningEvidence(models.Model):
    """Lightweight record that a student engaged with the tutor.

    This is intentionally not analytics. It never claims a misconception; it
    only stores that a question was asked or a practice problem attempted.
    """

    class Kind(models.TextChoices):
        QUESTION_ASKED = "question_asked", "Question asked"
        PRACTICE_ATTEMPTED = "practice_attempted", "Practice attempted"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="learning_evidence",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.CASCADE,
        related_name="learning_evidence",
    )
    session = models.ForeignKey(
        TutorSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_evidence",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    tutor_mode = models.CharField(max_length=20, blank=True, default="")
    detail = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lesson", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} for {self.lesson}"
