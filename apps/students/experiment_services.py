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
from apps.physics.simulations_kinematics import (
    MAX_ACCELERATION_MS2,
    MAX_INITIAL_POSITION_M,
    MAX_INITIAL_VELOCITY_MS,
    MAX_TIME_S,
    clamp_acceleration,
    clamp_initial_position,
    clamp_initial_velocity,
    clamp_time,
    kinematics_state,
)

from .misconception_services import assess_student_misconceptions
from .models import ExperimentAttempt, LearningEvidence

logger = logging.getLogger(__name__)

# Anything past these is a nonsense submission, not a slider value -> reject.
MASS_HARD_MAX_KG = MAX_MASS_KG * 5
FORCE_HARD_MAX_N = MAX_FORCE_N * 5
FORCE_HARD_MIN_N = -1.0

POSITION_HARD_MAX_M = MAX_INITIAL_POSITION_M * 5
VELOCITY_HARD_MAX_MS = MAX_INITIAL_VELOCITY_MS * 5
ACCELERATION_HARD_MAX_MS2 = MAX_ACCELERATION_MS2 * 5
TIME_HARD_MAX_S = MAX_TIME_S * 5

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


@dataclass(frozen=True)
class ValidatedKinematics:
    """Server-recomputed, deterministic Kinematics values (SI units)."""

    initial_position_m: float
    initial_velocity_m_s: float
    acceleration_m_s2: float
    time_s: float
    position_m: float
    velocity_m_s: float

    def as_dict(self) -> dict:
        return {
            "initial_position_m": self.initial_position_m,
            "initial_velocity_m_s": self.initial_velocity_m_s,
            "acceleration_m_s2": self.acceleration_m_s2,
            "time_s": self.time_s,
            "position_m": self.position_m,
            "velocity_m_s": self.velocity_m_s,
        }


def validate_kinematics(
    initial_position_m, initial_velocity_m_s, acceleration_m_s2, time_s
) -> ValidatedKinematics:
    """Recompute position/velocity on the server. Reject nonsense; clamp to lab bounds."""

    try:
        x0_raw = float(initial_position_m)
        v0_raw = float(initial_velocity_m_s)
        a_raw = float(acceleration_m_s2)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError(
            "Initial position, initial velocity, acceleration and time must be numbers."
        )

    if any(math.isnan(v) or math.isinf(v) for v in (x0_raw, v0_raw, a_raw, t_raw)):
        raise ExperimentValidationError(
            "Initial position, initial velocity, acceleration and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if (
        abs(x0_raw) > POSITION_HARD_MAX_M
        or abs(v0_raw) > VELOCITY_HARD_MAX_MS
        or abs(a_raw) > ACCELERATION_HARD_MAX_MS2
        or t_raw > TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError(
            "Those values are outside the simulation's range."
        )

    state = kinematics_state(
        initial_position=x0_raw, initial_velocity=v0_raw, acceleration=a_raw, time=t_raw
    )
    return ValidatedKinematics(
        initial_position_m=clamp_initial_position(x0_raw),
        initial_velocity_m_s=clamp_initial_velocity(v0_raw),
        acceleration_m_s2=state["acceleration_m_s2"],
        time_s=clamp_time(t_raw),
        position_m=state["position_m"],
        velocity_m_s=state["velocity_m_s"],
    )


# --- per-simulation-type dispatch ---------------------------------------
#
# The generic record_experiment_observation/explanation functions below never
# hardcode a simulation's field names. Each simulation type registers three
# small functions here: how to validate raw submitted values, how to write
# the trusted result onto the dedicated ExperimentAttempt fields, and how to
# write it into ExperimentAttempt.parameters (JSON). Adding a third
# simulation type means adding one more entry to each dict, not touching the
# functions that use them.


def _validate_newtons_second_law(values: dict) -> ValidatedNewtonsSecondLaw:
    return validate_newtons_second_law(values.get("mass_kg"), values.get("force_n"))


def _validate_kinematics(values: dict) -> ValidatedKinematics:
    return validate_kinematics(
        values.get("initial_position_m"),
        values.get("initial_velocity_m_s"),
        values.get("acceleration_m_s2"),
        values.get("time_s"),
    )


_VALIDATORS = {
    "newtons_second_law": _validate_newtons_second_law,
    "kinematics": _validate_kinematics,
}

# Which submitted fields must ALL be present before Explain recomputes the
# trusted values (mirrors the original "mass_kg is not None and force_n is
# not None" guard).
_EXPLAIN_REQUIRED_FIELDS = {
    "newtons_second_law": ("mass_kg", "force_n"),
    "kinematics": ("initial_position_m", "initial_velocity_m_s", "acceleration_m_s2", "time_s"),
}


def _apply_fields_newtons_second_law(attempt, validated: ValidatedNewtonsSecondLaw) -> None:
    attempt.mass_kg = validated.mass_kg
    attempt.force_n = validated.force_n
    attempt.acceleration_m_s2 = validated.acceleration_m_s2


def _apply_fields_kinematics(attempt, validated: ValidatedKinematics) -> None:
    attempt.acceleration_m_s2 = validated.acceleration_m_s2


_FIELD_APPLIERS = {
    "newtons_second_law": _apply_fields_newtons_second_law,
    "kinematics": _apply_fields_kinematics,
}


def _apply_parameters_newtons_second_law(attempt, simulation, validated: ValidatedNewtonsSecondLaw) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation": simulation.simulation_type,
        "observed": validated.as_dict(),
    }


def _apply_parameters_kinematics(attempt, simulation, validated: ValidatedKinematics) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "initial_position_m": validated.initial_position_m,
        "initial_velocity_m_s": validated.initial_velocity_m_s,
        "acceleration_m_s2": validated.acceleration_m_s2,
        "observed_time_s": validated.time_s,
        "observed_position_m": validated.position_m,
        "observed_velocity_m_s": validated.velocity_m_s,
    }


_PARAMETER_APPLIERS = {
    "newtons_second_law": _apply_parameters_newtons_second_law,
    "kinematics": _apply_parameters_kinematics,
}


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
    if simulation.simulation_type == "kinematics":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("initial_position_m", "initial_velocity_m_s"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_position_m" in params:
            context["position_m"] = params["observed_position_m"]
        if "observed_velocity_m_s" in params:
            context["velocity_m_s"] = params["observed_velocity_m_s"]
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
    *, student, simulation, observation, session=None, lesson=None, **physics_values
) -> tuple[ExperimentAttempt, object]:
    """Learning moment 2: the student reports what happened. Values recomputed.

    ``**physics_values`` carries whatever raw fields this simulation type
    needs (``mass_kg``/``force_n`` for Newton's Second Law,
    ``initial_position_m``/``initial_velocity_m_s``/``acceleration_m_s2``/
    ``time_s`` for Kinematics) -- never trusted as-is, always re-validated
    against the deterministic model for ``simulation.simulation_type``.
    """

    text = _clean_text(observation, field_label="observation")
    validator = _VALIDATORS.get(simulation.simulation_type)
    if validator is None:
        raise ExperimentValidationError("This simulation type does not support experiments yet.")
    validated = validator(physics_values)

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    attempt.observation = text
    _FIELD_APPLIERS[simulation.simulation_type](attempt, validated)
    _PARAMETER_APPLIERS[simulation.simulation_type](attempt, simulation, validated)
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
    session=None,
    lesson=None,
    provider=None,
    assess: bool = True,
    **physics_values,
) -> tuple[ExperimentAttempt, list]:
    """Learning moment 3: the student explains their reasoning.

    This is the richest evidence. The explanation is also passed through the
    existing misconception engine; any candidate stays a *candidate* -- only a
    teacher can confirm it.
    """

    text = _clean_text(explanation, field_label="explanation")

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    required = _EXPLAIN_REQUIRED_FIELDS.get(simulation.simulation_type, ())
    if required and all(physics_values.get(f) is not None for f in required):
        validator = _VALIDATORS.get(simulation.simulation_type)
        validated = validator(physics_values)
        _FIELD_APPLIERS[simulation.simulation_type](attempt, validated)
        # Keep ``parameters`` in step with the dedicated fields above -- for
        # Kinematics, position/velocity/time live ONLY in parameters, so a
        # fresh explain-time setup must refresh them too, or the evidence
        # context built from ``attempt.parameters`` would pair a fresh
        # acceleration with a stale position/velocity/time snapshot.
        _PARAMETER_APPLIERS[simulation.simulation_type](attempt, simulation, validated)
    attempt.explanation = text
    attempt.save(
        update_fields=[
            "explanation",
            "mass_kg",
            "force_n",
            "acceleration_m_s2",
            "parameters",
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
