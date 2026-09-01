from __future__ import annotations

import json
import re

from django.conf import settings

from apps.ai.providers import AIProvider, get_ai_provider

from .misconception_rules import detect_misconceptions

_RECOMMENDED_INTERVENTIONS = {
    "FREE_FALL_MASS_ACCELERATION": (
        "Ask the student to predict two different masses falling in a vacuum, "
        "then compare with the free-fall result."
    ),
    "FORCE_VS_ACCELERATION": (
        "Work through F = ma with numbers so force and acceleration stay distinct."
    ),
    "DISTANCE_VS_DISPLACEMENT": (
        "Compare a there-and-back walk: same distance, zero displacement."
    ),
}

_EXCERPT_BLOCK = re.compile(
    r"Student statements to assess:\s*(.+)$", re.IGNORECASE | re.DOTALL
)
_LOOSE_FREE_FALL = (
    re.compile(r"heav|more mass|bigger|larger mass"),
    re.compile(r"fall|drop|descend|hit the ground|hits the ground|reach the ground"),
    re.compile(r"fast|faster|quick|sooner|first|before"),
)
_FREE_FALL_CLEAR = re.compile(
    r"same (time|rate|speed|acceleration)|regardless of mass|independent of mass|air resistance"
)


class FakeMisconceptionProvider(AIProvider):
    """Deterministic, network-free provider for misconception assessment.

    It re-uses the transparent rule detectors on the student excerpts and adds
    one slightly looser free-fall check. It never hallucinates a candidate: if
    nothing matches, it returns an empty assessments list.
    """

    name = "fake"
    model = "fake-misconception"

    def __init__(self, response: str | None = None):
        self._fixed_response = response
        self.calls: list[dict[str, str]] = []

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if self._fixed_response is not None:
            return self._fixed_response

        excerpts = self._excerpts(prompt)
        text = " \n ".join(excerpts).lower()
        seen: set[str] = set()
        assessments: list[dict] = []

        for signal in detect_misconceptions(evidence=text):
            if signal.code in seen:
                continue
            seen.add(signal.code)
            assessments.append(
                {
                    "candidate_code": signal.code,
                    "evidence_strength": "moderate",
                    "confidence": "low",
                    "reasoning": (
                        f"Student wording aligns with {signal.code} "
                        f"({signal.matched_phrase}). One signal, not a pattern."
                    ),
                    "recommended_intervention": _RECOMMENDED_INTERVENTIONS.get(
                        signal.code, ""
                    ),
                }
            )

        if "FREE_FALL_MASS_ACCELERATION" not in seen and self._loose_free_fall(text):
            assessments.append(
                {
                    "candidate_code": "FREE_FALL_MASS_ACCELERATION",
                    "evidence_strength": "weak",
                    "confidence": "low",
                    "reasoning": (
                        "The phrasing loosely ties heavier mass to falling faster; "
                        "worth a gentle check, nothing more."
                    ),
                    "recommended_intervention": _RECOMMENDED_INTERVENTIONS[
                        "FREE_FALL_MASS_ACCELERATION"
                    ],
                }
            )

        return json.dumps({"assessments": assessments})

    @staticmethod
    def _excerpts(prompt: str) -> tuple[str, ...]:
        match = _EXCERPT_BLOCK.search(prompt)
        if not match:
            return ()
        lines = []
        for raw in match.group(1).splitlines():
            line = raw.strip().lstrip("-").strip().strip('"')
            if line and not line.startswith("("):
                lines.append(line)
        return tuple(lines)

    @staticmethod
    def _loose_free_fall(text: str) -> bool:
        if _FREE_FALL_CLEAR.search(text):
            return False
        return all(pattern.search(text) for pattern in _LOOSE_FREE_FALL)


def get_misconception_provider() -> AIProvider:
    """Return the provider for misconception assessment for this configuration."""

    provider_name = (getattr(settings, "AI_PROVIDER", "fake") or "fake").strip().lower()
    if provider_name == "fake":
        return FakeMisconceptionProvider()
    return get_ai_provider()
