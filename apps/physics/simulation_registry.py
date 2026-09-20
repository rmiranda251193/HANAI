"""Deterministic registry of Physics Lab simulation definitions.

Maps ``PhysicsSimulation.simulation_type`` to the metadata the rest of the app
needs to render that simulation type generically: which template to use,
its equations/units for display, its input bounds, and its default state.

This is a plain Python dict populated at import time by each simulation's own
module (``apps/physics/simulations.py`` for Newton's Second Law,
``apps/physics/simulations_kinematics.py`` for Kinematics) calling
``register(...)`` -- the same pattern the browser side uses
(``PhysicsLab.register("newtons_second_law", factory)`` in
``static/js/physics/lab.js``). Nothing here is ever evaluated as code or run
dynamically: a new simulation type is added by writing a new Python module
(server-side validation/calculation) and a new JS module (browser
rendering), not by storing an expression in the database.

Deterministic validation and persistence (turning a raw submission into a
trusted, saved ``ExperimentAttempt``) is NOT part of this registry -- that
stays in ``apps.students.experiment_services``, which owns the
``ExperimentAttempt`` model. This module only answers "what does this
simulation look like", never "what did the student do".

``ScenarioCapability`` (optional, on ``SimulationDefinition.scenario``) is
what lets a simulation type participate in Teacher Scenario Studio and the
deterministic scenario checker (``apps.physics.lab_scenarios``) -- see that
module's docstring. A simulation declares its own authoritative state
calculation and the observable quantities a scenario may target; Scenario
Studio never hard-codes a per-topic branch to find out whether a simulation
supports scenarios, it just asks the definition (``is_scenario_capable`` /
``scenario_capable_simulation_types``). A simulation with no
``ScenarioCapability`` is simply not offered there -- everything else about
it (rendering, Predict/Observe/Explain) is completely unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScenarioCapability:
    """Declares how a simulation type participates in the one deterministic
    scenario checker (``apps.physics.lab_scenarios.evaluate_scenario``).

    ``observable_fields``: the state-field names a target condition may name
    for this simulation type -- e.g. Kinematics exposes
    ``{"position_m", "velocity_m_s", "acceleration_m_s2"}``. This is the
    authoritative allow-list ``TargetCondition`` itself validates against;
    there is no separate, hand-copied list anywhere else.

    ``state_at``: ``(parameters: dict, at_time_s: float) -> dict[str, float]``.
    The authoritative, deterministic reconstruction of this simulation's
    observable state, given raw submitted-or-stored parameter values (keyed
    by this simulation's own ``input_fields``) and a target time. Every
    value must be clamped to this simulation's own supported range *inside*
    this function -- the one place a forged value gets neutralised, so a
    submitted ``9e99`` can never pass a check by overflowing anything.

    ``supports_reverses`` / ``reverses_at``: optional -- only a simulation
    whose motion can meaningfully reverse direction (a state field can go
    negative) implements this pair; see ``lab_scenarios.allowed_target_kinds``.
    """

    observable_fields: frozenset[str]
    state_at: Callable[[dict, float], dict]
    supports_reverses: bool = False
    reverses_at: Callable[[dict], tuple[bool, str]] | None = None


@dataclass(frozen=True)
class SimulationDefinition:
    """Everything the Lab view needs to render one simulation type generically."""

    simulation_type: str
    template: str
    equations: tuple[str, ...]
    units: dict[str, str]
    bounds: dict[str, tuple[float, float]]
    default_state: dict[str, float]
    # POST field names this simulation's Observe/Explain step expects, e.g.
    # ("mass_kg", "force_n") or ("initial_position_m", ...). Lets the view pull
    # exactly the right values out of request.POST without knowing what a
    # simulation type "is" -- see apps/physics/views.py.
    input_fields: tuple[str, ...]
    #: Optional -- present only for a simulation that participates in
    #: Teacher Scenario Studio / the deterministic scenario checker.
    scenario: ScenarioCapability | None = None


_REGISTRY: dict[str, SimulationDefinition] = {}


def register(definition: SimulationDefinition) -> None:
    _REGISTRY[definition.simulation_type] = definition


def unregister(simulation_type: str) -> None:
    """Remove a registration. Only meant for test isolation -- a test that
    registers a throwaway simulation definition to prove the generic
    contract (see ``apps.physics.tests_scenario_platform``) uses this so the
    registration never leaks into another test."""

    _REGISTRY.pop(simulation_type, None)


def get_simulation_definition(simulation_type: str) -> SimulationDefinition | None:
    return _REGISTRY.get(simulation_type)


def registered_simulation_types() -> tuple[str, ...]:
    """Deterministic (sorted) list of every registered simulation type."""

    return tuple(sorted(_REGISTRY))


def is_scenario_capable(simulation_type: str) -> bool:
    definition = get_simulation_definition(simulation_type)
    return definition is not None and definition.scenario is not None


def scenario_capable_simulation_types() -> frozenset[str]:
    """Every registered simulation type that declares a ``ScenarioCapability``
    -- the single source of truth Teacher Scenario Studio uses to decide
    which simulations are selectable, so it never hard-codes a per-topic
    ``if simulation_type == "..."`` branch."""

    return frozenset(t for t, d in _REGISTRY.items() if d.scenario is not None)
