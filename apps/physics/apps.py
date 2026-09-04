from django.apps import AppConfig


class PhysicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.physics"

    def ready(self):
        # Populate the simulation registry (apps.physics.simulation_registry) --
        # each module registers itself as a side effect of being imported, the
        # same way apps.teachers.apps wires up its signal receivers.
        from . import simulations  # noqa: F401
        from . import simulations_kinematics  # noqa: F401
