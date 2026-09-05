from django.contrib import admin

from .models import (
    ExperimentAttempt,
    LearningEvidence,
    MisconceptionEvidence,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentProfile,
    StudentRecoveryActivityCompletion,
    TutorMessage,
    TutorSession,
)


class _ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class TutorMessageInline(_ReadOnlyInline):
    model = TutorMessage
    fields = ("role", "mode", "content", "created_at")
    readonly_fields = fields
    ordering = ("created_at", "id")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at")
    search_fields = ("display_name", "user__username")
    readonly_fields = ("created_at",)


@admin.register(TutorSession)
class TutorSessionAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "status", "started_at", "updated_at")
    list_filter = ("status", "started_at")
    search_fields = ("student__display_name", "lesson__title")
    list_select_related = ("student", "lesson")
    date_hierarchy = "started_at"
    readonly_fields = ("started_at", "updated_at")
    inlines = (TutorMessageInline,)


@admin.register(TutorMessage)
class TutorMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "mode", "created_at")
    list_filter = ("role", "mode", "created_at")
    search_fields = ("content", "session__lesson__title")
    list_select_related = ("session", "session__lesson")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(LearningEvidence)
class LearningEvidenceAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "kind", "tutor_mode", "created_at")
    list_filter = ("kind", "tutor_mode", "created_at")
    search_fields = ("student__display_name", "lesson__title", "detail")
    list_select_related = ("student", "lesson", "session")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(ExperimentAttempt)
class ExperimentAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "simulation",
        "lesson",
        "mass_kg",
        "force_n",
        "acceleration_m_s2",
        "completed_at",
        "started_at",
    )
    list_filter = ("simulation__simulation_type", "started_at", "completed_at")
    search_fields = (
        "student__display_name",
        "simulation__title",
        "prediction",
        "observation",
        "explanation",
    )
    list_select_related = ("student", "simulation", "lesson")
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


class MisconceptionEvidenceInline(_ReadOnlyInline):
    model = MisconceptionEvidence
    fields = ("source", "detector", "excerpt", "reasoning", "created_at")
    readonly_fields = fields
    ordering = ("created_at", "id")


@admin.register(StudentMisconception)
class StudentMisconceptionAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "misconception",
        "confidence",
        "status",
        "observation_count",
        "last_observed_at",
    )
    list_filter = ("status", "confidence", "misconception__physics_concept__topic")
    search_fields = ("student__display_name", "misconception__code", "misconception__title")
    list_select_related = ("student", "misconception", "misconception__physics_concept")
    date_hierarchy = "last_observed_at"
    readonly_fields = (
        "student",
        "misconception",
        "confidence",
        "first_observed_at",
        "last_observed_at",
        "observation_count",
        "evidence_summary",
        "created_at",
        "updated_at",
    )
    inlines = (MisconceptionEvidenceInline,)

    def has_add_permission(self, request):
        return False


@admin.register(MisconceptionEvidence)
class MisconceptionEvidenceAdmin(admin.ModelAdmin):
    list_display = ("observation", "source", "detector", "created_at")
    list_filter = ("source", "detector", "created_at")
    search_fields = ("excerpt", "reasoning", "observation__student__display_name")
    list_select_related = ("observation", "observation__student")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


class StudentRecoveryActivityCompletionInline(_ReadOnlyInline):
    model = StudentRecoveryActivityCompletion
    fields = ("activity", "result", "evidence", "completed_at")
    readonly_fields = fields
    ordering = ("completed_at", "id")


@admin.register(StudentMisconceptionRecovery)
class StudentMisconceptionRecoveryAdmin(admin.ModelAdmin):
    list_display = ("student", "path", "started_at", "completed_at")
    list_filter = ("path", "completed_at")
    search_fields = ("student__display_name", "path__title", "observation__misconception__code")
    list_select_related = ("student", "path", "observation")
    date_hierarchy = "started_at"
    readonly_fields = (
        "student",
        "observation",
        "path",
        "started_at",
        "completed_at",
    )
    inlines = (StudentRecoveryActivityCompletionInline,)

    def has_add_permission(self, request):
        return False


@admin.register(StudentRecoveryActivityCompletion)
class StudentRecoveryActivityCompletionAdmin(admin.ModelAdmin):
    list_display = ("recovery", "activity", "result", "completed_at")
    list_filter = ("result", "completed_at")
    search_fields = ("recovery__student__display_name", "activity__label")
    list_select_related = ("recovery", "activity")
    date_hierarchy = "completed_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
