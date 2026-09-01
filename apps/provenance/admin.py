from django.contrib import admin

from .models import (
    GeneratedLessonDraft,
    LessonDraftReview,
    PersistedReviewIssue,
    ProvenanceEvent,
    ReviewIssueDecision,
)


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """Base admin for immutable AI / audit records.

    These rows are written only by the provenance services during the lesson
    workflow. Admin exposes them for inspection but never for editing, so the
    audit history cannot be altered by mistake.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(ProvenanceEvent)
class ProvenanceEventAdmin(ReadOnlyModelAdmin):
    list_display = ("lesson", "event_type", "source", "created_at")
    list_filter = ("event_type", "source", "created_at")
    search_fields = ("lesson__title", "event_type", "source")
    list_select_related = ("lesson", "actor")
    date_hierarchy = "created_at"


@admin.register(GeneratedLessonDraft)
class GeneratedLessonDraftAdmin(ReadOnlyModelAdmin):
    list_display = (
        "lesson",
        "provider_name",
        "model",
        "prompt_version",
        "created_at",
        "finalized_at",
    )
    list_filter = ("provider_name", "model", "prompt_version", "created_at")
    search_fields = ("lesson__title", "provider_name", "model", "prompt_version")
    list_select_related = ("lesson", "finalized_by")
    date_hierarchy = "created_at"


@admin.register(LessonDraftReview)
class LessonDraftReviewAdmin(ReadOnlyModelAdmin):
    list_display = ("draft", "created_at")
    list_filter = ("created_at",)
    search_fields = ("draft__lesson__title", "overall_summary")
    list_select_related = ("draft", "draft__lesson")
    date_hierarchy = "created_at"


@admin.register(PersistedReviewIssue)
class PersistedReviewIssueAdmin(ReadOnlyModelAdmin):
    list_display = (
        "review",
        "category",
        "severity",
        "status",
        "confidence",
        "created_at",
    )
    list_filter = ("category", "severity", "status", "confidence", "created_at")
    search_fields = (
        "review__draft__lesson__title",
        "issue",
        "explanation",
        "affected_section",
    )
    list_select_related = ("review", "review__draft", "review__draft__lesson")
    date_hierarchy = "created_at"


@admin.register(ReviewIssueDecision)
class ReviewIssueDecisionAdmin(ReadOnlyModelAdmin):
    list_display = ("issue", "decision", "teacher", "created_at")
    list_filter = ("decision", "created_at")
    search_fields = ("issue__issue", "teacher_note", "edited_text")
    list_select_related = ("issue", "teacher")
    date_hierarchy = "created_at"
