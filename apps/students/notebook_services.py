"""The student's Experiment Notebook -- a read-only projection over each of
the student's own ``ExperimentAttempt`` rows (prediction / variables /
observation / measurements / explanation).

This adds no persistence and no new telemetry: it reuses ``ExperimentContext``
(``apps.students.requests``), the same type-aware, server-recomputed
projection the Tutor prompt already builds from, so a new simulation type
needs only its field list added to ``_VARIABLE_FIELDS`` / ``_MEASUREMENT_FIELDS``
below -- nothing else in this module changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import reverse

from .models import ExperimentAttempt
from .requests import ExperimentContext

# A real student builds up tens, not thousands, of experiment attempts; this
# keeps a pathological account's notebook page bounded.
MAX_ENTRIES = 60

# (attribute on ExperimentContext, display label, unit) -- "variables" are the
# setup a student chose before running the experiment; "measurements" are
# what the server computed once it ran. Ordered for display.
_VARIABLE_FIELDS = {
    "kinematics": (
        ("initial_position_m", "Initial position", "m"),
        ("initial_velocity_m_s", "Initial velocity", "m/s"),
        ("acceleration_m_s2", "Acceleration", "m/s²"),
    ),
    "newtons_second_law": (
        ("mass_kg", "Mass", "kg"),
        ("force_n", "Net force", "N"),
    ),
    "projectile_motion": (
        ("initial_speed_m_s", "Initial speed", "m/s"),
        ("launch_angle_deg", "Launch angle", "°"),
        ("initial_height_m", "Initial height", "m"),
    ),
}
_MEASUREMENT_FIELDS = {
    "kinematics": (
        ("time_s", "Time", "s"),
        ("position_m", "Position", "m"),
        ("velocity_m_s", "Velocity", "m/s"),
    ),
    "newtons_second_law": (
        ("acceleration_m_s2", "Acceleration", "m/s²"),
    ),
    "projectile_motion": (
        ("time_s", "Time", "s"),
        ("position_x_m", "Horizontal distance", "m"),
        ("position_y_m", "Height", "m"),
    ),
}


@dataclass(frozen=True)
class NotebookEntry:
    attempt_id: int
    simulation_title: str
    concept_name: str
    lesson_title: str
    started_at: object
    is_complete: bool
    prediction: str
    variables: tuple = field(default_factory=tuple)
    observation: str = ""
    measurements: tuple = field(default_factory=tuple)
    explanation: str = ""
    lab_url: str = ""


def _rows_for(ctx: ExperimentContext, field_map: dict) -> tuple:
    spec = field_map.get(ctx.simulation_type, ())
    rows = []
    for attr, label, unit in spec:
        value = getattr(ctx, attr, None)
        if value is not None:
            rows.append((label, value, unit))
    return tuple(rows)


def build_student_notebook(*, student, limit: int = MAX_ENTRIES) -> list[NotebookEntry]:
    """Every one of ``student``'s own experiment attempts with any recorded
    content, newest first. Attempts with no prediction/observation/explanation
    at all (e.g. an abandoned run) are skipped -- an empty notebook page is
    handled by the template, not by fabricating a blank entry."""

    attempts = (
        ExperimentAttempt.objects.filter(student=student)
        .select_related("simulation", "simulation__concept", "lesson")
        .order_by("-started_at")[:limit]
    )
    entries = []
    for attempt in attempts:
        ctx = ExperimentContext.from_attempt(attempt)
        if not ctx.has_content:
            continue
        entries.append(
            NotebookEntry(
                attempt_id=attempt.pk,
                simulation_title=attempt.simulation.title,
                concept_name=attempt.simulation.concept.name,
                lesson_title=attempt.lesson.title if attempt.lesson else "",
                started_at=attempt.started_at,
                is_complete=attempt.is_complete,
                prediction=ctx.prediction,
                variables=_rows_for(ctx, _VARIABLE_FIELDS),
                observation=ctx.observation,
                measurements=_rows_for(ctx, _MEASUREMENT_FIELDS),
                explanation=ctx.explanation,
                lab_url=reverse("physics_lab:detail", args=[attempt.simulation.slug]),
            )
        )
    return entries
