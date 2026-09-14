"""Deterministic reference model for the Coulomb's Law lab.

Two point charges, ``charge1`` and ``charge2`` (signed, in microcoulombs),
separated by a fixed distance ``separation``. Like ``simulations_circuits.py``,
there is no time axis: with fixed charges at a fixed separation the force is
constant, so "at time t" is not a meaningful question here either.

    F = k * |q1 * q2| / r^2      (force magnitude, always >= 0)
    U = k * q1 * q2 / r          (potential energy -- genuinely SIGNED:
                                   negative when the charges attract,
                                   positive when they repel, unlike
                                   gravitational PE which is always negative)
    E1_at_2 = k * |q1| / r^2     (field from charge 1, at charge 2's location)
    E2_at_1 = k * |q2| / r^2     (field from charge 2, at charge 1's location)

The interaction is attractive when the charges have opposite signs and
repulsive when they have the same sign (q1*q2 < 0 and > 0 respectively) --
unlike ``simulations_orbital_motion.py``'s gravity, which is ALWAYS
attractive. This is the one genuine physics difference this module exists to
show, so charge inputs are deliberately allowed to be negative or exactly
zero (a neutral "charge" with zero force is a physically real, valid case)
-- only the separation must be strictly positive (division by zero).

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/coulombs-law.js`` mirrors it exactly for
live interaction, and nothing here ever touches an AI provider -- every
value is computed from first principles.
"""

from __future__ import annotations

import math

# Coulomb's constant, in N*m^2/C^2 (the real physical constant -- not scaled,
# unlike Orbital Motion's friendly "mu"; microcoulomb-scale charges at
# metre-scale separations already land in a readable force range).
COULOMB_K = 8.99e9

# UI-facing bounds, in SI-shaped units (charge in microcoulombs). Kept in
# sync with the JS module.
MIN_CHARGE_UC = -8.0
MAX_CHARGE_UC = 8.0
MIN_SEPARATION_M = 0.1
MAX_SEPARATION_M = 5.0

DEFAULT_CHARGE1_UC = 3.0
DEFAULT_CHARGE2_UC = -2.0  # opposite signs by default -- attraction, the
                            # one behaviour gravity can never show
DEFAULT_SEPARATION_M = 1.0


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


def clamp_charge(value) -> float:
    """Validate and clamp a charge, in microcoulombs. Zero and negative
    values are physically valid (a neutral charge, or the opposite sign) --
    only non-finite/non-numeric input is rejected."""

    number = _as_float(value, "Charge")
    return max(MIN_CHARGE_UC, min(MAX_CHARGE_UC, number))


def clamp_separation(value) -> float:
    """Validate and clamp the separation. Non-positive is rejected outright
    -- two point charges cannot occupy the same point (division by zero)."""

    number = _as_float(value, "Separation")
    if number <= 0:
        raise SimulationError("Separation must be positive.")
    return max(MIN_SEPARATION_M, min(MAX_SEPARATION_M, number))


def coulombs_law_state(*, charge1, charge2, separation) -> dict:
    """Return the force, potential energy and field values for two point
    charges at a fixed separation.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    q1_uc = clamp_charge(charge1)
    q2_uc = clamp_charge(charge2)
    r = clamp_separation(separation)

    q1_c = q1_uc * 1e-6
    q2_c = q2_uc * 1e-6

    force_n = COULOMB_K * abs(q1_c * q2_c) / (r ** 2)
    potential_energy_j = COULOMB_K * q1_c * q2_c / r
    is_attractive = (q1_c * q2_c) < 0
    field_1_at_2_n_per_c = COULOMB_K * abs(q1_c) / (r ** 2)
    field_2_at_1_n_per_c = COULOMB_K * abs(q2_c) / (r ** 2)

    return {
        "charge1_uc": q1_uc,
        "charge2_uc": q2_uc,
        "separation_m": r,
        "force_n": force_n,
        "is_attractive": is_attractive,
        "potential_energy_j": potential_energy_j,
        "field_1_at_2_n_per_c": field_1_at_2_n_per_c,
        "field_2_at_1_n_per_c": field_2_at_1_n_per_c,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="coulombs_law",
        template="physics/coulombs_law.html",
        equations=(
            "F = k |q1 q2| / r^2",
            "U = k q1 q2 / r  (signed: negative = attraction, positive = repulsion)",
        ),
        units={
            "charge1_uc": "µC",
            "charge2_uc": "µC",
            "separation_m": "m",
            "force_n": "N",
            "potential_energy_j": "J",
            "field_1_at_2_n_per_c": "N/C",
            "field_2_at_1_n_per_c": "N/C",
        },
        bounds={
            "charge1_uc": (MIN_CHARGE_UC, MAX_CHARGE_UC),
            "charge2_uc": (MIN_CHARGE_UC, MAX_CHARGE_UC),
            "separation_m": (MIN_SEPARATION_M, MAX_SEPARATION_M),
        },
        default_state={
            "charge1_uc": DEFAULT_CHARGE1_UC,
            "charge2_uc": DEFAULT_CHARGE2_UC,
            "separation_m": DEFAULT_SEPARATION_M,
        },
        input_fields=(
            "charge1_uc",
            "charge2_uc",
            "separation_m",
        ),
    )
)
