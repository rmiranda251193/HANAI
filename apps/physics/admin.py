from django.contrib import admin

from .models import PhysicsConcept


@admin.register(PhysicsConcept)
class PhysicsConceptAdmin(admin.ModelAdmin):
    list_display = ("name", "topic", "difficulty", "is_active", "updated_at")
    list_filter = ("topic", "difficulty", "is_active")
    search_fields = ("name", "description")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Concept", {"fields": ("name", "slug", "description", "topic", "difficulty")} ),
        (
            "Learning reference",
            {
                "fields": (
                    "prerequisites",
                    "equations",
                    "si_units",
                    "common_misconceptions",
                )
            },
        ),
        ("Availability", {"fields": ("is_active",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
