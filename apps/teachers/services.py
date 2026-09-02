"""Teacher workspace: derived evidence + explicit teacher actions.

Derived activity (timeline, concepts, experiments, tutor counts) is reused from
the student progress service so the two UIs cannot drift. This module adds the
teacher-only layers: possible-misconception candidates with their supporting
evidence, the intervention form's real target choices, a deterministic
(non-LLM) suggestion, and the create/persist path for a ``TeacherIntervention``.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept
from apps.provenance.services import sanitize_provenance_metadata
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    StudentMisconception,
    StudentProfile,
)
from apps.students.progress_services import build_student_learning_progress

from .models import TeacherIntervention

logger = logging.getLogger(__name__)

NOTE_LIMIT = 2000
LESSON_CHOICE_LIMIT = 60


class InterventionError(ValueError):
    """A teacher intervention submission was missing or inconsistent."""


# --- student list ----------------------------------------------------------


def list_teacher_students() -> list[dict]:
    """One bounded pass over every student for the workspace list."""

    students = list(
        StudentProfile.objects.annotate(
            _last_evidence_at=Max("learning_evidence__created_at"),
            _last_experiment_at=Max("experiment_attempts__started_at"),
        ).order_by("display_name")
    )

    experiment_counts: dict = {}
    for student_id in ExperimentAttempt.objects.values_list("student_id", flat=True):
        experiment_counts[student_id] = experiment_counts.get(student_id, 0) + 1

    concepts_by_student: dict = {}
    evidence_concepts = (
        LearningEvidence.objects.filter(lesson__isnull=False)
        .values_list("student_id", "lesson__physics_concepts__name")
        .order_by("-created_at")[:3000]
    )
    for student_id, name in evidence_concepts:
        if name:
            concepts_by_student.setdefault(student_id, set()).add(name)
    for student_id, name in ExperimentAttempt.objects.values_list(
        "student_id", "simulation__concept__name"
    ):
        if name:
            concepts_by_student.setdefault(student_id, set()).add(name)

    rows = []
    for student in students:
        stamps = [
            s
            for s in (student._last_evidence_at, student._last_experiment_at)
            if s is not None
        ]
        rows.append(
            {
                "student": student,
                "last_activity_at": max(stamps) if stamps else None,
                "experiments": experiment_counts.get(student.pk, 0),
                "recent_concepts": sorted(concepts_by_student.get(student.pk, set()))[:4],
            }
        )
    return rows


# --- one student's evidence + intervention context ----------------------


def _candidate_why(observation, evidence_items: list[dict]) -> str:
    """A plain-language reason, built from evidence kinds -- never detector names."""

    if not evidence_items:
        return (
            f"Observed {observation.observation_count} time(s); no stored excerpts."
        )
    kinds = sorted({item["kind"] for item in evidence_items if item["kind"]})
    where = ", ".join(kinds).lower() if kinds else "student activity"
    count = observation.observation_count
    return (
        f"Appeared from {where} "
        f"({count} observation{'s' if count != 1 else ''}). "
        "The student's own words are quoted below."
    )


def _candidate_rows(student: StudentProfile) -> list[dict]:
    observations = (
        StudentMisconception.objects.filter(student=student)
        .select_related("misconception", "misconception__physics_concept")
        .prefetch_related("evidence__learning_evidence")
        .order_by("status", "-last_observed_at")
    )
    rows = []
    for observation in observations:
        evidence_items = [
            {
                "source": ev.get_source_display(),
                "kind": (
                    ev.learning_evidence.get_kind_display()
                    if ev.learning_evidence_id
                    else ""
                ),
                "excerpt": ev.excerpt,
            }
            for ev in observation.evidence.all()
        ]
        rows.append(
            {
                "observation": observation,
                "why": _candidate_why(observation, evidence_items),
                "evidence": evidence_items,
            }
        )
    return rows


def _intervention_history(student: StudentProfile) -> list[TeacherIntervention]:
    return list(
        TeacherIntervention.objects.filter(student=student)
        .select_related(
            "teacher", "lesson", "concept", "misconception__misconception"
        )
        .order_by("-created_at")
    )


def _evidence_hint(exploring: list[str]) -> str:
    """A neutral, deterministic prompt for the teacher. Never an LLM call."""

    if not exploring:
        return (
            "There is little activity yet. A short lesson or a first tutor "
            "question may be a good starting point."
        )
    focus = ", ".join(exploring[:2])
    return (
        f"Evidence shows this student has recently explored {focus}. "
        "You may want to consider an experiment, a lesson review, or a tutor "
        "follow-up -- your call."
    )


def build_teacher_student_evidence(*, student: StudentProfile) -> dict:
    """Compose the full context for one student's teacher workspace page."""

    progress = build_student_learning_progress(student=student)
    candidates = _candidate_rows(student)

    concept_choices = list(
        PhysicsConcept.objects.filter(is_active=True)
        .order_by("name")
        .values_list("pk", "name")
    )
    lesson_choices = list(
        Lesson.objects.order_by("title").values_list("pk", "title")[:LESSON_CHOICE_LIMIT]
    )

    context = dict(progress)
    context.update(
        {
            "candidates": candidates,
            "candidate_status": StudentMisconception.Status.CANDIDATE,
            "interventions": _intervention_history(student),
            "action_choices": TeacherIntervention.ActionType.choices,
            "lesson_choices": lesson_choices,
            "concept_choices": concept_choices,
            "misconception_choices": [
                (
                    row["observation"].pk,
                    f"{row['observation'].misconception.title} "
                    f"({row['observation'].get_status_display()})",
                )
                for row in candidates
            ],
            "evidence_hint": _evidence_hint(progress.get("exploring", [])),
        }
    )
    return context


# --- create an intervention ------------------------------------------


def _resolve_lesson(raw_id):
    if not raw_id:
        return None
    try:
        lesson = Lesson.objects.filter(pk=raw_id).first()
    except (ValidationError, ValueError, TypeError):
        lesson = None
    if lesson is None:
        raise InterventionError("That lesson could not be found.")
    return lesson


def _resolve_concept(raw_id):
    if not raw_id:
        return None
    try:
        concept = PhysicsConcept.objects.filter(pk=int(raw_id)).first()
    except (TypeError, ValueError):
        concept = None
    if concept is None:
        raise InterventionError("That Physics concept could not be found.")
    return concept


def _resolve_misconception(raw_id, *, student):
    if not raw_id:
        return None
    try:
        observation = (
            StudentMisconception.objects.select_related("misconception")
            .filter(pk=int(raw_id), student=student)
            .first()
        )
    except (TypeError, ValueError):
        observation = None
    if observation is None:
        # Either not found or -- crucially -- it belongs to another student.
        raise InterventionError(
            "That learning signal does not belong to this student."
        )
    return observation


@transaction.atomic
def create_teacher_intervention(
    *,
    student: StudentProfile,
    teacher,
    action_type: str,
    note: str = "",
    lesson_id=None,
    concept_id=None,
    misconception_id=None,
) -> TeacherIntervention:
    """Validate and persist one teacher intervention.

    ``student`` comes from the URL and ``teacher`` from the authenticated
    request -- never from POST data. Targets are validated against the project
    and, for a linked signal, against *this* student.
    """

    action = (action_type or "").strip().lower()
    if action not in TeacherIntervention.ActionType.values:
        raise InterventionError("Choose a valid intervention action.")

    note = (note or "").strip()[:NOTE_LIMIT]
    if action == TeacherIntervention.ActionType.TEACHER_NOTE and not note:
        raise InterventionError("A teacher note needs some text.")

    lesson = _resolve_lesson(lesson_id)
    concept = _resolve_concept(concept_id)
    misconception = _resolve_misconception(misconception_id, student=student)

    metadata = sanitize_provenance_metadata(
        {
            "action_type": action,
            "teacher": getattr(teacher, "get_username", lambda: "")()
            if teacher is not None
            else "",
            "student_id": student.pk,
            "lesson_id": str(lesson.pk) if lesson else None,
            "concept_id": concept.pk if concept else None,
            "misconception_id": misconception.pk if misconception else None,
        }
    )

    return TeacherIntervention.objects.create(
        student=student,
        teacher=teacher if getattr(teacher, "is_authenticated", False) else None,
        lesson=lesson,
        concept=concept,
        misconception=misconception,
        action_type=action,
        note=note,
        metadata=metadata,
    )
