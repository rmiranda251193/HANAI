"""Teacher-guided learning goals: create, close, project, and honestly complete.

A goal is a teacher's instructional decision. This module never creates one from
AI, the pattern engine, the misconception engine, the concept graph, or student
activity -- only :func:`create_learning_goal`, called from a ``teacher_required``
view, does. Completion is signal-driven and conservative: a goal advances to
``completed`` only when a real target activity actually finishes *after* the goal
was set, and it is never labelled "mastered". The student-facing projection
carries a controlled description and safe destinations only -- never the private
``teacher_note`` or any misconception detail.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.concept_graph import (
    build_physics_concept_graph,
    get_adjacent_concepts,
)
from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.students.concept_path_services import build_concept_destination_maps
from apps.students.models import (
    ExperimentAttempt,
    PracticeAttempt,
    StudentMisconception,
    StudentProfile,
)
from apps.students.practice_services import get_practice_questions

from .models import TeacherLearningGoal

logger = logging.getLogger(__name__)

GOAL_NOTE_LIMIT = 2000
GOAL_LIST_LIMIT = 40
CONNECTED_CONCEPT_LIMIT = 6

_Status = TeacherLearningGoal.Status


class GoalError(ValueError):
    """A learning-goal request was missing, inconsistent, or a duplicate."""


class GoalNotFound(GoalError):
    """The goal does not exist or does not belong to this student."""


# --- target resolution -------------------------------------------------


def _resolve_concept(raw_id) -> PhysicsConcept:
    if not raw_id:
        raise GoalError("Choose a Physics concept for this learning goal.")
    try:
        concept = PhysicsConcept.objects.filter(pk=int(raw_id)).first()
    except (TypeError, ValueError):
        concept = None
    if concept is None:
        raise GoalError("That Physics concept could not be found.")
    if not concept.is_active:
        raise GoalError("That Physics concept is not available.")
    return concept


def _resolve_lesson(raw_id):
    if not raw_id:
        return None
    try:
        lesson = Lesson.objects.filter(pk=raw_id).prefetch_related("physics_concepts").first()
    except (ValidationError, ValueError, TypeError):
        lesson = None
    if lesson is None:
        raise GoalError("That lesson could not be found.")
    return lesson


def _resolve_simulation(raw_id):
    if not raw_id:
        return None
    try:
        simulation = PhysicsSimulation.objects.filter(pk=int(raw_id), is_active=True).first()
    except (TypeError, ValueError):
        simulation = None
    if simulation is None:
        raise GoalError("That Physics Lab simulation could not be found.")
    return simulation


def _resolve_misconception(raw_id, *, student):
    if not raw_id:
        return None
    try:
        observation = (
            StudentMisconception.objects.filter(pk=int(raw_id), student=student).first()
        )
    except (TypeError, ValueError):
        observation = None
    if observation is None:
        # Either not found, or -- crucially -- it belongs to another student.
        raise GoalError("That learning signal does not belong to this student.")
    return observation


# --- controlled student-facing text (Section 12) ---------------------


def build_student_goal_message(concept_name: str, lesson_title: str, simulation_title: str) -> str:
    """Deterministic, plain-text description. No HTML, no LLM."""

    concept_name = (concept_name or "this concept").strip()
    lesson_title = (lesson_title or "").strip()
    simulation_title = (simulation_title or "").strip()
    if lesson_title and simulation_title:
        return (
            f"Explore {concept_name} through the lesson “{lesson_title}” "
            "and the Physics Lab."
        )
    if lesson_title:
        return (
            f"Explore {concept_name} through the lesson “{lesson_title}”, "
            "or by asking the Physics Tutor."
        )
    if simulation_title:
        return (
            f"Explore {concept_name} in the Physics Lab, or by asking the Physics Tutor."
        )
    return (
        f"Explore {concept_name} through a lesson, a Physics Lab experiment, or a "
        "Tutor discussion."
    )


# --- safe destinations (Section 26 / 27) ----------------------------


def _lesson_for_concept(concept):
    return (
        Lesson.objects.filter(physics_concepts=concept)
        .order_by("-published_at", "-updated_at", "-id")
        .first()
    )


def _simulation_for_concept(concept):
    return (
        PhysicsSimulation.objects.filter(concept=concept, is_active=True)
        .order_by("title", "slug")
        .first()
    )


def build_learning_goal_destination(goal, *, lesson_by_slug=None, sim_by_slug=None) -> dict:
    """A real, server-reversed activity for the goal. Never built from input.

    ``lesson_by_slug`` / ``sim_by_slug`` (from
    :func:`build_concept_destination_maps`) let a caller resolve many goals with
    a fixed number of queries instead of one lookup per concept-only goal.
    """

    lesson = goal.lesson
    simulation = goal.simulation

    if lesson is None and simulation is None:
        if lesson_by_slug is not None:
            lesson = lesson_by_slug.get(goal.concept.slug)
            if lesson is None:
                simulation = (sim_by_slug or {}).get(goal.concept.slug)
        else:
            lesson = _lesson_for_concept(goal.concept)
            if lesson is None:
                simulation = _simulation_for_concept(goal.concept)

    if lesson is not None:
        primary = {
            "url": reverse("students:tutor", args=[lesson.slug]),
            "label": "Open the lesson",
        }
        secondary = {
            "url": reverse("students:practice", args=[lesson.slug]),
            "label": "Try the practice",
        }
        return {"primary": primary, "secondary": secondary}

    if simulation is not None:
        return {
            "primary": {
                "url": reverse("physics_lab:detail", args=[simulation.slug]),
                "label": "Open the Physics Lab",
            },
            "secondary": None,
        }

    return {
        "primary": {"url": reverse("students:lessons"), "label": "Browse lessons"},
        "secondary": None,
    }


# --- create / close ---------------------------------------------------


@transaction.atomic
def create_learning_goal(
    *,
    student: StudentProfile,
    teacher,
    concept_id,
    lesson_id=None,
    simulation_id=None,
    misconception_id=None,
    teacher_note: str = "",
) -> TeacherLearningGoal:
    """Validate targets and record one teacher learning goal.

    ``student`` comes from the URL and ``teacher`` from the authenticated
    request -- never from POST. ``status`` and timestamps are server-set.
    """

    concept = _resolve_concept(concept_id)
    lesson = _resolve_lesson(lesson_id)
    simulation = _resolve_simulation(simulation_id)
    misconception = _resolve_misconception(misconception_id, student=student)

    if lesson is not None and not lesson.physics_concepts.filter(pk=concept.pk).exists():
        raise GoalError("That lesson does not teach the selected concept.")
    if simulation is not None and simulation.concept_id != concept.pk:
        raise GoalError("That simulation is not linked to the selected concept.")

    # Serialise goal creation for this student so the duplicate check below and
    # the create cannot be raced (the partial unique index can't cover a
    # concept-only goal, whose lesson/simulation targets are NULL).
    StudentProfile.objects.select_for_update().filter(pk=student.pk).first()

    duplicate = TeacherLearningGoal.objects.filter(
        student=student,
        concept=concept,
        lesson=lesson,
        simulation=simulation,
        status=_Status.ACTIVE,
    ).exists()
    if duplicate:
        raise GoalError(
            "An active learning goal for that concept and target already exists."
        )

    try:
        goal = TeacherLearningGoal.objects.create(
            student=student,
            teacher=teacher if getattr(teacher, "is_authenticated", False) else None,
            concept=concept,
            lesson=lesson,
            simulation=simulation,
            misconception=misconception,
            teacher_note=(teacher_note or "").strip()[:GOAL_NOTE_LIMIT],
        )
    except IntegrityError:
        raise GoalError(
            "An active learning goal for that concept and target already exists."
        )
    return goal


@transaction.atomic
def close_learning_goal(*, goal_id, student: StudentProfile) -> TeacherLearningGoal:
    """Teacher closes an active goal. History rows are never deleted."""

    goal = (
        TeacherLearningGoal.objects.select_for_update()
        .filter(pk=goal_id, student=student)
        .first()
    )
    if goal is None:
        raise GoalNotFound("That learning goal was not found.")
    if goal.status != _Status.ACTIVE:
        raise GoalError("That learning goal is no longer active.")
    goal.status = _Status.CLOSED
    goal.closed_at = timezone.now()
    goal.save(update_fields=["status", "closed_at"])
    return goal


# --- honest completion (signal-driven, forward-only) ----------------


def _experiment_target_met(goal: TeacherLearningGoal) -> bool:
    return ExperimentAttempt.objects.filter(
        student_id=goal.student_id,
        simulation_id=goal.simulation_id,
        completed_at__isnull=False,
        completed_at__gte=goal.created_at,
    ).exists()


def _practice_target_met(goal: TeacherLearningGoal) -> bool:
    questions = {q.key for q in get_practice_questions(goal.lesson)}
    if not questions:
        return False  # no stable lesson-completion mechanism -> stay active
    attempted = set(
        PracticeAttempt.objects.filter(
            student_id=goal.student_id, lesson_id=goal.lesson_id
        ).values_list("question_key", flat=True)
    )
    if not questions.issubset(attempted):
        return False
    return PracticeAttempt.objects.filter(
        student_id=goal.student_id,
        lesson_id=goal.lesson_id,
        created_at__gte=goal.created_at,
    ).exists()


def _goal_completion_met(goal: TeacherLearningGoal) -> bool:
    """True when *any* of the goal's target activities finished after it was set.

    A goal may carry both a lesson and a simulation; either one being genuinely
    completed completes the goal. A concept-only goal has no reliable automatic
    signal and never auto-completes.
    """

    if goal.simulation_id and _experiment_target_met(goal):
        return True
    if goal.lesson_id and _practice_target_met(goal):
        return True
    return False


@transaction.atomic
def sync_learning_goal_completion(goal: TeacherLearningGoal) -> bool:
    """Advance a single active goal to ``completed`` iff its condition is met.

    Idempotent and centralised: every completion path (the experiment signal,
    the practice signal) goes through here, so the rules live in one place.
    The write is conditional on ``status=active`` at the database, so a teacher
    close committing in the same window can never be flipped to ``completed``.
    """

    if goal.status != _Status.ACTIVE:
        return False
    if not _goal_completion_met(goal):
        return False
    updated = TeacherLearningGoal.objects.filter(
        pk=goal.pk, status=_Status.ACTIVE
    ).update(status=_Status.COMPLETED, completed_at=timezone.now())
    if updated:
        goal.refresh_from_db(fields=["status", "completed_at"])
    return bool(updated)


def sync_learning_goals_for_experiment(attempt) -> None:
    """Signal entry point: a finished experiment may complete matching goals."""

    if attempt.completed_at is None or attempt.simulation_id is None:
        return
    goals = TeacherLearningGoal.objects.filter(
        student_id=attempt.student_id,
        simulation_id=attempt.simulation_id,
        status=_Status.ACTIVE,
    )
    for goal in goals:
        sync_learning_goal_completion(goal)


def sync_learning_goals_for_practice(attempt) -> None:
    """Signal entry point: a practice attempt may complete matching goals."""

    if attempt.lesson_id is None:
        return
    goals = TeacherLearningGoal.objects.filter(
        student_id=attempt.student_id,
        lesson_id=attempt.lesson_id,
        status=_Status.ACTIVE,
    ).select_related("lesson")
    for goal in goals:
        sync_learning_goal_completion(goal)


# --- student-visible projection (Section 10 / 42) -----------------


def _student_goal_view(goal: TeacherLearningGoal, lesson_by_slug=None, sim_by_slug=None) -> dict:
    destination = build_learning_goal_destination(
        goal, lesson_by_slug=lesson_by_slug, sim_by_slug=sim_by_slug
    )
    return {
        "concept": goal.concept.name,
        "lesson": goal.lesson.title if goal.lesson_id else "",
        "simulation": goal.simulation.title if goal.simulation_id else "",
        "message": build_student_goal_message(
            goal.concept.name,
            goal.lesson.title if goal.lesson_id else "",
            goal.simulation.title if goal.simulation_id else "",
        ),
        "status": goal.status,
        "status_label": goal.get_status_display(),
        "created": goal.created_at,
        "primary_url": destination["primary"]["url"],
        "primary_label": destination["primary"]["label"],
        "secondary_url": destination["secondary"]["url"] if destination["secondary"] else "",
        "secondary_label": destination["secondary"]["label"] if destination["secondary"] else "",
    }


def list_student_visible_goals(*, student: StudentProfile) -> dict:
    """Student-safe active + historical goals. No teacher note, no misconception."""

    goals = list(
        TeacherLearningGoal.objects.filter(student=student)
        .select_related("concept", "lesson", "simulation")
        .order_by("-created_at")[:GOAL_LIST_LIMIT]
    )
    lesson_by_slug = sim_by_slug = None
    if any(g.lesson_id is None and g.simulation_id is None for g in goals):
        lesson_by_slug, sim_by_slug = build_concept_destination_maps()

    def view(goal):
        return _student_goal_view(goal, lesson_by_slug, sim_by_slug)

    active = [view(g) for g in goals if g.status == _Status.ACTIVE]
    history = [view(g) for g in goals if g.status != _Status.ACTIVE]
    return {
        "goals_active": active,
        "goals_history": history,
        "goals_has_any": bool(goals),
    }


def active_goal_count(student: StudentProfile) -> int:
    return TeacherLearningGoal.objects.filter(
        student=student, status=_Status.ACTIVE
    ).count()


def active_goal_concepts(student: StudentProfile) -> list[str]:
    """Concept names of the student's active goals, newest first. Distinct."""

    seen: set[str] = set()
    names: list[str] = []
    for name in (
        TeacherLearningGoal.objects.filter(student=student, status=_Status.ACTIVE)
        .order_by("-created_at")
        .values_list("concept__name", flat=True)
    ):
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


# --- teacher-facing projection (Section 16 / 28 / 29 / 32) --------


def _teacher_goal_row(goal: TeacherLearningGoal, activity_by_concept: dict, graph) -> dict:
    activity = activity_by_concept.get(goal.concept.name, {})
    practice = activity.get("practice", {}).get("attempts", 0) if activity else 0
    experiments = activity.get("experiment", {}).get("completed", 0) if activity else 0
    tutor = activity.get("tutor", {}).get("student_messages", 0) if activity else 0

    connected: list[str] = []
    slug = graph.slug_for_name(goal.concept.name) if graph is not None else None
    if slug:
        adjacent = get_adjacent_concepts(graph, slug)
        connected = [n.name for n in adjacent["prerequisites"]]
        connected += [n.name for n in adjacent["next_concepts"]]

    return {
        "id": goal.pk,
        "concept": goal.concept.name,
        "topic": goal.concept.topic,
        "target_label": goal.target_label,
        "lesson": goal.lesson.title if goal.lesson_id else "",
        "simulation": goal.simulation.title if goal.simulation_id else "",
        "teacher_note": goal.teacher_note,
        "status": goal.status,
        "status_label": goal.get_status_display(),
        "created": goal.created_at,
        "completed_at": goal.completed_at,
        "closed_at": goal.closed_at,
        "teacher": goal.teacher.get_username() if goal.teacher_id else "System",
        "activity": {"practice": practice, "experiments": experiments, "tutor": tutor},
        "connected_concepts": connected[:CONNECTED_CONCEPT_LIMIT],
        "can_close": goal.status == _Status.ACTIVE,
    }


def build_teacher_learning_goals(
    *, student: StudentProfile, learning_patterns: dict, graph=None
) -> dict:
    """Teacher view of one student's goals, reusing already-built pattern counts."""

    activity_by_concept = {
        row["concept"]: row
        for row in (learning_patterns or {}).get("concept_activity", [])
    }
    if graph is None:
        graph = build_physics_concept_graph()

    goals = list(
        TeacherLearningGoal.objects.filter(student=student)
        .select_related("concept", "lesson", "simulation", "teacher")
        .order_by("-created_at")[:GOAL_LIST_LIMIT]
    )
    active, history = [], []
    for goal in goals:
        row = _teacher_goal_row(goal, activity_by_concept, graph)
        (active if goal.status == _Status.ACTIVE else history).append(row)

    return {
        "goals_active": active,
        "goals_history": history,
        "goals_has_any": bool(goals),
    }
