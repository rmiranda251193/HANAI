"""Deterministic reference model for the Circular Motion lab.

Uniform circular motion: an object moves at constant speed around a circle
of radius ``r``, completing one full revolution every ``period`` seconds.
Starting at angle 0 (position ``(r, 0)``) and rotating counterclockwise:

    omega  = 2*pi / period                     (angular speed, rad/s)
    theta(t) = omega * t
    x(t)   = r * cos(theta)
    y(t)   = r * sin(theta)
    speed  = omega * r                         (constant magnitude)
    vx(t)  = -omega * r * sin(theta)
    vy(t)  =  omega * r * cos(theta)
    a_c    = omega^2 * r  =  speed^2 / r        (centripetal acceleration,
                                                  always points toward the
                                                  center: (-omega^2*x, -omega^2*y))

Mirrors ``apps/physics/simulations_projectile.py`` in shape and intent: this
module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/circular-motion.js`` mirrors it exactly
for live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_RADIUS_M = 0.5
MAX_RADIUS_M = 10.0
MIN_PERIOD_S = 0.5
MAX_PERIOD_S = 20.0

# The simulation runs from t=0 to this many seconds -- unbounded time is
# never allowed. Generous enough to show several full revolutions even at
# the slowest supported period.
MIN_TIME_S = 0.0
MAX_TIME_S = 60.0

DEFAULT_RADIUS_M = 2.0
DEFAULT_PERIOD_S = 4.0


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


def clamp_radius(value) -> float:
    number = _as_float(value, "Radius")
    return max(MIN_RADIUS_M, min(MAX_RADIUS_M, number))


def clamp_period(value) -> float:
    """Validate and clamp the period. A non-positive period is rejected
    outright -- there is no such thing as an instant or backwards-time lap."""

    number = _as_float(value, "Period")
    if number <= 0:
        raise SimulationError("Period must be positive.")
    return max(MIN_PERIOD_S, min(MAX_PERIOD_S, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def circular_motion_state(*, radius, period, time) -> dict:
    """Return position/velocity/centripetal acceleration at ``time`` seconds.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    r = clamp_radius(radius)
    period_s = clamp_period(period)
    t = clamp_time(time)

    omega = 2.0 * math.pi / period_s
    theta = omega * t

    x = r * math.cos(theta)
    y = r * math.sin(theta)
    speed = omega * r
    vx = -omega * r * math.sin(theta)
    vy = omega * r * math.cos(theta)
    centripetal_acceleration = omega * omega * r

    angle_deg = math.degrees(theta) % 360.0

    return {
        "position_x_m": x,
        "position_y_m": y,
        "velocity_x_m_s": vx,
        "velocity_y_m_s": vy,
        "speed_m_s": speed,
        "centripetal_acceleration_m_s2": centripetal_acceleration,
        "angle_deg": angle_deg,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="circular_motion",
        template="physics/circular_motion.html",
        equations=("v = 2πr / T", "a_c = v² / r = ω²r"),
        units={
            "radius_m": "m",
            "period_s": "s",
            "time_s": "s",
            "position_x_m": "m",
            "position_y_m": "m",
            "speed_m_s": "m/s",
            "centripetal_acceleration_m_s2": "m/s²",
        },
        bounds={
            "radius_m": (MIN_RADIUS_M, MAX_RADIUS_M),
            "period_s": (MIN_PERIOD_S, MAX_PERIOD_S),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "radius_m": DEFAULT_RADIUS_M,
            "period_s": DEFAULT_PERIOD_S,
        },
        input_fields=(
            "radius_m",
            "period_s",
            "time_s",
        ),
    )
)
