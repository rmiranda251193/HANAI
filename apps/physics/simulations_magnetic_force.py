"""Deterministic reference model for the Magnetic Force lab.

A charged particle -- mass ``mass``, charge magnitude ``charge_magnitude``
(always positive; ``positive_charge`` says which sign), moving at speed
``speed`` -- enters a uniform magnetic field ``field`` perpendicular to its
velocity. The magnetic force is always perpendicular to the velocity, so it
changes the particle's DIRECTION but never its SPEED (exactly what the
seeded "Magnetic force on a moving charge" concept states) -- the particle
moves in a perfect circle at constant speed, with the magnetic force
playing the centripetal role (mirrors ``simulations_circular_motion.py``'s
shape, the way ``simulations_orbital_motion.py``'s gravity does):

    omega = |q| B / m                 (angular speed -- also known as the
                                        cyclotron frequency)
    r = m v / (|q| B) = v / omega     (orbital radius)
    T = 2*pi*m / (|q| B) = 2*pi/omega (orbital period -- notice v drops
                                        out completely: the period does
                                        NOT depend on speed, just like a
                                        pendulum's amplitude-independence
                                        elsewhere in this project)
    F = |q| v B                       (force magnitude, theta=90 fixed)

    x(t) = r*cos(direction*omega*t), y(t) = r*sin(direction*omega*t)

``direction`` is +1 for a positive charge (counterclockwise, for this
module's fixed field orientation) and -1 for a negative charge (clockwise)
-- the sign of the charge flips which way the particle circles, a real and
testable physical fact.

Charge magnitude, mass, speed and field are all expressed in friendly,
scaled units (not real electron/proton values) so the lab's sliders stay in
the same "small, readable numbers" range as every other lab -- this is an
idealized world, not a claim about any specific real particle.
``charge_magnitude`` must be strictly positive: at zero charge there is no
magnetic force at all, and the radius/period formulas above divide by it,
so zero is a genuine mathematical singularity here (unlike
``simulations_coulombs_law.py``, where zero charge is a perfectly valid,
well-defined case).

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/magnetic-force.js`` mirrors it exactly
for live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in scaled friendly units. Kept in sync with the JS module.
MIN_CHARGE_MAGNITUDE_C = 0.5
MAX_CHARGE_MAGNITUDE_C = 3.0
MIN_MASS_KG = 0.01
MAX_MASS_KG = 2.0
MIN_SPEED_M_S = 1.0
MAX_SPEED_M_S = 50.0
MIN_FIELD_T = 0.5
MAX_FIELD_T = 5.0

MIN_TIME_S = 0.0
MAX_TIME_S = 20.0

DEFAULT_CHARGE_MAGNITUDE_C = 1.0
DEFAULT_POSITIVE_CHARGE = 1.0  # positive by default
DEFAULT_MASS_KG = 0.1
DEFAULT_SPEED_M_S = 10.0
DEFAULT_FIELD_T = 2.0


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


def clamp_charge_magnitude(value) -> float:
    """Validate and clamp the charge magnitude. Non-positive is rejected
    outright -- see the module docstring for why zero charge is a genuine
    singularity here, not just a boundary."""

    number = _as_float(value, "Charge magnitude")
    if number <= 0:
        raise SimulationError("Charge magnitude must be positive.")
    return max(MIN_CHARGE_MAGNITUDE_C, min(MAX_CHARGE_MAGNITUDE_C, number))


def clamp_mass(value) -> float:
    """Validate and clamp the particle's mass. Non-positive is rejected
    outright."""

    number = _as_float(value, "Mass")
    if number <= 0:
        raise SimulationError("Mass must be positive.")
    return max(MIN_MASS_KG, min(MAX_MASS_KG, number))


def clamp_speed(value) -> float:
    """Validate and clamp the particle's speed. Non-positive is rejected
    outright -- a stationary charge feels no magnetic force at all."""

    number = _as_float(value, "Speed")
    if number <= 0:
        raise SimulationError("Speed must be positive.")
    return max(MIN_SPEED_M_S, min(MAX_SPEED_M_S, number))


def clamp_field(value) -> float:
    """Validate and clamp the magnetic field strength. Non-positive is
    rejected outright."""

    number = _as_float(value, "Magnetic field")
    if number <= 0:
        raise SimulationError("Magnetic field must be positive.")
    return max(MIN_FIELD_T, min(MAX_FIELD_T, number))


def clamp_positive_charge(value) -> float:
    """Rounds to exactly 0.0 (negative charge) or 1.0 (positive charge) --
    the same two-choice-as-a-number convention
    ``simulations_collision.py``'s ``clamp_elastic`` and
    ``simulations_circuits.py``'s ``clamp_series`` use."""

    number = _as_float(value, "Charge sign")
    return 1.0 if number >= 0.5 else 0.0


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def magnetic_force_state(*, charge_magnitude, positive_charge, mass, speed, field, time) -> dict:
    """Return the orbiting charged particle's position/velocity/period at
    ``time`` seconds in a uniform perpendicular magnetic field.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    q = clamp_charge_magnitude(charge_magnitude)
    is_positive = clamp_positive_charge(positive_charge) >= 0.5
    m = clamp_mass(mass)
    v = clamp_speed(speed)
    b = clamp_field(field)
    t = clamp_time(time)

    omega = (q * b) / m
    radius = v / omega
    period = 2.0 * math.pi / omega
    force_n = q * v * b
    direction = 1.0 if is_positive else -1.0

    theta = direction * omega * t
    x = radius * math.cos(theta)
    y = radius * math.sin(theta)
    vx = -v * direction * math.sin(theta)
    vy = v * direction * math.cos(theta)
    speed_now = math.hypot(vx, vy)

    return {
        "charge_magnitude_c": q,
        "positive_charge": is_positive,
        "mass_kg": m,
        "speed_m_s": v,
        "field_t": b,
        "time_s": t,
        "radius_m": radius,
        "period_s": period,
        "force_n": force_n,
        "position_x_m": x,
        "position_y_m": y,
        "velocity_x_m_s": vx,
        "velocity_y_m_s": vy,
        "current_speed_m_s": speed_now,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="magnetic_force",
        template="physics/magnetic_force.html",
        equations=(
            "F = |q| v B",
            "r = m v / (|q| B)",
            "T = 2*pi*m / (|q| B)  (independent of speed)",
        ),
        units={
            "charge_magnitude_c": "C",
            "mass_kg": "kg",
            "speed_m_s": "m/s",
            "field_t": "T",
            "time_s": "s",
            "radius_m": "m",
            "period_s": "s",
            "force_n": "N",
        },
        bounds={
            "charge_magnitude_c": (MIN_CHARGE_MAGNITUDE_C, MAX_CHARGE_MAGNITUDE_C),
            "positive_charge": (0.0, 1.0),
            "mass_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "speed_m_s": (MIN_SPEED_M_S, MAX_SPEED_M_S),
            "field_t": (MIN_FIELD_T, MAX_FIELD_T),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "charge_magnitude_c": DEFAULT_CHARGE_MAGNITUDE_C,
            "positive_charge": DEFAULT_POSITIVE_CHARGE,
            "mass_kg": DEFAULT_MASS_KG,
            "speed_m_s": DEFAULT_SPEED_M_S,
            "field_t": DEFAULT_FIELD_T,
        },
        input_fields=(
            "charge_magnitude_c",
            "positive_charge",
            "mass_kg",
            "speed_m_s",
            "field_t",
            "time_s",
        ),
    )
)
