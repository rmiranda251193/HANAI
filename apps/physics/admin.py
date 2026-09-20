from django.contrib import admin

from .models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsScenario,
    PhysicsSimulation,
)
from .scenario_services import is_used


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


@admin.register(PhysicsMisconception)
class PhysicsMisconceptionAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "physics_concept", "is_active", "updated_at")
    list_filter = ("is_active", "physics_concept__topic")
    search_fields = ("code", "title", "description")
    list_select_related = ("physics_concept",)
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Catalog entry", {"fields": ("code", "title", "description", "physics_concept")}),
        ("Guidance", {"fields": ("detection_guidance", "intervention_guidance")}),
        ("Availability", {"fields": ("is_active",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(PhysicsSimulation)
class PhysicsSimulationAdmin(admin.ModelAdmin):
    list_display = ("title", "concept", "simulation_type", "is_active", "updated_at")
    list_filter = ("is_active", "simulation_type", "concept__topic")
    search_fields = ("title", "slug", "description", "concept__name")
    list_select_related = ("concept",)
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Simulation", {"fields": ("title", "slug", "description", "concept", "simulation_type")}),
        ("Availability", {"fields": ("is_active",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


class MisconceptionRecoveryActivityInline(admin.TabularInline):
    model = MisconceptionRecoveryActivity
    extra = 0
    fields = (
        "order",
        "activity_type",
        "label",
        "simulation",
        "check_prompt",
        "check_correct_choice",
        "is_active",
    )
    ordering = ("order",)


@admin.register(MisconceptionRecoveryPath)
class MisconceptionRecoveryPathAdmin(admin.ModelAdmin):
    list_display = ("title", "misconception", "is_active", "updated_at")
    list_filter = ("is_active", "misconception__physics_concept__topic")
    search_fields = ("title", "student_summary", "misconception__code", "misconception__title")
    list_select_related = ("misconception",)
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (MisconceptionRecoveryActivityInline,)

    fieldsets = (
        ("Recovery path", {"fields": ("misconception", "title", "student_summary")}),
        ("Availability", {"fields": ("is_active",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(MisconceptionRecoveryActivity)
class MisconceptionRecoveryActivityAdmin(admin.ModelAdmin):
    list_display = ("path", "order", "activity_type", "label", "is_active", "updated_at")
    list_filter = ("activity_type", "is_active")
    search_fields = ("label", "instructions", "check_prompt", "path__title")
    list_select_related = ("path", "simulation")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PhysicsScenario)
class PhysicsScenarioAdmin(admin.ModelAdmin):
    list_display = ("title", "simulation", "difficulty", "status", "created_by", "updated_at")
    list_filter = ("status", "difficulty", "category", "simulation__simulation_type")
    search_fields = ("title", "slug", "description", "instructions")
    list_select_related = ("simulation", "created_by")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        """Once a student has a real check against this scenario, its
        Physics identity is locked here too -- the same rule
        ``scenario_services.update_scenario`` enforces for the teacher UI,
        so a staff user in /admin/ cannot silently rewrite what a past
        result meant."""

        fields = list(self.readonly_fields)
        if obj is not None and is_used(obj):
            fields += ["simulation", "initial_state", "target_condition"]
        return fields

    fieldsets = (
        ("Scenario", {"fields": ("title", "slug", "simulation", "description", "instructions")}),
        ("Guidance", {"fields": ("prediction_prompt", "reflection_prompt")}),
        ("Physics", {"fields": ("initial_state", "target_condition")}),
        ("Classification", {"fields": ("difficulty", "category")}),
        ("Status", {"fields": ("status", "created_by")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
