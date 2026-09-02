from django.apps import AppConfig


class TeachersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.teachers"

    def ready(self):
        # Connect the signal handlers that honestly advance a recommendation's
        # status when a student actually completes the target activity.
        from . import signals  # noqa: F401
