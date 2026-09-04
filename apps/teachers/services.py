"""Teacher workspace: derived evidence + explicit teacher actions.

Derived activity (timeline, concepts, experiments, tutor counts) is reused from
the student progress service so the two UIs cannot drift. This module adds the
teacher-only layers: possible-misconception candidates with their supporting
evidence, the intervention form's real target choices, a deterministic
(non-LLM) suggestion, and the create/persist path for a ``TeacherIntervention``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from apps.assessments.services import get_teacher_assessment_evidence
from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.provenance.services import sanitize_provenance_metadata
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    PracticeAttempt,
    StudentMisconception,
    StudentProfile,
)
from apps.physics.concept_graph import build_physics_concept_graph
from apps.students.activity_planner import build_adaptive_activity_plan
from apps.students.concept_path_services import build_student_concept_path
from apps.students.pattern_services import build_student_learning_patterns
from apps.students.progress_services import build_student_learning_progress

from .goal_services import build_teacher_learning_goals
from .models import TeacherIntervention

logger = logging.getLogger(__name__)

NOTE_LIMIT = 2000
LESSON_CHOICE_LIMIT = 60
PRACTICE_ATTEMPT_SCAN = 300
PRACTICE_ATTEMPT_SHOWN = 20

_VISIBLE = TeacherIntervention.STUDENT_VISIBLE_ACTIONS
_ActionType = TeacherIntervention.ActionType
_Status = TeacherIntervention.Status


class InterventionError(ValueError):
    """A teacher intervention submission was missing or inconsistent."""


class RecommendationError(ValueError):
    """A student recommendation action was invalid for its current state."""


class RecommendationNotFound(RecommendationError):
    """The recommendation does not exist or does not belong to this student."""


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


def _practice_evidence(student: StudentProfile) -> dict:
    """Compact, factual practice record: question / answer / result / attempt N of M.

    Counts are labelled as attempts, correct attempts and incorrect attempts --
    never a score, mastery or performance rating. Correctness is the server's
    deterministic verdict, shown as text.
    """

    attempts = list(
        PracticeAttempt.objects.filter(student=student)
        .select_related("lesson", "concept")
        .order_by("-created_at", "-id")[:PRACTICE_ATTEMPT_SCAN]
    )

    totals_by_key: dict[tuple, int] = {}
    for attempt in attempts:
        totals_by_key[(attempt.lesson_id, attempt.question_key)] = max(
            totals_by_key.get((attempt.lesson_id, attempt.question_key), 0),
            attempt.attempt_number,
        )

    rows = []
    for attempt in attempts[:PRACTICE_ATTEMPT_SHOWN]:
        if attempt.is_correct is True:
            result = "Correct"
        elif attempt.is_correct is False:
            result = "Incorrect"
        else:
            result = "Recorded"
        rows.append(
            {
                "when": attempt.created_at,
                "lesson": attempt.lesson,
                "prompt": attempt.question_prompt,
                "answer": attempt.answer_text,
                "result": result,
                "attempt_number": attempt.attempt_number,
                "attempt_total": totals_by_key.get(
                    (attempt.lesson_id, attempt.question_key), attempt.attempt_number
                ),
                "concept": attempt.concept.name if attempt.concept_id else "",
                "expected_display": attempt.expected_display,
            }
        )

    scored = [a for a in attempts if a.is_correct is not None]
    return {
        "rows": rows,
        "attempts": len(attempts),
        "correct_attempts": sum(1 for a in scored if a.is_correct),
        "incorrect_attempts": sum(1 for a in scored if not a.is_correct),
        "has_more": len(attempts) > len(rows),
    }


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
    # next_investigation is needed by the shared activity planner so the
    # teacher's plan matches the student's own /student/plan/ view exactly.
    learning_patterns = build_student_learning_patterns(student=student)
    concept_graph = build_physics_concept_graph()

    concept_choices = list(
        PhysicsConcept.objects.filter(is_active=True)
        .order_by("name")
        .values_list("pk", "name")
    )
    lesson_choices = list(
        Lesson.objects.order_by("title").values_list("pk", "title")[:LESSON_CHOICE_LIMIT]
    )
    simulation_choices = list(
        PhysicsSimulation.objects.filter(is_active=True)
        .order_by("title")
        .values_list("pk", "title")
    )

    context = dict(progress)
    context.update(
        {
            "candidates": candidates,
            "candidate_status": StudentMisconception.Status.CANDIDATE,
            "practice_evidence": _practice_evidence(student),
            "assessment_evidence": get_teacher_assessment_evidence(student),
            "learning_patterns": learning_patterns,
            "learning_path": build_student_concept_path(
                student=student,
                patterns=learning_patterns,
                with_actions=False,
                graph=concept_graph,
            ),
            "learning_goals": build_teacher_learning_goals(
                student=student,
                learning_patterns=learning_patterns,
                graph=concept_graph,
            ),
            "activity_plan": build_adaptive_activity_plan(
                student=student,
                patterns=learning_patterns,
                graph=concept_graph,
            ),
            "interventions": _intervention_history(student),
            "action_choices": TeacherIntervention.ActionType.choices,
            "lesson_choices": lesson_choices,
            "concept_choices": concept_choices,
            "simulation_choices": simulation_choices,
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


def _resolve_simulation(raw_id):
    if not raw_id:
        return None
    try:
        simulation = PhysicsSimulation.objects.filter(
            pk=int(raw_id), is_active=True
        ).first()
    except (TypeError, ValueError):
        simulation = None
    if simulation is None:
        raise InterventionError("That simulation could not be found.")
    return simulation


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
    simulation_id=None,
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
    if action == _ActionType.TEACHER_NOTE and not note:
        raise InterventionError("A teacher note needs some text.")

    lesson = _resolve_lesson(lesson_id)
    concept = _resolve_concept(concept_id)
    simulation = _resolve_simulation(simulation_id)
    misconception = _resolve_misconception(misconception_id, student=student)

    if action == _ActionType.RECOMMEND_LESSON and not (lesson or concept):
        raise InterventionError(
            "Pick a lesson or a Physics concept for a lesson recommendation."
        )
    if action == _ActionType.RECOMMEND_EXPERIMENT and not (simulation or concept):
        raise InterventionError(
            "Pick a simulation or a Physics concept for an experiment recommendation."
        )

    metadata = sanitize_provenance_metadata(
        {
            "action_type": action,
            "teacher": getattr(teacher, "get_username", lambda: "")()
            if teacher is not None
            else "",
            "student_id": student.pk,
            "lesson_id": str(lesson.pk) if lesson else None,
            "concept_id": concept.pk if concept else None,
            "simulation_id": simulation.pk if simulation else None,
            "misconception_id": misconception.pk if misconception else None,
        }
    )

    return TeacherIntervention.objects.create(
        student=student,
        teacher=teacher if getattr(teacher, "is_authenticated", False) else None,
        lesson=lesson,
        concept=concept,
        simulation=simulation,
        misconception=misconception,
        action_type=action,
        status=_Status.PENDING,
        note=note,
        metadata=metadata,
    )


# --- student recommendation inbox ------------------------------------


@dataclass(frozen=True)
class StudentRecommendation:
    """A deliberately narrow, student-safe view of one teacher recommendation.

    It carries only fields chosen for the student. The teacher's private note,
    any misconception link, confidence, detector or metadata never appear here.
    """

    id: int
    action_key: str
    action_badge: str
    title: str
    description: str
    target_label: str
    status: str
    status_label: str
    created_at: datetime
    acted_at: datetime | None
    destination_url: str
    open_url: str
    dismiss_url: str


_ACTION_BADGE = {
    _ActionType.RECOMMEND_LESSON: "Lesson",
    _ActionType.RECOMMEND_EXPERIMENT: "Physics Lab",
    _ActionType.TUTOR_FOLLOW_UP: "Physics Tutor",
}
_ACTION_BUTTON = {
    _ActionType.RECOMMEND_LESSON: "Open the lesson",
    _ActionType.RECOMMEND_EXPERIMENT: "Open the Physics Lab",
    _ActionType.TUTOR_FOLLOW_UP: "Talk to the Tutor",
}


def _lesson_for_concept(concept):
    if concept is None:
        return None
    return (
        Lesson.objects.filter(physics_concepts=concept)
        .order_by("-updated_at")
        .first()
    )


def _simulation_for_concept(concept):
    if concept is None:
        return None
    return (
        PhysicsSimulation.objects.filter(concept=concept, is_active=True)
        .order_by("title")
        .first()
    )


def _recommendation_view(intervention: TeacherIntervention) -> dict:
    """Build the controlled, student-safe title / description / destination.

    All text is generated from the action and the target's *own* name -- never
    from the teacher's note. Destination URLs are always server-reversed.
    """

    action = intervention.action_type
    lesson = intervention.lesson
    concept = intervention.concept
    simulation = intervention.simulation

    destination = ""
    title = "A next step from your teacher"
    description = ""
    target_label = ""

    if action == _ActionType.RECOMMEND_LESSON:
        target_lesson = lesson or _lesson_for_concept(concept)
        if target_lesson is not None:
            destination = reverse("students:tutor", args=[target_lesson.slug])
            title = f"Review {target_lesson.title}"
            target_label = target_lesson.title
            description = (
                f"Open the lesson “{target_lesson.title}” and work "
                "through it with your Physics Tutor."
            )
        else:
            destination = reverse("students:lessons")
            title = "Review a lesson"
            description = "Open your lessons and study the one your teacher had in mind."
        if concept is not None and not target_label:
            target_label = concept.name

    elif action == _ActionType.RECOMMEND_EXPERIMENT:
        target_sim = simulation or _simulation_for_concept(concept)
        if target_sim is not None:
            destination = reverse("physics_lab:detail", args=[target_sim.slug])
            title = f"Explore {concept.name if concept else target_sim.title}"
            target_label = target_sim.title
            description = (
                f"Open the {target_sim.title} in the Physics Lab. Change the "
                "setup, predict what will happen, then observe and explain."
            )
        else:
            destination = reverse("physics_lab:index")
            title = "Run an experiment"
            description = "Open the Physics Lab and run the experiment your teacher suggested."
        if concept is not None and not target_label:
            target_label = concept.name

    elif action == _ActionType.TUTOR_FOLLOW_UP:
        target_lesson = lesson or _lesson_for_concept(concept)
        focus = (
            target_lesson.title
            if target_lesson is not None
            else (concept.name if concept is not None else "this topic")
        )
        if target_lesson is not None:
            destination = reverse("students:tutor", args=[target_lesson.slug])
            target_label = target_lesson.title
        else:
            destination = reverse("students:lessons")
            target_label = concept.name if concept is not None else ""
        title = "Continue the Tutor discussion"
        description = f"Continue exploring {focus} with your Physics Tutor."

    return {
        "title": title,
        "description": description,
        "target_label": target_label,
        "destination_url": destination,
    }


def _to_student_recommendation(intervention: TeacherIntervention) -> StudentRecommendation:
    view = _recommendation_view(intervention)
    return StudentRecommendation(
        id=intervention.pk,
        action_key=intervention.action_type,
        action_badge=_ACTION_BADGE.get(intervention.action_type, "Recommendation"),
        title=view["title"],
        description=view["description"],
        target_label=view["target_label"],
        status=intervention.status,
        status_label=intervention.get_status_display(),
        created_at=intervention.created_at,
        acted_at=intervention.acted_at,
        destination_url=view["destination_url"],
        open_url=reverse("students:recommendation_open", args=[intervention.pk]),
        dismiss_url=reverse("students:recommendation_dismiss", args=[intervention.pk]),
    )


def list_student_recommendations(*, student: StudentProfile) -> dict:
    """Return the student-safe pending list and history for one student."""

    rows = list(
        TeacherIntervention.objects.filter(
            student=student, action_type__in=_VISIBLE
        )
        .select_related("lesson", "concept", "simulation")
        .order_by("-created_at")
    )
    pending, history = [], []
    for row in rows:
        item = _to_student_recommendation(row)
        (pending if row.status == _Status.PENDING else history).append(item)
    history.sort(key=lambda r: r.acted_at or r.created_at, reverse=True)
    return {"pending": pending, "history": history}


def count_pending_recommendations(student: StudentProfile) -> int:
    return TeacherIntervention.objects.filter(
        student=student, action_type__in=_VISIBLE, status=_Status.PENDING
    ).count()


def _owned_recommendation(intervention_id, *, student):
    return TeacherIntervention.objects.select_related(
        "lesson", "concept", "simulation"
    ).filter(
        pk=intervention_id, student=student, action_type__in=_VISIBLE
    ).first()


@transaction.atomic
def open_recommendation(*, intervention_id, student: StudentProfile) -> str:
    """Mark a pending recommendation opened and return its safe destination URL."""

    rec = _owned_recommendation(intervention_id, student=student)
    if rec is None or rec.status == _Status.DISMISSED:
        raise RecommendationNotFound("That recommendation is not available.")
    if rec.status == _Status.PENDING:
        rec.status = _Status.OPENED
        rec.acted_at = rec.acted_at or timezone.now()
        rec.save(update_fields=["status", "acted_at"])
    return _recommendation_view(rec)["destination_url"]


@transaction.atomic
def dismiss_recommendation(*, intervention_id, student: StudentProfile) -> TeacherIntervention:
    """Let the student clear a recommendation. Never deletes the history row."""

    rec = _owned_recommendation(intervention_id, student=student)
    if rec is None:
        raise RecommendationNotFound("That recommendation is not available.")
    if rec.status not in (_Status.PENDING, _Status.OPENED):
        raise RecommendationError("That recommendation can no longer be dismissed.")
    rec.status = _Status.DISMISSED
    rec.acted_at = rec.acted_at or timezone.now()
    rec.save(update_fields=["status", "acted_at"])
    return rec


# --- honest automatic completion (driven by real activity signals) -----


@transaction.atomic
def sync_experiment_recommendation(attempt) -> TeacherIntervention | None:
    """A finished experiment completes the latest matching recommendation.

    Deterministic: same student, same simulation, action ``recommend_experiment``,
    still pending or opened -- only the most recent one, never a broad sweep.
    """

    if attempt.completed_at is None or attempt.simulation_id is None:
        return None
    rec = (
        TeacherIntervention.objects.select_for_update()
        .filter(
            student_id=attempt.student_id,
            simulation_id=attempt.simulation_id,
            action_type=_ActionType.RECOMMEND_EXPERIMENT,
            status__in=[_Status.PENDING, _Status.OPENED],
        )
        .order_by("-created_at")
        .first()
    )
    if rec is None:
        return None
    rec.status = _Status.COMPLETED
    rec.acted_at = rec.acted_at or timezone.now()
    rec.save(update_fields=["status", "acted_at"])
    return rec


@transaction.atomic
def sync_tutor_recommendation(message) -> TeacherIntervention | None:
    """A student tutor message after opening a follow-up recommendation completes it.

    Requires the recommendation to have been explicitly *opened* first, and the
    message to belong to the same student (and lesson, when the recommendation
    targets one). Otherwise the recommendation stays honestly ``opened``.
    """

    from apps.students.models import TutorSession

    session = (
        TutorSession.objects.filter(pk=message.session_id)
        .values_list("student_id", "lesson_id")
        .first()
    )
    if session is None:
        return None
    student_id, lesson_id = session
    rec = (
        TeacherIntervention.objects.select_for_update()
        .filter(
            student_id=student_id,
            action_type=_ActionType.TUTOR_FOLLOW_UP,
            status=_Status.OPENED,
            acted_at__lte=message.created_at,
        )
        .filter(Q(lesson__isnull=True) | Q(lesson_id=lesson_id))
        .order_by("-created_at")
        .first()
    )
    if rec is None:
        return None
    rec.status = _Status.COMPLETED
    rec.save(update_fields=["status"])
    return rec
