"""Deterministic reference model for the Series and Parallel Circuits lab.

An ideal voltage source (no internal resistance) connected to two ohmic
resistors, wired either in series or in parallel. Unlike every other lab in
this project, there is no time axis here: real inductors/capacitors would
introduce transients, but with ideal resistors and ideal (zero-resistance)
wires the circuit reaches its steady state instantly the moment the switch
closes -- so "at time t" is not a meaningful question for this idealized
model. Every quantity below is exact and constant once V, R1 and R2 are
chosen.

Series (same current through every component, voltage divides):

    R_total = R1 + R2
    I = V / R_total                 (same current through R1 and R2)
    V1 = I * R1,  V2 = I * R2       (V1 + V2 = V)

Parallel (same voltage across every branch, current divides):

    R_total = (R1 * R2) / (R1 + R2)
    I = V / R_total                 (total current drawn from the source)
    I1 = V / R1,  I2 = V / R2       (I1 + I2 = I)
    V1 = V2 = V

Either way, power is conserved: P_total = V * I = P1 + P2, where
P1 = I1 * V1 and P2 = I2 * V2 -- the electrical analogue of the energy-
conservation check in ``simulations_energy_incline.py`` and the momentum
check in ``simulations_collision.py``.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/circuits.js`` mirrors it exactly for live
interaction, and nothing here ever touches an AI provider -- every value is
computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_VOLTAGE_V = 1.0
MAX_VOLTAGE_V = 24.0
MIN_RESISTANCE_OHM = 1.0
MAX_RESISTANCE_OHM = 100.0

DEFAULT_VOLTAGE_V = 12.0
DEFAULT_RESISTANCE1_OHM = 10.0
DEFAULT_RESISTANCE2_OHM = 20.0
DEFAULT_SERIES = 1.0  # series by default


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


def clamp_voltage(value) -> float:
    """Validate and clamp the source voltage. Non-positive is rejected
    outright -- there is no current without a potential difference."""

    number = _as_float(value, "Voltage")
    if number <= 0:
        raise SimulationError("Voltage must be positive.")
    return max(MIN_VOLTAGE_V, min(MAX_VOLTAGE_V, number))


def clamp_resistance(value) -> float:
    """Validate and clamp a resistor's resistance. Non-positive is rejected
    outright -- zero resistance is a short circuit (undefined current here),
    and negative resistance is not a real ohmic resistor."""

    number = _as_float(value, "Resistance")
    if number <= 0:
        raise SimulationError("Resistance must be positive.")
    return max(MIN_RESISTANCE_OHM, min(MAX_RESISTANCE_OHM, number))


def clamp_series(value) -> float:
    """Rounds to exactly 0.0 (parallel) or 1.0 (series) -- a two-choice
    toggle represented as a number, the same convention
    ``simulations_collision.py``'s ``clamp_elastic`` uses for elastic vs
    perfectly inelastic."""

    number = _as_float(value, "Circuit type")
    return 1.0 if number >= 0.5 else 0.0


def circuit_state(*, voltage, resistance1, resistance2, series) -> dict:
    """Return every current/voltage/power value for this circuit, in both
    the chosen topology and (for comparison) the other one.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    v = clamp_voltage(voltage)
    r1 = clamp_resistance(resistance1)
    r2 = clamp_resistance(resistance2)
    is_series = clamp_series(series) >= 0.5

    series_total_ohm = r1 + r2
    parallel_total_ohm = (r1 * r2) / (r1 + r2)

    if is_series:
        total_resistance = series_total_ohm
        total_current = v / total_resistance
        current_1 = total_current
        current_2 = total_current
        voltage_1 = current_1 * r1
        voltage_2 = current_2 * r2
    else:
        total_resistance = parallel_total_ohm
        total_current = v / total_resistance
        voltage_1 = v
        voltage_2 = v
        current_1 = voltage_1 / r1
        current_2 = voltage_2 / r2

    power_1 = current_1 * voltage_1
    power_2 = current_2 * voltage_2
    total_power = power_1 + power_2

    return {
        "voltage_v": v,
        "resistance1_ohm": r1,
        "resistance2_ohm": r2,
        "series": is_series,
        "total_resistance_ohm": total_resistance,
        "total_current_a": total_current,
        "current_1_a": current_1,
        "current_2_a": current_2,
        "voltage_1_v": voltage_1,
        "voltage_2_v": voltage_2,
        "power_1_w": power_1,
        "power_2_w": power_2,
        "total_power_w": total_power,
        "series_total_resistance_ohm": series_total_ohm,
        "parallel_total_resistance_ohm": parallel_total_ohm,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="series_parallel_circuit",
        template="physics/series_parallel_circuit.html",
        equations=(
            "series: R = R1 + R2, I = V / R (same for both)",
            "parallel: 1/R = 1/R1 + 1/R2, I1 = V/R1, I2 = V/R2 (V same for both)",
            "P = V * I = P1 + P2 (always)",
        ),
        units={
            "voltage_v": "V",
            "resistance1_ohm": "Ω",
            "resistance2_ohm": "Ω",
            "series": "",
            "total_resistance_ohm": "Ω",
            "total_current_a": "A",
            "current_1_a": "A",
            "current_2_a": "A",
            "voltage_1_v": "V",
            "voltage_2_v": "V",
            "total_power_w": "W",
        },
        bounds={
            "voltage_v": (MIN_VOLTAGE_V, MAX_VOLTAGE_V),
            "resistance1_ohm": (MIN_RESISTANCE_OHM, MAX_RESISTANCE_OHM),
            "resistance2_ohm": (MIN_RESISTANCE_OHM, MAX_RESISTANCE_OHM),
            "series": (0.0, 1.0),
        },
        default_state={
            "voltage_v": DEFAULT_VOLTAGE_V,
            "resistance1_ohm": DEFAULT_RESISTANCE1_OHM,
            "resistance2_ohm": DEFAULT_RESISTANCE2_OHM,
            "series": DEFAULT_SERIES,
        },
        input_fields=(
            "voltage_v",
            "resistance1_ohm",
            "resistance2_ohm",
            "series",
        ),
    )
)
