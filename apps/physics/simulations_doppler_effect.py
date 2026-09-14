"""Deterministic reference model for the Doppler Effect lab.

A sound source emitting at frequency ``source_freq`` (Hz), moving along the
line toward an observer at signed velocity ``source_velocity`` (positive =
toward the observer, negative = away), with the observer itself also
possibly moving along that same line at signed velocity
``observer_velocity`` (positive = toward the source, negative = away):

    f_observed = f_source * (v_sound + v_observer) / (v_sound - v_source)

where v_sound = 343 m/s (the real speed of sound in air at room
temperature -- like Orbital Motion's mu is a friendly scaled value but the
Ideal Gas Law's R is the real physical constant, this module uses the real
v_sound, and the default state's numbers are deliberately realistic).

A genuinely non-obvious, testable fact this module's tests check directly:
source motion and observer motion do NOT produce the same frequency shift
even at the same speed -- the two enter the formula differently (source in
the denominator, observer in the numerator). This is real physics, not an
approximation error, and it's why the classical (non-relativistic) Doppler
formula has this asymmetric shape at all.

Like ``simulations_calorimetry.py`` and ``simulations_ideal_gas_law.py``,
there is no branching case and no time axis -- one formula, evaluated
instantly for whatever velocities are set. Source and observer speeds are
kept well below the speed of sound (see ``MAX_VELOCITY_M_S``) so the
denominator never approaches zero -- a source actually reaching or
exceeding the speed of sound produces a real physical discontinuity (a
sonic boom) that is out of scope for this lab's idealized model.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/doppler-effect.js`` mirrors it exactly
for live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

SPEED_OF_SOUND_M_S = 343.0

# UI-facing bounds. Kept in sync with the JS module. Velocities are signed
# and symmetric (positive = toward the other party) and kept comfortably
# subsonic -- see the module docstring for why.
MIN_FREQ_HZ = 20.0
MAX_FREQ_HZ = 2000.0
MAX_VELOCITY_M_S = 60.0  # ~134 mph -- fast, but nowhere near the speed of sound

DEFAULT_SOURCE_FREQ_HZ = 440.0  # concert A
DEFAULT_SOURCE_VELOCITY_M_S = 20.0  # approaching
DEFAULT_OBSERVER_VELOCITY_M_S = 0.0  # stationary


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


def clamp_freq(value) -> float:
    """Validate and clamp the source frequency. Non-positive is rejected
    outright -- there is no sound at zero or negative frequency."""

    number = _as_float(value, "Source frequency")
    if number <= 0:
        raise SimulationError("Source frequency must be positive.")
    return max(MIN_FREQ_HZ, min(MAX_FREQ_HZ, number))


def clamp_velocity(value) -> float:
    """Validate and clamp a signed velocity along the source-observer line.
    Zero and negative values are physically valid (stationary or moving
    away) -- only non-finite/non-numeric input and exceeding the subsonic
    bound are rejected/clamped."""

    number = _as_float(value, "Velocity")
    return max(-MAX_VELOCITY_M_S, min(MAX_VELOCITY_M_S, number))


def doppler_effect_state(*, source_freq, source_velocity, observer_velocity) -> dict:
    """Return the observed frequency for a source and observer moving
    along the line between them.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    f_source = clamp_freq(source_freq)
    v_source = clamp_velocity(source_velocity)
    v_observer = clamp_velocity(observer_velocity)

    f_observed = f_source * (SPEED_OF_SOUND_M_S + v_observer) / (SPEED_OF_SOUND_M_S - v_source)
    wavelength_ahead_m = (SPEED_OF_SOUND_M_S - v_source) / f_source
    wavelength_behind_m = (SPEED_OF_SOUND_M_S + v_source) / f_source

    return {
        "source_freq_hz": f_source,
        "source_velocity_m_s": v_source,
        "observer_velocity_m_s": v_observer,
        "observed_freq_hz": f_observed,
        "wavelength_ahead_m": wavelength_ahead_m,
        "wavelength_behind_m": wavelength_behind_m,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="doppler_effect",
        template="physics/doppler_effect.html",
        equations=("f_observed = f_source (v_sound + v_observer) / (v_sound - v_source)",),
        units={
            "source_freq_hz": "Hz",
            "source_velocity_m_s": "m/s",
            "observer_velocity_m_s": "m/s",
            "observed_freq_hz": "Hz",
        },
        bounds={
            "source_freq_hz": (MIN_FREQ_HZ, MAX_FREQ_HZ),
            "source_velocity_m_s": (-MAX_VELOCITY_M_S, MAX_VELOCITY_M_S),
            "observer_velocity_m_s": (-MAX_VELOCITY_M_S, MAX_VELOCITY_M_S),
        },
        default_state={
            "source_freq_hz": DEFAULT_SOURCE_FREQ_HZ,
            "source_velocity_m_s": DEFAULT_SOURCE_VELOCITY_M_S,
            "observer_velocity_m_s": DEFAULT_OBSERVER_VELOCITY_M_S,
        },
        input_fields=(
            "source_freq_hz",
            "source_velocity_m_s",
            "observer_velocity_m_s",
        ),
    )
)
