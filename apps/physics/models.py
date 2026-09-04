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
