from __future__ import annotations

import json
from abc import ABC, abstractmethod

from django.conf import settings

from .exceptions import UnsupportedAIProviderError
from .schemas import example_lesson_draft_dict

RESERVED_PROVIDERS = frozenset({"openai", "ollama"})


class AIProvider(ABC):
    """Application-facing text generation boundary.

    Views and services must depend on this interface, never on a vendor SDK.
    """

    name: str
    model: str

    @abstractmethod
    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        """Return raw model text. Callers parse and validate structured output."""


class FakeAIProvider(AIProvider):
    """Deterministic in-process provider for tests and local development.

    Does not call a network API.
    """

    name = "fake"

    def __init__(self, response: str | None = None, model: str | None = None):
        self.model = model or "fake-lesson-draft"
        self._fixed_response = response
        self.calls: list[dict[str, str]] = []

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if self._fixed_response is not None:
            return self._fixed_response
        return json.dumps(example_lesson_draft_dict())


def get_ai_provider() -> AIProvider:
    """Return the configured provider. Only the fake provider is implemented."""

    provider_name = (getattr(settings, "AI_PROVIDER", "fake") or "fake").strip().lower()
    model = (getattr(settings, "AI_MODEL", "") or "").strip()

    if provider_name == "fake":
        return FakeAIProvider(model=model or "fake-lesson-draft")

    if provider_name in RESERVED_PROVIDERS:
        raise UnsupportedAIProviderError(
            f"The '{provider_name}' provider is reserved but not implemented yet."
        )

    raise UnsupportedAIProviderError(f"Unknown AI provider '{provider_name}'.")
