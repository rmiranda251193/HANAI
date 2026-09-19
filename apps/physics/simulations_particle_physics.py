"""Deterministic reference model for the Relativistic Energy and Momentum
lab.

The relativistic energy-momentum relation ties a particle's total energy
to its momentum and rest mass:

    E^2 = (pc)^2 + (mc^2)^2

Expressed entirely in energy units of MeV -- the natural units particle
physicists actually use for this, so a particle's momentum is quoted as
``pc`` (in MeV) and its rest mass as ``mc^2`` (in MeV) rather than raw
kilograms and kg m/s, which would make every everyday-sized number here
either astronomically small or need constant unit juggling. This is the
same "real quantity, the field's own natural unit" choice Ideal Gas Law
made for its gas constant R and Doppler Effect made for the speed of
sound, and the same MeV scale Bohr Model's ionization energy and this
project's Nuclear Physics binding-energy concept already use.

Two familiar special cases fall out of this one formula with no branching
at all:
  - at zero momentum, E = mc^2 exactly -- the particle's REST energy (the
    famous case of Einstein's mass-energy equivalence).
  - at very high momentum relative to mc^2 (an ultra-relativistic
    particle), E approaches pc -- the same relation a strictly massless
    particle would satisfy exactly.

Two derived quantities are reported alongside the total energy:
  - kinetic_energy_mev = E - mc^2 (always >= 0, exactly 0 only when the
    particle is at rest -- never negative, since E >= mc^2 always holds
    for real momentum and mass).
  - velocity_fraction_c = pc / E, the particle's speed as a fraction of
    the speed of light (beta). Because rest energy is required to be
    strictly positive here (see ``clamp_rest_energy``), E is always
    strictly greater than pc, so beta is ALWAYS strictly less than 1 --
    unlike Time Dilation, this lab never needs to explicitly reject an
    unreachable beta >= 1; it falls out of the formula automatically for
    every supported input.

This lab's default state is a genuine real-world example that connects
directly to the Time Dilation and Length Contraction lab: a muon (rest
energy 105.66 MeV, the real value) with momentum 200 MeV/c travels at
about 88% of the speed of light. Muons like this are created when cosmic
rays strike the upper atmosphere and, despite a rest-frame lifetime of
only about 2.2 microseconds, reach the ground in large numbers -- a
famous, historically important confirmation of relativistic time
dilation: without it, at 88% of c a muon's own decay would let very few
of them survive a trip of that length.

Like ``simulations_calorimetry.py``/``simulations_time_dilation.py``/
``simulations_hubbles_law.py``, there is no time axis and no sentinel-
value-plus-flag pair -- one formula, evaluated instantly, always
well-defined for any supported rest energy and momentum.

This module is the single source of truth for the mathematics, the
browser simulation in ``static/js/physics/particle-physics.js`` mirrors
it exactly for live interaction, and nothing here ever touches an AI
provider -- every value is computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds. Kept in sync with the JS module. The rest-energy range
# spans from below the electron (0.511 MeV) to above the proton (938.27
# MeV); the momentum range comfortably covers everyday particle-physics
# examples like the default muon below.
MIN_REST_ENERGY_MEV = 0.1
MAX_REST_ENERGY_MEV = 1000.0
MIN_MOMENTUM_MEV_C = 0.0
MAX_MOMENTUM_MEV_C = 2000.0

DEFAULT_REST_ENERGY_MEV = 105.66  # the real muon rest energy
DEFAULT_MOMENTUM_MEV_C = 200.0


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


def clamp_rest_energy(value) -> float:
    """Validate and clamp the rest energy mc^2. Non-positive is rejected
    outright: a massless particle is a genuinely different, degenerate
    case (E = pc exactly, beta = 1 exactly) that this lab does not model,
    the same way Time Dilation's proper length/time must be positive."""

    number = _as_float(value, "Rest energy")
    if number <= 0:
        raise SimulationError("Rest energy must be a positive number.")
    return max(MIN_REST_ENERGY_MEV, min(MAX_REST_ENERGY_MEV, number))


def clamp_momentum(value) -> float:
    """Validate and clamp the momentum pc. Zero is a valid, meaningful
    state (a particle at rest) -- only negative is rejected outright,
    since momentum here is a magnitude, not a signed component."""

    number = _as_float(value, "Momentum")
    if number < 0:
        raise SimulationError("Momentum cannot be negative.")
    return max(MIN_MOMENTUM_MEV_C, min(MAX_MOMENTUM_MEV_C, number))


def particle_physics_state(*, rest_energy_mev, momentum_mev_c) -> dict:
    """Return the total energy, kinetic energy and speed (as a fraction of
    c) of a particle with the given rest energy and momentum.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    mc2 = clamp_rest_energy(rest_energy_mev)
    pc = clamp_momentum(momentum_mev_c)

    total_energy_mev = math.sqrt(pc * pc + mc2 * mc2)
    kinetic_energy_mev = total_energy_mev - mc2
    velocity_fraction_c = pc / total_energy_mev

    return {
        "rest_energy_mev": mc2,
        "momentum_mev_c": pc,
        "total_energy_mev": total_energy_mev,
        "kinetic_energy_mev": kinetic_energy_mev,
        "velocity_fraction_c": velocity_fraction_c,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="particle_physics",
        template="physics/particle_physics.html",
        equations=("E^2 = (pc)^2 + (mc^2)^2", "beta = pc / E"),
        units={
            "rest_energy_mev": "MeV",
            "momentum_mev_c": "MeV/c",
            "total_energy_mev": "MeV",
            "kinetic_energy_mev": "MeV",
            "velocity_fraction_c": "",
        },
        bounds={
            "rest_energy_mev": (MIN_REST_ENERGY_MEV, MAX_REST_ENERGY_MEV),
            "momentum_mev_c": (MIN_MOMENTUM_MEV_C, MAX_MOMENTUM_MEV_C),
        },
        default_state={
            "rest_energy_mev": DEFAULT_REST_ENERGY_MEV,
            "momentum_mev_c": DEFAULT_MOMENTUM_MEV_C,
        },
        input_fields=(
            "rest_energy_mev",
            "momentum_mev_c",
        ),
    )
)
