"""The one generic, deterministic Physics Lab scenario checker -- built-in
scenarios below, and teacher-authored ones
(``apps.physics.models.PhysicsScenario``, via
``apps.physics.scenario_services.to_lab_scenario``) converted into this exact
same shape on the fly.

A scenario is a small **structured description** of a goal ("make the cart reach
~20 m at t = 4 s"). It contains no code and no expressions -- only validated
data. ``evaluate_scenario`` reconstructs the relevant state on the server using
the *selected simulation's own* authoritative, deterministic calculation
(``apps.physics.simulation_registry.ScenarioCapability.state_at``) and checks
the target with a documented tolerance. Nothing here persists anything: the
durable learning evidence for a challenge is the explanation the student
submits through the normal Explain step (teacher-authored scenarios
additionally get a compact LearningEvidence row per check -- see
``scenario_services.record_scenario_check`` -- reusing the existing evidence
model, not a second one).

This module owns exactly one thing: the closed, code-reviewed allow-list of
*target condition kinds* (``value``/``greater_than``/``less_than``/
``within_range``/``reverses``) and the one ``evaluate_scenario`` function that
checks them. It does NOT own any simulation's Physics -- that stays in each
simulation's own module (``simulations_kinematics.py``, ``simulations.py``,
...), which registers a ``ScenarioCapability`` declaring its own observable
quantities and its own authoritative state calculation (see
``apps.physics.simulation_registry``). Adding a new scenario-capable
simulation therefore never touches this module, Teacher Scenario Studio, or
the checker -- it is entirely a matter of that simulation registering its own
capability, the "grown one at a time" discipline
``hands_on_experiments.py``/``depth_layers.py`` already use for other catalogs.

Teacher-authored scenarios and the two built-in scenarios below use identical
semantics: both become the same ``LabScenario`` shape, and both are graded by
the exact same ``evaluate_scenario`` call.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass

from .simulation_registry import get_simulation_definition

# The only condition kinds the checker understands. A closed set, checked in one
# place -- never extended by data or by the client.
_KIND_VALUE = "value"                # a named state field is within tolerance of a target
_KIND_GREATER_THAN = "greater_than"  # a named state field exceeds a threshold
_KIND_LESS_THAN = "less_than"        # a named state field is below a threshold
_KIND_WITHIN_RANGE = "within_range"  # a named state field falls in [range_min, range_max]
_KIND_REVERSES = "reverses"          # starts forward, decelerates, stops, then reverses
_ALLOWED_KINDS = frozenset(
    {_KIND_VALUE, _KIND_GREATER_THAN, _KIND_LESS_THAN, _KIND_WITHIN_RANGE, _KIND_REVERSES}
)
_FIELD_KINDS = frozenset({_KIND_VALUE, _KIND_GREATER_THAN, _KIND_LESS_THAN, _KIND_WITHIN_RANGE})
_RANGE_KINDS = frozenset({_KIND_WITHIN_RANGE})


def value_fields_for(simulation_type) -> frozenset[str]:
    """The state fields a target condition may name for this simulation
    type -- read straight from that simulation's own registered
    ``ScenarioCapability``, never a hand-copied list. Empty for a simulation
    type that is not registered, or not scenario-capable at all."""

    definition = get_simulation_definition(simulation_type)
    if definition is None or definition.scenario is None:
        return frozenset()
    return definition.scenario.observable_fields


def allowed_target_kinds(simulation_type: str = "") -> frozenset[str]:
    """The target kinds usable for this simulation type. "Reverses direction"
    is only offered when that simulation's own ``ScenarioCapability`` sets
    ``supports_reverses=True``; every other kind (equals / greater than /
    less than / within a range) applies to any scenario-capable simulation."""

    definition = get_simulation_definition(simulation_type)
    if definition is not None and definition.scenario is not None and definition.scenario.supports_reverses:
        return _ALLOWED_KINDS
    return _FIELD_KINDS


@dataclass(frozen=True)
class TargetCondition:
    kind: str
    description: str
    field: str = ""
    at_time_s: float = 0.0
    target: float = 0.0
    tolerance: float = 0.0
    range_min: float = 0.0
    range_max: float = 0.0
    #: Which simulation type this condition was validated for -- required at
    #: construction so ``field`` is checked against *that* simulation's own
    #: observable fields, never a stale global list. Not stored on the
    #: instance (a scenario's Physics identity already lives on
    #: ``PhysicsScenario.simulation``); this is validation-only.
    simulation_type: InitVar[str] = None

    def __post_init__(self, simulation_type: str | None):
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unknown target kind {self.kind!r}.")
        if simulation_type is None:
            raise ValueError("simulation_type is required to validate a target condition.")
        if self.kind in _FIELD_KINDS and self.field not in value_fields_for(simulation_type):
            raise ValueError(f"Unknown target field {self.field!r} for {simulation_type!r}.")
        if self.kind == _KIND_REVERSES and self.kind not in allowed_target_kinds(simulation_type):
            raise ValueError(f"{simulation_type!r} does not support the 'reverses' condition.")
        if self.kind in _RANGE_KINDS and self.range_min > self.range_max:
            raise ValueError("range_min cannot be greater than range_max.")


@dataclass(frozen=True)
class LabScenario:
    scenario_id: str
    title: str
    description: str
    simulation_type: str
    editable: tuple[str, ...]
    fixed: dict
    targets: tuple[TargetCondition, ...]
    teacher_message: str = ""

    @property
    def as_client_dict(self) -> dict:
        """Student-safe description for the page. No tolerances-as-cheat-sheet."""

        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "editable": list(self.editable),
            "fixed": dict(self.fixed),
            "goals": [t.description for t in self.targets],
        }


_SCENARIOS: dict[str, LabScenario] = {}

#: Public: the ``scenario_id`` prefix that marks a teacher-authored (DB-backed)
#: scenario, as opposed to one of the code-defined ones registered below.
TEACHER_SCENARIO_PREFIX = "teacher-"
_TEACHER_PREFIX = TEACHER_SCENARIO_PREFIX


def _register(scenario: LabScenario) -> None:
    _SCENARIOS[scenario.scenario_id] = scenario


def to_lab_scenario(scenario) -> LabScenario:
    """Convert one ``apps.physics.models.PhysicsScenario`` row into exactly
    the same ``LabScenario`` shape the built-in challenges use below, so
    ``evaluate_scenario`` (and everything else in this module) treats a
    teacher-authored scenario identically to a code-defined one. Raises
    ``ValueError``/``TypeError`` for a malformed ``target_condition`` --
    callers treat that as "not available", never a 500."""

    from .simulation_registry import get_simulation_definition

    definition = get_simulation_definition(scenario.simulation.simulation_type)
    editable = tuple(definition.input_fields) if definition is not None else ()
    return LabScenario(
        scenario_id=f"{_TEACHER_PREFIX}{scenario.slug}",
        title=scenario.title,
        description=scenario.instructions,
        simulation_type=scenario.simulation.simulation_type,
        editable=editable,
        fixed={},
        targets=(
            TargetCondition(
                simulation_type=scenario.simulation.simulation_type,
                **scenario.target_condition,
            ),
        ),
        teacher_message=scenario.reflection_prompt,
    )


def get_scenario(scenario_id) -> LabScenario | None:
    _ensure_builtin_scenarios_registered()
    if not isinstance(scenario_id, str):
        return None
    if scenario_id in _SCENARIOS:
        return _SCENARIOS[scenario_id]
    if not scenario_id.startswith(_TEACHER_PREFIX):
        return None

    from .models import PhysicsScenario

    slug = scenario_id[len(_TEACHER_PREFIX):]
    scenario = (
        PhysicsScenario.objects.filter(slug=slug, status=PhysicsScenario.Status.ACTIVE)
        .select_related("simulation")
        .first()
    )
    if scenario is None or not scenario.simulation.is_active:
        return None
    try:
        return to_lab_scenario(scenario)
    except (ValueError, TypeError):
        return None


def scenarios_for(simulation_type) -> tuple[LabScenario, ...]:
    _ensure_builtin_scenarios_registered()
    built_in = tuple(s for s in _SCENARIOS.values() if s.simulation_type == simulation_type)

    from .models import PhysicsScenario

    rows = (
        PhysicsScenario.objects.filter(
            status=PhysicsScenario.Status.ACTIVE,
            simulation__simulation_type=simulation_type,
            simulation__is_active=True,
        )
        .select_related("simulation")
        .order_by("title", "id")
    )
    teacher_authored = []
    for row in rows:
        try:
            teacher_authored.append(to_lab_scenario(row))
        except (ValueError, TypeError):
            continue
    return built_in + tuple(teacher_authored)


def evaluate_scenario(scenario: LabScenario, *, parameters: dict) -> dict:
    """Reconstruct the outcome server-side and report per-goal results.

    ``parameters`` are raw, submitted-or-stored values keyed by the
    scenario's own simulation type's registered ``input_fields`` (Kinematics:
    ``initial_position_m``/``initial_velocity_m_s``/``acceleration_m_s2``;
    Newton's Second Law: ``mass_kg``/``force_n``; any future scenario-capable
    simulation: whatever it registers). The state reconstruction itself is
    that simulation's own ``ScenarioCapability.state_at`` -- this function
    never computes Physics, it only asks the selected simulation and checks
    the result against the target. Every value is clamped to that
    simulation's own supported range *inside* its own ``state_at`` before
    anything is computed, so a forged ``9e99`` cannot pass a check by
    overflowing anything. Returns ``{"met": bool, "checks": [...]}``.
    """

    definition = get_simulation_definition(scenario.simulation_type)
    capability = definition.scenario if definition is not None else None
    if capability is None:
        unavailable = "This simulation type does not support scenario checks yet."
        return {
            "met": False,
            "checks": [
                {"description": t.description, "met": False, "detail": unavailable}
                for t in scenario.targets
            ],
        }

    checks = []
    for target in scenario.targets:
        if target.kind in _FIELD_KINDS:
            state = capability.state_at(parameters, target.at_time_s)
            actual = state[target.field]
            label = target.field.replace("_", " ")
            if target.kind == _KIND_VALUE:
                met = abs(actual - target.target) <= target.tolerance
                detail = f"{label} was {actual:.2f}; goal is {target.target:.2f} ± {target.tolerance:.2f}"
            elif target.kind == _KIND_GREATER_THAN:
                met = actual > target.target
                detail = f"{label} was {actual:.2f}; goal is greater than {target.target:.2f}"
            elif target.kind == _KIND_LESS_THAN:
                met = actual < target.target
                detail = f"{label} was {actual:.2f}; goal is less than {target.target:.2f}"
            else:  # _KIND_WITHIN_RANGE
                met = target.range_min <= actual <= target.range_max
                detail = (
                    f"{label} was {actual:.2f}; goal is between "
                    f"{target.range_min:.2f} and {target.range_max:.2f}"
                )
            checks.append({"description": target.description, "met": met, "detail": detail})
        else:  # _KIND_REVERSES
            if not capability.supports_reverses or capability.reverses_at is None:
                checks.append({
                    "description": target.description, "met": False,
                    "detail": "This condition does not apply to this simulation.",
                })
            else:
                reverses, detail = capability.reverses_at(parameters)
                checks.append({"description": target.description, "met": reverses, "detail": detail})

    return {"met": all(c["met"] for c in checks), "checks": checks}


# --- the built-in kinematics challenges ------------------------------
#
# Registered lazily (on first call to get_scenario/scenarios_for) rather than
# at module import time: a TargetCondition now validates its field against
# the selected simulation's own registered ScenarioCapability, which means
# Kinematics' own module must already have registered before these can be
# constructed. Django's app loading does not guarantee that ordering across
# apps (e.g. django.contrib.admin's autodiscovery can import this module,
# transitively, before apps.physics.apps.PhysicsConfig.ready() has imported
# simulations_kinematics) -- but by the time any real request or test
# actually calls get_scenario/scenarios_for, app loading has fully finished
# and the registry is guaranteed populated.

_BUILTIN_SCENARIOS_REGISTERED = False


def _ensure_builtin_scenarios_registered() -> None:
    global _BUILTIN_SCENARIOS_REGISTERED
    if _BUILTIN_SCENARIOS_REGISTERED:
        return

    _register(
        LabScenario(
            scenario_id="reach-20-at-4",
            title="Challenge 01 · Hit the mark",
            description=(
                "Choose an initial velocity and an acceleration so the cart is at "
                "about 20 m when 4 seconds have passed. The cart starts at x₀ = 0."
            ),
            simulation_type="kinematics",
            editable=("initial_velocity_m_s", "acceleration_m_s2"),
            fixed={"initial_position_m": 0.0},
            targets=(
                TargetCondition(
                    kind=_KIND_VALUE,
                    simulation_type="kinematics",
                    field="position_m",
                    at_time_s=4.0,
                    target=20.0,
                    tolerance=1.0,
                    description="Position is 20 m (±1 m) at t = 4 s.",
                ),
            ),
            teacher_message="There are many correct answers -- ask the student to find a second one.",
        )
    )

    _register(
        LabScenario(
            scenario_id="stop-and-reverse",
            title="Challenge 02 · There and back",
            description=(
                "Set up a motion where the cart starts moving forward, slows down, "
                "stops, and then moves backward -- all within the 20 second window."
            ),
            simulation_type="kinematics",
            editable=("initial_velocity_m_s", "acceleration_m_s2"),
            fixed={"initial_position_m": 0.0},
            targets=(
                TargetCondition(
                    kind=_KIND_REVERSES,
                    simulation_type="kinematics",
                    description="The cart moves forward, stops, then reverses.",
                ),
            ),
            teacher_message="This needs v₀ > 0 and a < 0. Ask why the sign of a matters.",
        )
    )

    _BUILTIN_SCENARIOS_REGISTERED = True
