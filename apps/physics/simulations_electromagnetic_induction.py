"""Deterministic reference model for the Electromagnetic Induction lab.

A coil of ``turns`` (N) loops, each of area ``area_m2``, sits in a magnetic
field that changes from ``field_initial_t`` to ``field_final_t`` (in Tesla)
over a time interval ``time_interval_s``. Faraday's law of induction:

    delta_Phi = area * (field_final - field_initial)   (change in flux
                                                          through ONE loop)
    EMF = N * |delta_Phi| / time_interval               (magnitude of the
                                                          induced EMF)

This module reports the EMF's MAGNITUDE (the number a voltmeter would
read); the *direction* of the induced current is Lenz's law's domain, not
a number -- it always opposes the change that caused it, which this module
represents as the boolean ``flux_increasing`` (field growing vs shrinking)
rather than a signed EMF, so a growing and an equally-fast shrinking field
correctly produce the same EMF magnitude with opposite qualitative
directions.

Unlike ``simulations_coulombs_law.py``, an instantaneous (zero-duration)
flux change is not a valid state here: EMF = N * delta_Phi / time_interval
divides by the time interval, so ``time_interval_s`` must be strictly
positive -- a zero-time change would demand infinite EMF, a genuine
mathematical singularity, the same class of edge case
``simulations_magnetic_force.py``'s zero-charge rejection handles.

Like ``simulations_calorimetry.py``/``simulations_ideal_gas_law.py``, there
is no time axis in the animation sense and no branching case beyond that
one rejection -- one formula, evaluated instantly for whatever setup is
chosen.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/electromagnetic-induction.js`` mirrors it
exactly for live interaction, and nothing here ever touches an AI provider
-- every value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds. Kept in sync with the JS module.
MIN_TURNS = 1.0
MAX_TURNS = 500.0
MIN_AREA_M2 = 0.001
MAX_AREA_M2 = 1.0
MIN_FIELD_T = 0.0
MAX_FIELD_T = 2.0
MIN_TIME_INTERVAL_S = 0.01
MAX_TIME_INTERVAL_S = 10.0

DEFAULT_TURNS = 100.0
DEFAULT_AREA_M2 = 0.05
DEFAULT_FIELD_INITIAL_T = 0.0
DEFAULT_FIELD_FINAL_T = 1.0
DEFAULT_TIME_INTERVAL_S = 0.5  # -> EMF = 10 V exactly, a clean worked example


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


def clamp_turns(value) -> float:
    """Validate and clamp the coil's number of turns. Non-positive is
    rejected outright -- a coil needs at least one loop."""

    number = _as_float(value, "Number of turns")
    if number <= 0:
        raise SimulationError("Number of turns must be positive.")
    return max(MIN_TURNS, min(MAX_TURNS, number))


def clamp_area(value) -> float:
    """Validate and clamp the loop area. Non-positive is rejected outright."""

    number = _as_float(value, "Loop area")
    if number <= 0:
        raise SimulationError("Loop area must be positive.")
    return max(MIN_AREA_M2, min(MAX_AREA_M2, number))


def clamp_field(value) -> float:
    """Validate and clamp a magnetic field strength. Negative is rejected
    outright -- this lab treats field strength as a non-negative magnitude;
    zero (no field) is a perfectly valid starting or ending value."""

    number = _as_float(value, "Magnetic field")
    if number < 0:
        raise SimulationError("Magnetic field cannot be negative.")
    return max(MIN_FIELD_T, min(MAX_FIELD_T, number))


def clamp_time_interval(value) -> float:
    """Validate and clamp the time interval over which the field changes.
    Non-positive is rejected outright -- see the module docstring for why
    zero is a genuine singularity here, not just a boundary."""

    number = _as_float(value, "Time interval")
    if number <= 0:
        raise SimulationError("Time interval must be positive.")
    return max(MIN_TIME_INTERVAL_S, min(MAX_TIME_INTERVAL_S, number))


def electromagnetic_induction_state(
    *, turns, area_m2, field_initial_t, field_final_t, time_interval_s
) -> dict:
    """Return the flux change and induced EMF for a coil in a magnetic
    field that changes linearly over the given time interval.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    n = clamp_turns(turns)
    a = clamp_area(area_m2)
    b1 = clamp_field(field_initial_t)
    b2 = clamp_field(field_final_t)
    dt = clamp_time_interval(time_interval_s)

    delta_flux_wb = a * (b2 - b1)
    emf_v = n * abs(delta_flux_wb) / dt
    flux_increasing = b2 > b1

    return {
        "turns": n,
        "area_m2": a,
        "field_initial_t": b1,
        "field_final_t": b2,
        "time_interval_s": dt,
        "delta_flux_wb": delta_flux_wb,
        "emf_v": emf_v,
        "flux_increasing": flux_increasing,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="electromagnetic_induction",
        template="physics/electromagnetic_induction.html",
        equations=(
            "Phi = B A",
            "EMF = N |delta Phi| / delta t",
        ),
        units={
            "turns": "",
            "area_m2": "m²",
            "field_initial_t": "T",
            "field_final_t": "T",
            "time_interval_s": "s",
            "delta_flux_wb": "Wb",
            "emf_v": "V",
        },
        bounds={
            "turns": (MIN_TURNS, MAX_TURNS),
            "area_m2": (MIN_AREA_M2, MAX_AREA_M2),
            "field_initial_t": (MIN_FIELD_T, MAX_FIELD_T),
            "field_final_t": (MIN_FIELD_T, MAX_FIELD_T),
            "time_interval_s": (MIN_TIME_INTERVAL_S, MAX_TIME_INTERVAL_S),
        },
        default_state={
            "turns": DEFAULT_TURNS,
            "area_m2": DEFAULT_AREA_M2,
            "field_initial_t": DEFAULT_FIELD_INITIAL_T,
            "field_final_t": DEFAULT_FIELD_FINAL_T,
            "time_interval_s": DEFAULT_TIME_INTERVAL_S,
        },
        input_fields=(
            "turns",
            "area_m2",
            "field_initial_t",
            "field_final_t",
            "time_interval_s",
        ),
    )
)
