from django.contrib import admin

from .models import LearningEvidence, StudentProfile, TutorMessage, TutorSession


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
