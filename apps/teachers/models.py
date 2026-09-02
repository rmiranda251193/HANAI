from __future__ import annotations

from django.conf import settings
from django.db import models


class TeacherIntervention(models.Model):
    """One explicit teacher action taken after reviewing a student's evidence.

    An intervention is a historical teacher decision, not derived data and not a
    mutation of the evidence it responds to. Rows are immutable once written; the
    newest-first list is the audit trail.
    """

    class ActionType(models.TextChoices):
        RECOMMEND_LESSON = "recommend_lesson", "Recommend a lesson"
        RECOMMEND_EXPERIMENT = "recommend_experiment", "Recommend an experiment"
        TUTOR_FOLLOW_UP = "tutor_follow_up", "Follow up with the Tutor"
        TEACHER_NOTE = "teacher_note", "Teacher note"

    student = models.ForeignKey(
        "students.StudentProfile",
        on_delete=models.CASCADE,
        related_name="teacher_interventions",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_interventions",
        help_text="The authenticated teacher who recorded this action.",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_interventions",
    )
    concept = models.ForeignKey(
        "physics.PhysicsConcept",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_interventions",
    )
    misconception = models.ForeignKey(
        "students.StudentMisconception",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_interventions",
        help_text="An optional possible-misconception this action responds to.",
    )
    action_type = models.CharField(max_length=32, choices=ActionType.choices)
    note = models.TextField(blank=True, default="")
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sanitised snapshot of the target ids for the audit trail.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_type_display()} for {self.student}"

    @property
    def target_label(self) -> str:
        if self.lesson_id:
            return f"Lesson: {self.lesson.title}"
        if self.concept_id:
            return f"Concept: {self.concept.name}"
        if self.misconception_id:
            return f"Signal: {self.misconception.misconception.title}"
        return ""
