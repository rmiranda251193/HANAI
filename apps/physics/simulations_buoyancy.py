"""Deterministic reference model for the Buoyancy lab.

A solid object of density ``object_density``, volume ``volume``, submerged
fully or partly in a fluid of density ``fluid_density``. Archimedes'
principle: the buoyant force equals the weight of the fluid the object
displaces. Like ``simulations_circuits.py`` and ``simulations_coulombs_law.py``,
there is no time axis -- an object released in a fluid reaches its floating
equilibrium (or keeps sinking) essentially at once at this idealized level,
so "at time t" is not the question this lab asks.

    weight = object_density * volume * g
    max_buoyant_force = fluid_density * volume * g   (buoyant force if the
                                                        object were FULLY
                                                        submerged)

Whether the object floats or sinks depends only on how its DENSITY compares
to the fluid's -- not its absolute weight, size or mass (the exact
misconception the seeded "Archimedes' principle and buoyancy" concept
names: "believing heavier objects always sink ... rather than it depending
on density relative to the fluid"). A large, heavy, low-density object
(a foam block) floats; a small, light, high-density object (a pebble)
sinks -- this module's tests verify that directly, not just the formula.

    floats (object_density <= fluid_density):
        submerged_fraction = object_density / fluid_density
        buoyant_force = weight            (equilibrium: buoyant force
                                             exactly balances weight)
        net_force = 0

    sinks (object_density > fluid_density):
        submerged_fraction = 1.0          (fully submerged)
        buoyant_force = max_buoyant_force (less than the weight)
        net_force = weight - max_buoyant_force   (net downward force --
                                                    the object keeps sinking)

This module is the single source of truth for the mathematics, the browser
simulation in ``static/js/physics/buoyancy.js`` mirrors it exactly for live
interaction, and nothing here ever touches an AI provider -- every value is
computed from first principles.
"""

from __future__ import annotations

import math

GRAVITY_MS2 = 9.8

# UI-facing bounds, in SI units. Kept in sync with the JS module. The same
# bounds apply to both object and fluid density -- either can be the denser
# one, which is the whole point of the lab.
MIN_DENSITY_KG_M3 = 100.0
MAX_DENSITY_KG_M3 = 12000.0
MIN_VOLUME_M3 = 0.001
MAX_VOLUME_M3 = 1.0

DEFAULT_OBJECT_DENSITY_KG_M3 = 600.0  # wood-like -- floats in water
DEFAULT_FLUID_DENSITY_KG_M3 = 1000.0  # water
DEFAULT_VOLUME_M3 = 0.05


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


def clamp_density(value) -> float:
    """Validate and clamp a density. Non-positive is rejected outright --
    zero or negative density/mass is not a real material."""

    number = _as_float(value, "Density")
    if number <= 0:
        raise SimulationError("Density must be positive.")
    return max(MIN_DENSITY_KG_M3, min(MAX_DENSITY_KG_M3, number))


def clamp_volume(value) -> float:
    """Validate and clamp the object's volume. Non-positive is rejected
    outright -- an object must take up some space."""

    number = _as_float(value, "Volume")
    if number <= 0:
        raise SimulationError("Volume must be positive.")
    return max(MIN_VOLUME_M3, min(MAX_VOLUME_M3, number))


def buoyancy_state(*, object_density, fluid_density, volume) -> dict:
    """Return the weight, buoyant force, submerged fraction and net force
    for an object of the given density and volume in a fluid of the given
    density.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    rho_object = clamp_density(object_density)
    rho_fluid = clamp_density(fluid_density)
    v = clamp_volume(volume)

    weight = rho_object * v * GRAVITY_MS2
    max_buoyant_force = rho_fluid * v * GRAVITY_MS2
    floats = weight <= max_buoyant_force

    if floats:
        submerged_fraction = rho_object / rho_fluid
        buoyant_force = weight
        net_force = 0.0
    else:
        submerged_fraction = 1.0
        buoyant_force = max_buoyant_force
        net_force = weight - max_buoyant_force

    return {
        "object_density_kg_m3": rho_object,
        "fluid_density_kg_m3": rho_fluid,
        "volume_m3": v,
        "weight_n": weight,
        "max_buoyant_force_n": max_buoyant_force,
        "buoyant_force_n": buoyant_force,
        "submerged_fraction": submerged_fraction,
        "floats": floats,
        "net_force_n": net_force,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="buoyancy",
        template="physics/buoyancy.html",
        equations=(
            "F_b = rho_fluid * V * g  (buoyant force, if fully submerged)",
            "floats when rho_object <= rho_fluid, regardless of weight or size",
        ),
        units={
            "object_density_kg_m3": "kg/m³",
            "fluid_density_kg_m3": "kg/m³",
            "volume_m3": "m³",
            "weight_n": "N",
            "buoyant_force_n": "N",
            "net_force_n": "N",
        },
        bounds={
            "object_density_kg_m3": (MIN_DENSITY_KG_M3, MAX_DENSITY_KG_M3),
            "fluid_density_kg_m3": (MIN_DENSITY_KG_M3, MAX_DENSITY_KG_M3),
            "volume_m3": (MIN_VOLUME_M3, MAX_VOLUME_M3),
        },
        default_state={
            "object_density_kg_m3": DEFAULT_OBJECT_DENSITY_KG_M3,
            "fluid_density_kg_m3": DEFAULT_FLUID_DENSITY_KG_M3,
            "volume_m3": DEFAULT_VOLUME_M3,
        },
        input_fields=(
            "object_density_kg_m3",
            "fluid_density_kg_m3",
            "volume_m3",
        ),
    )
)
