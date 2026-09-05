from django.apps import AppConfig


class StudentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.students"

    def ready(self):
        # Connect the signal handlers that advance a misconception recovery
        # only when the student actually completes the target activity.
        from . import signals  # noqa: F401
