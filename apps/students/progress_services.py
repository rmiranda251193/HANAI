"""Derive a student's learning-journey view from records that already exist.

This is a read-only projection over ``LearningEvidence``, ``ExperimentAttempt``,
``TutorSession`` / ``TutorMessage`` and the lesson/concept relationships. It adds
no persistence and makes no evaluative claims -- it records activity, evidence
and reflection, never grades or mastery.

The misconception engine is deliberately NOT consulted here: its candidates and
internal codes are a teacher-support signal and must never surface to a student.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.utils import timezone
from django.utils.formats import date_format

from apps.physics.models import PhysicsSimulation

from .models import ExperimentAttempt, LearningEvidence, TutorMessage, TutorSession

# How much history to load for the timeline / aggregates. A real student builds
# up tens, not thousands, of rows; this keeps a pathological account bounded.
MAX_EVIDENCE_ROWS = 500
TIMELINE_LIMIT = 40
RECENT_LESSONS_LIMIT = 6

# Student-friendly presentation for each internal evidence kind. Internal enum
# names are never shown.
_KIND_PRESENTATION = {
    LearningEvidence.Kind.QUESTION_ASKED: ("Question", "Asked a Physics question", "❓"),
    LearningEvidence.Kind.PRACTICE_ATTEMPTED: ("Practice", "Attempted a practice problem", "✏️"),
    LearningEvidence.Kind.PREDICTION_SUBMITTED: ("Prediction", "Submitted an experiment prediction", "\U0001f52e"),
    LearningEvidence.Kind.EXPERIMENT_OBSERVED: ("Observation", "Recorded an experiment observation", "\U0001f52c"),
    LearningEvidence.Kind.EXPLANATION_SUBMITTED: ("Explanation", "Explained the experiment", "\U0001f4a1"),
    LearningEvidence.Kind.ASSESSMENT_ATTEMPTED: ("Assessment", "Answered an assessment question", "\U0001f4dd"),
}
_EXPERIMENT_KINDS = {
    LearningEvidence.Kind.PREDICTION_SUBMITTED,
    LearningEvidence.Kind.EXPERIMENT_OBSERVED,
    LearningEvidence.Kind.EXPLANATION_SUBMITTED,
}


def _practice_snapshot(evidence: LearningEvidence) -> dict | None:
    """Factual practice detail from a deterministic practice evidence row.

    Only rows written by the practice engine carry ``context['practice']``.
    Older tutor-reviewed practice evidence has no structured context and is left
    as a plain timeline entry. Nothing here is a score or a mastery signal.
    """

    if evidence.kind != LearningEvidence.Kind.PRACTICE_ATTEMPTED:
        return None
    context = evidence.context if isinstance(evidence.context, dict) else {}
    if not context.get("practice"):
        return None
    is_correct = context.get("is_correct")
    if is_correct is True:
        result = "Correct"
    elif is_correct is False:
        result = "Incorrect"
    else:
        result = "Recorded"
    return {
        "concept": context.get("concept") or "",
        "result": result,
        "attempt_number": context.get("attempt_number"),
    }


def _assessment_snapshot(evidence: LearningEvidence) -> dict | None:
    """Factual assessment-answer detail from a structured assessment evidence row.

    Mirrors ``_practice_snapshot`` exactly, for the same reason: only the
    server's own deterministic verdict is ever shown, and only what was
    actually recorded -- never an answer key, never a mastery judgement.
    """

    if evidence.kind != LearningEvidence.Kind.ASSESSMENT_ATTEMPTED:
        return None
    context = evidence.context if isinstance(evidence.context, dict) else {}
    if not context.get("assessment"):
        return None
    is_correct = context.get("is_correct")
    if is_correct is True:
        result = "Correct"
    elif is_correct is False:
        result = "Incorrect"
    else:
        result = "Recorded"
    return {
        "assessment": context.get("assessment") or "",
        "concept": context.get("concept") or "",
        "result": result,
    }


def _simulation_label(key: str) -> str:
    try:
        return PhysicsSimulation.SimulationType(key).label
    except ValueError:
        return (key or "Simulation").replace("_", " ").strip().title() or "Simulation"


def _experiment_snapshot(evidence: LearningEvidence) -> dict | None:
    """Pull the deterministic experiment values out of an evidence row's context."""

    if evidence.kind not in _EXPERIMENT_KINDS:
        return None
    context = evidence.context if isinstance(evidence.context, dict) else {}
    simulation = context.get("simulation")
    if not simulation:
        return None
    snapshot = {
        "simulation": _simulation_label(simulation),
        "mass_kg": None,
        "force_n": None,
        "acceleration_m_s2": None,
    }
    for field in ("mass_kg", "force_n", "acceleration_m_s2"):
        value = context.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            snapshot[field] = float(value)
    return snapshot


def _day_label(when, *, today) -> str:
    local_date = timezone.localtime(when).date()
    if local_date == today:
        return "Today"
    if local_date == today - timedelta(days=1):
        return "Yesterday"
    return date_format(local_date, "DATE_FORMAT")


def _timeline(evidence_rows) -> list[dict]:
    """Group the newest evidence rows into day sections, newest first."""

    today = timezone.localdate()
    days: list[dict] = []
    for evidence in evidence_rows[:TIMELINE_LIMIT]:
        short_label, friendly_title, icon = _KIND_PRESENTATION.get(
            evidence.kind, ("Activity", evidence.get_kind_display(), "•")
        )
        concepts = []
        if evidence.lesson_id:
            concepts = [c.name for c in evidence.lesson.physics_concepts.all()]
        entry = {
            "when": evidence.created_at,
            "kind_label": short_label,
            "title": friendly_title,
            "icon": icon,
            "detail": (evidence.detail or "").strip(),
            "lesson": evidence.lesson,
            "concepts": concepts,
            "experiment": _experiment_snapshot(evidence),
            "practice": _practice_snapshot(evidence),
            "assessment": _assessment_snapshot(evidence),
        }
        label = _day_label(evidence.created_at, today=today)
        if not days or days[-1]["label"] != label:
            days.append({"label": label, "entries": []})
        days[-1]["entries"].append(entry)
    return days


def _concepts_explored(evidence_rows, attempts, sessions) -> list[dict]:
    """Concepts the student has actually touched, with an activity count.

    Sources are existing relationships only: a lesson attached to a piece of
    evidence or a tutor session, and the concept behind an experiment's
    simulation. No concept is invented and none is shown just for existing.

    A structured assessment may have no lesson at all (Section 17: lesson is
    optional) -- its evidence still names the concept in ``context['concept']``
    (see :func:`_assessment_snapshot`), so that case is resolved separately in
    one batched query rather than being silently dropped.
    """

    tally: dict[str, dict] = {}

    def bump(concept):
        entry = tally.setdefault(concept.name, {"concept": concept, "count": 0})
        entry["count"] += 1

    lessonless_assessment_names: set[str] = set()
    for evidence in evidence_rows:
        if evidence.lesson_id:
            for concept in evidence.lesson.physics_concepts.all():
                bump(concept)
        elif evidence.kind == LearningEvidence.Kind.ASSESSMENT_ATTEMPTED:
            context = evidence.context if isinstance(evidence.context, dict) else {}
            name = context.get("concept")
            if name:
                lessonless_assessment_names.add(name)

    if lessonless_assessment_names:
        from apps.physics.models import PhysicsConcept

        for concept in PhysicsConcept.objects.filter(name__in=lessonless_assessment_names):
            bump(concept)

    for attempt in attempts:
        concept = getattr(attempt.simulation, "concept", None)
        if concept is not None:
            bump(concept)
    for session in sessions:
        for concept in session.lesson.physics_concepts.all():
            bump(concept)

    return [
        {
            "name": entry["concept"].name,
            "topic": entry["concept"].topic,
            "count": entry["count"],
        }
        for entry in sorted(
            tally.values(), key=lambda e: (-e["count"], e["concept"].name)
        )
    ]


def _recent_lessons(evidence_rows, attempts, sessions) -> list[dict]:
    latest: dict = {}

    def note(lesson, when):
        if lesson is None:
            return
        current = latest.get(lesson.pk)
        if current is None or when > current["last_activity_at"]:
            latest[lesson.pk] = {"lesson": lesson, "last_activity_at": when}

    for evidence in evidence_rows:
        if evidence.lesson_id:
            note(evidence.lesson, evidence.created_at)
    for session in sessions:
        note(session.lesson, session.updated_at)
    for attempt in attempts:
        if attempt.lesson_id:
            note(attempt.lesson, attempt.updated_at)

    return sorted(
        latest.values(), key=lambda e: e["last_activity_at"], reverse=True
    )[:RECENT_LESSONS_LIMIT]


def _experiment_summary(attempts) -> dict:
    completed = [a for a in attempts if a.is_complete]
    latest = attempts[0] if attempts else None
    return {
        "attempted": len(attempts),
        "completed": len(completed),
        "latest": latest,
        "latest_concept": (
            getattr(latest.simulation, "concept", None) if latest else None
        ),
        "latest_acceleration": latest.acceleration_m_s2 if latest else None,
    }


def _tutor_activity(student, sessions) -> dict:
    student_messages = TutorMessage.objects.filter(
        session__student=student, role=TutorMessage.Role.STUDENT
    ).count()
    latest = sessions[0] if sessions else None
    return {
        "messages": student_messages,
        "sessions": len(sessions),
        "last_lesson": latest.lesson if latest else None,
        "last_at": latest.updated_at if latest else None,
    }


def _next_step(*, has_activity, attempts, has_student_message) -> str:
    """A single deterministic next-step suggestion. Never an LLM call."""

    if not has_activity:
        return (
            "Start by opening a Physics lesson or asking the Physics Tutor a "
            "question."
        )

    latest = attempts[0] if attempts else None
    if latest is not None and not latest.is_complete:
        if latest.prediction and not latest.observation:
            return "Return to the Physics Lab and record what happened."
        if latest.observation and not latest.explanation:
            return "Explain what you think caused the result."

    if any(a.is_complete for a in attempts):
        return (
            "Try the experiment again with a different mass or force, and "
            "predict what will change."
        )

    if has_student_message:
        return (
            "Continue the investigation by running a related experiment in the "
            "Physics Lab."
        )

    return "Ask the Physics Tutor a question about something you want to understand better."


def build_student_learning_progress(*, student) -> dict:
    """Return the full context for one student's learning-journey page."""

    evidence_rows = list(
        LearningEvidence.objects.filter(student=student)
        .select_related("lesson", "session")
        .prefetch_related("lesson__physics_concepts")
        .order_by("-created_at")[:MAX_EVIDENCE_ROWS]
    )
    attempts = list(
        ExperimentAttempt.objects.filter(student=student)
        .select_related("simulation", "simulation__concept", "lesson")
        .order_by("-started_at")
    )
    sessions = list(
        TutorSession.objects.filter(student=student)
        .select_related("lesson")
        .prefetch_related("lesson__physics_concepts")
        .order_by("-updated_at")
    )

    by_kind = Counter(evidence.kind for evidence in evidence_rows)
    practice_correct = 0
    practice_incorrect = 0
    for evidence in evidence_rows:
        snapshot = _practice_snapshot(evidence)
        if snapshot is None:
            continue
        if snapshot["result"] == "Correct":
            practice_correct += 1
        elif snapshot["result"] == "Incorrect":
            practice_incorrect += 1
    experiment_summary = _experiment_summary(attempts)
    concepts = _concepts_explored(evidence_rows, attempts, sessions)
    tutor_activity = _tutor_activity(student, sessions)
    has_activity = bool(evidence_rows or attempts or sessions)

    return {
        "has_activity": has_activity,
        "recent_activity_days": _timeline(evidence_rows),
        "concepts": concepts,
        "exploring": [c["name"] for c in concepts[:5]],
        "recent_lessons": _recent_lessons(evidence_rows, attempts, sessions),
        "experiment_summary": experiment_summary,
        "tutor_activity": tutor_activity,
        "next_step": _next_step(
            has_activity=has_activity,
            attempts=attempts,
            has_student_message=tutor_activity["messages"] > 0,
        ),
        "summary_counts": {
            "evidence": len(evidence_rows),
            "questions": by_kind[LearningEvidence.Kind.QUESTION_ASKED],
            "practice": by_kind[LearningEvidence.Kind.PRACTICE_ATTEMPTED],
            "practice_correct": practice_correct,
            "practice_incorrect": practice_incorrect,
            "predictions": by_kind[LearningEvidence.Kind.PREDICTION_SUBMITTED],
            "observations": by_kind[LearningEvidence.Kind.EXPERIMENT_OBSERVED],
            "explanations": by_kind[LearningEvidence.Kind.EXPLANATION_SUBMITTED],
            "assessment_questions": by_kind[LearningEvidence.Kind.ASSESSMENT_ATTEMPTED],
            "experiments_completed": experiment_summary["completed"],
            "experiments_attempted": experiment_summary["attempted"],
            "concepts": len(concepts),
        },
    }
