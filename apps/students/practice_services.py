"""Deterministic Physics practice: server-evaluated attempts as learning evidence.

No LLM ever decides whether a numeric or multiple-choice answer is correct.
Evaluation is pure arithmetic against trusted lesson data (``Lesson.problems``),
independently testable and free of database writes. The existing misconception
engine is consulted only for explanatory *text*; a bare number carries no
semantic signal and never triggers a diagnosis.

Question shapes accepted in ``Lesson.problems`` (a JSON list):

* a plain string -> a free-text prompt (no deterministic grading); this is the
  historic shape and it keeps working unchanged.
* a dict with a stable ``key`` and a ``type``:

    {"key": "nsl-1", "type": "numeric",
     "prompt": "A 20 N net force acts on a 2 kg cart. Find its acceleration.",
     "answer": 10, "unit": "m/s^2", "tolerance": 0.1,
     "concept": "Newton's Second Law", "hint": "Start from a = F / m."}

    {"key": "nsl-2", "type": "multiple_choice",
     "prompt": "Doubling the net force on a fixed mass ...",
     "choices": ["halves a", "doubles a", "no change"], "answer": 1,
     "concept": "Newton's Second Law"}

Anything malformed (a numeric question with no readable answer, a choice
question with fewer than two options) degrades to a free-text prompt rather
than raising.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from django.db import transaction
from django.urls import reverse
from django.utils.http import urlencode

from .misconception_services import assess_student_misconceptions
from .models import LearningEvidence, PracticeAttempt

logger = logging.getLogger(__name__)

# --- limits & policy ---------------------------------------------------------

MAX_PROBLEMS = 50
MAX_KEY_LEN = 100
ANSWER_MAX_LEN = 200
DEFAULT_REL_TOLERANCE = 0.01
DEFAULT_ABS_TOLERANCE = 0.01
# After this many wrong tries the expected answer is shown so nobody stays stuck.
REVEAL_AFTER_ATTEMPTS = 3

_Q = PracticeAttempt.QuestionType

# Deterministic hints are offered ONLY for concepts we genuinely support. The
# equation is a fixed reference string, never invented per question.
SUPPORTED_HINT_EQUATIONS = {
    "newton's second law": "a = F / m",
    "newtons second law": "a = F / m",
    "acceleration": "a = F / m",
    "speed": "v = d / t",
    "velocity": "v = d / t",
    "average speed": "v = d / t",
    "density": "ρ = m / V",
}


class PracticeError(ValueError):
    """The question could not be resolved from trusted lesson data."""


class AnswerValidationError(ValueError):
    """The student's submitted answer was empty or not a usable value."""


# --- pure evaluation (no database) -----------------------------------------


@dataclass(frozen=True)
class NumericEvaluation:
    is_correct: bool
    submitted_value: float
    expected_value: float
    tolerance: float


@dataclass(frozen=True)
class ChoiceEvaluation:
    is_correct: bool
    submitted_index: int
    submitted_label: str
    expected_index: int
    expected_label: str


def _resolve_tolerance(expected: float, tolerance) -> float:
    if tolerance is not None:
        try:
            tol = abs(float(tolerance))
        except (TypeError, ValueError):
            tol = None
        if tol is not None and math.isfinite(tol):
            return tol
    return max(abs(expected) * DEFAULT_REL_TOLERANCE, DEFAULT_ABS_TOLERANCE)


def _coerce_number(raw) -> float:
    """Parse a student-entered number. Reject empty / non-numeric / NaN / inf."""

    text = re.sub(r"\s+", " ", str(raw if raw is not None else "")).strip()
    if not text:
        raise AnswerValidationError("Enter an answer before submitting.")
    if len(text) > ANSWER_MAX_LEN:
        raise AnswerValidationError("That answer is too long. Keep it short.")
    cleaned = text.replace(",", "")
    try:
        value = float(cleaned)
    except (TypeError, ValueError):
        raise AnswerValidationError(
            "Enter your answer as a number, for example 9.8."
        )
    if not math.isfinite(value):
        raise AnswerValidationError("Enter a finite number.")
    return value


def evaluate_numeric_answer(submitted_value, expected_value, tolerance=None) -> NumericEvaluation:
    """Compare a submitted number to a trusted expected value within a tolerance.

    Pure: no database, no AI. Raises :class:`AnswerValidationError` if the
    submitted text is not a finite number.
    """

    expected = float(expected_value)
    tol = _resolve_tolerance(expected, tolerance)
    value = _coerce_number(submitted_value)
    is_correct = abs(value - expected) <= tol + 1e-12
    return NumericEvaluation(
        is_correct=is_correct,
        submitted_value=value,
        expected_value=expected,
        tolerance=tol,
    )


def _normalise_choice_labels(choices) -> list[str]:
    if not isinstance(choices, (list, tuple)):
        return []
    labels = [re.sub(r"\s+", " ", str(c)).strip() for c in choices]
    return [label for label in labels if label]


def _expected_choice_index(correct_choice, labels: list[str]) -> int:
    """Accept an integer index or the exact text of the correct option."""

    if isinstance(correct_choice, bool):  # guard: bool is an int subclass
        raise PracticeError("This practice question has an invalid answer key.")
    if isinstance(correct_choice, int):
        if 0 <= correct_choice < len(labels):
            return correct_choice
        raise PracticeError("This practice question has an out-of-range answer key.")
    text = re.sub(r"\s+", " ", str(correct_choice if correct_choice is not None else "")).strip()
    if text.isdigit():
        idx = int(text)
        if 0 <= idx < len(labels):
            return idx
    lowered = [label.lower() for label in labels]
    if text.lower() in lowered:
        return lowered.index(text.lower())
    raise PracticeError("This practice question has an invalid answer key.")


def evaluate_choice_answer(submitted_choice, choices, correct_choice) -> ChoiceEvaluation:
    """Match a submitted choice (index or exact label) against the correct one.

    Pure: no database, no AI. Raises :class:`PracticeError` for malformed
    question data and :class:`AnswerValidationError` for an unusable submission.
    """

    labels = _normalise_choice_labels(choices)
    if len(labels) < 2:
        raise PracticeError("This practice question does not have enough choices.")

    expected_index = _expected_choice_index(correct_choice, labels)

    submitted = re.sub(r"\s+", " ", str(submitted_choice if submitted_choice is not None else "")).strip()
    if not submitted:
        raise AnswerValidationError("Choose an answer before submitting.")
    if len(submitted) > ANSWER_MAX_LEN:
        raise AnswerValidationError("That answer is too long.")

    submitted_index = None
    if submitted.isdigit():
        idx = int(submitted)
        if 0 <= idx < len(labels):
            submitted_index = idx
    if submitted_index is None:
        lowered = [label.lower() for label in labels]
        if submitted.lower() in lowered:
            submitted_index = lowered.index(submitted.lower())
    if submitted_index is None:
        raise AnswerValidationError("That is not one of the available choices.")

    return ChoiceEvaluation(
        is_correct=submitted_index == expected_index,
        submitted_index=submitted_index,
        submitted_label=labels[submitted_index],
        expected_index=expected_index,
        expected_label=labels[expected_index],
    )


# --- reading questions out of trusted lesson data --------------------------


@dataclass(frozen=True)
class PracticeQuestion:
    """A student-safe view of one question -- carries no answer or tolerance."""

    key: str
    number: int  # 1-based, among renderable questions
    total: int
    type: str
    prompt: str
    unit: str
    choices: tuple[str, ...]
    concept: str
    has_hint: bool


def _raw_problems(lesson) -> list:
    items = getattr(lesson, "problems", None)
    if not isinstance(items, list):
        return []
    return items[:MAX_PROBLEMS]


def _raw_prompt(raw) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for field in ("prompt", "problem", "question", "text"):
            value = raw.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _raw_key(raw, position: int) -> str:
    if isinstance(raw, dict):
        for field in ("key", "id", "slug"):
            value = raw.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()[:MAX_KEY_LEN]
    return f"q{position + 1}"


def _raw_type(raw) -> str:
    if isinstance(raw, dict):
        declared = str(raw.get("type") or "").strip().lower().replace("-", "_")
        if declared in {"numeric", "number", "num"}:
            return _Q.NUMERIC
        if declared in {"multiple_choice", "choice", "mcq", "multiplechoice"}:
            return _Q.MULTIPLE_CHOICE
    return _Q.FREE_TEXT


def _raw_concept_name(raw) -> str:
    if isinstance(raw, dict):
        value = raw.get("concept") or raw.get("concept_name")
        if isinstance(value, str):
            return value.strip()
    return ""


def _numeric_spec(raw):
    """(expected_value, tolerance_or_None, unit) for a numeric question, or None."""

    if not isinstance(raw, dict):
        return None
    for field in ("answer", "expected", "expected_value", "value", "correct_answer"):
        if field not in raw or raw[field] is None:
            continue
        candidate = raw[field]
        if isinstance(candidate, bool):
            return None
        try:
            expected = float(candidate)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(expected):
            return None
        tolerance = raw.get("tolerance")
        if tolerance is not None:
            try:
                tolerance = abs(float(tolerance))
            except (TypeError, ValueError):
                tolerance = None
            else:
                if not math.isfinite(tolerance):
                    tolerance = None
        unit = str(raw.get("unit") or "").strip()
        return expected, tolerance, unit
    return None


def _choice_spec(raw):
    """(labels, expected_index) for a multiple-choice question, or None."""

    if not isinstance(raw, dict):
        return None
    labels = _normalise_choice_labels(raw.get("choices"))
    if len(labels) < 2:
        return None
    for field in ("answer", "correct_choice", "correct", "correct_index", "expected"):
        if field not in raw or raw[field] is None:
            continue
        try:
            expected_index = _expected_choice_index(raw[field], labels)
        except PracticeError:
            return None
        return labels, expected_index
    return None


def _effective_type(raw, declared_type: str) -> str:
    """Downgrade a structured question to free-text if its data is unusable."""

    if declared_type == _Q.NUMERIC and _numeric_spec(raw) is None:
        return _Q.FREE_TEXT
    if declared_type == _Q.MULTIPLE_CHOICE and _choice_spec(raw) is None:
        return _Q.FREE_TEXT
    return declared_type


def get_practice_questions(lesson) -> list[PracticeQuestion]:
    """Trusted, student-safe list of the lesson's renderable practice questions."""

    renderable = []
    seen_keys: set[str] = set()
    for position, raw in enumerate(_raw_problems(lesson)):
        prompt = _raw_prompt(raw)
        if not prompt:
            continue
        key = _raw_key(raw, position)
        while key in seen_keys:
            key = f"{key}-{position + 1}"
        seen_keys.add(key)
        renderable.append((key, raw, prompt))

    total = len(renderable)
    questions: list[PracticeQuestion] = []
    for index, (key, raw, prompt) in enumerate(renderable):
        qtype = _effective_type(raw, _raw_type(raw))
        unit = ""
        choices: tuple[str, ...] = ()
        if qtype == _Q.NUMERIC:
            spec = _numeric_spec(raw)
            unit = spec[2] if spec else ""
        elif qtype == _Q.MULTIPLE_CHOICE:
            spec = _choice_spec(raw)
            choices = tuple(spec[0]) if spec else ()
        questions.append(
            PracticeQuestion(
                key=key,
                number=index + 1,
                total=total,
                type=qtype,
                prompt=prompt,
                unit=unit,
                choices=choices,
                concept=_raw_concept_name(raw),
                has_hint=bool(isinstance(raw, dict) and str(raw.get("hint") or "").strip()),
            )
        )
    return questions


def _resolve_raw(lesson, question_key: str):
    """Return ``(key, raw_problem)`` for a key that belongs to *this* lesson."""

    key = re.sub(r"\s+", " ", str(question_key or "")).strip()
    if not key or len(key) > MAX_KEY_LEN:
        raise PracticeError("That practice question could not be found.")
    seen_keys: set[str] = set()
    for position, raw in enumerate(_raw_problems(lesson)):
        if not _raw_prompt(raw):
            continue
        resolved = _raw_key(raw, position)
        while resolved in seen_keys:
            resolved = f"{resolved}-{position + 1}"
        seen_keys.add(resolved)
        if resolved == key:
            return resolved, raw
    raise PracticeError("That practice question could not be found.")


def _match_concept(lesson, raw):
    """Link the attempt to one of the lesson's own concepts, by name. Never invents."""

    name = _raw_concept_name(raw)
    if not name:
        return None
    lowered = name.lower()
    for concept in lesson.physics_concepts.all():
        if concept.name.lower() == lowered:
            return concept
    return None


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4g}"


def _has_explanatory_text(qtype: str, text: str) -> bool:
    """True only when the answer is prose worth sending to the misconception engine."""

    if qtype == _Q.NUMERIC:
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    return len([w for w in re.split(r"\s+", text.strip()) if w]) >= 3


# --- recording an attempt (transactional) --------------------------------


@transaction.atomic
def record_practice_attempt(
    *,
    student,
    lesson,
    question_key,
    submitted_answer,
    session=None,
    assess: bool = True,
    provider=None,
) -> PracticeAttempt:
    """Evaluate one answer against trusted lesson data and persist the attempt.

    Writes a :class:`PracticeAttempt` and a matching ``PRACTICE_ATTEMPTED``
    :class:`LearningEvidence` row in one transaction. A retry is always a new
    row. The misconception engine is called afterwards for explanatory wrong
    *text* only; its failure is logged and never rolls back the attempt.
    """

    key, raw = _resolve_raw(lesson, question_key)
    prompt = _raw_prompt(raw)
    qtype = _effective_type(raw, _raw_type(raw))
    concept = _match_concept(lesson, raw)

    answer_text = re.sub(r"\s+", " ", str(submitted_answer if submitted_answer is not None else "")).strip()
    if not answer_text:
        raise AnswerValidationError("Enter an answer before submitting.")
    if len(answer_text) > ANSWER_MAX_LEN:
        raise AnswerValidationError("That answer is too long. Keep it short.")

    is_correct = None
    expected_display = ""

    if qtype == _Q.NUMERIC:
        expected, tolerance, unit = _numeric_spec(raw)
        evaluation = evaluate_numeric_answer(answer_text, expected, tolerance)
        is_correct = evaluation.is_correct
        expected_display = _format_number(expected)
        if unit:
            expected_display = f"{expected_display} {unit}"
    elif qtype == _Q.MULTIPLE_CHOICE:
        labels, expected_index = _choice_spec(raw)
        evaluation = evaluate_choice_answer(answer_text, labels, expected_index)
        is_correct = evaluation.is_correct
        answer_text = evaluation.submitted_label
        expected_display = evaluation.expected_label

    attempt_number = (
        PracticeAttempt.objects.filter(
            student=student, lesson=lesson, question_key=key
        ).count()
        + 1
    )

    context = {
        "practice": True,
        "question_key": key,
        "question_type": qtype,
        "attempt_number": attempt_number,
    }
    concept_name = concept.name if concept is not None else _raw_concept_name(raw)
    if concept_name:
        context["concept"] = concept_name
    if is_correct is not None:
        context["is_correct"] = is_correct

    evidence = LearningEvidence.objects.create(
        student=student,
        lesson=lesson,
        session=session,
        kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED,
        detail=answer_text[:300],
        context=context,
    )
    attempt = PracticeAttempt.objects.create(
        student=student,
        lesson=lesson,
        session=session,
        concept=concept,
        evidence=evidence,
        question_key=key,
        question_type=qtype,
        question_prompt=prompt[:500],
        answer_text=answer_text[:500],
        is_correct=is_correct,
        attempt_number=attempt_number,
        expected_display=expected_display[:200],
    )

    if assess and is_correct is not True and _has_explanatory_text(qtype, answer_text):
        try:
            assess_student_misconceptions(
                student=student,
                lesson=lesson,
                text=answer_text,
                learning_evidence=evidence,
                tutor_message=None,
                provider=provider,
            )
        except Exception:  # pragma: no cover - defensive; must not lose the attempt
            logger.exception(
                "Misconception assessment failed for practice attempt %s.", attempt.pk
            )

    return attempt


# --- deterministic feedback ---------------------------------------------


def _deterministic_hint(attempt: PracticeAttempt, raw) -> str:
    if isinstance(raw, dict):
        explicit = str(raw.get("hint") or "").strip()
        if explicit:
            return explicit[:300]
    name = ""
    if attempt.concept_id and attempt.concept is not None:
        name = attempt.concept.name.strip().lower()
    if not name:
        name = _raw_concept_name(raw).lower()
    equation = SUPPORTED_HINT_EQUATIONS.get(name)
    if equation:
        return f"Start from {equation} and substitute the values given in the question."
    return ""


def build_practice_feedback(attempt: PracticeAttempt, *, lesson, reveal: bool = False) -> dict:
    """Deterministic, non-judgemental feedback for one recorded attempt."""

    try:
        _key, raw = _resolve_raw(lesson, attempt.question_key)
    except PracticeError:
        raw = None

    hint = _deterministic_hint(attempt, raw)

    if attempt.is_correct is True:
        body = "Your answer matches the expected result."
        if attempt.expected_display:
            body = f"Correct — the expected result is {attempt.expected_display}."
        return {
            "status": "correct",
            "headline": "Correct.",
            "body": body,
            "hint": "",
            "expected_display": attempt.expected_display,
            "can_retry": False,
            "offer_tutor": False,
        }

    if attempt.is_correct is False:
        reveal_now = reveal or attempt.attempt_number >= REVEAL_AFTER_ATTEMPTS
        return {
            "status": "incorrect",
            "headline": "Not quite.",
            "body": (
                "That is not the expected answer. Check your working and try again."
                if not reveal_now
                else "That is still not the expected answer."
            ),
            "hint": hint,
            "expected_display": attempt.expected_display if reveal_now else "",
            "can_retry": True,
            "offer_tutor": True,
        }

    return {
        "status": "recorded",
        "headline": "Answer recorded.",
        "body": (
            "There is no single value to check here. Take your reasoning to the "
            "Physics Tutor to talk it through."
        ),
        "hint": hint,
        "expected_display": "",
        "can_retry": True,
        "offer_tutor": True,
    }


def practice_tutor_url(lesson, attempt: PracticeAttempt) -> str:
    """A safe pre-fill link into the existing tutor flow. No internal labels."""

    if attempt.is_correct is False:
        outcome = "was marked not correct"
    elif attempt.is_correct is True:
        outcome = "was marked correct"
    else:
        outcome = "was recorded for discussion"
    prefill = (
        f'I am working on this practice question: "{attempt.question_prompt}". '
        f'My answer "{attempt.answer_text}" {outcome}. '
        "Can you help me understand how to approach it?"
    )
    return f"{reverse('students:tutor', args=[lesson.slug])}?{urlencode({'prefill': prefill})}"


# --- page assembly (keeps the view thin) -------------------------------


def build_practice_page(
    *,
    lesson,
    student,
    current_key: str | None = None,
    last_feedback: dict | None = None,
    error: str = "",
) -> dict:
    """Everything ``students/practice.html`` needs for one student and lesson."""

    questions = get_practice_questions(lesson)
    question_keys = [q.key for q in questions]
    key_set = set(question_keys)

    attempts = list(
        PracticeAttempt.objects.filter(student=student, lesson=lesson)
        .order_by("created_at", "id")
    )
    by_key: dict[str, list[PracticeAttempt]] = {}
    for attempt in attempts:
        by_key.setdefault(attempt.question_key, []).append(attempt)

    def is_answered(key: str) -> bool:
        return bool(by_key.get(key))

    def is_correct(key: str) -> bool:
        return any(a.is_correct is True for a in by_key.get(key, []))

    current = None
    if current_key and current_key in key_set:
        current = next(q for q in questions if q.key == current_key)
    if current is None:
        current = next((q for q in questions if not is_answered(q.key)), None)
    if current is None and questions:
        current = questions[0]

    nav = [
        {
            "key": q.key,
            "number": q.number,
            "answered": is_answered(q.key),
            "correct": is_correct(q.key),
            "is_current": current is not None and q.key == current.key,
        }
        for q in questions
    ]

    current_history = by_key.get(current.key, []) if current is not None else []

    answered_count = sum(1 for key in question_keys if is_answered(key))
    correct_count = sum(1 for key in question_keys if is_correct(key))
    scored_attempts = [a for a in attempts if a.question_key in key_set]

    discuss_url = ""
    if last_feedback and last_feedback.get("offer_tutor") and current_history:
        discuss_url = practice_tutor_url(lesson, current_history[-1])

    return {
        "lesson": lesson,
        "practice_questions": questions,
        "practice_has_questions": bool(questions),
        "practice_nav": nav,
        "current_question": current,
        "current_history": current_history,
        "practice_total": len(questions),
        "practice_answered": answered_count,
        "practice_correct": correct_count,
        "practice_incorrect": max(answered_count - correct_count, 0),
        "practice_complete": bool(questions) and answered_count >= len(questions),
        "practice_attempt_total": len(scored_attempts),
        "last_feedback": last_feedback,
        "practice_error": error,
        "discuss_url": discuss_url,
    }
