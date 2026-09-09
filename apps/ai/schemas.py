from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field

from .exceptions import InvalidLessonDraftError, InvalidLessonReviewError

# --- schema / draft versions ---------------------------------------------

LESSON_DRAFT_SCHEMA_V1 = "lesson-draft-v1"
LESSON_DRAFT_SCHEMA_V2 = "lesson-draft-v2"

# A generated activity may *suggest* one of these instructional types. It is
# advisory only -- it never creates a real ``LessonActivity`` (Step 26 owns
# that). Kept in sync with the types Step 26 authoring can actually accept
# (``concept_check`` maps to a practice activity there; ``recovery`` is
# teacher-only and never AI-suggested here).
GENERATED_ACTIVITY_TYPES = frozenset(
    {"explanation", "physics_lab", "practice", "concept_check", "tutor", "assessment"}
)
SUGGESTION_DIFFICULTIES = frozenset({"easy", "medium", "hard"})

# Guard rails for numeric AI output.
MAX_ESTIMATED_MINUTES = 600
MAX_OBJECTIVE_INDEX = 200
MAX_LIST_ITEMS = 60

LESSON_DRAFT_JSON_SCHEMA = {
    "schema_version": "lesson-draft-v2",
    "title": "string",
    "overview": "string",
    "learning_objectives": ["string"],
    "prerequisites": ["string"],
    "key_concepts": ["string"],
    "explanation": "string",
    "worked_examples": [
        {"title": "string", "problem": "string", "solution": "string"},
    ],
    "activities": [
        {"title": "string", "description": "string"},
    ],
    "assessment_questions": [
        {"question": "string", "expected_reasoning": "string"},
    ],
    "teacher_notes": ["string"],
    "activity_plan": [
        {
            "title": "string",
            "description": "string",
            "activity_type": "explanation | physics_lab | practice | concept_check | tutor | assessment",
            "objective_alignment": ["<0-based index into learning_objectives>"],
            "estimated_minutes": "<integer 1..600>",
            "instructions": "string (may be empty)",
            "simulation_type": "string (physics_lab only; must be an existing simulation type)",
        }
    ],
    "practice_suggestions": [
        {
            "prompt": "string",
            "concept": "string (an existing PhysicsConcept name)",
            "expected_reasoning": "string",
            "difficulty": "easy | medium | hard",
        }
    ],
    "assessment_suggestions": [
        {
            "question": "string",
            "expected_reasoning": "string",
            "concept": "string (an existing PhysicsConcept name)",
            "difficulty": "easy | medium | hard",
        }
    ],
    "misconception_awareness": [
        {
            "misconception_code": "string (an existing PhysicsMisconception code)",
            "why_relevant": "string",
            "instructional_note": "string",
        }
    ],
}

REVIEW_ISSUE_CATEGORIES = frozenset(
    {
        "physics",
        "units",
        "calculation",
        "pedagogy",
        "misconception",
        "clarity",
        "alignment",
    }
)
REVIEW_ISSUE_SEVERITIES = frozenset({"info", "warning", "error"})
REVIEW_ISSUE_CONFIDENCES = frozenset({"low", "medium", "high"})

LESSON_REVIEW_JSON_SCHEMA = {
    "overall_summary": "string",
    "issues": [
        {
            "category": "physics | units | calculation | pedagogy | misconception | clarity | alignment",
            "severity": "info | warning | error",
            "issue": "string",
            "explanation": "string",
            "affected_section": "string",
            "suggested_revision": "string",
            "confidence": "low | medium | high",
        }
    ],
}

_FENCE_PREFIX = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_SUFFIX = re.compile(r"\s*```$")


def example_lesson_draft_v1_dict() -> dict:
    """The pre-Step-27 payload shape (no ``schema_version``, no structured plan).

    Kept so tests can prove a historical persisted draft still parses.
    """

    return {
        "title": "Introduction to Newton's Second Law",
        "overview": (
            "Students relate net force, mass, and acceleration using F_net = ma, "
            "and confront the idea that mass alone determines acceleration."
        ),
        "learning_objectives": [
            "Calculate acceleration from net force and mass.",
            "Explain why net force, not a single force, determines acceleration.",
        ],
        "prerequisites": ["Force", "Acceleration"],
        "key_concepts": ["Force", "Newton's Second Law"],
        "explanation": (
            "Newton's second law states that an object's acceleration is determined "
            "by the net force acting on it and the object's mass. Doubling the net "
            "force doubles the acceleration; doubling the mass halves it."
        ),
        "worked_examples": [
            {
                "title": "Cart on a low-friction track",
                "problem": (
                    "A 2.0 kg cart has a net force of 6.0 N. What is its acceleration?"
                ),
                "solution": (
                    "Use a = F_net / m. a = 6.0 N / 2.0 kg = 3.0 m/s² in the direction "
                    "of the net force."
                ),
            }
        ],
        "activities": [
            {
                "title": "Predict then measure",
                "description": (
                    "Students predict how acceleration changes if mass doubles at the "
                    "same net force, then compare with a simple cart demonstration."
                ),
            }
        ],
        "assessment_questions": [
            {
                "question": (
                    "Two students pull a wagon with equal-magnitude opposite forces. "
                    "Does the wagon accelerate? Explain using net force."
                ),
                "expected_reasoning": (
                    "If the forces are equal and opposite, F_net is zero, so "
                    "acceleration is zero even though forces are present."
                ),
            }
        ],
        "teacher_notes": [
            "This is a draft. Review equations, units, and misconception language "
            "before students see the lesson."
        ],
    }


def example_lesson_draft_dict() -> dict:
    """Canonical valid v2 payload used by the fake provider and contract tests.

    Every v1 field is preserved so existing assertions keep passing; the v2
    structured-plan fields are added.
    """

    return {
        "schema_version": LESSON_DRAFT_SCHEMA_V2,
        "title": "Introduction to Newton's Second Law",
        "overview": (
            "Students relate net force, mass, and acceleration using F_net = ma, "
            "and confront the idea that mass alone determines acceleration."
        ),
        "learning_objectives": [
            "Calculate acceleration from net force and mass.",
            "Explain why net force, not a single force, determines acceleration.",
        ],
        "prerequisites": ["Force", "Acceleration"],
        "key_concepts": ["Force", "Newton's Second Law"],
        "explanation": (
            "Newton's second law states that an object's acceleration is determined "
            "by the net force acting on it and the object's mass. Doubling the net "
            "force doubles the acceleration; doubling the mass halves it."
        ),
        "worked_examples": [
            {
                "title": "Cart on a low-friction track",
                "problem": (
                    "A 2.0 kg cart has a net force of 6.0 N. What is its acceleration?"
                ),
                "solution": (
                    "Use a = F_net / m. a = 6.0 N / 2.0 kg = 3.0 m/s² in the direction "
                    "of the net force."
                ),
            }
        ],
        "activities": [
            {
                "title": "Predict then measure",
                "description": (
                    "Students predict how acceleration changes if mass doubles at the "
                    "same net force, then compare with a simple cart demonstration."
                ),
            }
        ],
        "assessment_questions": [
            {
                "question": (
                    "Two students pull a wagon with equal-magnitude opposite forces. "
                    "Does the wagon accelerate? Explain using net force."
                ),
                "expected_reasoning": (
                    "If the forces are equal and opposite, F_net is zero, so "
                    "acceleration is zero even though forces are present."
                ),
            }
        ],
        "teacher_notes": [
            "This is a draft. Review equations, units, and misconception language "
            "before students see the lesson."
        ],
        "activity_plan": [
            {
                "title": "Warm-up: forces you can feel",
                "description": (
                    "Short teacher-led discussion connecting pushes and pulls to a "
                    "change in motion, before any equations."
                ),
                "activity_type": "explanation",
                "objective_alignment": [1],
                "estimated_minutes": 8,
                "instructions": "Ask students where they have felt a force change how something moves.",
                "simulation_type": "",
            },
            {
                "title": "Predict, run, and explain the cart",
                "description": (
                    "Students predict how acceleration changes when the net force "
                    "doubles, then run the Newton's Second Law simulation and explain."
                ),
                "activity_type": "physics_lab",
                "objective_alignment": [0, 1],
                "estimated_minutes": 20,
                "instructions": "Predict before you run it. Explain any difference afterwards.",
                "simulation_type": "newtons_second_law",
            },
            {
                "title": "Check: balanced vs unbalanced forces",
                "description": (
                    "One short question distinguishing 'forces present' from "
                    "'net force is non-zero'."
                ),
                "activity_type": "concept_check",
                "objective_alignment": [1],
                "estimated_minutes": 5,
                "instructions": "",
                "simulation_type": "",
            },
        ],
        "practice_suggestions": [
            {
                "prompt": (
                    "A 4.0 kg box has a net force of 12 N acting on it. Find its "
                    "acceleration and state the direction."
                ),
                "concept": "Newton's Second Law",
                "expected_reasoning": (
                    "a = F_net / m = 12 N / 4.0 kg = 3.0 m/s^2 in the direction of the net force."
                ),
                "difficulty": "easy",
            },
            {
                "prompt": (
                    "Two forces act on a cart: 8 N right and 5 N left. The cart is "
                    "2 kg. What is its acceleration?"
                ),
                "concept": "Newton's Second Law",
                "expected_reasoning": (
                    "Net force = 8 - 5 = 3 N right, so a = 3 / 2 = 1.5 m/s^2 to the right."
                ),
                "difficulty": "medium",
            },
        ],
        "assessment_suggestions": [
            {
                "question": (
                    "A student says 'the cart is not moving, so there is no force on it.' "
                    "Evaluate this claim."
                ),
                "expected_reasoning": (
                    "Several forces can act while the net force is zero; 'not moving' "
                    "means zero net force, not zero forces."
                ),
                "concept": "Newton's Second Law",
                "difficulty": "medium",
            }
        ],
        "misconception_awareness": [
            {
                "misconception_code": "FORCE_VS_ACCELERATION",
                "why_relevant": (
                    "Students often treat 'a force is acting' as equivalent to "
                    "'the object accelerates', ignoring the net force."
                ),
                "instructional_note": (
                    "Compare a balanced-force case with an unbalanced-force case before "
                    "students predict the cart result."
                ),
            }
        ],
    }


def example_lesson_review_dict() -> dict:
    """Canonical valid review payload used by the fake provider and tests."""

    return {
        "overall_summary": (
            "The draft is broadly suitable for review, with one meaningful "
            "misconception-focused improvement to consider."
        ),
        "issues": [
            {
                "category": "misconception",
                "severity": "warning",
                "issue": "The activity could make the net-force misconception more explicit.",
                "explanation": (
                    "Students may still confuse the presence of forces with a nonzero "
                    "net force unless they compare balanced and unbalanced cases."
                ),
                "affected_section": "Activities",
                "suggested_revision": (
                    "Add a balanced-force comparison before students predict the "
                    "unbalanced-force result."
                ),
                "confidence": "high",
            }
        ],
    }


def parse_model_json(
    text: str,
    *,
    error_class: type[InvalidLessonDraftError] | type[InvalidLessonReviewError] = InvalidLessonDraftError,
) -> dict:
    """Parse a model response into a JSON object, allowing optional markdown fences."""

    if not isinstance(text, str) or not text.strip():
        raise error_class("AI response was empty.")

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_PREFIX.sub("", stripped, count=1)
        stripped = _FENCE_SUFFIX.sub("", stripped)
        stripped = stripped.strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise error_class("AI response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise error_class("AI response must be a JSON object.")
    return payload


def _require_string(data: dict, key: str, reasons: list[str], *, allow_empty: bool = False) -> str:
    if key not in data:
        reasons.append(f"Missing required field '{key}'.")
        return ""
    value = data[key]
    if not isinstance(value, str):
        reasons.append(f"Field '{key}' must be a string.")
        return ""
    value = value.strip()
    if not allow_empty and not value:
        reasons.append(f"Field '{key}' cannot be empty.")
    return value


def _require_string_list(data: dict, key: str, reasons: list[str]) -> tuple[str, ...]:
    if key not in data:
        reasons.append(f"Missing required field '{key}'.")
        return ()
    value = data[key]
    if not isinstance(value, list) or isinstance(value, str):
        reasons.append(f"Field '{key}' must be a list of strings.")
        return ()

    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            reasons.append(f"Field '{key}[{index}]' must be a string.")
            continue
        cleaned = item.strip()
        if cleaned:
            items.append(cleaned)
    return tuple(items)


def _require_choice(
    data: dict,
    key: str,
    allowed_values: frozenset[str],
    reasons: list[str],
) -> str:
    value = _require_string(data, key, reasons)
    if value and value not in allowed_values:
        options = ", ".join(sorted(allowed_values))
        reasons.append(f"Field '{key}' must be one of: {options}.")
    return value


def _reject_unexpected_fields(
    data: dict,
    allowed_fields: frozenset[str],
    reasons: list[str],
) -> None:
    for field_name in sorted(set(data) - allowed_fields):
        reasons.append(f"Unexpected field '{field_name}'.")


def _require_object_list(
    data: dict,
    key: str,
    required_fields: tuple[str, ...],
    reasons: list[str],
) -> tuple[dict[str, str], ...]:
    if key not in data:
        reasons.append(f"Missing required field '{key}'.")
        return ()
    value = data[key]
    if not isinstance(value, list):
        reasons.append(f"Field '{key}' must be a list of objects.")
        return ()

    items: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            reasons.append(f"Field '{key}[{index}]' must be an object.")
            continue
        cleaned: dict[str, str] = {}
        valid = True
        for field_name in required_fields:
            field_value = item.get(field_name)
            if not isinstance(field_value, str) or not field_value.strip():
                reasons.append(
                    f"Field '{key}[{index}].{field_name}' must be a non-empty string."
                )
                valid = False
            else:
                cleaned[field_name] = field_value.strip()
        if valid:
            items.append(cleaned)
    return tuple(items)


# --- Step 27 helpers: bounded ints and optional structured lists --------


def _bounded_int(value, key: str, reasons: list[str], *, low: int, high: int):
    """A JSON int in ``[low, high]``. Rejects bool, float, NaN/Infinity, strings."""

    if isinstance(value, bool) or not isinstance(value, int):
        # A float like 5.0 is still not a valid JSON integer for this contract.
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            value = int(value)
        else:
            reasons.append(f"Field '{key}' must be an integer.")
            return None
    if value < low or value > high:
        reasons.append(f"Field '{key}' must be between {low} and {high}.")
        return None
    return value


def _int_index_tuple(value, key: str, reasons: list[str]) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or isinstance(value, (str, bytes)):
        reasons.append(f"Field '{key}' must be a list of integers.")
        return ()
    out: list[int] = []
    for i, item in enumerate(value[:MAX_LIST_ITEMS]):
        idx = _bounded_int(item, f"{key}[{i}]", reasons, low=0, high=MAX_OBJECTIVE_INDEX)
        if idx is not None:
            out.append(idx)
    return tuple(out)


def _optional_object_list(
    data: dict, key: str, reasons: list[str]
) -> tuple[dict, ...]:
    """A list of dicts, or ``()`` when the key is absent (v1 backward-compat)."""

    if key not in data or data[key] in (None, []):
        return ()
    value = data[key]
    if not isinstance(value, list) or isinstance(value, (str, bytes)):
        reasons.append(f"Field '{key}' must be a list of objects.")
        return ()
    if len(value) > MAX_LIST_ITEMS:
        reasons.append(f"Field '{key}' has too many items (max {MAX_LIST_ITEMS}).")
        return ()
    out: list[dict] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            reasons.append(f"Field '{key}[{i}]' must be an object.")
            continue
        out.append(item)
    return tuple(out)


@dataclass(frozen=True)
class GeneratedActivity:
    """An AI-suggested activity. Advisory only -- never a real ``LessonActivity``."""

    title: str
    description: str
    activity_type: str
    objective_alignment: tuple[int, ...]
    estimated_minutes: int
    instructions: str = ""
    simulation_type: str = ""

    @classmethod
    def from_dict(cls, data: dict, index: int, reasons: list[str]) -> "GeneratedActivity | None":
        prefix = f"activity_plan[{index}]"
        title = _require_string(data, "title", reasons)
        description = _require_string(data, "description", reasons)
        activity_type = _require_choice(
            data, "activity_type", GENERATED_ACTIVITY_TYPES, reasons
        )
        alignment = _int_index_tuple(
            data.get("objective_alignment", []), f"{prefix}.objective_alignment", reasons
        )
        minutes = _bounded_int(
            data.get("estimated_minutes"),
            f"{prefix}.estimated_minutes",
            reasons,
            low=1,
            high=MAX_ESTIMATED_MINUTES,
        )
        instructions = _require_string(data, "instructions", reasons, allow_empty=True)
        simulation_type = _require_string(
            data, "simulation_type", reasons, allow_empty=True
        )
        _reject_unexpected_fields(
            data,
            frozenset(
                {
                    "title",
                    "description",
                    "activity_type",
                    "objective_alignment",
                    "estimated_minutes",
                    "instructions",
                    "simulation_type",
                }
            ),
            reasons,
        )
        if not title or not description or not activity_type or minutes is None:
            return None
        return cls(
            title=title,
            description=description,
            activity_type=activity_type,
            objective_alignment=alignment,
            estimated_minutes=minutes,
            instructions=instructions,
            simulation_type=simulation_type,
        )


@dataclass(frozen=True)
class PracticeSuggestion:
    """An AI-suggested practice item. Never becomes a ``QuestionBankItem`` on its own."""

    prompt: str
    concept: str
    expected_reasoning: str
    difficulty: str

    @classmethod
    def from_dict(cls, data: dict, index: int, reasons: list[str]) -> "PracticeSuggestion | None":
        prompt = _require_string(data, "prompt", reasons)
        concept = _require_string(data, "concept", reasons)
        expected = _require_string(data, "expected_reasoning", reasons)
        difficulty = _require_choice(
            data, "difficulty", SUGGESTION_DIFFICULTIES, reasons
        )
        _reject_unexpected_fields(
            data,
            frozenset({"prompt", "concept", "expected_reasoning", "difficulty"}),
            reasons,
        )
        if not prompt or not concept or not expected or not difficulty:
            return None
        return cls(prompt=prompt, concept=concept, expected_reasoning=expected, difficulty=difficulty)


@dataclass(frozen=True)
class AssessmentSuggestion:
    """An AI-suggested assessment item. Never becomes an ``Assessment`` on its own."""

    question: str
    expected_reasoning: str
    concept: str
    difficulty: str

    @classmethod
    def from_dict(cls, data: dict, index: int, reasons: list[str]) -> "AssessmentSuggestion | None":
        question = _require_string(data, "question", reasons)
        expected = _require_string(data, "expected_reasoning", reasons)
        concept = _require_string(data, "concept", reasons)
        difficulty = _require_choice(
            data, "difficulty", SUGGESTION_DIFFICULTIES, reasons
        )
        _reject_unexpected_fields(
            data,
            frozenset({"question", "expected_reasoning", "concept", "difficulty"}),
            reasons,
        )
        if not question or not expected or not concept or not difficulty:
            return None
        return cls(
            question=question,
            expected_reasoning=expected,
            concept=concept,
            difficulty=difficulty,
        )


@dataclass(frozen=True)
class MisconceptionAwareness:
    """An AI note about an existing misconception. Instructional metadata, not a diagnosis.

    ``misconception_code`` is a *claim* -- the domain layer resolves it against
    the ``PhysicsMisconception`` catalog and a miss becomes a review issue.
    """

    misconception_code: str
    why_relevant: str
    instructional_note: str

    @classmethod
    def from_dict(cls, data: dict, index: int, reasons: list[str]) -> "MisconceptionAwareness | None":
        code = _require_string(data, "misconception_code", reasons)
        why = _require_string(data, "why_relevant", reasons)
        note = _require_string(data, "instructional_note", reasons)
        _reject_unexpected_fields(
            data,
            frozenset({"misconception_code", "why_relevant", "instructional_note"}),
            reasons,
        )
        if not code or not why or not note:
            return None
        return cls(misconception_code=code[:120], why_relevant=why, instructional_note=note)


@dataclass(frozen=True)
class WorkedExample:
    title: str
    problem: str
    solution: str


@dataclass(frozen=True)
class Activity:
    title: str
    description: str


@dataclass(frozen=True)
class AssessmentQuestion:
    question: str
    expected_reasoning: str


@dataclass(frozen=True)
class LessonDraft:
    """Validated structured lesson draft produced by an AI provider.

    The v1 fields are unchanged and always required. The v2 structured-plan
    fields are optional: a historical persisted draft with none of them parses
    fine and simply carries empty tuples.
    """

    title: str
    overview: str
    learning_objectives: tuple[str, ...]
    prerequisites: tuple[str, ...]
    key_concepts: tuple[str, ...]
    explanation: str
    worked_examples: tuple[WorkedExample, ...]
    activities: tuple[Activity, ...]
    assessment_questions: tuple[AssessmentQuestion, ...]
    teacher_notes: tuple[str, ...]
    # --- v2 additions (optional / backward-compatible) ---
    schema_version: str = LESSON_DRAFT_SCHEMA_V1
    activity_plan: tuple[GeneratedActivity, ...] = field(default_factory=tuple)
    practice_suggestions: tuple[PracticeSuggestion, ...] = field(default_factory=tuple)
    assessment_suggestions: tuple[AssessmentSuggestion, ...] = field(default_factory=tuple)
    misconception_awareness: tuple[MisconceptionAwareness, ...] = field(default_factory=tuple)

    @property
    def is_v2(self) -> bool:
        return self.schema_version == LESSON_DRAFT_SCHEMA_V2

    @classmethod
    def from_dict(cls, data: dict) -> LessonDraft:
        if not isinstance(data, dict):
            raise InvalidLessonDraftError("Lesson draft must be a JSON object.")

        reasons: list[str] = []
        title = _require_string(data, "title", reasons)
        overview = _require_string(data, "overview", reasons)
        explanation = _require_string(data, "explanation", reasons)
        learning_objectives = _require_string_list(data, "learning_objectives", reasons)
        prerequisites = _require_string_list(data, "prerequisites", reasons)
        key_concepts = _require_string_list(data, "key_concepts", reasons)
        teacher_notes = _require_string_list(data, "teacher_notes", reasons)
        worked_example_payloads = _require_object_list(
            data, "worked_examples", ("title", "problem", "solution"), reasons
        )
        activity_payloads = _require_object_list(
            data, "activities", ("title", "description"), reasons
        )
        question_payloads = _require_object_list(
            data,
            "assessment_questions",
            ("question", "expected_reasoning"),
            reasons,
        )

        # v2 structured plan -- all optional.
        v2_keys = {
            "schema_version",
            "activity_plan",
            "practice_suggestions",
            "assessment_suggestions",
            "misconception_awareness",
        }
        has_v2 = bool(v2_keys & set(data))
        raw_version = data.get("schema_version")
        if raw_version is not None and not isinstance(raw_version, str):
            reasons.append("Field 'schema_version' must be a string.")
            raw_version = None
        if raw_version and raw_version not in (LESSON_DRAFT_SCHEMA_V1, LESSON_DRAFT_SCHEMA_V2):
            reasons.append(
                f"Field 'schema_version' must be one of: "
                f"{LESSON_DRAFT_SCHEMA_V1}, {LESSON_DRAFT_SCHEMA_V2}."
            )
        schema_version = raw_version or (
            LESSON_DRAFT_SCHEMA_V2 if has_v2 else LESSON_DRAFT_SCHEMA_V1
        )

        activity_plan = tuple(
            filter(
                None,
                (
                    GeneratedActivity.from_dict(item, i, reasons)
                    for i, item in enumerate(_optional_object_list(data, "activity_plan", reasons))
                ),
            )
        )
        practice_suggestions = tuple(
            filter(
                None,
                (
                    PracticeSuggestion.from_dict(item, i, reasons)
                    for i, item in enumerate(
                        _optional_object_list(data, "practice_suggestions", reasons)
                    )
                ),
            )
        )
        assessment_suggestions = tuple(
            filter(
                None,
                (
                    AssessmentSuggestion.from_dict(item, i, reasons)
                    for i, item in enumerate(
                        _optional_object_list(data, "assessment_suggestions", reasons)
                    )
                ),
            )
        )
        misconception_awareness = tuple(
            filter(
                None,
                (
                    MisconceptionAwareness.from_dict(item, i, reasons)
                    for i, item in enumerate(
                        _optional_object_list(data, "misconception_awareness", reasons)
                    )
                ),
            )
        )

        if reasons:
            raise InvalidLessonDraftError(
                "AI lesson draft failed validation.",
                reasons=reasons,
            )

        return cls(
            title=title,
            overview=overview,
            learning_objectives=learning_objectives,
            prerequisites=prerequisites,
            key_concepts=key_concepts,
            explanation=explanation,
            worked_examples=tuple(
                WorkedExample(**item) for item in worked_example_payloads
            ),
            activities=tuple(Activity(**item) for item in activity_payloads),
            assessment_questions=tuple(
                AssessmentQuestion(**item) for item in question_payloads
            ),
            teacher_notes=teacher_notes,
            schema_version=schema_version,
            activity_plan=activity_plan,
            practice_suggestions=practice_suggestions,
            assessment_suggestions=assessment_suggestions,
            misconception_awareness=misconception_awareness,
        )

    def to_dict(self) -> dict:
        # ``dataclasses.asdict`` preserves tuples, whereas this is the JSON
        # contract consumed by ``from_dict`` and Django's JSONField.  Return
        # lists even before a draft is written and reloaded from the database.
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "overview": self.overview,
            "learning_objectives": list(self.learning_objectives),
            "prerequisites": list(self.prerequisites),
            "key_concepts": list(self.key_concepts),
            "explanation": self.explanation,
            "worked_examples": [asdict(example) for example in self.worked_examples],
            "activities": [asdict(activity) for activity in self.activities],
            "assessment_questions": [
                asdict(question) for question in self.assessment_questions
            ],
            "teacher_notes": list(self.teacher_notes),
            "activity_plan": [
                {**asdict(a), "objective_alignment": list(a.objective_alignment)}
                for a in self.activity_plan
            ],
            "practice_suggestions": [asdict(p) for p in self.practice_suggestions],
            "assessment_suggestions": [asdict(a) for a in self.assessment_suggestions],
            "misconception_awareness": [asdict(m) for m in self.misconception_awareness],
        }


@dataclass(frozen=True)
class ReviewIssue:
    """One bounded, review-only finding about a generated lesson draft."""

    category: str
    severity: str
    issue: str
    explanation: str
    affected_section: str
    suggested_revision: str
    confidence: str

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewIssue":
        if not isinstance(data, dict):
            raise InvalidLessonReviewError("Review issue must be a JSON object.")

        reasons: list[str] = []
        _reject_unexpected_fields(
            data,
            frozenset(
                {
                    "category",
                    "severity",
                    "issue",
                    "explanation",
                    "affected_section",
                    "suggested_revision",
                    "confidence",
                }
            ),
            reasons,
        )
        category = _require_choice(
            data, "category", REVIEW_ISSUE_CATEGORIES, reasons
        )
        severity = _require_choice(
            data, "severity", REVIEW_ISSUE_SEVERITIES, reasons
        )
        issue = _require_string(data, "issue", reasons)
        explanation = _require_string(data, "explanation", reasons)
        affected_section = _require_string(data, "affected_section", reasons)
        suggested_revision = _require_string(data, "suggested_revision", reasons)
        confidence = _require_choice(
            data, "confidence", REVIEW_ISSUE_CONFIDENCES, reasons
        )

        if reasons:
            raise InvalidLessonReviewError(
                "AI lesson review issue failed validation.", reasons=reasons
            )

        return cls(
            category=category,
            severity=severity,
            issue=issue,
            explanation=explanation,
            affected_section=affected_section,
            suggested_revision=suggested_revision,
            confidence=confidence,
        )


@dataclass(frozen=True)
class LessonReviewResult:
    """Validated review findings for a generated lesson draft."""

    overall_summary: str
    issues: tuple[ReviewIssue, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "LessonReviewResult":
        if not isinstance(data, dict):
            raise InvalidLessonReviewError("Lesson review must be a JSON object.")

        reasons: list[str] = []
        _reject_unexpected_fields(
            data, frozenset({"overall_summary", "issues"}), reasons
        )
        overall_summary = _require_string(data, "overall_summary", reasons)
        issues_payload = data.get("issues")
        issues: list[ReviewIssue] = []

        if "issues" not in data:
            reasons.append("Missing required field 'issues'.")
        elif not isinstance(issues_payload, list):
            reasons.append("Field 'issues' must be a list of review issues.")
        else:
            for index, issue_payload in enumerate(issues_payload):
                try:
                    issues.append(ReviewIssue.from_dict(issue_payload))
                except InvalidLessonReviewError as exc:
                    reasons.extend(
                        f"Issue {index}: {reason}" for reason in exc.reasons
                    )

        if reasons:
            raise InvalidLessonReviewError(
                "AI lesson review failed validation.", reasons=reasons
            )

        return cls(overall_summary=overall_summary, issues=tuple(issues))

    def to_dict(self) -> dict:
        return asdict(self)
