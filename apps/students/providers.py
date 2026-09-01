from __future__ import annotations

import json

from django.conf import settings

from apps.ai.providers import AIProvider, get_ai_provider

from .schemas import example_tutor_response_dict

_CONFUSION_MARKERS = (
    "don't understand",
    "dont understand",
    "don't know",
    "dont know",
    "how do i",
    "how do you",
    "not sure how",
    "stuck",
    "confused",
    "help me",
    "where do i start",
)
_EXPLAIN_MARKERS = (
    "what is",
    "what are",
    "what's",
    "define",
    "explain",
    "why does",
    "why is",
    "how does",
)


class FakeTutorProvider(AIProvider):
    """Deterministic in-process tutor provider for tests and local development.

    It never calls a network API. It inspects the prompt so the local
    experience feels like real tutoring: confusion gets a hint, a direct
    question gets an explanation, an attempt gets feedback.
    """

    name = "fake"
    model = "fake-physics-tutor"

    def __init__(self, response: str | None = None):
        self._fixed_response = response
        self.calls: list[dict[str, str]] = []

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if self._fixed_response is not None:
            return self._fixed_response

        text = prompt.lower()
        payload = example_tutor_response_dict()

        if "student attempt to review:" in text:
            payload.update(
                mode="feedback",
                message=(
                    "Good start. Name the quantity you are solving for, then check "
                    "that your units end up as m/s^2. Show which equation links the "
                    "quantities you used."
                ),
                hint="Compare the units on both sides of your final line.",
                next_question="Which values in the problem did you substitute, and why?",
                needs_student_attempt=False,
            )
        elif any(marker in text for marker in _CONFUSION_MARKERS):
            payload.update(
                mode="hint",
                message=(
                    "Let's build it up step by step. Start by writing down what the "
                    "problem gives you and what it is asking for."
                ),
                hint="List the known quantities and the single quantity you need to find.",
                next_question="What are you trying to find, and which values are you given?",
                needs_student_attempt=True,
            )
        elif any(marker in text for marker in _EXPLAIN_MARKERS):
            payload.update(mode="explain", needs_student_attempt=False)
        else:
            payload.update(
                mode="question",
                message="Tell me what you have tried so far, or which part is unclear.",
                hint="",
                next_question="Which specific step are you unsure about?",
                needs_student_attempt=True,
            )

        return json.dumps(payload)


def get_tutor_provider() -> AIProvider:
    """Return the provider the tutor should use for the current configuration.

    Reuses the shared AI provider selection for real providers and swaps in a
    tutor-aware fake when ``AI_PROVIDER`` is ``fake`` so local development and
    tests never call a remote API.
    """

    provider_name = (getattr(settings, "AI_PROVIDER", "fake") or "fake").strip().lower()
    if provider_name == "fake":
        return FakeTutorProvider()
    return get_ai_provider()
