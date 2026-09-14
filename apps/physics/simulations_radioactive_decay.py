"""Deterministic reference model for the Radioactive Decay lab.

A large sample of ``initial_count`` unstable nuclei, with a fixed
``half_life`` (the time for half of any remaining sample to decay,
regardless of how much has already decayed -- see the seeded "Half-life"
concept). Individual decay is random, but a large sample's average behaviour
is exactly predictable, which is the idealization this module uses:

    lambda = ln(2) / T_half                      (decay constant)
    N(t) = N0 * (1/2)^(t / T_half) = N0 * e^(-lambda*t)
    activity(t) = lambda * N(t)                   (decays per second, the
                                                     instantaneous decay rate)

Unlike Circular Motion, Simple Harmonic Motion or Orbital Motion, this is
the first lab whose quantity NEVER returns to a previous value -- N(t) only
ever decreases, approaching (never reaching) zero. remaining_count(t) +
decayed_count(t) = initial_count at every instant, the conservation-style
check this module's tests verify explicitly (mirroring the momentum/energy
checks in ``simulations_collision.py``/``simulations_energy_incline.py``).

``half_life`` is expressed in friendly, scaled seconds here (not a real
isotope's half-life, which ranges from microseconds to billions of years)
so the lab's sliders stay in the same "small, readable numbers" range as
every other lab -- this is an idealized world, not a claim about any
specific real isotope.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/radioactive-decay.js`` mirrors it exactly
for live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in scaled friendly units. Kept in sync with the JS module.
MIN_INITIAL_COUNT = 100.0
MAX_INITIAL_COUNT = 10000.0
MIN_HALF_LIFE_S = 1.0
MAX_HALF_LIFE_S = 20.0
MIN_TIME_S = 0.0
MAX_TIME_S = 60.0

DEFAULT_INITIAL_COUNT = 1000.0
DEFAULT_HALF_LIFE_S = 5.0


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


def clamp_initial_count(value) -> float:
    """Validate and clamp the starting sample size. Non-positive is rejected
    outright -- there is nothing to decay in an empty or negative sample."""

    number = _as_float(value, "Initial count")
    if number <= 0:
        raise SimulationError("Initial count must be positive.")
    return max(MIN_INITIAL_COUNT, min(MAX_INITIAL_COUNT, number))


def clamp_half_life(value) -> float:
    """Validate and clamp the half-life. Non-positive is rejected outright
    -- a half-life of zero or less is not physically meaningful."""

    number = _as_float(value, "Half-life")
    if number <= 0:
        raise SimulationError("Half-life must be positive.")
    return max(MIN_HALF_LIFE_S, min(MAX_HALF_LIFE_S, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def radioactive_decay_state(*, initial_count, half_life, time) -> dict:
    """Return the remaining/decayed count and activity at ``time`` seconds
    into the decay of a sample with the given half-life.

    Pure: no database writes, no randomness (the *sample* decays randomly in
    reality, but this models the statistically predictable large-N average,
    exactly as the seeded "Radioactive decay" concept describes). Inputs are
    clamped to the supported UI range first so the result is always
    well-defined."""

    n0 = clamp_initial_count(initial_count)
    half_life_s = clamp_half_life(half_life)
    t = clamp_time(time)

    decay_constant = math.log(2) / half_life_s
    half_lives_elapsed = t / half_life_s
    remaining = n0 * (0.5 ** half_lives_elapsed)
    decayed = n0 - remaining
    activity = decay_constant * remaining

    return {
        "initial_count": n0,
        "half_life_s": half_life_s,
        "time_s": t,
        "decay_constant_per_s": decay_constant,
        "half_lives_elapsed": half_lives_elapsed,
        "remaining_count": remaining,
        "decayed_count": decayed,
        "remaining_fraction": remaining / n0,
        "activity_per_s": activity,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="radioactive_decay",
        template="physics/radioactive_decay.html",
        equations=(
            "N(t) = N0 * (1/2)^(t / T_half)",
            "lambda = ln(2) / T_half",
            "activity = lambda * N(t)",
        ),
        units={
            "initial_count": "",
            "half_life_s": "s",
            "time_s": "s",
            "remaining_count": "",
            "decayed_count": "",
            "activity_per_s": "decays/s",
        },
        bounds={
            "initial_count": (MIN_INITIAL_COUNT, MAX_INITIAL_COUNT),
            "half_life_s": (MIN_HALF_LIFE_S, MAX_HALF_LIFE_S),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "initial_count": DEFAULT_INITIAL_COUNT,
            "half_life_s": DEFAULT_HALF_LIFE_S,
        },
        input_fields=(
            "initial_count",
            "half_life_s",
            "time_s",
        ),
    )
)
