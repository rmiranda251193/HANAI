"""Code-defined, allow-listed Physics Lab scenario challenges -- built-in ones
below, and teacher-authored ones (``apps.physics.models.PhysicsScenario``,
via ``apps.physics.scenario_services.to_lab_scenario``) converted into this
exact same shape on the fly.

A scenario is a small **structured description** of a goal ("make the cart reach
~20 m at t = 4 s"). It contains no code and no expressions -- only validated
data. ``evaluate_scenario`` reconstructs the relevant final state on the server
using the existing deterministic Kinematics model and checks the target with a
documented tolerance. Nothing here persists anything: the durable learning
evidence for a challenge is the explanation the student submits through the
normal Explain step (teacher-authored scenarios additionally get a compact
LearningEvidence row per check -- see ``scenario_services.record_scenario_check``
-- reusing the existing evidence model, not a second one).

This was originally "deliberately not a general scenario engine", with
teacher-authored scenarios noted as a future extension that would "add rows
... reusing evaluate_scenario unchanged". That future has arrived for the
*target* side: the two original kinds (``value``/``reverses``) are now three
more general comparison kinds richer (``greater_than``/``less_than``/
``within_range``), covering the target types a teacher actually needs
(velocity_equals, position_within_range, acceleration_greater_than, ...)
without inventing formulas -- still a closed, code-reviewed allow-list, still
zero teacher-supplied code. ``evaluate_scenario``'s own signature and the two
built-in scenarios below are UNCHANGED.
"""

from __future__ import annotations

from dataclasses import dataclass

from .simulations_kinematics import (
    MAX_TIME_S,
    clamp_acceleration,
    clamp_initial_position,
    clamp_initial_velocity,
    kinematics_state,
)

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

_VALUE_FIELDS = frozenset({"position_m", "velocity_m_s", "acceleration_m_s2"})


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

    def __post_init__(self):
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unknown target kind {self.kind!r}.")
        if self.kind in _FIELD_KINDS and self.field not in _VALUE_FIELDS:
            raise ValueError(f"Unknown target field {self.field!r}.")
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
        targets=(TargetCondition(**scenario.target_condition),),
        teacher_message=scenario.reflection_prompt,
    )


_VALUE_FIELDS_BY_SIMULATION_TYPE = {"kinematics": _VALUE_FIELDS}


def value_fields_for(simulation_type) -> frozenset[str]:
    """The state fields a target condition may name for this simulation
    type -- the single source of truth ``TargetCondition`` itself validates
    against, exported so ``scenario_services.py`` never hand-copies the list."""

    return _VALUE_FIELDS_BY_SIMULATION_TYPE.get(simulation_type, frozenset())


def allowed_target_kinds() -> frozenset[str]:
    return _ALLOWED_KINDS


def get_scenario(scenario_id) -> LabScenario | None:
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


def evaluate_scenario(scenario: LabScenario, *, initial_position, initial_velocity, acceleration) -> dict:
    """Reconstruct the outcome server-side and report per-goal results.

    Every submitted parameter is clamped to the model's supported range first
    (identical to ``kinematics_state``), so a forged ``9e99`` cannot pass a
    check by overflowing anything. Returns ``{"met": bool, "checks": [...]}``.
    """

    x0 = clamp_initial_position(initial_position)
    v0 = clamp_initial_velocity(initial_velocity)
    a = clamp_acceleration(acceleration)

    checks = []
    for target in scenario.targets:
        if target.kind in _FIELD_KINDS:
            state = kinematics_state(
                initial_position=x0,
                initial_velocity=v0,
                acceleration=a,
                time=target.at_time_s,
            )
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
            reverses = False
            detail = "the object never reversed direction"
            if v0 > 0 and a < 0:
                t_stop = -v0 / a
                if 0 < t_stop < MAX_TIME_S:
                    end = kinematics_state(
                        initial_position=x0, initial_velocity=v0,
                        acceleration=a, time=min(MAX_TIME_S, t_stop * 2),
                    )
                    reverses = end["velocity_m_s"] < 0
                    if reverses:
                        detail = (
                            f"it moved forward, stopped near t = {t_stop:.1f} s, "
                            "then moved backward"
                        )
            checks.append({"description": target.description, "met": reverses, "detail": detail})

    return {"met": all(c["met"] for c in checks), "checks": checks}


# --- the built-in kinematics challenges ------------------------------

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
                description="The cart moves forward, stops, then reverses.",
            ),
        ),
        teacher_message="This needs v₀ > 0 and a < 0. Ask why the sign of a matters.",
    )
)
