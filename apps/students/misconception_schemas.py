from __future__ import annotations

from dataclasses import dataclass

from .exceptions import InvalidMisconceptionAssessmentError

EVIDENCE_STRENGTHS = frozenset({"none", "weak", "moderate", "strong"})
ASSESSMENT_CONFIDENCES = frozenset({"low", "medium", "high"})

MISCONCEPTION_ASSESSMENT_JSON_SCHEMA = {
    "assessments": [
        {
            "candidate_code": "string (a code from the supplied catalog, never invented)",
            "evidence_strength": "none | weak | moderate | strong",
            "confidence": "low | medium | high",
            "reasoning": "string (cite the student words you relied on)",
            "recommended_intervention": "string (a teaching move, may be empty)",
        }
    ]
}

_ASSESSMENT_FIELDS = frozenset(
    {
        "candidate_code",
        "evidence_strength",
        "confidence",
        "reasoning",
        "recommended_intervention",
    }
)


def example_misconception_assessment_dict() -> dict:
    """Canonical valid payload used by the fake provider and contract tests."""

    return {
        "assessments": [
            {
                "candidate_code": "FREE_FALL_MASS_ACCELERATION",
                "evidence_strength": "moderate",
                "confidence": "low",
                "reasoning": (
                    "The student wrote that heavier objects fall faster, which "
                    "may link mass to gravitational acceleration. This is one "
                    "statement, not a confirmed pattern."
                ),
                "recommended_intervention": (
                    "Invite a prediction about two different masses falling in a "
                    "vacuum, then compare with the free-fall result."
                ),
            }
        ]
    }


@dataclass(frozen=True)
class MisconceptionAssessment:
    """One validated AI judgement about a single catalog candidate."""

    candidate_code: str
    evidence_strength: str
    confidence: str
    reasoning: str
    recommended_intervention: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "MisconceptionAssessment":
        if not isinstance(data, dict):
            raise InvalidMisconceptionAssessmentError(
                "Each assessment must be a JSON object."
            )

        reasons: list[str] = []
        for field_name in sorted(set(data) - _ASSESSMENT_FIELDS):
            reasons.append(f"Unexpected field '{field_name}'.")

        code = data.get("candidate_code")
        if not isinstance(code, str) or not code.strip():
            reasons.append("Field 'candidate_code' must be a non-empty string.")
            code = ""
        else:
            code = code.strip()

        strength = data.get("evidence_strength")
        if not isinstance(strength, str) or strength.strip().lower() not in EVIDENCE_STRENGTHS:
            options = ", ".join(sorted(EVIDENCE_STRENGTHS))
            reasons.append(f"Field 'evidence_strength' must be one of: {options}.")
            strength = ""
        else:
            strength = strength.strip().lower()

        confidence = data.get("confidence")
        if not isinstance(confidence, str) or confidence.strip().lower() not in ASSESSMENT_CONFIDENCES:
            options = ", ".join(sorted(ASSESSMENT_CONFIDENCES))
            reasons.append(f"Field 'confidence' must be one of: {options}.")
            confidence = ""
        else:
            confidence = confidence.strip().lower()

        reasoning = data.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            reasons.append("Field 'reasoning' must be a non-empty string.")
            reasoning = ""
        else:
            reasoning = reasoning.strip()

        intervention = data.get("recommended_intervention", "")
        if intervention is None:
            intervention = ""
        if not isinstance(intervention, str):
            reasons.append("Field 'recommended_intervention' must be a string.")
            intervention = ""
        else:
            intervention = intervention.strip()

        if reasons:
            raise InvalidMisconceptionAssessmentError(
                "AI misconception assessment failed validation.", reasons=reasons
            )

        return cls(
            candidate_code=code,
            evidence_strength=strength,
            confidence=confidence,
            reasoning=reasoning,
            recommended_intervention=intervention,
        )

    @property
    def has_evidence(self) -> bool:
        return self.evidence_strength in {"weak", "moderate", "strong"}


@dataclass(frozen=True)
class MisconceptionAssessmentBatch:
    """Validated set of AI assessments for one analysis pass."""

    assessments: tuple[MisconceptionAssessment, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "MisconceptionAssessmentBatch":
        if not isinstance(data, dict):
            raise InvalidMisconceptionAssessmentError(
                "Misconception assessment must be a JSON object."
            )

        reasons: list[str] = []
        for field_name in sorted(set(data) - {"assessments"}):
            reasons.append(f"Unexpected field '{field_name}'.")

        raw = data.get("assessments")
        items: list[MisconceptionAssessment] = []
        if "assessments" not in data:
            reasons.append("Missing required field 'assessments'.")
        elif not isinstance(raw, list):
            reasons.append("Field 'assessments' must be a list.")
        else:
            for index, entry in enumerate(raw):
                try:
                    items.append(MisconceptionAssessment.from_dict(entry))
                except InvalidMisconceptionAssessmentError as exc:
                    reasons.extend(f"Assessment {index}: {reason}" for reason in exc.reasons)

        if reasons:
            raise InvalidMisconceptionAssessmentError(
                "AI misconception assessment failed validation.", reasons=reasons
            )

        return cls(assessments=tuple(items))
