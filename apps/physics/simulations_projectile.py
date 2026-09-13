"""Deterministic reference model for the Projectile Motion lab.

Two-dimensional motion under constant gravity, no air resistance, launched
from height ``y0`` at speed ``v0`` and angle ``theta`` above the horizontal:

    vx0 = v0 * cos(theta),  vy0 = v0 * sin(theta)
    x(t)  = vx0 * t
    y(t)  = y0 + vy0*t - (1/2)*g*t^2
    vx(t) = vx0
    vy(t) = vy0 - g*t

Mirrors ``apps/physics/simulations_kinematics.py`` in shape and intent: this
module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/projectile.js`` mirrors it exactly for live
interaction, and nothing here ever touches an AI provider -- every value is
computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_INITIAL_SPEED_MS = 0.0
MAX_INITIAL_SPEED_MS = 40.0
MIN_LAUNCH_ANGLE_DEG = 0.0
MAX_LAUNCH_ANGLE_DEG = 90.0
MIN_INITIAL_HEIGHT_M = 0.0
MAX_INITIAL_HEIGHT_M = 50.0

# Earth surface gravity. Not a user-adjustable input -- this is an idealized
# "no air resistance, constant g" model, the same idealization discipline as
# the Kinematics and Newton's Second Law labs.
GRAVITY_MS2 = 9.8

# The simulation runs from t=0 to this many seconds -- unbounded time is never
# allowed. Generous enough for the slowest fall (max height alone) combined
# with the longest possible flight (max speed straight up).
MIN_TIME_S = 0.0
MAX_TIME_S = 12.0

DEFAULT_INITIAL_SPEED_MS = 15.0
DEFAULT_LAUNCH_ANGLE_DEG = 45.0
DEFAULT_INITIAL_HEIGHT_M = 0.0


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


def clamp_initial_speed(value) -> float:
    number = _as_float(value, "Initial speed")
    return max(MIN_INITIAL_SPEED_MS, min(MAX_INITIAL_SPEED_MS, number))


def clamp_launch_angle(value) -> float:
    number = _as_float(value, "Launch angle")
    return max(MIN_LAUNCH_ANGLE_DEG, min(MAX_LAUNCH_ANGLE_DEG, number))


def clamp_initial_height(value) -> float:
    number = _as_float(value, "Initial height")
    return max(MIN_INITIAL_HEIGHT_M, min(MAX_INITIAL_HEIGHT_M, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def projectile_state(*, initial_speed, launch_angle, initial_height, time) -> dict:
    """Return position/velocity at ``time`` seconds into the flight.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined. This does
    not stop the object at "the ground" (y=0) -- like ``kinematics_state``,
    it is a plain evaluation of the closed-form equations of motion at the
    requested time; the UI's time bound already keeps that within a sensible
    window for the supported speed/angle/height ranges.
    """

    v0 = clamp_initial_speed(initial_speed)
    theta_deg = clamp_launch_angle(launch_angle)
    y0 = clamp_initial_height(initial_height)
    t = clamp_time(time)

    theta = math.radians(theta_deg)
    vx0 = v0 * math.cos(theta)
    vy0 = v0 * math.sin(theta)

    x = vx0 * t
    y = y0 + vy0 * t - 0.5 * GRAVITY_MS2 * t * t
    vx = vx0
    vy = vy0 - GRAVITY_MS2 * t

    return {
        "position_x_m": x,
        "position_y_m": y,
        "velocity_x_m_s": vx,
        "velocity_y_m_s": vy,
        "speed_m_s": math.hypot(vx, vy),
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="projectile_motion",
        template="physics/projectile_motion.html",
        equations=("x = v₀cos(θ)t", "y = y₀ + v₀sin(θ)t − ½gt²"),
        units={
            "initial_speed_m_s": "m/s",
            "launch_angle_deg": "°",
            "initial_height_m": "m",
            "time_s": "s",
            "position_x_m": "m",
            "position_y_m": "m",
            "speed_m_s": "m/s",
        },
        bounds={
            "initial_speed_m_s": (MIN_INITIAL_SPEED_MS, MAX_INITIAL_SPEED_MS),
            "launch_angle_deg": (MIN_LAUNCH_ANGLE_DEG, MAX_LAUNCH_ANGLE_DEG),
            "initial_height_m": (MIN_INITIAL_HEIGHT_M, MAX_INITIAL_HEIGHT_M),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "initial_speed_m_s": DEFAULT_INITIAL_SPEED_MS,
            "launch_angle_deg": DEFAULT_LAUNCH_ANGLE_DEG,
            "initial_height_m": DEFAULT_INITIAL_HEIGHT_M,
        },
        input_fields=(
            "initial_speed_m_s",
            "launch_angle_deg",
            "initial_height_m",
            "time_s",
        ),
    )
)
