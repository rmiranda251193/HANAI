from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
import uuid

from apps.physics.models import PhysicsConcept

User = get_user_model()

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


class LessonFeedback(models.Model):
    """Teacher feedback on AI-generated lessons"""
    
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(1, 'Poor'), (2, 'Fair'), (3, 'Good'), (4, 'Very Good'), (5, 'Excellent')])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Feedback for {self.lesson.title} - Rating: {self.rating}"
