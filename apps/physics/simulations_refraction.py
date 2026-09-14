"""Deterministic reference model for the Refraction (Snell's Law) lab.

A light ray traveling in a medium of refractive index ``n1``, hitting a flat
interface with a second medium of refractive index ``n2`` at an angle of
incidence ``angle1`` (measured from the normal -- the line perpendicular to
the interface). Snell's law:

    n1 * sin(theta1) = n2 * sin(theta2)

Like ``simulations_buoyancy.py``, there is no time axis: refraction is an
instantaneous geometric relationship, not a process that unfolds over time.

Going from a denser medium into a less dense one (n1 > n2) has a special
case: past a critical angle, ALL the light reflects back into the first
medium instead of refracting through -- total internal reflection (TIR).
The critical angle is where the refracted ray would have to bend to exactly
90 degrees (grazing along the interface):

    critical_angle = arcsin(n2 / n1)          (only defined when n1 > n2)

TIR happens whenever ``n1 * sin(theta1) / n2 > 1`` -- there is no real angle
whose sine exceeds 1, so no refracted ray exists past that point. This
module represents "no refracted ray" with ``angle2_deg = 0.0`` and
``total_internal_reflection = True`` together (never interpret the 0.0
alone as meaning "refracts straight through" -- always check the flag
first, exactly like ``simulations_coulombs_law.py``'s zero-force/
``is_attractive`` convention). Snell's law is also reversible: refracting
from medium 1 into medium 2 and then back from medium 2 into medium 1 at
the resulting angle returns exactly the original angle -- this module's
tests verify that directly.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/refraction.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds. Kept in sync with the JS module. 1.0 is the refractive
# index of a vacuum (air is close enough to treat as 1.0 here); real
# materials go up to roughly 2.4-2.5 (diamond).
MIN_INDEX = 1.0
MAX_INDEX = 2.5
MIN_ANGLE_DEG = 0.0
MAX_ANGLE_DEG = 89.0

DEFAULT_N1 = 1.0  # air
DEFAULT_N2 = 1.5  # glass
DEFAULT_ANGLE1_DEG = 30.0


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


def clamp_index(value) -> float:
    """Validate and clamp a refractive index. Less than 1.0 is rejected
    outright -- this lab treats 1.0 (vacuum/air) as the floor."""

    number = _as_float(value, "Refractive index")
    if number < 1.0:
        raise SimulationError("Refractive index must be at least 1.0.")
    return max(MIN_INDEX, min(MAX_INDEX, number))


def clamp_angle(value) -> float:
    """Validate and clamp the angle of incidence. Negative is rejected
    outright -- an angle from the normal cannot be negative here."""

    number = _as_float(value, "Angle of incidence")
    if number < 0:
        raise SimulationError("Angle of incidence cannot be negative.")
    return max(MIN_ANGLE_DEG, min(MAX_ANGLE_DEG, number))


def refraction_state(*, n1, n2, angle1_deg) -> dict:
    """Return the refracted (or totally-internally-reflected) angle for a
    ray crossing from a medium of index ``n1`` into one of index ``n2`` at
    angle of incidence ``angle1_deg``.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    n1c = clamp_index(n1)
    n2c = clamp_index(n2)
    theta1_deg = clamp_angle(angle1_deg)
    theta1_rad = math.radians(theta1_deg)

    has_critical_angle = n1c > n2c
    if has_critical_angle:
        critical_angle_deg = math.degrees(math.asin(n2c / n1c))
    else:
        critical_angle_deg = 0.0  # not applicable -- see module docstring

    sin_theta2 = (n1c / n2c) * math.sin(theta1_rad)
    total_internal_reflection = sin_theta2 > 1.0

    if total_internal_reflection:
        angle2_deg = 0.0  # no refracted ray -- see module docstring
    else:
        angle2_deg = math.degrees(math.asin(min(1.0, sin_theta2)))

    return {
        "n1": n1c,
        "n2": n2c,
        "angle1_deg": theta1_deg,
        "has_critical_angle": has_critical_angle,
        "critical_angle_deg": critical_angle_deg,
        "total_internal_reflection": total_internal_reflection,
        "angle2_deg": angle2_deg,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="refraction",
        template="physics/refraction.html",
        equations=(
            "n1 sin(theta1) = n2 sin(theta2)",
            "critical angle = arcsin(n2 / n1)  (only when n1 > n2)",
        ),
        units={
            "n1": "",
            "n2": "",
            "angle1_deg": "°",
            "angle2_deg": "°",
            "critical_angle_deg": "°",
        },
        bounds={
            "n1": (MIN_INDEX, MAX_INDEX),
            "n2": (MIN_INDEX, MAX_INDEX),
            "angle1_deg": (MIN_ANGLE_DEG, MAX_ANGLE_DEG),
        },
        default_state={
            "n1": DEFAULT_N1,
            "n2": DEFAULT_N2,
            "angle1_deg": DEFAULT_ANGLE1_DEG,
        },
        input_fields=(
            "n1",
            "n2",
            "angle1_deg",
        ),
    )
)
