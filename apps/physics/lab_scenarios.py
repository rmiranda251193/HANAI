"""Code-defined, allow-listed Physics Lab scenario challenges.

A scenario is a small **structured description** of a goal ("make the cart reach
~20 m at t = 4 s"). It contains no code and no expressions -- only validated
data. ``evaluate_scenario`` reconstructs the relevant final state on the server
using the existing deterministic Kinematics model and checks the target with a
documented tolerance. Nothing here persists anything: the durable learning
evidence for a challenge is the explanation the student submits through the
normal Explain step.

This is deliberately not a general scenario engine. Teacher-authored scenarios
are a future extension: they would add rows to an allow-listed store validated
into exactly this shape, reusing ``evaluate_scenario`` unchanged.
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
_KIND_VALUE = "value"        # a named state field is within tolerance of a target
_KIND_REVERSES = "reverses"  # starts forward, decelerates, stops, then reverses
_ALLOWED_KINDS = frozenset({_KIND_VALUE, _KIND_REVERSES})

_VALUE_FIELDS = frozenset({"position_m", "velocity_m_s"})


@dataclass(frozen=True)
class TargetCondition:
    kind: str
    description: str
    field: str = ""
    at_time_s: float = 0.0
    target: float = 0.0
    tolerance: float = 0.0

    def __post_init__(self):
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unknown target kind {self.kind!r}.")
        if self.kind == _KIND_VALUE and self.field not in _VALUE_FIELDS:
            raise ValueError(f"Unknown target field {self.field!r}.")


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


def _register(scenario: LabScenario) -> None:
    _SCENARIOS[scenario.scenario_id] = scenario


def get_scenario(scenario_id) -> LabScenario | None:
    if not isinstance(scenario_id, str):
        return None
    return _SCENARIOS.get(scenario_id)


def scenarios_for(simulation_type) -> tuple[LabScenario, ...]:
    return tuple(
        s for s in _SCENARIOS.values() if s.simulation_type == simulation_type
    )


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
        if target.kind == _KIND_VALUE:
            state = kinematics_state(
                initial_position=x0,
                initial_velocity=v0,
                acceleration=a,
                time=target.at_time_s,
            )
            actual = state[target.field]
            met = abs(actual - target.target) <= target.tolerance
            checks.append(
                {
                    "description": target.description,
                    "met": met,
                    "detail": (
                        f"{target.field.replace('_', ' ')} was {actual:.2f}; "
                        f"goal is {target.target:.2f} ± {target.tolerance:.2f}"
                    ),
                }
            )
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
