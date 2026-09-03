"""Advance a recommendation's status only when the student really acts.

The system never claims completion because a link was clicked. Completion comes
from an actual activity signal: a finished ``ExperimentAttempt`` for an
experiment recommendation, or a student tutor message after a tutor follow-up
recommendation was explicitly opened.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.students.models import ExperimentAttempt, PracticeAttempt, TutorMessage

from .goal_services import (
    sync_learning_goals_for_experiment,
    sync_learning_goals_for_practice,
)
from .services import sync_experiment_recommendation, sync_tutor_recommendation

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ExperimentAttempt, dispatch_uid="teachers.experiment_recommendation")
def _on_experiment_saved(sender, instance, created, update_fields=None, **kwargs):
    if instance.completed_at is None:
        return
    # React only to a real completion: a fresh already-complete row, or the
    # explicit completion save from complete_experiment(). The per-phase saves
    # (prediction / observation / explanation) never touch ``completed_at``.
    touches_completion = created or (update_fields and "completed_at" in update_fields)
    if not touches_completion:
        return
    try:
        sync_experiment_recommendation(instance)
    except Exception:  # pragma: no cover - defensive; must not break the lab flow
        logger.exception(
            "Experiment recommendation sync failed for attempt %s.", instance.pk
        )
    try:
        sync_learning_goals_for_experiment(instance)
    except Exception:  # pragma: no cover - defensive; must not break the lab flow
        logger.exception(
            "Learning-goal experiment sync failed for attempt %s.", instance.pk
        )


@receiver(post_save, sender=TutorMessage, dispatch_uid="teachers.tutor_recommendation")
def _on_tutor_message_saved(sender, instance, created, **kwargs):
    if not created or instance.role != TutorMessage.Role.STUDENT:
        return
    try:
        sync_tutor_recommendation(instance)
    except Exception:  # pragma: no cover - defensive; must not break the tutor flow
        logger.exception(
            "Tutor recommendation sync failed for message %s.", instance.pk
        )


@receiver(post_save, sender=PracticeAttempt, dispatch_uid="teachers.practice_learning_goal")
def _on_practice_attempt_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        sync_learning_goals_for_practice(instance)
    except Exception:  # pragma: no cover - defensive; must not break practice
        logger.exception(
            "Learning-goal practice sync failed for attempt %s.", instance.pk
        )
