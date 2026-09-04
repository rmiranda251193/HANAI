from django.contrib import admin

from . import services
from .models import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    QuestionBankItem,
)


@admin.register(QuestionBankItem)
class QuestionBankItemAdmin(admin.ModelAdmin):
    list_display = ("key", "question_type", "concept", "difficulty", "is_active", "updated_at")
    list_filter = ("question_type", "difficulty", "is_active", "concept__topic")
    search_fields = ("key", "prompt")
    list_select_related = ("concept",)
    list_editable = ("is_active",)
    readonly_fields = ("key", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        """Once a question has a real student answer against it, its trusted
        answer definition is locked here too -- the same rule
        ``services.update_question`` enforces for the teacher UI, so a staff
        user in /admin/ cannot silently change what "correct" meant for
        already-graded answers."""

        fields = list(self.readonly_fields)
        if obj is not None and services.is_used(obj):
            fields += ["question_type", "choices", "correct_choice", "expected_value", "expected_unit", "tolerance"]
        return fields

    fieldsets = (
        ("Question", {"fields": ("key", "question_type", "prompt", "concept", "difficulty")}),
        ("Multiple choice", {"fields": ("choices", "correct_choice")}),
        ("Numeric", {"fields": ("expected_value", "expected_unit", "tolerance")}),
        ("Support text", {"fields": ("hint", "explanation")}),
        ("Availability", {"fields": ("is_active", "created_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


class AssessmentQuestionInline(admin.TabularInline):
    """View-only. Adding/removing/reordering questions goes through the
    teacher assessment builder (``/teacher/assessments/<id>/``), which is the
    only place ``add_question_to_assessment`` / ``remove_question_from_assessment``
    are enforced (draft-only, active-question-only, no duplicates)."""

    model = AssessmentQuestion
    extra = 0
    fields = ("question", "position")
    readonly_fields = ("question", "position")
    ordering = ("position", "id")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    """``status`` is read-only here: publishing/archiving must go through
    ``services.publish_assessment`` / ``archive_assessment`` (via the teacher
    workspace), which are the only places the "at least one question, every
    question active" invariant is enforced. Editing ``status`` directly in
    /admin/ would bypass that guard entirely."""

    list_display = ("title", "status", "concept", "lesson", "updated_at")
    list_filter = ("status", "concept__topic")
    search_fields = ("title", "slug", "description")
    list_select_related = ("concept", "lesson")
    readonly_fields = ("slug", "status", "created_at", "updated_at", "published_at")
    inlines = [AssessmentQuestionInline]

    fieldsets = (
        ("Assessment", {"fields": ("title", "slug", "description", "lesson", "concept")}),
        ("Status", {"fields": ("status", "created_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "published_at")}),
    )


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "assessment", "started_at", "completed_at")
    list_filter = ("assessment__status",)
    list_select_related = ("student", "assessment")
    search_fields = ("student__display_name", "assessment__title")
    readonly_fields = ("student", "assessment", "started_at", "completed_at")

    def has_add_permission(self, request):
        return False


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "assessment_question", "is_correct", "attempted_at")
    list_filter = ("is_correct",)
    list_select_related = ("attempt", "assessment_question")
    readonly_fields = ("attempt", "assessment_question", "answer_text", "is_correct", "evidence", "attempted_at")

    def has_add_permission(self, request):
        return False
