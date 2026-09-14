"""Deterministic reference model for the Ideal Gas Law lab.

An ideal gas: negligible particle volume, no intermolecular forces. Given
the amount ``moles`` (n), absolute temperature ``temperature`` (T, in
kelvin) and volume ``volume`` (V), the ideal gas law gives the pressure:

    P V = n R T   =>   P = n R T / V

where R = 8.314 J/(mol*K) is the real universal gas constant -- unlike
Orbital Motion's scaled "mu", this module uses the actual physical value,
and the default state (1 mole, 298 K, ~24.5 L) lands close to 1 standard
atmosphere (101325 Pa) on purpose, as a real-world sanity check.

Like ``simulations_calorimetry.py``, there is no branching case and no time
axis: one formula covers every combination of inputs, and changing a
control is treated as reaching the new equilibrium state instantly. The
three classical gas laws are all just this one formula holding two
variables fixed:

    Boyle's law (n, T fixed):    P is proportional to 1/V
    Gay-Lussac's law (n, V fixed): P is proportional to T
    Avogadro's law (T, V fixed): P is proportional to n

This module's tests verify all three directly by comparing two computed
states, not just trusting the algebra.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/ideal-gas-law.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

GAS_CONSTANT_J_PER_MOL_K = 8.314

# UI-facing bounds, in SI units (temperature in kelvin). Kept in sync with
# the JS module.
MIN_MOLES = 0.1
MAX_MOLES = 10.0
MIN_TEMPERATURE_K = 100.0
MAX_TEMPERATURE_K = 1000.0
MIN_VOLUME_M3 = 0.001
MAX_VOLUME_M3 = 1.0

DEFAULT_MOLES = 1.0
DEFAULT_TEMPERATURE_K = 298.0
DEFAULT_VOLUME_M3 = 0.0245  # ~1 atmosphere at the defaults above


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


def clamp_moles(value) -> float:
    """Validate and clamp the amount of gas. Non-positive is rejected
    outright -- there is no gas to describe in an empty or negative amount."""

    number = _as_float(value, "Amount of gas")
    if number <= 0:
        raise SimulationError("Amount of gas must be positive.")
    return max(MIN_MOLES, min(MAX_MOLES, number))


def clamp_temperature(value) -> float:
    """Validate and clamp the absolute temperature. Non-positive is
    rejected outright -- 0 K (absolute zero) and below are not reachable
    or meaningful for an ideal gas."""

    number = _as_float(value, "Temperature")
    if number <= 0:
        raise SimulationError("Temperature must be positive (it's measured in kelvin).")
    return max(MIN_TEMPERATURE_K, min(MAX_TEMPERATURE_K, number))


def clamp_volume(value) -> float:
    """Validate and clamp the volume. Non-positive is rejected outright --
    a gas must occupy some space."""

    number = _as_float(value, "Volume")
    if number <= 0:
        raise SimulationError("Volume must be positive.")
    return max(MIN_VOLUME_M3, min(MAX_VOLUME_M3, number))


def ideal_gas_law_state(*, moles, temperature, volume) -> dict:
    """Return the pressure of an ideal gas with the given amount,
    temperature and volume.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    n = clamp_moles(moles)
    t = clamp_temperature(temperature)
    v = clamp_volume(volume)

    pressure_pa = (n * GAS_CONSTANT_J_PER_MOL_K * t) / v

    return {
        "moles": n,
        "temperature_k": t,
        "volume_m3": v,
        "pressure_pa": pressure_pa,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="ideal_gas_law",
        template="physics/ideal_gas_law.html",
        equations=("P V = n R T", "P = n R T / V"),
        units={
            "moles": "mol",
            "temperature_k": "K",
            "volume_m3": "m³",
            "pressure_pa": "Pa",
        },
        bounds={
            "moles": (MIN_MOLES, MAX_MOLES),
            "temperature_k": (MIN_TEMPERATURE_K, MAX_TEMPERATURE_K),
            "volume_m3": (MIN_VOLUME_M3, MAX_VOLUME_M3),
        },
        default_state={
            "moles": DEFAULT_MOLES,
            "temperature_k": DEFAULT_TEMPERATURE_K,
            "volume_m3": DEFAULT_VOLUME_M3,
        },
        input_fields=(
            "moles",
            "temperature_k",
            "volume_m3",
        ),
    )
)
