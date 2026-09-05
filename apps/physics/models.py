from django.db import models
from django.utils.text import slugify


class PhysicsConcept(models.Model):
    """Reusable reference concept for Physics learning content and validation."""

    class Difficulty(models.TextChoices):
        FOUNDATIONAL = "foundational", "Foundational"
        INTRODUCTORY = "introductory", "Introductory"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(
        help_text="A concise, scientifically accurate explanation of the concept."
    )
    topic = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Broad Physics category, such as Kinematics or Dynamics.",
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.FOUNDATIONAL,
    )
    common_misconceptions = models.JSONField(
        default=list,
        blank=True,
        help_text="Common incorrect ideas associated with this concept.",
    )
    prerequisites = models.JSONField(
        default=list,
        blank=True,
        help_text="Names of concepts learners should understand first.",
    )
    equations = models.JSONField(
        default=list,
        blank=True,
        help_text="Relevant equations expressed as readable strings.",
    )
    si_units = models.JSONField(
        default=list,
        blank=True,
        help_text="Relevant SI units expressed as readable strings.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive concepts are retained but excluded from normal use.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["topic", "name"]
        verbose_name = "Physics concept"
        verbose_name_plural = "Physics concepts"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PhysicsMisconception(models.Model):
    """Reusable catalog entry describing a *possible* physics misunderstanding.

    This is domain knowledge, not a diagnosis. Each entry names a pattern of
    reasoning that learners sometimes show, links it to the concept it distorts,
    and records cautious guidance for detecting and addressing it. Nothing here
    asserts that any particular student holds the misconception.
    """

    code = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable machine identifier, e.g. FREE_FALL_MASS_ACCELERATION.",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(
        help_text=(
            "Cautious, educational summary of the possible misunderstanding. "
            "Phrase it as something a learner *may* believe, never as a verdict."
        )
    )
    physics_concept = models.ForeignKey(
        PhysicsConcept,
        on_delete=models.PROTECT,
        related_name="misconceptions",
        help_text="The concept this misconception most directly distorts.",
    )
    detection_guidance = models.TextField(
        blank=True,
        default="",
        help_text="Reasoning patterns or statements that may suggest this confusion.",
    )
    intervention_guidance = models.TextField(
        blank=True,
        default="",
        help_text="A teaching move the tutor can use, e.g. a controlled comparison.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Physics misconception"
        verbose_name_plural = "Physics misconceptions"

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class PhysicsSimulation(models.Model):
    """A reusable, concept-linked interactive Physics Lab simulation.

    The catalog row is deliberately thin: it names a simulation and ties it to a
    :class:`PhysicsConcept`. All simulation state (mass, force, time, motion)
    lives in the client-side simulation, and every physical value is computed
    deterministically in code -- never by an AI provider.
    """

    class SimulationType(models.TextChoices):
        NEWTONS_SECOND_LAW = "newtons_second_law", "Newton's Second Law"
        KINEMATICS = "kinematics", "Kinematics"

    concept = models.ForeignKey(
        PhysicsConcept,
        on_delete=models.PROTECT,
        related_name="simulations",
        help_text="The concept this simulation lets a student explore.",
    )
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    simulation_type = models.CharField(
        max_length=40,
        choices=SimulationType.choices,
        help_text="Selects which client-side simulation and template to render.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Physics simulation"
        verbose_name_plural = "Physics simulations"

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class MisconceptionRecoveryPath(models.Model):
    """A reusable, teacher-authored recovery sequence for one misconception.

    This is a definition, not a student's progress -- the same PhysicsX /
    StudentX split already used for PhysicsMisconception / StudentMisconception
    and PhysicsSimulation / ExperimentAttempt. A student's actual run through a
    path lives in ``apps.students.models.StudentMisconceptionRecovery``.
    """

    misconception = models.ForeignKey(
        PhysicsMisconception,
        on_delete=models.CASCADE,
        related_name="recovery_paths",
    )
    title = models.CharField(max_length=150)
    student_summary = models.CharField(
        max_length=300,
        help_text=(
            "Student-facing framing shown on the recovery page. Plain, "
            "encouraging language -- never the misconception's name or code."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["misconception__code", "id"]
        verbose_name = "Misconception recovery path"
        verbose_name_plural = "Misconception recovery paths"

    def __str__(self) -> str:
        return f"Recovery path for {self.misconception.code}: {self.title}"


class MisconceptionRecoveryActivity(models.Model):
    """One ordered step in a recovery path.

    ``activity_type`` is an explicit, closed set of identifiers with their own
    server-side handlers in ``apps.students.recovery_services`` -- there is no
    stored code or expression here, only trusted data (labels, instructions,
    a linked simulation, and a small fixed concept-check question).
    """

    class ActivityType(models.TextChoices):
        PHYSICS_LAB = "physics_lab", "Physics Lab"
        TUTOR_REFLECTION = "tutor_reflection", "Tutor reflection"
        CONCEPT_CHECK = "concept_check", "Concept check"

    path = models.ForeignKey(
        MisconceptionRecoveryPath,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    order = models.PositiveSmallIntegerField(
        help_text="1-based position in the path. Activities are completed in this order."
    )
    activity_type = models.CharField(max_length=32, choices=ActivityType.choices)
    label = models.CharField(max_length=150, help_text="Short student-facing step title.")
    instructions = models.TextField(
        blank=True,
        default="",
        help_text="Student-facing framing for this step (Think / Predict prompts etc.).",
    )
    simulation = models.ForeignKey(
        PhysicsSimulation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Required for a 'physics_lab' step; unused otherwise.",
    )
    check_prompt = models.CharField(
        max_length=300, blank=True, default="", help_text="Required for a 'concept_check' step."
    )
    check_choices = models.JSONField(
        default=list,
        blank=True,
        help_text="Plain list of answer choice strings for a 'concept_check' step.",
    )
    check_correct_choice = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0-based index into check_choices."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path", "order", "id"]
        verbose_name = "Misconception recovery activity"
        verbose_name_plural = "Misconception recovery activities"
        constraints = [
            models.UniqueConstraint(
                fields=["path", "order"], name="uniq_recovery_activity_order"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path.title} step {self.order}: {self.label}"
