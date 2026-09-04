"""Deterministic reference model for the Kinematics -- Straight-Line Motion lab.

One-dimensional motion under a constant acceleration:

    v = v0 + a*t
    x = x0 + v0*t + (1/2)*a*t^2

Mirrors ``apps/physics/simulations.py`` in shape and intent: this module is
the single source of truth for the mathematics, the browser simulation in
``static/js/physics/kinematics.js`` mirrors it exactly for live interaction,
and nothing here ever touches an AI provider -- every value is computed from
first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_INITIAL_POSITION_M = -20.0
MAX_INITIAL_POSITION_M = 20.0
MIN_INITIAL_VELOCITY_MS = -20.0
MAX_INITIAL_VELOCITY_MS = 20.0
MIN_ACCELERATION_MS2 = -10.0
MAX_ACCELERATION_MS2 = 10.0

# The simulation runs from t=0 to this many seconds -- unbounded time is never
# allowed (Section 16).
MIN_TIME_S = 0.0
MAX_TIME_S = 20.0

DEFAULT_INITIAL_POSITION_M = 0.0
DEFAULT_INITIAL_VELOCITY_MS = 2.0
DEFAULT_ACCELERATION_MS2 = 1.0

# Fixed educational timestep, matching simulations.py's TIME_STEP_S.
TIME_STEP_S = 0.05


class SimulationError(ValueError):
    """A simulation input was outside the physically or numerically valid range."""


def _as_float(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SimulationError(f"{label} must be a number.")
    if math.isnan(number) or math.isinf(number):
        raise SimulationError(f"{label} must be a finite number.")
    return number


def clamp_initial_position(value) -> float:
    number = _as_float(value, "Initial position")
    return max(MIN_INITIAL_POSITION_M, min(MAX_INITIAL_POSITION_M, number))


def clamp_initial_velocity(value) -> float:
    number = _as_float(value, "Initial velocity")
    return max(MIN_INITIAL_VELOCITY_MS, min(MAX_INITIAL_VELOCITY_MS, number))


def clamp_acceleration(value) -> float:
    number = _as_float(value, "Acceleration")
    return max(MIN_ACCELERATION_MS2, min(MAX_ACCELERATION_MS2, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def kinematics_state(
    *, initial_position, initial_velocity, acceleration, time
) -> dict:
    """Return {position_m, velocity_m_s, acceleration_m_s2} at ``time`` seconds.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined.
    """

    x0 = clamp_initial_position(initial_position)
    v0 = clamp_initial_velocity(initial_velocity)
    a = clamp_acceleration(acceleration)
    t = clamp_time(time)

    velocity = v0 + a * t
    position = x0 + v0 * t + 0.5 * a * t * t
    return {
        "position_m": position,
        "velocity_m_s": velocity,
        "acceleration_m_s2": a,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="kinematics",
        template="physics/kinematics.html",
        equations=("v = v₀ + at", "x = x₀ + v₀t + ½at²"),
        units={
            "initial_position_m": "m",
            "initial_velocity_m_s": "m/s",
            "acceleration_m_s2": "m/s^2",
            "time_s": "s",
            "position_m": "m",
            "velocity_m_s": "m/s",
        },
        bounds={
            "initial_position_m": (MIN_INITIAL_POSITION_M, MAX_INITIAL_POSITION_M),
            "initial_velocity_m_s": (MIN_INITIAL_VELOCITY_MS, MAX_INITIAL_VELOCITY_MS),
            "acceleration_m_s2": (MIN_ACCELERATION_MS2, MAX_ACCELERATION_MS2),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "initial_position_m": DEFAULT_INITIAL_POSITION_M,
            "initial_velocity_m_s": DEFAULT_INITIAL_VELOCITY_MS,
            "acceleration_m_s2": DEFAULT_ACCELERATION_MS2,
        },
        input_fields=(
            "initial_position_m",
            "initial_velocity_m_s",
            "acceleration_m_s2",
            "time_s",
        ),
    )
)
