"""Deterministic reference model for the Bohr Model lab.

The Bohr model of hydrogen: an electron can only occupy specific, quantised
energy levels, numbered n = 1, 2, 3, ...:

    E_n = -13.6 eV / n^2       (13.6 eV -- the real ionization energy of
                                 hydrogen, i.e. -E_1)

A transition between an initial level ``initial_level`` and a final level
``final_level`` absorbs or emits a photon whose energy exactly matches the
gap between them:

    E_photon = |E_final - E_initial|
    wavelength = (h c) / E_photon    (h*c = 1239.84 eV*nm -- the real
                                       Planck's-constant-times-speed-of-
                                       light product, expressed in these
                                       units, the same "real constant,
                                       domain's natural unit" choice
                                       ``simulations_photoelectric_effect.py``
                                       makes)

The electron ABSORBS a photon when jumping to a higher level (final_level >
initial_level) and EMITS one when falling to a lower level (final_level <
initial_level) -- represented here as ``is_absorption``. When
initial_level equals final_level, there is no transition at all: photon
energy is exactly zero and no wavelength is defined. This module reports
``wavelength_nm = 0.0`` together with ``has_transition = False`` in that
case (never interpret the 0.0 alone as "an infinitely energetic photon" --
always check the flag first, the same convention
``simulations_coulombs_law.py``'s zero-force/``is_attractive`` pair and
``simulations_refraction.py``'s zero-angle/``total_internal_reflection``
pair use).

The default state (initial_level=3, final_level=2) is a genuine, famous,
independently-checkable real-world value: the Balmer-series H-alpha line
at 656.3 nm, the red line visible in hydrogen's emission spectrum.

Like ``simulations_calorimetry.py``/``simulations_ideal_gas_law.py``, there
is no time axis -- one formula, evaluated instantly for whichever two
levels are chosen.

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/bohr-model.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

RYDBERG_ENERGY_EV = 13.6
HC_EV_NM = 1239.84

# UI-facing bounds. Kept in sync with the JS module. Levels are treated as
# integers -- see clamp_level for why non-integer input is rejected.
MIN_LEVEL = 1
MAX_LEVEL = 6

DEFAULT_INITIAL_LEVEL = 3
DEFAULT_FINAL_LEVEL = 2  # -> the real Balmer-series H-alpha line, 656.3 nm


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


def clamp_level(value) -> int:
    """Validate and clamp a quantum energy level. Energy levels are
    discrete integers by definition -- rounds to the nearest one, then
    clamps to the supported range. Non-positive is rejected outright: n=0
    or below has no meaning in this model."""

    number = _as_float(value, "Energy level")
    if number <= 0:
        raise SimulationError("Energy level must be a positive integer.")
    rounded = round(number)
    return int(max(MIN_LEVEL, min(MAX_LEVEL, rounded)))


def bohr_model_state(*, initial_level, final_level) -> dict:
    """Return the energy levels, photon energy and wavelength for a
    transition between two quantum levels of hydrogen.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    n1 = clamp_level(initial_level)
    n2 = clamp_level(final_level)

    energy_initial_ev = -RYDBERG_ENERGY_EV / (n1 ** 2)
    energy_final_ev = -RYDBERG_ENERGY_EV / (n2 ** 2)
    photon_energy_ev = abs(energy_final_ev - energy_initial_ev)
    has_transition = n1 != n2
    is_absorption = n2 > n1

    wavelength_nm = (HC_EV_NM / photon_energy_ev) if has_transition else 0.0

    return {
        "initial_level": n1,
        "final_level": n2,
        "energy_initial_ev": energy_initial_ev,
        "energy_final_ev": energy_final_ev,
        "photon_energy_ev": photon_energy_ev,
        "has_transition": has_transition,
        "is_absorption": is_absorption,
        "wavelength_nm": wavelength_nm,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="bohr_model",
        template="physics/bohr_model.html",
        equations=("E_n = -13.6 eV / n^2", "E_photon = |E_final - E_initial|"),
        units={
            "initial_level": "",
            "final_level": "",
            "energy_initial_ev": "eV",
            "energy_final_ev": "eV",
            "photon_energy_ev": "eV",
            "wavelength_nm": "nm",
        },
        bounds={
            "initial_level": (MIN_LEVEL, MAX_LEVEL),
            "final_level": (MIN_LEVEL, MAX_LEVEL),
        },
        default_state={
            "initial_level": DEFAULT_INITIAL_LEVEL,
            "final_level": DEFAULT_FINAL_LEVEL,
        },
        input_fields=(
            "initial_level",
            "final_level",
        ),
    )
)
