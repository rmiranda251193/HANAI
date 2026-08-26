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
