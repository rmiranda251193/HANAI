"""Turn Physics Lab interaction into explicit, meaningful learning evidence.

A simulation action is not automatically learning evidence. Nothing here is
recorded for a slider move. Evidence is written only at the four learning
moments: prediction, observation, explanation, and the tutor turn that follows.

Every physical value is recomputed on the server with the deterministic model
(a = F / m). The browser's acceleration is never trusted.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.physics.simulations import (
    MAX_FORCE_N,
    MAX_MASS_KG,
    clamp_force,
    clamp_mass,
    newtons_second_law_acceleration,
)

from .misconception_services import assess_student_misconceptions
from .models import ExperimentAttempt, LearningEvidence

logger = logging.getLogger(__name__)

# Anything past these is a nonsense submission, not a slider value -> reject.
MASS_HARD_MAX_KG = MAX_MASS_KG * 5
FORCE_HARD_MAX_N = MAX_FORCE_N * 5
FORCE_HARD_MIN_N = -1.0

TEXT_LIMIT = 2000


class ExperimentValidationError(ValueError):
    """A submitted experiment value or text was missing or invalid."""


@dataclass(frozen=True)
class ValidatedNewtonsSecondLaw:
    """Server-recomputed, deterministic experiment values (SI units)."""

    mass_kg: float
    force_n: float
    acceleration_m_s2: float

    def as_dict(self) -> dict:
        return {
            "mass_kg": self.mass_kg,
            "force_n": self.force_n,
            "acceleration_m_s2": self.acceleration_m_s2,
        }


def validate_newtons_second_law(mass_kg, force_n) -> ValidatedNewtonsSecondLaw:
    """Recompute a = F / m on the server. Reject nonsense; clamp to lab bounds."""

    try:
        mass_raw = float(mass_kg)
        force_raw = float(force_n)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Mass and net force must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (mass_raw, force_raw)):
        raise ExperimentValidationError("Mass and net force must be finite numbers.")
    if mass_raw <= 0:
        raise ExperimentValidationError("Mass must be greater than zero (kg).")
    if (
        mass_raw > MASS_HARD_MAX_KG
        or force_raw > FORCE_HARD_MAX_N
        or force_raw < FORCE_HARD_MIN_N
    ):
        raise ExperimentValidationError(
            "Those values are outside the simulation's range."
        )

    mass = clamp_mass(mass_raw)
    force = clamp_force(force_raw)
    acceleration = newtons_second_law_acceleration(force, mass)
    return ValidatedNewtonsSecondLaw(
        mass_kg=mass, force_n=force, acceleration_m_s2=acceleration
    )


def _clean_text(value: str, *, field_label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ExperimentValidationError(f"Write your {field_label} before submitting.")
    return text[:TEXT_LIMIT]


def _active_attempt(student, simulation, *, session=None, lesson=None) -> ExperimentAttempt:
    """The student's current, not-yet-completed attempt for this simulation."""

    attempt = (
        ExperimentAttempt.objects.filter(
            student=student, simulation=simulation, completed_at__isnull=True
        )
        .order_by("-started_at")
        .first()
    )
    if attempt is None:
        attempt = ExperimentAttempt.objects.create(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
        )
    else:
        dirty = []
        if session is not None and attempt.session_id is None:
            attempt.session = session
            dirty.append("session")
        if lesson is not None and attempt.lesson_id is None:
            attempt.lesson = lesson
            dirty.append("lesson")
        if dirty:
            attempt.save(update_fields=dirty + ["updated_at"])
    return attempt


def _record_evidence(attempt, kind, detail, *, context=None) -> LearningEvidence:
    return LearningEvidence.objects.create(
        student=attempt.student,
        lesson=attempt.lesson,
        session=attempt.session,
        kind=kind,
        detail=(detail or "")[:300],
        context=context or {},
    )


def _base_context(attempt, simulation) -> dict:
    context = {"simulation": simulation.simulation_type}
    if attempt.mass_kg is not None:
        context["mass_kg"] = attempt.mass_kg
    if attempt.force_n is not None:
        context["force_n"] = attempt.force_n
    if attempt.acceleration_m_s2 is not None:
        context["acceleration_m_s2"] = attempt.acceleration_m_s2
    return context


@transaction.atomic
def record_experiment_prediction(
    *, student, simulation, prediction, session=None, lesson=None
) -> ExperimentAttempt:
    """Learning moment 1: the student commits to a prediction. Not judged now."""

    text = _clean_text(prediction, field_label="prediction")
    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    attempt.prediction = text
    attempt.save(update_fields=["prediction", "updated_at"])
    _record_evidence(
        attempt,
        LearningEvidence.Kind.PREDICTION_SUBMITTED,
        text,
        context={"simulation": simulation.simulation_type, "phase": "prediction"},
    )
    return attempt


@transaction.atomic
def record_experiment_observation(
    *, student, simulation, observation, mass_kg, force_n, session=None, lesson=None
) -> tuple[ExperimentAttempt, ValidatedNewtonsSecondLaw]:
    """Learning moment 2: the student reports what happened. Values recomputed."""

    text = _clean_text(observation, field_label="observation")
    validated = validate_newtons_second_law(mass_kg, force_n)

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    attempt.observation = text
    attempt.mass_kg = validated.mass_kg
    attempt.force_n = validated.force_n
    attempt.acceleration_m_s2 = validated.acceleration_m_s2
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation": simulation.simulation_type,
        "observed": validated.as_dict(),
    }
    attempt.save(
        update_fields=[
            "observation",
            "mass_kg",
            "force_n",
            "acceleration_m_s2",
            "parameters",
            "updated_at",
        ]
    )
    _record_evidence(
        attempt,
        LearningEvidence.Kind.EXPERIMENT_OBSERVED,
        text,
        context={**_base_context(attempt, simulation), "phase": "observation"},
    )
    return attempt, validated


@transaction.atomic
def record_experiment_explanation(
    *,
    student,
    simulation,
    explanation,
    mass_kg=None,
    force_n=None,
    session=None,
    lesson=None,
    provider=None,
    assess: bool = True,
) -> tuple[ExperimentAttempt, list]:
    """Learning moment 3: the student explains their reasoning.

    This is the richest evidence. The explanation is also passed through the
    existing misconception engine; any candidate stays a *candidate* -- only a
    teacher can confirm it.
    """

    text = _clean_text(explanation, field_label="explanation")

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    if mass_kg is not None and force_n is not None:
        validated = validate_newtons_second_law(mass_kg, force_n)
        attempt.mass_kg = validated.mass_kg
        attempt.force_n = validated.force_n
        attempt.acceleration_m_s2 = validated.acceleration_m_s2
    attempt.explanation = text
    attempt.save(
        update_fields=[
            "explanation",
            "mass_kg",
            "force_n",
            "acceleration_m_s2",
            "updated_at",
        ]
    )
    evidence = _record_evidence(
        attempt,
        LearningEvidence.Kind.EXPLANATION_SUBMITTED,
        text,
        context={**_base_context(attempt, simulation), "phase": "explanation"},
    )

    outcomes: list = []
    if assess:
        try:
            outcomes = assess_student_misconceptions(
                student=student,
                lesson=attempt.lesson,
                text=text,
                learning_evidence=evidence,
                tutor_message=None,
                provider=provider,
            )
        except Exception:  # pragma: no cover - defensive; must not block the flow
            logger.exception(
                "Misconception assessment failed for experiment attempt %s.",
                attempt.pk,
            )
    return attempt, outcomes


@transaction.atomic
def complete_experiment(attempt: ExperimentAttempt) -> ExperimentAttempt:
    """Mark the attempt finished so the next prediction starts a fresh run."""

    if attempt.completed_at is None:
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["completed_at", "updated_at"])
    return attempt


def latest_attempt_for(student, simulation) -> ExperimentAttempt | None:
    """The student's most recent attempt (complete or not) for this simulation."""

    return (
        ExperimentAttempt.objects.filter(student=student, simulation=simulation)
        .order_by("-started_at")
        .first()
    )
