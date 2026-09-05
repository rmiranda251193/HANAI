"""Advance a misconception recovery only when the student really acts.

Mirrors ``apps.teachers.signals`` exactly: recovery progress is never
inferred from a page visit or a link click, only from a genuine activity
signal -- a completed ``ExperimentAttempt`` or a student's own Tutor message.
Neither receiver touches the Physics Lab or Tutor code paths; they only
react, after the fact, to rows those existing flows already write.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ExperimentAttempt, TutorMessage
from .recovery_services import sync_recovery_for_experiment, sync_recovery_for_tutor_message

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ExperimentAttempt, dispatch_uid="students.recovery_experiment_sync")
def _on_experiment_saved(sender, instance, created, update_fields=None, **kwargs):
    if instance.completed_at is None:
        return
    # Same guard as the teacher-recommendation receiver: react only to a real
    # completion, not every per-phase save of an in-progress attempt.
    touches_completion = created or (update_fields and "completed_at" in update_fields)
    if not touches_completion:
        return
    try:
        sync_recovery_for_experiment(instance)
    except Exception:  # pragma: no cover - defensive; must not break the lab flow
        logger.exception("Recovery experiment sync failed for attempt %s.", instance.pk)


@receiver(post_save, sender=TutorMessage, dispatch_uid="students.recovery_tutor_sync")
def _on_tutor_message_saved(sender, instance, created, **kwargs):
    if not created or instance.role != TutorMessage.Role.STUDENT:
        return
    try:
        sync_recovery_for_tutor_message(instance)
    except Exception:  # pragma: no cover - defensive; must not break the tutor flow
        logger.exception("Recovery tutor sync failed for message %s.", instance.pk)
