"""Deterministic reference model for the Hubble's Law lab.

Hubble's law: the recession speed of a distant galaxy is directly
proportional to its distance from us --

    v = H0 * d

where ``H0`` (the Hubble constant) is expressed in km/s/Mpc -- kilometres
per second of recession speed for every megaparsec of distance -- so ``v``
comes out directly in km/s when ``d`` is in Mpc, with no unit conversion
needed. This is the observational evidence that space itself is
expanding, first reported by Edwin Hubble in 1929.

The value of H0 is itself a live, unresolved measurement in cosmology --
different methods currently disagree (the "Hubble tension"), placing it
somewhere around 67-74 km/s/Mpc -- so this lab treats H0 as a genuine
adjustable measurement, not a fixed constant, with a default of 70
km/s/Mpc, the commonly cited round figure.

A second, derived quantity is reported alongside the recession speed: the
redshift z = v / c, the fractional stretch in a distant galaxy's light
that astronomers actually measure with a spectrograph (v is not observed
directly). Both distance and H0 stay in the non-relativistic regime this
lab restricts itself to (v well under c), where z = v/c is an accurate
approximation -- capping the distance at 200 Mpc keeps even the worst-case
corner (200 Mpc, H0 = 80 km/s/Mpc) at v = 16,000 km/s, only about 5% of c,
comfortably inside the "nearby universe" regime real Hubble-diagram
analyses restrict themselves to for exactly this reason. A much larger
distance bound (e.g. 5000 Mpc) would let v = H0 d exceed the speed of
light outright at the upper corner of the UI range -- not a bug in the
formula itself (recession from cosmic expansion is not a velocity through
space, so special relativity does not cap it), but a claim this
introductory lab deliberately does not make, so the input range is capped
to keep the "non-relativistic, z = v/c" framing honest everywhere the
sliders can reach.

Unlike most other labs so far, there is no sentinel-value-plus-flag pair
here: Hubble's law is a plain proportional relationship with no
physically impossible case to special-case for any of its supported
inputs -- distance and H0 are both always positive, so recession speed
and redshift are always positive and well-defined.

Like ``simulations_calorimetry.py``/``simulations_bohr_model.py``, there
is no time axis -- one formula, evaluated instantly for whichever distance
and Hubble constant are chosen.

This module is the single source of truth for the mathematics, the
browser simulation in ``static/js/physics/hubbles-law.js`` mirrors it
exactly for live interaction, and nothing here ever touches an AI
provider -- every value is computed from first principles.
"""

from __future__ import annotations

import math

SPEED_OF_LIGHT_KM_S = 299792.458

# UI-facing bounds. Kept in sync with the JS module. MAX_DISTANCE_MPC is
# deliberately capped well short of the ~4300 Mpc Hubble distance (c / H0)
# -- see the module docstring for why.
MIN_DISTANCE_MPC = 1.0
MAX_DISTANCE_MPC = 200.0
MIN_HUBBLE_CONSTANT_KM_S_MPC = 60.0
MAX_HUBBLE_CONSTANT_KM_S_MPC = 80.0

DEFAULT_DISTANCE_MPC = 100.0
DEFAULT_HUBBLE_CONSTANT_KM_S_MPC = 70.0


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


def clamp_distance(value) -> float:
    number = _as_float(value, "Distance")
    if number <= 0:
        raise SimulationError("Distance must be a positive number.")
    return max(MIN_DISTANCE_MPC, min(MAX_DISTANCE_MPC, number))


def clamp_hubble_constant(value) -> float:
    number = _as_float(value, "Hubble constant")
    if number <= 0:
        raise SimulationError("Hubble constant must be a positive number.")
    return max(MIN_HUBBLE_CONSTANT_KM_S_MPC, min(MAX_HUBBLE_CONSTANT_KM_S_MPC, number))


def hubbles_law_state(*, distance_mpc, hubble_constant_km_s_mpc) -> dict:
    """Return the recession speed and redshift of a galaxy at the given
    distance, for the given Hubble constant.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    d = clamp_distance(distance_mpc)
    h0 = clamp_hubble_constant(hubble_constant_km_s_mpc)

    recession_velocity_km_s = h0 * d
    redshift_z = recession_velocity_km_s / SPEED_OF_LIGHT_KM_S

    return {
        "distance_mpc": d,
        "hubble_constant_km_s_mpc": h0,
        "recession_velocity_km_s": recession_velocity_km_s,
        "redshift_z": redshift_z,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="hubbles_law",
        template="physics/hubbles_law.html",
        equations=("v = H0 d", "z = v / c"),
        units={
            "distance_mpc": "Mpc",
            "hubble_constant_km_s_mpc": "km/s/Mpc",
            "recession_velocity_km_s": "km/s",
            "redshift_z": "",
        },
        bounds={
            "distance_mpc": (MIN_DISTANCE_MPC, MAX_DISTANCE_MPC),
            "hubble_constant_km_s_mpc": (
                MIN_HUBBLE_CONSTANT_KM_S_MPC,
                MAX_HUBBLE_CONSTANT_KM_S_MPC,
            ),
        },
        default_state={
            "distance_mpc": DEFAULT_DISTANCE_MPC,
            "hubble_constant_km_s_mpc": DEFAULT_HUBBLE_CONSTANT_KM_S_MPC,
        },
        input_fields=(
            "distance_mpc",
            "hubble_constant_km_s_mpc",
        ),
    )
)
