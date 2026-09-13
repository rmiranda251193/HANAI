"""Deterministic reference model for the Simple Harmonic Motion lab.

A mass on a spring, pulled back to amplitude ``A`` and released from rest
(no initial push), oscillating with period ``T``:

    omega = 2*pi / T
    x(t)  = A * cos(omega*t)
    v(t)  = -A*omega * sin(omega*t)
    a(t)  = -A*omega^2 * cos(omega*t)  =  -omega^2 * x(t)

The restoring acceleration is always proportional to displacement and
points back toward equilibrium (x=0) -- the defining feature of SHM, and
exactly the same relationship as ``simulations_circular_motion.py``'s
``x(t) = r*cos(omega*t)``: SHM is the shadow of uniform circular motion
projected onto one axis. Mirrors that module in shape and intent: this is
the single source of truth for the mathematics, the browser simulation in
``static/js/physics/shm.js`` mirrors it exactly for live interaction, and
nothing here ever touches an AI provider -- every value is computed from
first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_AMPLITUDE_M = 0.1
MAX_AMPLITUDE_M = 2.0
MIN_PERIOD_S = 0.5
MAX_PERIOD_S = 10.0

# The simulation runs from t=0 to this many seconds -- unbounded time is
# never allowed.
MIN_TIME_S = 0.0
MAX_TIME_S = 40.0

DEFAULT_AMPLITUDE_M = 1.0
DEFAULT_PERIOD_S = 2.0


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


def clamp_amplitude(value) -> float:
    number = _as_float(value, "Amplitude")
    return max(MIN_AMPLITUDE_M, min(MAX_AMPLITUDE_M, number))


def clamp_period(value) -> float:
    """Validate and clamp the period. A non-positive period is rejected
    outright -- there is no such thing as an instant or backwards-time cycle."""

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


def shm_state(*, amplitude, period, time) -> dict:
    """Return displacement/velocity/acceleration at ``time`` seconds.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    a = clamp_amplitude(amplitude)
    period_s = clamp_period(period)
    t = clamp_time(time)

    omega = 2.0 * math.pi / period_s
    x = a * math.cos(omega * t)
    v = -a * omega * math.sin(omega * t)
    accel = -omega * omega * x

    return {
        "position_m": x,
        "velocity_m_s": v,
        "acceleration_m_s2": accel,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="simple_harmonic_motion",
        template="physics/simple_harmonic_motion.html",
        equations=("x = A cos(ωt)", "a = −ω²x"),
        units={
            "amplitude_m": "m",
            "period_s": "s",
            "time_s": "s",
            "position_m": "m",
            "velocity_m_s": "m/s",
            "acceleration_m_s2": "m/s²",
        },
        bounds={
            "amplitude_m": (MIN_AMPLITUDE_M, MAX_AMPLITUDE_M),
            "period_s": (MIN_PERIOD_S, MAX_PERIOD_S),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "amplitude_m": DEFAULT_AMPLITUDE_M,
            "period_s": DEFAULT_PERIOD_S,
        },
        input_fields=(
            "amplitude_m",
            "period_s",
            "time_s",
        ),
    )
)
