from django.contrib import admin

from .models import Lesson


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "grade_level",
        "duration_minutes",
        "status",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "grade_level")
    search_fields = ("title", "slug", "description")
    filter_horizontal = ("physics_concepts",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "published_at")

    fieldsets = (
        ("Lesson details", {"fields": ("title", "slug", "description", "topic", "grade_level", "duration_minutes", "difficulty")} ),
        ("Physics domain", {"fields": ("physics_concepts",)}),
        (
            "Learning design",
            {"fields": ("learning_objectives", "common_misconceptions", "content", "problems")},
        ),
        ("Status", {"fields": ("status", "published_at")} ),
        ("Provenance", {"fields": ("created_by", "ai_generated", "ai_model", "ai_version")} ),
        ("Timestamps", {"fields": ("created_at", "updated_at")} ),
    )
