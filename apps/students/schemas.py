from __future__ import annotations

from dataclasses import dataclass

from .exceptions import InvalidTutorResponseError

TUTOR_RESPONSE_MODES = frozenset(
    {"explain", "hint", "question", "feedback", "solution", "practice"}
)

TUTOR_RESPONSE_JSON_SCHEMA = {
    "mode": "explain | hint | question | feedback | solution | practice",
    "message": "string (what the tutor says to the student)",
    "concept": "string (relevant Physics concept name, may be empty)",
    "hint": "string (a nudge that does not give the answer, may be empty)",
    "next_question": "string (a guiding follow-up question, may be empty)",
    "needs_student_attempt": "boolean (true if the student should try before more help)",
}

_ALLOWED_FIELDS = frozenset(
    {"mode", "message", "concept", "hint", "next_question", "needs_student_attempt"}
)
_OPTIONAL_STRING_FIELDS = ("concept", "hint", "next_question")


def example_tutor_response_dict() -> dict:
    """Canonical valid payload used by the fake tutor provider and tests."""

    return {
        "mode": "explain",
        "message": (
            "Acceleration is the rate at which an object's velocity changes over "
            "time. It is a vector, so both a change in speed and a change in "
            "direction count. In SI units it is measured in metres per second "
            "squared (m/s^2)."
        ),
        "concept": "Acceleration",
        "hint": (
            "Focus on how much the velocity changes each second, not on how fast "
            "the object is already moving."
        ),
        "next_question": (
            "If a car speeds up from 10 m/s to 16 m/s in 3 s, what is its "
            "acceleration?"
        ),
        "needs_student_attempt": False,
    }


@dataclass(frozen=True)
class TutorResponse:
    """Validated, structured tutoring reply. Never trust raw AI text directly."""

    mode: str
    message: str
    concept: str = ""
    hint: str = ""
    next_question: str = ""
    needs_student_attempt: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "TutorResponse":
        if not isinstance(data, dict):
            raise InvalidTutorResponseError("Tutor response must be a JSON object.")

        reasons: list[str] = []

        for field_name in sorted(set(data) - _ALLOWED_FIELDS):
            reasons.append(f"Unexpected field '{field_name}'.")

        mode = data.get("mode")
        if not isinstance(mode, str) or not mode.strip():
            reasons.append("Field 'mode' is required and must be a non-empty string.")
            mode = ""
        else:
            mode = mode.strip().lower()
            if mode not in TUTOR_RESPONSE_MODES:
                options = ", ".join(sorted(TUTOR_RESPONSE_MODES))
                reasons.append(f"Field 'mode' must be one of: {options}.")

        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            reasons.append("Field 'message' is required and must be a non-empty string.")
            message = ""
        else:
            message = message.strip()

        optional_values: dict[str, str] = {}
        for field_name in _OPTIONAL_STRING_FIELDS:
            value = data.get(field_name, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                reasons.append(f"Field '{field_name}' must be a string.")
                value = ""
            optional_values[field_name] = value.strip()

        needs_attempt = data.get("needs_student_attempt", False)
        if not isinstance(needs_attempt, bool):
            reasons.append("Field 'needs_student_attempt' must be a boolean.")
            needs_attempt = False

        if reasons:
            raise InvalidTutorResponseError(
                "AI tutor response failed validation.", reasons=reasons
            )

        return cls(
            mode=mode,
            message=message,
            concept=optional_values["concept"],
            hint=optional_values["hint"],
            next_question=optional_values["next_question"],
            needs_student_attempt=needs_attempt,
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "message": self.message,
            "concept": self.concept,
            "hint": self.hint,
            "next_question": self.next_question,
            "needs_student_attempt": self.needs_student_attempt,
        }
