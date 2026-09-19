from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
import uuid

from apps.physics.level_catalog import all_levels
from apps.physics.models import PhysicsConcept

User = get_user_model()

# (key, title) choices for the optional Lesson.level field below, sourced
# from the same code-defined level taxonomy the Physics Library already
# displays a difficulty-based range from (apps.physics.level_catalog).
LEVEL_CHOICES = [(lvl.key, lvl.title) for lvl in all_levels()]

class Lesson(models.Model):
    """Teacher-owned learning content linked to reusable Physics concepts."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Under review"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    DIFFICULTY_CHOICES = [
        (1, 'Beginner'),
        (2, 'Easy'),
        (3, 'Intermediate'),
        (4, 'Advanced'),
        (5, 'Expert'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    topic = models.CharField(max_length=255)
    grade_level = models.CharField(max_length=50, help_text="e.g., 9, 10, 11, 12")
    level = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=LEVEL_CHOICES,
        help_text=(
            "Optional physics depth level this lesson targets (from the "
            "level taxonomy) -- distinct from grade_level, since the same "
            "school grade can be taught at different physics depths."
        ),
    )
    duration_minutes = models.PositiveSmallIntegerField(
        default=60,
        help_text="Planned lesson duration in minutes.",
    )
    description = models.TextField(blank=True)

    learning_objectives = models.JSONField(
        default=list,
        help_text="Learning objectives for this lesson.",
    )
    difficulty = models.IntegerField(choices=DIFFICULTY_CHOICES, default=1)
    content = models.JSONField(default=dict, help_text="Generated lesson content")
    problems = models.JSONField(default=list, help_text="Practice problems")
    common_misconceptions = models.JSONField(
        default=list,
        help_text="Lesson-specific misconceptions to address.",
    )

    ai_generated = models.BooleanField(default=False)
    ai_model = models.CharField(max_length=50, blank=True, null=True)
    ai_version = models.CharField(max_length=20, blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    physics_concepts = models.ManyToManyField(
        PhysicsConcept,
        related_name="lessons",
        blank=True,
        help_text="Physics concepts taught or applied by this lesson.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="lessons",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['topic']),
            models.Index(fields=['grade_level']),
            models.Index(fields=['level']),
        ]
    
    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "lesson"
            candidate_slug = base_slug
            suffix = 2

            while type(self).objects.filter(slug=candidate_slug).exclude(pk=self.pk).exists():
                candidate_slug = f"{base_slug}-{suffix}"
                suffix += 1

            self.slug = candidate_slug
        super().save(*args, **kwargs)

    def publish(self):
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save()


class LessonActivity(models.Model):
    """One ordered step in a teacher-authored lesson's learning sequence.

    A reference/orchestration layer only. It points at an existing
    ``PhysicsSimulation`` / ``QuestionBankItem`` / ``Assessment`` /
    ``MisconceptionRecoveryPath`` and never copies or re-persists their
    content. Student execution reuses the existing Physics Lab / practice /
    assessment / tutor / recovery systems and their existing evidence
    mechanisms -- this model records only the learning-design intent, never
    student behaviour.
    """

    class ActivityType(models.TextChoices):
        EXPLANATION = "explanation", "Explanation"
        PHYSICS_LAB = "physics_lab", "Physics Lab"
        PRACTICE = "practice", "Practice question"
        TUTOR = "tutor", "Tutor discussion"
        ASSESSMENT = "assessment", "Assessment"
        RECOVERY = "recovery", "Misconception recovery"

    # Which reference field each type reads. Types not listed here (explanation,
    # tutor) carry no object reference.
    REFERENCE_FIELD = {
        ActivityType.PHYSICS_LAB: "simulation",
        ActivityType.PRACTICE: "question",
        ActivityType.ASSESSMENT: "assessment",
        ActivityType.RECOVERY: "recovery_path",
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="activities"
    )
    position = models.PositiveSmallIntegerField(
        help_text="1-based order within the lesson."
    )
    activity_type = models.CharField(max_length=32, choices=ActivityType.choices)
    title = models.CharField(max_length=200)
    instructions = models.TextField(
        blank=True,
        default="",
        help_text="Concise teacher guidance shown to the student for this step.",
    )
    tutor_focus = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Optional safe instructional focus for a tutor activity.",
    )

    # Exactly one of these is meaningful, selected by ``activity_type``. Always
    # resolved and validated server-side -- never trusted from a hidden field.
    simulation = models.ForeignKey(
        "physics.PhysicsSimulation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    question = models.ForeignKey(
        "assessments.QuestionBankItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    assessment = models.ForeignKey(
        "assessments.Assessment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    recovery_path = models.ForeignKey(
        "physics.MisconceptionRecoveryPath",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["lesson", "position", "id"]
        verbose_name = "Lesson activity"
        verbose_name_plural = "Lesson activities"
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "position"], name="uniq_lesson_activity_position"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.lesson.title} #{self.position}: {self.title}"

    @property
    def reference_field_name(self) -> str | None:
        return self.REFERENCE_FIELD.get(self.activity_type)

    @property
    def reference(self):
        """The linked object for this activity's type, or None."""

        field = self.reference_field_name
        return getattr(self, field) if field else None


class LessonFeedback(models.Model):
    """Teacher feedback on AI-generated lessons"""
    
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(1, 'Poor'), (2, 'Fair'), (3, 'Good'), (4, 'Very Good'), (5, 'Excellent')])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Feedback for {self.lesson.title} - Rating: {self.rating}"
