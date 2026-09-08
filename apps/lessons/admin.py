from django.contrib import admin

from .models import Lesson, LessonActivity


class LessonActivityInline(admin.TabularInline):
    model = LessonActivity
    extra = 0
    fields = (
        "position",
        "activity_type",
        "title",
        "simulation",
        "question",
        "assessment",
        "recovery_path",
        "tutor_focus",
    )
    ordering = ("position",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "grade_level",
        "duration_minutes",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "grade_level")
    search_fields = ("title", "slug", "description")
    filter_horizontal = ("physics_concepts",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "published_at")
    inlines = (LessonActivityInline,)

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


@admin.register(LessonActivity)
class LessonActivityAdmin(admin.ModelAdmin):
    list_display = ("lesson", "position", "activity_type", "title", "updated_at")
    list_filter = ("activity_type",)
    search_fields = ("title", "instructions", "lesson__title")
    list_select_related = ("lesson", "simulation", "question", "assessment", "recovery_path")
    readonly_fields = ("created_at", "updated_at")
