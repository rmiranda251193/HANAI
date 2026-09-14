"""Deterministic reference model for the Photoelectric Effect lab.

Light of wavelength ``wavelength_nm`` strikes a metal with work function
``work_function_ev`` (the minimum energy needed to eject an electron from
that particular metal). Einstein's photoelectric equation:

    E_photon = h f                        (energy of one photon)
    KE_max = E_photon - phi = h f - phi    (maximum kinetic energy of an
                                             ejected electron)

using the real speed of light c = 3e8 m/s (f = c / wavelength) and the real
Planck's constant, expressed in electron-volt-seconds (h = 4.135667696e-15
eV*s -- the natural unit at this energy scale, the same "real constant, in
the domain's natural unit" choice ``simulations_ideal_gas_law.py`` made
with R and ``simulations_doppler_effect.py`` made with the speed of sound).

Below the metal's threshold frequency (equivalently, above its threshold
wavelength), E_photon < phi and NO electrons are ejected at all --
regardless of how intense the light is. This is the exact, genuinely
counter-intuitive fact the seeded "The photoelectric effect" concept names
as its own misconception target: "believing that brighter (more intense)
light alone ... should always be able to eject electrons". This module
models that directly: ``intensity`` only scales how many electrons are
ejected per second (via ``photoelectron_rate``) when ejection is already
happening -- it has ZERO effect on ``ke_max_ev``, and produces exactly zero
electrons, at any intensity, below the threshold.

When E_photon < phi, KE_max would be mathematically negative -- but a
negative kinetic energy isn't a real physical result, it just means no
ejection happens. This module reports ``ke_max_ev = 0.0`` together with
``ejects_electrons = False`` in that case (never interpret the 0.0 alone as
"an electron was ejected with zero energy" -- always check the flag first,
the same convention ``simulations_coulombs_law.py``'s zero-force/
``is_attractive`` pair and ``simulations_refraction.py``'s zero-angle/
``total_internal_reflection`` pair use).

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/photoelectric-effect.js`` mirrors it
exactly for live interaction, and nothing here ever touches an AI provider
-- every value is computed from first principles.
"""

from __future__ import annotations

import math

SPEED_OF_LIGHT_M_S = 3.0e8
PLANCK_CONSTANT_EV_S = 4.135667696e-15

# UI-facing bounds. Kept in sync with the JS module.
MIN_WAVELENGTH_NM = 100.0
MAX_WAVELENGTH_NM = 700.0
MIN_WORK_FUNCTION_EV = 1.0
MAX_WORK_FUNCTION_EV = 6.0
MIN_INTENSITY = 1.0
MAX_INTENSITY = 10.0

DEFAULT_WAVELENGTH_NM = 400.0
DEFAULT_WORK_FUNCTION_EV = 2.3  # sodium-like
DEFAULT_INTENSITY = 5.0


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


def clamp_wavelength(value) -> float:
    """Validate and clamp the light's wavelength. Non-positive is rejected
    outright."""

    number = _as_float(value, "Wavelength")
    if number <= 0:
        raise SimulationError("Wavelength must be positive.")
    return max(MIN_WAVELENGTH_NM, min(MAX_WAVELENGTH_NM, number))


def clamp_work_function(value) -> float:
    """Validate and clamp the metal's work function. Non-positive is
    rejected outright -- every real metal needs positive energy to release
    an electron."""

    number = _as_float(value, "Work function")
    if number <= 0:
        raise SimulationError("Work function must be positive.")
    return max(MIN_WORK_FUNCTION_EV, min(MAX_WORK_FUNCTION_EV, number))


def clamp_intensity(value) -> float:
    """Validate and clamp the light's (relative) intensity. Non-positive is
    rejected outright."""

    number = _as_float(value, "Intensity")
    if number <= 0:
        raise SimulationError("Intensity must be positive.")
    return max(MIN_INTENSITY, min(MAX_INTENSITY, number))


def photoelectric_effect_state(*, wavelength_nm, work_function_ev, intensity) -> dict:
    """Return the photon energy, maximum ejected-electron kinetic energy
    and photoelectron rate for light of the given wavelength hitting a
    metal of the given work function.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    wavelength = clamp_wavelength(wavelength_nm)
    phi = clamp_work_function(work_function_ev)
    intensity_c = clamp_intensity(intensity)

    frequency_hz = SPEED_OF_LIGHT_M_S / (wavelength * 1e-9)
    photon_energy_ev = PLANCK_CONSTANT_EV_S * frequency_hz
    ke_max_raw_ev = photon_energy_ev - phi
    ejects_electrons = ke_max_raw_ev > 0
    ke_max_ev = max(0.0, ke_max_raw_ev)
    photoelectron_rate = intensity_c if ejects_electrons else 0.0

    threshold_frequency_hz = phi / PLANCK_CONSTANT_EV_S
    threshold_wavelength_nm = (SPEED_OF_LIGHT_M_S / threshold_frequency_hz) * 1e9

    return {
        "wavelength_nm": wavelength,
        "work_function_ev": phi,
        "intensity": intensity_c,
        "frequency_hz": frequency_hz,
        "photon_energy_ev": photon_energy_ev,
        "ejects_electrons": ejects_electrons,
        "ke_max_ev": ke_max_ev,
        "photoelectron_rate": photoelectron_rate,
        "threshold_wavelength_nm": threshold_wavelength_nm,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="photoelectric_effect",
        template="physics/photoelectric_effect.html",
        equations=("E_photon = h f", "KE_max = h f - phi"),
        units={
            "wavelength_nm": "nm",
            "work_function_ev": "eV",
            "intensity": "",
            "frequency_hz": "Hz",
            "photon_energy_ev": "eV",
            "ke_max_ev": "eV",
            "photoelectron_rate": "",
            "threshold_wavelength_nm": "nm",
        },
        bounds={
            "wavelength_nm": (MIN_WAVELENGTH_NM, MAX_WAVELENGTH_NM),
            "work_function_ev": (MIN_WORK_FUNCTION_EV, MAX_WORK_FUNCTION_EV),
            "intensity": (MIN_INTENSITY, MAX_INTENSITY),
        },
        default_state={
            "wavelength_nm": DEFAULT_WAVELENGTH_NM,
            "work_function_ev": DEFAULT_WORK_FUNCTION_EV,
            "intensity": DEFAULT_INTENSITY,
        },
        input_fields=(
            "wavelength_nm",
            "work_function_ev",
            "intensity",
        ),
    )
)
