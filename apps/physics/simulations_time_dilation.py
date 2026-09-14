"""Deterministic reference model for the Time Dilation and Length
Contraction lab.

Special relativity's two companion effects, both driven by the same
Lorentz factor. ``velocity_fraction_c`` is the relative speed as a
fraction of the speed of light (beta = v/c -- the standard way this is
taught, since raw m/s makes every everyday speed look identical to zero):

    gamma = 1 / sqrt(1 - beta^2)          (Lorentz factor, always >= 1)
    dilated_time = proper_time * gamma     (a moving clock's tick, AS
                                             MEASURED by a stationary
                                             observer, always takes longer
                                             than the proper time measured
                                             in the clock's own rest frame)
    contracted_length = proper_length / gamma   (a moving object's length,
                                                   AS MEASURED by a
                                                   stationary observer,
                                                   is always shorter than
                                                   its proper length
                                                   measured at rest)

Both ratios equal the same gamma: dilated_time / proper_time =
proper_length / contracted_length = gamma -- one factor, two opposite-
looking effects (time stretches, length shrinks). Like
``simulations_calorimetry.py``/``simulations_ideal_gas_law.py``, there is
no branching case and no time axis -- one formula, evaluated instantly for
whatever speed is set.

beta is capped strictly below 1: at beta=1 (moving at the speed of light)
gamma is undefined (division by zero), and beta > 1 is not physically
possible for anything with mass. This module rejects beta >= 1 outright
with a distinct error message, rather than silently clamping it, since
attempting to reach or exceed the speed of light is a fundamentally
impossible claim, not just an out-of-range UI value.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/time-dilation.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds. Kept in sync with the JS module. beta is capped well
# short of 1 -- see the module docstring.
MIN_VELOCITY_FRACTION_C = 0.0
MAX_VELOCITY_FRACTION_C = 0.99
MIN_PROPER_TIME_S = 0.1
MAX_PROPER_TIME_S = 100.0
MIN_PROPER_LENGTH_M = 0.1
MAX_PROPER_LENGTH_M = 1000.0

DEFAULT_VELOCITY_FRACTION_C = 0.6  # gamma = 1.25 exactly -- a classic example
DEFAULT_PROPER_TIME_S = 10.0
DEFAULT_PROPER_LENGTH_M = 100.0


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


def clamp_velocity_fraction(value) -> float:
    """Validate and clamp beta = v/c. Negative is rejected outright (this
    lab treats it as a speed, not a signed velocity); reaching or exceeding
    1 (the speed of light) is rejected outright -- see the module
    docstring for why that's a distinct, harder error than an ordinary
    out-of-range value."""

    number = _as_float(value, "Velocity (as a fraction of c)")
    if number < 0:
        raise SimulationError("Velocity cannot be negative.")
    if number >= 1.0:
        raise SimulationError(
            "Nothing with mass can reach or exceed the speed of light."
        )
    return max(MIN_VELOCITY_FRACTION_C, min(MAX_VELOCITY_FRACTION_C, number))


def clamp_proper_time(value) -> float:
    """Validate and clamp the proper time interval. Non-positive is
    rejected outright."""

    number = _as_float(value, "Proper time")
    if number <= 0:
        raise SimulationError("Proper time must be positive.")
    return max(MIN_PROPER_TIME_S, min(MAX_PROPER_TIME_S, number))


def clamp_proper_length(value) -> float:
    """Validate and clamp the proper length. Non-positive is rejected
    outright."""

    number = _as_float(value, "Proper length")
    if number <= 0:
        raise SimulationError("Proper length must be positive.")
    return max(MIN_PROPER_LENGTH_M, min(MAX_PROPER_LENGTH_M, number))


def time_dilation_state(*, velocity_fraction_c, proper_time, proper_length) -> dict:
    """Return the Lorentz factor, dilated time and contracted length for a
    given relative speed (as a fraction of c).

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    beta = clamp_velocity_fraction(velocity_fraction_c)
    t0 = clamp_proper_time(proper_time)
    l0 = clamp_proper_length(proper_length)

    gamma = 1.0 / math.sqrt(1.0 - beta * beta)
    dilated_time = t0 * gamma
    contracted_length = l0 / gamma

    return {
        "velocity_fraction_c": beta,
        "proper_time_s": t0,
        "proper_length_m": l0,
        "lorentz_factor": gamma,
        "dilated_time_s": dilated_time,
        "contracted_length_m": contracted_length,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="time_dilation",
        template="physics/time_dilation.html",
        equations=(
            "gamma = 1 / sqrt(1 - v^2/c^2)",
            "delta t = delta t0 * gamma",
            "L = L0 / gamma",
        ),
        units={
            "velocity_fraction_c": "",
            "proper_time_s": "s",
            "proper_length_m": "m",
            "lorentz_factor": "",
            "dilated_time_s": "s",
            "contracted_length_m": "m",
        },
        bounds={
            "velocity_fraction_c": (MIN_VELOCITY_FRACTION_C, MAX_VELOCITY_FRACTION_C),
            "proper_time_s": (MIN_PROPER_TIME_S, MAX_PROPER_TIME_S),
            "proper_length_m": (MIN_PROPER_LENGTH_M, MAX_PROPER_LENGTH_M),
        },
        default_state={
            "velocity_fraction_c": DEFAULT_VELOCITY_FRACTION_C,
            "proper_time_s": DEFAULT_PROPER_TIME_S,
            "proper_length_m": DEFAULT_PROPER_LENGTH_M,
        },
        input_fields=(
            "velocity_fraction_c",
            "proper_time_s",
            "proper_length_m",
        ),
    )
)
