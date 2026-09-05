"""Deterministic registry of misconception recovery activity types.

Mirrors ``apps.physics.simulation_registry``: a plain dict of dataclasses,
populated at import time, describing what each ``activity_type`` means
generically -- a label, a student-facing description, and which existing
system is responsible for reporting its completion. Nothing here is ever
evaluated as code: a new activity type is added by writing a new Python
branch in ``apps.students.recovery_services`` (server-side handling) plus one
more entry here, not by storing an expression in the database.

The database (``apps.physics.models.MisconceptionRecoveryActivity``) is the
source of truth for which activity types exist (its ``ActivityType`` choices);
this registry only supplies presentation/validation metadata for the types
the service layer actually knows how to run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryActivityKind:
    """Generic, student-safe metadata for one recovery activity type."""

    activity_type: str
    label: str
    description: str
    completed_by: str  # human-readable: which existing system reports completion
    cta: str = ""  # button text for a step that launches into another page; "" if answered in-page


_REGISTRY: dict[str, RecoveryActivityKind] = {}


def register(kind: RecoveryActivityKind) -> None:
    _REGISTRY[kind.activity_type] = kind


def get_activity_kind(activity_type: str) -> RecoveryActivityKind | None:
    return _REGISTRY.get(activity_type)


def registered_activity_types() -> tuple[str, ...]:
    """Deterministic (sorted) list of every registered activity type."""

    return tuple(sorted(_REGISTRY))


register(
    RecoveryActivityKind(
        activity_type="physics_lab",
        label="Physics Lab",
        description=(
            "Predict, run the simulation, observe the result and explain it "
            "in the existing Physics Lab."
        ),
        completed_by="A completed ExperimentAttempt on the linked simulation.",
        cta="Open the Physics Lab",
    )
)
register(
    RecoveryActivityKind(
        activity_type="tutor_reflection",
        label="Talk to your Tutor",
        description="Discuss the idea with the Physics Tutor.",
        completed_by="A student message in the matching TutorSession.",
        cta="Talk to your Tutor",
    )
)
register(
    RecoveryActivityKind(
        activity_type="concept_check",
        label="Concept check",
        description="Answer one short question to check understanding.",
        completed_by="A submitted answer on the recovery page itself.",
    )
)
