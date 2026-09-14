"""Deterministic reference model for the Calorimetry lab.

Two substances -- mass ``mass1``/``mass2``, specific heat capacity
``specific_heat1``/``specific_heat2``, starting temperature ``temp1``/
``temp2`` (in Celsius; only differences matter, so Celsius and Kelvin give
the same physics) -- are mixed in an idealized, perfectly insulated system:
no heat escapes to the surroundings, and both substances reach one common
final temperature. Conservation of energy (heat lost by the warmer one
equals heat gained by the cooler one) gives a single weighted-average
formula that works regardless of which substance starts warmer -- unlike
``simulations_buoyancy.py`` (floats/sinks) or ``simulations_refraction.py``
(refracts/TIR), there is no branching case here at all:

    C1 = mass1 * specific_heat1              (heat capacity of substance 1,
    C2 = mass2 * specific_heat2                J/K -- how much energy it
                                                takes to change its temperature
                                                by 1 degree)

    T_eq = (C1*temp1 + C2*temp2) / (C1 + C2)  (equilibrium temperature --
                                                 always between temp1 and
                                                 temp2, pulled closer to
                                                 whichever substance has the
                                                 larger heat capacity)

    heat_transferred = |C1 * (temp1 - T_eq)| = |C2 * (T_eq - temp2)|
                                               (the two must be equal --
                                                that equality IS conservation
                                                of energy, and this module's
                                                tests check it directly)

Like ``simulations_circuits.py``/``simulations_coulombs_law.py``/
``simulations_buoyancy.py``/``simulations_refraction.py``, there is no time
axis -- this idealized mixing reaches equilibrium essentially instantly.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/calorimetry.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI-shaped units (temperature in Celsius). Kept in
# sync with the JS module. The same bounds apply to both substances.
MIN_MASS_KG = 0.01
MAX_MASS_KG = 10.0
MIN_SPECIFIC_HEAT = 100.0
MAX_SPECIFIC_HEAT = 4200.0
MIN_TEMP_C = -20.0
MAX_TEMP_C = 300.0

DEFAULT_MASS1_KG = 0.5
DEFAULT_SPECIFIC_HEAT1 = 4186.0  # water
DEFAULT_TEMP1_C = 20.0
DEFAULT_MASS2_KG = 0.2
DEFAULT_SPECIFIC_HEAT2 = 900.0  # aluminum
DEFAULT_TEMP2_C = 100.0


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
    """Validate and clamp a mass. Non-positive is rejected outright --
    there is no substance to mix in an empty or negative sample."""

    number = _as_float(value, "Mass")
    if number <= 0:
        raise SimulationError("Mass must be positive.")
    return max(MIN_MASS_KG, min(MAX_MASS_KG, number))


def clamp_specific_heat(value) -> float:
    """Validate and clamp a specific heat capacity. Non-positive is
    rejected outright -- it takes real, positive energy to change a real
    substance's temperature."""

    number = _as_float(value, "Specific heat")
    if number <= 0:
        raise SimulationError("Specific heat must be positive.")
    return max(MIN_SPECIFIC_HEAT, min(MAX_SPECIFIC_HEAT, number))


def clamp_temp(value) -> float:
    """Validate and clamp a temperature, in Celsius. Negative is a normal,
    valid temperature on this scale -- not rejected."""

    number = _as_float(value, "Temperature")
    return max(MIN_TEMP_C, min(MAX_TEMP_C, number))


def calorimetry_state(*, mass1, specific_heat1, temp1, mass2, specific_heat2, temp2) -> dict:
    """Return the equilibrium temperature and heat transferred when two
    substances are mixed in an idealized, perfectly insulated system.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    m1 = clamp_mass(mass1)
    c1 = clamp_specific_heat(specific_heat1)
    t1 = clamp_temp(temp1)
    m2 = clamp_mass(mass2)
    c2 = clamp_specific_heat(specific_heat2)
    t2 = clamp_temp(temp2)

    heat_capacity1 = m1 * c1
    heat_capacity2 = m2 * c2

    equilibrium_temp_c = (heat_capacity1 * t1 + heat_capacity2 * t2) / (
        heat_capacity1 + heat_capacity2
    )
    heat_transferred_j = abs(heat_capacity1 * (t1 - equilibrium_temp_c))

    return {
        "mass1_kg": m1,
        "specific_heat1": c1,
        "temp1_c": t1,
        "mass2_kg": m2,
        "specific_heat2": c2,
        "temp2_c": t2,
        "heat_capacity1_j_per_k": heat_capacity1,
        "heat_capacity2_j_per_k": heat_capacity2,
        "equilibrium_temp_c": equilibrium_temp_c,
        "heat_transferred_j": heat_transferred_j,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="calorimetry",
        template="physics/calorimetry.html",
        equations=(
            "C = m c  (heat capacity)",
            "T_eq = (C1 T1 + C2 T2) / (C1 + C2)",
        ),
        units={
            "mass1_kg": "kg",
            "specific_heat1": "J/(kg·K)",
            "temp1_c": "°C",
            "mass2_kg": "kg",
            "specific_heat2": "J/(kg·K)",
            "temp2_c": "°C",
            "equilibrium_temp_c": "°C",
            "heat_transferred_j": "J",
        },
        bounds={
            "mass1_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "specific_heat1": (MIN_SPECIFIC_HEAT, MAX_SPECIFIC_HEAT),
            "temp1_c": (MIN_TEMP_C, MAX_TEMP_C),
            "mass2_kg": (MIN_MASS_KG, MAX_MASS_KG),
            "specific_heat2": (MIN_SPECIFIC_HEAT, MAX_SPECIFIC_HEAT),
            "temp2_c": (MIN_TEMP_C, MAX_TEMP_C),
        },
        default_state={
            "mass1_kg": DEFAULT_MASS1_KG,
            "specific_heat1": DEFAULT_SPECIFIC_HEAT1,
            "temp1_c": DEFAULT_TEMP1_C,
            "mass2_kg": DEFAULT_MASS2_KG,
            "specific_heat2": DEFAULT_SPECIFIC_HEAT2,
            "temp2_c": DEFAULT_TEMP2_C,
        },
        input_fields=(
            "mass1_kg",
            "specific_heat1",
            "temp1_c",
            "mass2_kg",
            "specific_heat2",
            "temp2_c",
        ),
    )
)
