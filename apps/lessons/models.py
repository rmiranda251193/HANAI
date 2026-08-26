from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

User = get_user_model()

class Lesson(models.Model):
    """Core lesson model for HANAI Physics AI"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    DIFFICULTY_CHOICES = [
        (1, 'Beginner'),
        (2, 'Easy'),
        (3, 'Intermediate'),
        (4, 'Advanced'),
        (5, 'Expert'),
    ]
    
    # Basic info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    topic = models.CharField(max_length=255)
    grade_level = models.CharField(max_length=50, help_text="e.g., 9, 10, 11, 12")
    description = models.TextField(blank=True)
    
    # Metadata
    objectives = models.JSONField(default=list, help_text="Learning objectives")
    prerequisites = models.JSONField(default=list, help_text="Prerequisite knowledge")
    difficulty = models.IntegerField(choices=DIFFICULTY_CHOICES, default=1)
    
    # Content
    content = models.JSONField(default=dict, help_text="Generated lesson content")
    problems = models.JSONField(default=list, help_text="Practice problems")
    misconceptions = models.JSONField(default=list, help_text="Common misconceptions")
    
    # AI tracking
    ai_generated = models.BooleanField(default=False)
    ai_model = models.CharField(max_length=50, blank=True, null=True)
    ai_version = models.CharField(max_length=20, blank=True, null=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Relations
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lessons')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_lessons')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['topic']),
            models.Index(fields=['grade_level']),
        ]
    
    def __str__(self):
        return self.title
    
    def publish(self):
        self.status = 'published'
        self.published_at = timezone.now()
        self.save()
    
    def approve(self, user):
        self.status = 'approved'
        self.approved_by = user
        self.approved_at = timezone.now()
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