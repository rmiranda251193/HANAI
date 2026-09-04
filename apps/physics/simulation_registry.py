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
"""

from __future__ import annotations

from dataclasses import dataclass


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


_REGISTRY: dict[str, SimulationDefinition] = {}


def register(definition: SimulationDefinition) -> None:
    _REGISTRY[definition.simulation_type] = definition


def get_simulation_definition(simulation_type: str) -> SimulationDefinition | None:
    return _REGISTRY.get(simulation_type)


def registered_simulation_types() -> tuple[str, ...]:
    """Deterministic (sorted) list of every registered simulation type."""

    return tuple(sorted(_REGISTRY))
