from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


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
    """Lightweight record of a meaningful student learning moment.

    This is intentionally not analytics. It never claims a misconception; it
    only records that something worth noticing happened -- a question asked, a
    practice attempt, or a Physics Lab prediction / observation / explanation.
    """

    class Kind(models.TextChoices):
        QUESTION_ASKED = "question_asked", "Question asked"
        PRACTICE_ATTEMPTED = "practice_attempted", "Practice attempted"
        PREDICTION_SUBMITTED = "prediction_submitted", "Prediction submitted"
        EXPERIMENT_OBSERVED = "experiment_observed", "Experiment observed"
        EXPLANATION_SUBMITTED = "explanation_submitted", "Explanation submitted"
        ASSESSMENT_ATTEMPTED = "assessment_attempted", "Assessment attempted"
        RECOVERY_ACTIVITY_COMPLETED = "recovery_activity_completed", "Recovery activity completed"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="learning_evidence",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Optional structured context, e.g. deterministic experiment "
            "parameters {simulation, mass_kg, force_n, acceleration_m_s2}."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lesson", "created_at"]),
            models.Index(fields=["student", "kind"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} for {self.lesson or 'no lesson'}"


class StudentMisconception(models.Model):
    """A *possible* misconception observed for one student.

    This is a candidate, not a diagnosis. It carries a coarse confidence and a
    status the teacher controls. AI and rules may create or update a candidate;
    only a teacher may confirm one.
    """

    class Confidence(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        CONFIRMED_BY_TEACHER = "confirmed_by_teacher", "Confirmed by teacher"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="misconceptions",
    )
    misconception = models.ForeignKey(
        "physics.PhysicsMisconception",
        on_delete=models.CASCADE,
        related_name="student_observations",
    )
    confidence = models.CharField(
        max_length=8,
        choices=Confidence.choices,
        default=Confidence.LOW,
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.CANDIDATE,
    )
    first_observed_at = models.DateTimeField(default=timezone.now)
    last_observed_at = models.DateTimeField(default=timezone.now)
    observation_count = models.PositiveIntegerField(default=0)
    evidence_summary = models.CharField(max_length=500, blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="misconception_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    teacher_note = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_observed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "misconception"],
                name="uniq_student_misconception",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "last_observed_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"Possible: {self.misconception.code} for {self.student} "
            f"({self.get_confidence_display()}, {self.get_status_display()})"
        )

    @property
    def is_teacher_decided(self) -> bool:
        return self.status != self.Status.CANDIDATE


class MisconceptionEvidence(models.Model):
    """A short, real pointer to something the student actually did.

    It links an observation to the learning evidence and/or tutor message that
    prompted it, plus a brief excerpt. Whole conversations are never copied.
    """

    class Source(models.TextChoices):
        RULE = "rule", "Rule"
        AI = "ai", "AI"

    observation = models.ForeignKey(
        StudentMisconception,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    learning_evidence = models.ForeignKey(
        LearningEvidence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="misconception_evidence",
    )
    tutor_message = models.ForeignKey(
        TutorMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="misconception_evidence",
    )
    source = models.CharField(max_length=8, choices=Source.choices)
    detector = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Rule code or prompt version that produced this signal.",
    )
    excerpt = models.CharField(max_length=500)
    reasoning = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["observation", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_source_display()} evidence for {self.observation_id}"


class ExperimentAttempt(models.Model):
    """One student's run through a Physics Lab simulation as a learning activity.

    Predict -> experiment -> observe -> explain. The stored ``mass_kg`` /
    ``force_n`` / ``acceleration_m_s2`` are the server-recomputed deterministic
    result (a = F / m), never the browser's numbers. This is evidence of
    engagement and reasoning, not a grade.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="experiment_attempts",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="experiment_attempts",
    )
    simulation = models.ForeignKey(
        "physics.PhysicsSimulation",
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    session = models.ForeignKey(
        TutorSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="experiment_attempts",
    )

    prediction = models.TextField(blank=True, default="")
    observation = models.TextField(blank=True, default="")
    explanation = models.TextField(blank=True, default="")

    # Server-recomputed deterministic values (SI units). Not trusted from the browser.
    mass_kg = models.FloatField(null=True, blank=True)
    force_n = models.FloatField(null=True, blank=True)
    acceleration_m_s2 = models.FloatField(null=True, blank=True)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured experiment context recomputed on the server.",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["student", "simulation"]),
            models.Index(fields=["simulation", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"Experiment: {self.simulation} for {self.student}"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


class PracticeAttempt(models.Model):
    """One server-evaluated attempt at a lesson practice question.

    The *question* lives in lesson content (``Lesson.problems``); this row is the
    student's *attempt* at it. Correctness is decided by deterministic code
    (numeric tolerance / choice match), never by an AI provider, and it is
    evidence of engagement -- not a grade, score or mastery signal. A retry is a
    new row; earlier attempts are never overwritten.
    """

    class QuestionType(models.TextChoices):
        NUMERIC = "numeric", "Numeric"
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        FREE_TEXT = "free_text", "Free text"

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="practice_attempts",
    )
    lesson = models.ForeignKey(
        "lessons.Lesson",
        on_delete=models.CASCADE,
        related_name="practice_attempts",
    )
    session = models.ForeignKey(
        TutorSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_attempts",
    )
    concept = models.ForeignKey(
        "physics.PhysicsConcept",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_attempts",
    )
    evidence = models.ForeignKey(
        LearningEvidence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_attempts",
    )

    question_key = models.CharField(max_length=100)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    question_prompt = models.CharField(
        max_length=500,
        help_text="Snapshot of the question as it was shown for this attempt.",
    )
    answer_text = models.CharField(
        max_length=500,
        help_text="Exactly what the student submitted (a number as text, or a choice label).",
    )
    is_correct = models.BooleanField(
        null=True,
        blank=True,
        help_text="Deterministic verdict. NULL for free-text questions that have no single answer.",
    )
    attempt_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="1-based, per (student, lesson, question_key). A retry increments it.",
    )
    expected_display = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "Human-readable expected answer resolved from trusted lesson data at "
            "attempt time. A teacher reference only; never used to re-grade."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["student", "lesson", "question_key"]),
            models.Index(fields=["lesson", "created_at"]),
            models.Index(fields=["student", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Practice {self.question_key} for {self.student}"


class StudentMisconceptionRecovery(models.Model):
    """One student's run through a misconception's recovery path.

    This is orchestration state only -- it never duplicates ``ExperimentAttempt``,
    ``TutorSession`` or ``LearningEvidence``; it just tracks which of a path's
    ordered activities this student has completed. At most one *unfinished*
    recovery may exist per (student, observation) at a time; a resurfaced
    misconception can start a new recovery after an earlier one completed.
    """

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="misconception_recoveries",
    )
    observation = models.ForeignKey(
        StudentMisconception,
        on_delete=models.CASCADE,
        related_name="recoveries",
    )
    path = models.ForeignKey(
        "physics.MisconceptionRecoveryPath",
        on_delete=models.PROTECT,
        related_name="recoveries",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "observation"],
                condition=Q(completed_at__isnull=True),
                name="uniq_active_recovery_per_observation",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "completed_at"]),
        ]

    def __str__(self) -> str:
        return f"Recovery for {self.observation.misconception.code} ({self.student})"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


class StudentRecoveryActivityCompletion(models.Model):
    """One completed step of a student's recovery, linked to its evidence.

    ``evidence`` points at the *existing* ``LearningEvidence`` row written for
    this step (never a second evidence table). ``result`` is a short factual
    label -- never a score or mastery signal.
    """

    class Result(models.TextChoices):
        DONE = "done", "Done"
        CORRECT = "correct", "Correct"
        INCORRECT = "incorrect", "Incorrect"

    recovery = models.ForeignKey(
        StudentMisconceptionRecovery,
        on_delete=models.CASCADE,
        related_name="activity_completions",
    )
    activity = models.ForeignKey(
        "physics.MisconceptionRecoveryActivity",
        on_delete=models.PROTECT,
        related_name="+",
    )
    evidence = models.ForeignKey(
        LearningEvidence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    result = models.CharField(max_length=20, choices=Result.choices, blank=True, default="")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["completed_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recovery", "activity"], name="uniq_recovery_activity_completion"
            ),
        ]

    def __str__(self) -> str:
        return f"Completed activity {self.activity_id} for recovery {self.recovery_id}"
