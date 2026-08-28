from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .exceptions import InvalidLessonDraftError, InvalidLessonReviewError

LESSON_DRAFT_JSON_SCHEMA = {
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


def example_lesson_draft_dict() -> dict:
    """Canonical valid payload used by the fake provider and contract tests."""

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
    """Validated structured lesson draft produced by an AI provider."""

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
        )

    def to_dict(self) -> dict:
        # ``dataclasses.asdict`` preserves tuples, whereas this is the JSON
        # contract consumed by ``from_dict`` and Django's JSONField.  Return
        # lists even before a draft is written and reloaded from the database.
        return {
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
