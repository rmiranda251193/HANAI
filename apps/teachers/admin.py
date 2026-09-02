from django.contrib import admin

from .models import TeacherIntervention


@admin.register(TeacherIntervention)
class TeacherInterventionAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "action_type",
        "teacher",
        "lesson",
        "concept",
        "created_at",
    )
    list_filter = ("action_type", "created_at")
    search_fields = (
        "student__display_name",
        "teacher__username",
        "note",
        "lesson__title",
        "concept__name",
    )
    list_select_related = ("student", "teacher", "lesson", "concept")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
