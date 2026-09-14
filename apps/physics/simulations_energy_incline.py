"""Deterministic reference model for the Energy on an Incline lab.

A block of mass ``m`` starts from rest at height ``h`` above the bottom of a
frictionless incline of angle ``theta``, slides down the ramp, then
continues across frictionless flat ground. No energy is ever lost, so total
mechanical energy stays constant throughout -- kinetic and potential energy
just trade off:

    a = g*sin(theta)                        (acceleration along the ramp)
    ramp_length = h / sin(theta)
    t_end = sqrt(2*h/g) / sin(theta)         (time to reach the bottom)
    v_end = a*t_end = sqrt(2*g*h)            (speed at the bottom -- the
                                               classic energy-conservation
                                               result, independent of angle)

    while on the ramp (t < t_end):
        distance(t)      = (1/2)*a*t^2
        height_dropped(t) = distance(t)*sin(theta)
        speed(t)          = a*t

    once past the bottom (t >= t_end), the block keeps moving at v_end on
    flat ground: height_dropped stays at h, speed stays at v_end, and
    distance keeps increasing at that constant speed.

    KE(t) = (1/2)*m*speed(t)^2
    PE(t) = m*g*(h - height_dropped(t))      (relative to the bottom)
    total_energy(t) = KE(t) + PE(t)          (always equals m*g*h)

Mirrors the other ``simulations_*.py`` modules in shape and intent: this is
the single source of truth for the mathematics, the browser simulation in
``static/js/physics/energy-incline.js`` mirrors it exactly for live
interaction, and nothing here ever touches an AI provider -- every value is
computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_HEIGHT_M = 1.0
MAX_HEIGHT_M = 10.0
MIN_ANGLE_DEG = 10.0
MAX_ANGLE_DEG = 80.0
MIN_MASS_KG = 0.5
MAX_MASS_KG = 10.0

GRAVITY_MS2 = 9.8

MIN_TIME_S = 0.0
MAX_TIME_S = 15.0

DEFAULT_HEIGHT_M = 5.0
DEFAULT_ANGLE_DEG = 30.0
DEFAULT_MASS_KG = 2.0


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


def clamp_height(value) -> float:
    number = _as_float(value, "Height")
    return max(MIN_HEIGHT_M, min(MAX_HEIGHT_M, number))


def clamp_angle(value) -> float:
    number = _as_float(value, "Angle")
    return max(MIN_ANGLE_DEG, min(MAX_ANGLE_DEG, number))


def clamp_mass(value) -> float:
    number = _as_float(value, "Mass")
    return max(MIN_MASS_KG, min(MAX_MASS_KG, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def energy_incline_state(*, height, angle, mass, time) -> dict:
    """Return the block's distance/height-dropped/speed and its kinetic,
    potential and total mechanical energy at ``time`` seconds.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    h = clamp_height(height)
    angle_deg = clamp_angle(angle)
    m = clamp_mass(mass)
    t = clamp_time(time)

    theta = math.radians(angle_deg)
    a = GRAVITY_MS2 * math.sin(theta)
    t_end = math.sqrt(2.0 * h / GRAVITY_MS2) / math.sin(theta)
    v_end = a * t_end

    if t < t_end:
        distance = 0.5 * a * t * t
        height_dropped = distance * math.sin(theta)
        speed = a * t
    else:
        ramp_length = h / math.sin(theta)
        distance = ramp_length + v_end * (t - t_end)
        height_dropped = h
        speed = v_end

    kinetic_energy = 0.5 * m * speed * speed
    potential_energy = m * GRAVITY_MS2 * (h - height_dropped)
    total_energy = kinetic_energy + potential_energy

    return {
        "distance_m": distance,
        "height_dropped_m": height_dropped,
        "speed_m_s": speed,
        "kinetic_energy_j": kinetic_energy,
        "potential_energy_j": potential_energy,
        "total_energy_j": total_energy,
        "reached_bottom": t >= t_end,
        "time_at_bottom_s": t_end,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="energy_incline",
        template="physics/energy_incline.html",
        equations=("KE + PE = constant = mgh", "v_bottom = sqrt(2gh)"),
        units={
            "height_m": "m",
            "angle_deg": "°",
            "mass_kg": "kg",
            "time_s": "s",
            "distance_m": "m",
            "speed_m_s": "m/s",
            "kinetic_energy_j": "J",
            "potential_energy_j": "J",
            "total_energy_j": "J",
        },
        bounds={
            "height_m": (MIN_HEIGHT_M, MAX_HEIGHT_M),
            "angle_deg": (MIN_ANGLE_DEG, MAX_ANGLE_DEG),
            "mass_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "height_m": DEFAULT_HEIGHT_M,
            "angle_deg": DEFAULT_ANGLE_DEG,
            "mass_kg": DEFAULT_MASS_KG,
        },
        input_fields=(
            "height_m",
            "angle_deg",
            "mass_kg",
            "time_s",
        ),
    )
)
