"""Transparent, rule-based misconception detection.

Each rule is a small, readable pattern: a set of phrase groups that must all be
present (each group is an OR of alternatives), plus optional "clear" phrases that
suppress the signal when the student is actually stating the correct idea.

These rules are deliberately conservative. A single rule hit is one weak signal,
never a diagnosis. The confidence policy lives in ``misconception_services``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _contains_any(text: str, options: tuple[str, ...]) -> str:
    for option in options:
        if option in text:
            return option
    return ""


@dataclass(frozen=True)
class RuleSignal:
    """One rule firing on a piece of student text."""

    code: str
    detector: str
    concept_name: str
    matched_phrase: str
    reasoning: str


@dataclass(frozen=True)
class MisconceptionRule:
    code: str
    concept_name: str
    require_groups: tuple[tuple[str, ...], ...]
    clear_if_any: tuple[str, ...]
    reasoning: str

    @property
    def detector(self) -> str:
        return f"rule:{self.code.lower()}"

    def match(self, normalized_text: str) -> RuleSignal | None:
        if not normalized_text:
            return None
        if _contains_any(normalized_text, self.clear_if_any):
            return None

        matched: list[str] = []
        for group in self.require_groups:
            hit = _contains_any(normalized_text, group)
            if not hit:
                return None
            matched.append(hit)

        return RuleSignal(
            code=self.code,
            detector=self.detector,
            concept_name=self.concept_name,
            matched_phrase=" + ".join(matched),
            reasoning=self.reasoning,
        )


MISCONCEPTION_RULES: tuple[MisconceptionRule, ...] = (
    MisconceptionRule(
        code="FREE_FALL_MASS_ACCELERATION",
        concept_name="Acceleration",
        require_groups=(
            ("heavier", "heavy", "more mass", "bigger mass", "greater mass", "heavier object", "heavier objects"),
            ("fall faster", "falls faster", "fall quicker", "drop faster", "drops faster",
             "hit the ground first", "hits the ground first", "hit the ground sooner",
             "lands first", "land first", "fall sooner", "fall first",
             "reach the ground first", "reaches the ground first"),
        ),
        clear_if_any=(
            "same time", "same rate", "same acceleration", "same speed",
            "regardless of mass", "independent of mass", "air resistance is",
            "because of air resistance", "due to air resistance",
        ),
        reasoning=(
            "Student text links greater mass to a faster fall, which may confuse "
            "mass with gravitational acceleration in free fall."
        ),
    ),
    MisconceptionRule(
        code="FORCE_VS_ACCELERATION",
        concept_name="Newton's Second Law",
        require_groups=(
            ("force",),
            ("acceleration", "accelerate", "accelerating"),
            ("same thing", "same as", "is the same", "are the same", "equal to",
             "is acceleration", "means acceleration", "interchangeable", "just acceleration"),
        ),
        clear_if_any=(
            "f = ma", "f=ma", "f_net = ma", "proportional to", "divided by mass",
            "force causes acceleration", "net force causes", "not the same",
        ),
        reasoning=(
            "Student text treats force and acceleration as the same quantity "
            "rather than as related by F = ma."
        ),
    ),
    MisconceptionRule(
        code="DISTANCE_VS_DISPLACEMENT",
        concept_name="Displacement",
        require_groups=(
            ("distance",),
            ("displacement",),
            ("same", "identical", "no difference", "always equal", "the same thing",
             "always the same", "interchangeable"),
        ),
        clear_if_any=(
            "not the same", "differ", "different when", "unless", "only equal",
            "straight line without", "can be different", "are not always",
        ),
        reasoning=(
            "Student text treats distance and displacement as always identical, "
            "overlooking direction and path."
        ),
    ),
)

RULES_BY_CODE = {rule.code: rule for rule in MISCONCEPTION_RULES}


def detect_misconceptions(
    *,
    student=None,
    lesson=None,
    evidence: str = "",
    concept_names: set[str] | None = None,
) -> tuple[RuleSignal, ...]:
    """Return conservative rule signals for a piece of student text.

    ``student`` and ``lesson`` are accepted for a stable call signature and for
    future scoping; detection itself only needs the text. When ``concept_names``
    is given, only rules whose concept is in that set are considered.
    """

    normalized = _normalize(evidence)
    signals: list[RuleSignal] = []
    for rule in MISCONCEPTION_RULES:
        if concept_names is not None and rule.concept_name not in concept_names:
            continue
        signal = rule.match(normalized)
        if signal is not None:
            signals.append(signal)
    return tuple(signals)
