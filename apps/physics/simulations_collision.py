"""Deterministic reference model for the Momentum and Collisions lab.

Cart 1 starts at x=0 moving right at ``initial_velocity`` (always positive
-- it always approaches cart 2); cart 2 starts at rest at a fixed separation
``SEPARATION_M``. This is the standard "moving cart hits a stationary cart"
setup, chosen specifically so a collision always happens somewhere in the
simulated time window -- no "did they even meet" edge case to reason about.

Before the collision (t < t_c, where t_c = SEPARATION_M / initial_velocity):

    x1(t) = v1*t,  x2(t) = SEPARATION_M

At and after the collision, momentum is always conserved. Two idealized
outcomes are supported:

    elastic (kinetic energy also conserved):
        v1' = ((m1 - m2) / (m1 + m2)) * v1
        v2' = (2*m1 / (m1 + m2)) * v1

    perfectly inelastic (the carts stick together):
        v1' = v2' = (m1*v1) / (m1 + m2)

    x1(t) = SEPARATION_M + v1'*(t - t_c),  x2(t) = SEPARATION_M + v2'*(t - t_c)

Mirrors the other ``simulations_*.py`` modules in shape and intent: this is
the single source of truth for the mathematics, the browser simulation in
``static/js/physics/collision.js`` mirrors it exactly for live interaction,
and nothing here ever touches an AI provider -- every value is computed
from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_MASS_KG = 0.5
MAX_MASS_KG = 10.0
MIN_INITIAL_VELOCITY_MS = 0.5
MAX_INITIAL_VELOCITY_MS = 10.0

# Fixed setup, not a user-adjustable input -- this is what guarantees a
# collision always happens within the simulated time window.
SEPARATION_M = 8.0

MIN_TIME_S = 0.0
MAX_TIME_S = 20.0

DEFAULT_MASS1_KG = 2.0
DEFAULT_MASS2_KG = 2.0
DEFAULT_INITIAL_VELOCITY_MS = 4.0
DEFAULT_ELASTIC = 1.0  # elastic by default


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


def clamp_mass(value) -> float:
    number = _as_float(value, "Mass")
    return max(MIN_MASS_KG, min(MAX_MASS_KG, number))


def clamp_initial_velocity(value) -> float:
    number = _as_float(value, "Initial velocity")
    return max(MIN_INITIAL_VELOCITY_MS, min(MAX_INITIAL_VELOCITY_MS, number))


def clamp_elastic(value) -> float:
    """Rounds to exactly 0.0 (perfectly inelastic) or 1.0 (elastic) --
    a two-choice toggle represented as a number so it fits the same
    numeric input/bounds pattern every other field in this lab uses."""

    number = _as_float(value, "Collision type")
    return 1.0 if number >= 0.5 else 0.0


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def collision_state(*, mass1, mass2, initial_velocity, elastic, time) -> dict:
    """Return both carts' positions/velocities, and the system's total
    momentum and kinetic energy, at ``time`` seconds.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    m1 = clamp_mass(mass1)
    m2 = clamp_mass(mass2)
    v1 = clamp_initial_velocity(initial_velocity)
    is_elastic = clamp_elastic(elastic) >= 0.5
    t = clamp_time(time)

    collision_time = SEPARATION_M / v1

    if t < collision_time:
        x1 = v1 * t
        x2 = SEPARATION_M
        vel1 = v1
        vel2 = 0.0
        has_collided = False
    else:
        if is_elastic:
            vel1 = ((m1 - m2) / (m1 + m2)) * v1
            vel2 = (2.0 * m1 / (m1 + m2)) * v1
        else:
            vel1 = vel2 = (m1 * v1) / (m1 + m2)
        dt = t - collision_time
        x1 = SEPARATION_M + vel1 * dt
        x2 = SEPARATION_M + vel2 * dt
        has_collided = True

    momentum_total = m1 * vel1 + m2 * vel2
    kinetic_energy_total = 0.5 * m1 * vel1 * vel1 + 0.5 * m2 * vel2 * vel2

    return {
        "position_1_m": x1,
        "position_2_m": x2,
        "velocity_1_m_s": vel1,
        "velocity_2_m_s": vel2,
        "has_collided": has_collided,
        "collision_time_s": collision_time,
        "momentum_total_kg_m_s": momentum_total,
        "kinetic_energy_total_j": kinetic_energy_total,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="momentum_collision",
        template="physics/momentum_collision.html",
        equations=("p = m1v1 + m2v2 (always conserved)", "elastic: v1'=((m1-m2)/(m1+m2))v1, v2'=(2m1/(m1+m2))v1"),
        units={
            "mass1_kg": "kg",
            "mass2_kg": "kg",
            "initial_velocity_m_s": "m/s",
            "elastic": "",
            "time_s": "s",
            "position_1_m": "m",
            "position_2_m": "m",
            "velocity_1_m_s": "m/s",
            "velocity_2_m_s": "m/s",
            "momentum_total_kg_m_s": "kg m/s",
            "kinetic_energy_total_j": "J",
        },
        bounds={
            "mass1_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "mass2_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "initial_velocity_m_s": (MIN_INITIAL_VELOCITY_MS, MAX_INITIAL_VELOCITY_MS),
            "elastic": (0.0, 1.0),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "mass1_kg": DEFAULT_MASS1_KG,
            "mass2_kg": DEFAULT_MASS2_KG,
            "initial_velocity_m_s": DEFAULT_INITIAL_VELOCITY_MS,
            "elastic": DEFAULT_ELASTIC,
        },
        input_fields=(
            "mass1_kg",
            "mass2_kg",
            "initial_velocity_m_s",
            "elastic",
            "time_s",
        ),
    )
)
