"""Deterministic, idealized reference models for the Physics Lab.

This module is the single source of truth for the simulation mathematics. The
browser simulation in ``static/js/physics/`` mirrors it exactly. Nothing here
touches an AI provider -- every value is computed from first principles.

Newton's Second Law (idealized):

    a = F_net / m

with a constant net force, no friction and no air resistance. Motion is
integrated with a fixed educational timestep using simple (semi-implicit) Euler
steps -- good enough to *show* the force/mass/acceleration relationship, not a
high-fidelity dynamics engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# UI-facing bounds, in SI units. Kept in sync with the JS module.
MIN_MASS_KG = 0.1
MAX_MASS_KG = 20.0
MIN_FORCE_N = 0.0
MAX_FORCE_N = 50.0

DEFAULT_MASS_KG = 2.0
DEFAULT_FORCE_N = 10.0

# Fixed educational timestep (seconds of simulated time per integration step).
TIME_STEP_S = 0.05


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


def clamp_mass(mass_kg) -> float:
    """Validate and clamp a mass to the UI range. Zero or negative is rejected."""

    number = _as_float(mass_kg, "Mass")
    if number <= 0:
        raise SimulationError("Mass must be greater than zero (kg).")
    return max(MIN_MASS_KG, min(MAX_MASS_KG, number))


def clamp_force(force_n) -> float:
    """Validate and clamp a net force to the UI range. Zero is allowed."""

    number = _as_float(force_n, "Force")
    return max(MIN_FORCE_N, min(MAX_FORCE_N, number))


def newtons_second_law_acceleration(force_n, mass_kg) -> float:
    """Return a = F / m in m/s^2 after clamping inputs to the valid UI range."""

    return clamp_force(force_n) / clamp_mass(mass_kg)


@dataclass
class NewtonsSecondLawSimulation:
    """Client-mirroring simulation surface: set_mass / set_force / start / pause /
    reset / step / state.

    ``position_m`` and ``velocity_ms`` describe one-dimensional motion of an
    object under a constant net force, starting from rest.
    """

    mass_kg: float = DEFAULT_MASS_KG
    force_n: float = DEFAULT_FORCE_N
    time_s: float = 0.0
    velocity_ms: float = 0.0
    position_m: float = 0.0
    running: bool = False
    trace: list = field(default_factory=list)  # [(t, v), ...] for the graph

    def __post_init__(self):
        self.mass_kg = clamp_mass(self.mass_kg)
        self.force_n = clamp_force(self.force_n)
        self._record_trace()

    # -- controls -------------------------------------------------------------

    def set_mass(self, mass_kg) -> float:
        self.mass_kg = clamp_mass(mass_kg)
        return self.mass_kg

    def set_force(self, force_n) -> float:
        self.force_n = clamp_force(force_n)
        return self.force_n

    def start(self) -> None:
        self.running = True

    def pause(self) -> None:
        self.running = False

    def reset(self) -> None:
        """Return motion to the initial at-rest state, keeping mass and force."""

        self.time_s = 0.0
        self.velocity_ms = 0.0
        self.position_m = 0.0
        self.running = False
        self.trace = []
        self._record_trace()

    # -- integration --------------------------------------------------------

    @property
    def acceleration_ms2(self) -> float:
        return newtons_second_law_acceleration(self.force_n, self.mass_kg)

    def step(self, dt: float = TIME_STEP_S) -> "NewtonsSecondLawSimulation":
        """Advance simulated time by ``dt`` seconds (semi-implicit Euler)."""

        if dt <= 0:
            raise SimulationError("Timestep must be positive.")
        acceleration = self.acceleration_ms2
        self.velocity_ms += acceleration * dt
        self.position_m += self.velocity_ms * dt
        self.time_s += dt
        self._record_trace()
        return self

    def _record_trace(self) -> None:
        self.trace.append((round(self.time_s, 4), round(self.velocity_ms, 4)))

    # -- inspection -------------------------------------------------------

    def state(self) -> dict:
        return {
            "mass_kg": self.mass_kg,
            "force_n": self.force_n,
            "acceleration_ms2": self.acceleration_ms2,
            "time_s": self.time_s,
            "velocity_ms": self.velocity_ms,
            "position_m": self.position_m,
            "running": self.running,
        }


def make_initial_state(
    mass_kg: float = DEFAULT_MASS_KG, force_n: float = DEFAULT_FORCE_N
) -> NewtonsSecondLawSimulation:
    return NewtonsSecondLawSimulation(mass_kg=mass_kg, force_n=force_n)
