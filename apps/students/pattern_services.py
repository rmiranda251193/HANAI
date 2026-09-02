"""Deterministic synthesis of a student's real Physics activity into patterns.

This module is OBSERVATION, not INTERPRETATION. It reports counts and describes
sequences that genuinely happened in the records -- "attempted 4 problems",
"returned to a question and later answered it correctly", "explored a concept
through both practice and experiment". It never rates, ranks, labels, or
diagnoses the student, and it never calls an AI provider: the same rows always
yield the same patterns.

Sources are all existing records -- ``PracticeAttempt``, ``ExperimentAttempt``,
``TutorMessage``, ``PhysicsSimulation`` and the teacher-recommendation count.
Nothing is persisted; there is no new model. A concept is included only because
real activity references it (a graded practice attempt, a lab run, or a tutor
question about the lesson that teaches it).

``now`` is injectable so the 14-day recency window is fully testable.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.physics.models import PhysicsSimulation

from .models import ExperimentAttempt, PracticeAttempt, TutorMessage

# The window used for "recent" signals. Historical totals are still shown.
RECENT_WINDOW_DAYS = 14

# Bounded reads -- a real student has tens of rows, not thousands. These caps
# keep a pathological account from turning one page into a slow query.
MAX_PRACTICE_ROWS = 400
MAX_EXPERIMENT_ROWS = 200
MAX_TUTOR_ROWS = 400

CONCEPT_LIMIT = 8
RECENT_CONCEPT_LIMIT = 6
SIGNAL_LIMIT = 3
RECENT_QUESTION_MAXLEN = 140

# Stable identifiers for tests / styling. The ``text`` is what a person reads.
SIGNAL_RETRY_CORRECT = "retry_correct"
SIGNAL_INQUIRY_SEQUENCE = "inquiry_sequence"
SIGNAL_TUTOR_AND_LAB = "tutor_and_lab"
SIGNAL_PRACTICE_AND_LAB = "practice_and_lab"
SIGNAL_REPEATED_PRACTICE = "repeated_practice"

_SIGNAL_ORDER = [
    SIGNAL_RETRY_CORRECT,
    SIGNAL_INQUIRY_SEQUENCE,
    SIGNAL_TUTOR_AND_LAB,
    SIGNAL_PRACTICE_AND_LAB,
    SIGNAL_REPEATED_PRACTICE,
]

REPEATED_PRACTICE_THRESHOLD = 3


# --- small helpers -------------------------------------------------------


def _later(current, candidate):
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current


def _clip(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def _new_concept(name: str, topic: str) -> dict:
    return {
        "concept": name,
        "topic": topic,
        "practice": {
            "attempts": 0,
            "correct": 0,
            "incorrect": 0,
            "questions": set(),
            "retry_correct": 0,
            "recent_attempts": 0,
            "latest_activity": None,
        },
        "experiment": {
            "attempted": 0,
            "completed": 0,
            "predictions": 0,
            "observations": 0,
            "explanations": 0,
            "recent_attempted": 0,
            "has_full_inquiry": False,
            "latest_mass": None,
            "latest_force": None,
            "latest_acceleration": None,
            "latest_activity": None,
        },
        "tutor": {
            "student_messages": 0,
            "recent_messages": 0,
            "recent_question": "",
            "lesson": "",
            "latest_activity": None,
        },
        "latest_activity": None,
    }


def _sole_lesson_concept(lesson):
    """A lesson's concept name/topic only when it teaches exactly one concept.

    Practice attempts that do not name a concept are attributed here only when
    the attribution is unambiguous. A multi-concept lesson yields ``(None, None)``
    and the attempt is left out of the per-concept synthesis (it is never
    invented onto a concept it might not be about).
    """

    if lesson is None:
        return None, None
    concepts = list(lesson.physics_concepts.all())
    if len(concepts) == 1:
        return concepts[0].name, concepts[0].topic
    return None, None


def _concept_has_activity(bucket: dict) -> bool:
    return bool(
        bucket["practice"]["attempts"]
        or bucket["experiment"]["attempted"]
        or bucket["tutor"]["student_messages"]
    )


# --- presentation (clean context, never raw python structures) ----------


def _present_practice(bucket: dict) -> dict:
    practice = bucket["practice"]
    return {
        "concept": bucket["concept"],
        "attempts": practice["attempts"],
        "correct": practice["correct"],
        "incorrect": practice["incorrect"],
        "questions": len(practice["questions"]),
        "retry_correct": practice["retry_correct"],
        "latest_activity": practice["latest_activity"],
    }


def _present_experiment(bucket: dict) -> dict:
    experiment = bucket["experiment"]
    return {
        "concept": bucket["concept"],
        "attempted": experiment["attempted"],
        "completed": experiment["completed"],
        "predictions": experiment["predictions"],
        "observations": experiment["observations"],
        "explanations": experiment["explanations"],
        "latest_mass": experiment["latest_mass"],
        "latest_force": experiment["latest_force"],
        "latest_acceleration": experiment["latest_acceleration"],
        "latest_activity": experiment["latest_activity"],
    }


def _present_tutor(bucket: dict) -> dict:
    tutor = bucket["tutor"]
    return {
        "concept": bucket["concept"],
        "student_messages": tutor["student_messages"],
        "recent_question": tutor["recent_question"],
        "lesson": tutor["lesson"],
        "latest_activity": tutor["latest_activity"],
    }


def _present_concept(bucket: dict) -> dict:
    modes = []
    if bucket["practice"]["attempts"]:
        modes.append("practice")
    if bucket["experiment"]["attempted"]:
        modes.append("experiment")
    if bucket["tutor"]["student_messages"]:
        modes.append("tutor")
    return {
        "concept": bucket["concept"],
        "topic": bucket["topic"],
        "latest_activity": bucket["latest_activity"],
        "modes": modes,
        "practice": _present_practice(bucket),
        "experiment": _present_experiment(bucket),
        "tutor": _present_tutor(bucket),
    }


# --- learning signals (transparent rules over observed activity) --------


def _signals(active: list[dict]) -> list[dict]:
    found: list[tuple[str, str, str]] = []
    for bucket in active:
        name = bucket["concept"]
        practice = bucket["practice"]
        experiment = bucket["experiment"]
        tutor = bucket["tutor"]

        if practice["retry_correct"] >= 1:
            found.append(
                (
                    SIGNAL_RETRY_CORRECT,
                    name,
                    f"You returned to a practice question about {name} and later "
                    "answered it correctly.",
                )
            )
        if experiment["has_full_inquiry"]:
            found.append(
                (
                    SIGNAL_INQUIRY_SEQUENCE,
                    name,
                    f"You completed a full Physics Lab inquiry for {name} — "
                    "a prediction, an observation and an explanation.",
                )
            )
        # "been exploring ... " -> present tense, so it needs *recent* activity
        # on both sides.
        if tutor["recent_messages"] >= 1 and experiment["recent_attempted"] >= 1:
            found.append(
                (
                    SIGNAL_TUTOR_AND_LAB,
                    name,
                    f"You've been exploring {name} through both the Physics Tutor "
                    "and the Physics Lab.",
                )
            )
        # "have worked with ... " -> any time in the loaded history is enough.
        if practice["attempts"] >= 1 and experiment["attempted"] >= 1:
            found.append(
                (
                    SIGNAL_PRACTICE_AND_LAB,
                    name,
                    f"You've worked with {name} through both practice and experiment.",
                )
            )
        if practice["recent_attempts"] >= REPEATED_PRACTICE_THRESHOLD:
            found.append(
                (
                    SIGNAL_REPEATED_PRACTICE,
                    name,
                    f"You've practiced {name} several times recently.",
                )
            )

    # "practice and lab" is subsumed by "tutor and lab" for the same concept.
    tutor_lab_concepts = {
        name for code, name, _ in found if code == SIGNAL_TUTOR_AND_LAB
    }
    found = [
        row
        for row in found
        if not (row[0] == SIGNAL_PRACTICE_AND_LAB and row[1] in tutor_lab_concepts)
    ]

    rank = {code: index for index, code in enumerate(_SIGNAL_ORDER)}
    # Total order: signal priority, then concept name -- never input order.
    found.sort(key=lambda row: (rank.get(row[0], len(_SIGNAL_ORDER)), row[1]))
    return [
        {"code": code, "concept": name, "text": text}
        for code, name, text in found[:SIGNAL_LIMIT]
    ]


# --- deterministic next investigation ----------------------------------


_URL_LABELS = {
    "physics_lab": "Physics Lab",
    "recommendations": "Recommendations",
    "practice": "Practice",
    "tutor": "Physics Tutor",
    "lessons": "Lessons",
}


def _step(text: str, url: str, label: str, code: str = "fallback") -> dict:
    # ``code`` lets a caller tell an unfinished/teacher-directed step apart from
    # a generic fallback (used by the concept-graph path engine in Step 20).
    return {"text": text, "url": url, "url_label": label, "code": code}


def _next_investigation(
    *,
    active: list[dict],
    experiments: list[ExperimentAttempt],
    sim_concepts: set[str],
    concept_lesson: dict[str, dict],
    pending_recs: int,
    has_activity: bool,
) -> dict:
    lab_url = reverse("physics_lab:index")
    lessons_url = reverse("students:lessons")

    # Rule 1 -- an experiment left unfinished takes priority.
    incomplete = next((e for e in experiments if not e.is_complete), None)
    if incomplete is not None:
        prediction = (incomplete.prediction or "").strip()
        observation = (incomplete.observation or "").strip()
        explanation = (incomplete.explanation or "").strip()
        if prediction and not observation:
            return _step(
                "Return to the Physics Lab and record what happened.",
                lab_url,
                _URL_LABELS["physics_lab"],
                "incomplete_experiment",
            )
        if observation and not explanation:
            return _step(
                "Explain what you think caused the result.",
                lab_url,
                _URL_LABELS["physics_lab"],
                "incomplete_experiment",
            )
        return _step(
            "Return to the Physics Lab and finish your experiment.",
            lab_url,
            _URL_LABELS["physics_lab"],
            "incomplete_experiment",
        )

    # Rule 2 -- an unopened teacher recommendation is the next step.
    if pending_recs:
        return _step(
            "Your teacher suggested a next step — open your recommendations.",
            reverse("students:recommendations"),
            _URL_LABELS["recommendations"],
            "pending_recommendation",
        )

    # Rule 3 -- completed a lab for a concept but never practiced it.
    for bucket in active:
        if bucket["experiment"]["completed"] >= 1 and bucket["practice"]["attempts"] == 0:
            lesson = concept_lesson.get(bucket["concept"])
            if lesson:
                return _step(
                    f"Try a practice problem about {bucket['concept']}.",
                    reverse("students:practice", args=[lesson["slug"]]),
                    _URL_LABELS["practice"],
                    "practice_after_lab",
                )
            return _step(
                f"Try a practice problem about {bucket['concept']}.",
                lessons_url,
                _URL_LABELS["lessons"],
                "practice_after_lab",
            )

    # Rule 4 -- practiced a concept but never investigated it in the Lab.
    for bucket in active:
        if (
            bucket["practice"]["attempts"] >= 1
            and bucket["experiment"]["attempted"] == 0
            and bucket["concept"] in sim_concepts
        ):
            return _step(
                f"Investigate {bucket['concept']} in the Physics Lab.",
                lab_url,
                _URL_LABELS["physics_lab"],
                "lab_after_practice",
            )

    # Rule 5 -- practice and lab for a concept, but no recent tutor discussion.
    for bucket in active:
        if (
            bucket["practice"]["attempts"] >= 1
            and bucket["experiment"]["attempted"] >= 1
            and bucket["tutor"]["recent_messages"] == 0
        ):
            lesson = concept_lesson.get(bucket["concept"])
            if lesson:
                return _step(
                    "Discuss your result with the Physics Tutor.",
                    reverse("students:tutor", args=[lesson["slug"]]),
                    _URL_LABELS["tutor"],
                    "tutor_after_both",
                )
            return _step(
                "Discuss your result with the Physics Tutor.",
                lessons_url,
                _URL_LABELS["tutor"],
                "tutor_after_both",
            )

    # Rule 6 -- fall back to open exploration.
    if not has_activity:
        return _step(
            "Start with a lesson, a practice problem, the Physics Lab, or a Tutor question.",
            lessons_url,
            _URL_LABELS["lessons"],
            "start",
        )
    return _step(
        "Choose another Physics activity and keep investigating.",
        lessons_url,
        _URL_LABELS["lessons"],
        "fallback",
    )


# --- public API --------------------------------------------------------


def build_student_learning_patterns(
    *, student, now=None, include_next_investigation: bool = True
) -> dict:
    """Return a deterministic, read-only pattern projection for one student.

    ``include_next_investigation=False`` skips the next-step rules and their one
    extra query -- used by the teacher workspace, which shows the synthesis but
    not the student's personal next step.
    """

    now = now or timezone.now()
    cutoff = now - timedelta(days=RECENT_WINDOW_DAYS)

    # Keep the NEWEST attempts (like the other two sources), then walk them
    # oldest-first so retry detection sees an incorrect attempt before its
    # later correct one.
    practice_rows = list(
        PracticeAttempt.objects.filter(student=student)
        .select_related("concept", "lesson")
        .prefetch_related("lesson__physics_concepts")
        .order_by("-created_at", "-attempt_number", "-id")[:MAX_PRACTICE_ROWS]
    )
    practice_rows.reverse()
    experiment_rows = list(
        ExperimentAttempt.objects.filter(student=student)
        .select_related("simulation", "simulation__concept", "lesson")
        .prefetch_related("lesson__physics_concepts")
        .order_by("-started_at", "-id")[:MAX_EXPERIMENT_ROWS]
    )
    tutor_rows = list(
        TutorMessage.objects.filter(
            session__student=student, role=TutorMessage.Role.STUDENT
        )
        .select_related("session", "session__lesson")
        .prefetch_related("session__lesson__physics_concepts")
        .order_by("-created_at", "-id")[:MAX_TUTOR_ROWS]
    )

    has_activity = bool(practice_rows or experiment_rows or tutor_rows)

    concepts: dict[str, dict] = {}
    concept_lesson: dict[str, dict] = {}

    def bucket_for(name: str, topic: str) -> dict:
        entry = concepts.get(name)
        if entry is None:
            entry = _new_concept(name, topic)
            concepts[name] = entry
        elif topic and not entry["topic"]:
            entry["topic"] = topic
        return entry

    def note_lesson(name: str, lesson, when) -> None:
        if not name or lesson is None or when is None:
            return
        current = concept_lesson.get(name)
        if current is None or when > current["when"]:
            concept_lesson[name] = {
                "slug": lesson.slug,
                "title": lesson.title,
                "when": when,
            }

    # --- practice ---------------------------------------------------
    question_state: dict[tuple, dict] = {}
    for attempt in practice_rows:
        if attempt.concept_id:
            name, topic = attempt.concept.name, attempt.concept.topic
        else:
            name, topic = _sole_lesson_concept(attempt.lesson)
        if not name:
            continue  # ambiguous concept -- never guessed onto one

        bucket = bucket_for(name, topic)
        practice = bucket["practice"]
        practice["attempts"] += 1
        if attempt.is_correct is True:
            practice["correct"] += 1
        elif attempt.is_correct is False:
            practice["incorrect"] += 1
        # A question is identified by (lesson, key): the default keys are
        # positional ("q1", "q2"...) and only unique within a lesson.
        question_id = (attempt.lesson_id, attempt.question_key)
        practice["questions"].add(question_id)
        if attempt.created_at >= cutoff:
            practice["recent_attempts"] += 1
        practice["latest_activity"] = _later(practice["latest_activity"], attempt.created_at)
        bucket["latest_activity"] = _later(bucket["latest_activity"], attempt.created_at)

        state = question_state.setdefault(
            question_id, {"seen_incorrect": False, "counted": False}
        )
        if attempt.is_correct is False:
            state["seen_incorrect"] = True
        elif attempt.is_correct is True and state["seen_incorrect"] and not state["counted"]:
            practice["retry_correct"] += 1
            state["counted"] = True

        note_lesson(name, attempt.lesson, attempt.created_at)

    # --- experiments (newest first, so the first seen per concept is latest) ---
    for attempt in experiment_rows:
        concept = attempt.simulation.concept
        name, topic = concept.name, concept.topic
        bucket = bucket_for(name, topic)
        experiment = bucket["experiment"]
        when = attempt.updated_at or attempt.started_at

        experiment["attempted"] += 1
        if when >= cutoff:
            experiment["recent_attempted"] += 1
        if attempt.is_complete:
            experiment["completed"] += 1

        prediction = (attempt.prediction or "").strip()
        observation = (attempt.observation or "").strip()
        explanation = (attempt.explanation or "").strip()
        if prediction:
            experiment["predictions"] += 1
        if observation:
            experiment["observations"] += 1
        if explanation:
            experiment["explanations"] += 1
        if prediction and observation and explanation:
            experiment["has_full_inquiry"] = True

        if experiment["latest_activity"] is None:
            experiment["latest_activity"] = when
            experiment["latest_mass"] = attempt.mass_kg
            experiment["latest_force"] = attempt.force_n
            experiment["latest_acceleration"] = attempt.acceleration_m_s2

        bucket["latest_activity"] = _later(bucket["latest_activity"], when)
        # Only deep-link a concept to a lesson that actually teaches it: an
        # experiment's ``lesson`` is a loose FK and need not match its concept.
        if attempt.lesson_id and any(
            c.pk == concept.pk for c in attempt.lesson.physics_concepts.all()
        ):
            note_lesson(name, attempt.lesson, when)

    # --- tutor (student messages only; newest first) ---------------
    # A tutor question is attributed to a concept only when its lesson teaches
    # exactly one -- the same "no ambiguous attribution" rule used for practice.
    for message in tutor_rows:
        lesson = message.session.lesson
        name, topic = _sole_lesson_concept(lesson)
        if not name:
            continue
        bucket = bucket_for(name, topic)
        tutor = bucket["tutor"]
        tutor["student_messages"] += 1
        if message.created_at >= cutoff:
            tutor["recent_messages"] += 1
        if not tutor["recent_question"]:
            tutor["recent_question"] = _clip(message.content, RECENT_QUESTION_MAXLEN)
            tutor["lesson"] = lesson.title
        tutor["latest_activity"] = _later(tutor["latest_activity"], message.created_at)
        bucket["latest_activity"] = _later(bucket["latest_activity"], message.created_at)
        note_lesson(name, lesson, message.created_at)

    # --- assemble --------------------------------------------------
    # Total, stable order (newest activity first, concept name breaks ties).
    active_all = [b for b in concepts.values() if _concept_has_activity(b)]
    active_all.sort(
        key=lambda b: (b["latest_activity"] or cutoff, b["concept"]), reverse=True
    )
    # Signals and the next-step rules consider every touched concept; only the
    # on-page lists are truncated for readability.
    active_display = active_all[:CONCEPT_LIMIT]

    recent_concepts = [
        b["concept"]
        for b in active_all
        if b["latest_activity"] and b["latest_activity"] >= cutoff
    ][:RECENT_CONCEPT_LIMIT]

    concept_activity = [_present_concept(b) for b in active_display]
    practice_patterns = [
        _present_practice(b) for b in active_display if b["practice"]["attempts"] > 0
    ]
    experiment_patterns = [
        _present_experiment(b)
        for b in active_display
        if b["experiment"]["attempted"] > 0
    ]
    tutor_patterns = [
        _present_tutor(b)
        for b in active_display
        if b["tutor"]["student_messages"] > 0
    ]
    signals = _signals(active_all)

    next_investigation = None
    if include_next_investigation:
        sim_concepts = set(
            PhysicsSimulation.objects.filter(is_active=True).values_list(
                "concept__name", flat=True
            )
        )
        from apps.teachers.services import count_pending_recommendations

        next_investigation = _next_investigation(
            active=active_all,
            experiments=experiment_rows,
            sim_concepts=sim_concepts,
            concept_lesson=concept_lesson,
            pending_recs=count_pending_recommendations(student),
            has_activity=has_activity,
        )

    return {
        "has_activity": has_activity,
        "recency_days": RECENT_WINDOW_DAYS,
        "recent_concepts": recent_concepts,
        "concept_activity": concept_activity,
        "practice_patterns": practice_patterns,
        "experiment_patterns": experiment_patterns,
        "tutor_patterns": tutor_patterns,
        "signals": signals,
        "next_investigation": next_investigation,
    }
