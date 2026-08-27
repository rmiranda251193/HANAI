from __future__ import annotations

import json
from abc import ABC, abstractmethod

from django.conf import settings
from openai import OpenAI

from .exceptions import AIProviderError, UnsupportedAIProviderError
from .schemas import example_lesson_draft_dict, example_lesson_review_dict

RESERVED_PROVIDERS = frozenset({"ollama"})
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_TIMEOUT = 60.0


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

    def __init__(
        self,
        response: str | None = None,
        model: str | None = None,
        review_response: str | None = None,
    ):
        self.model = model or "fake-lesson-draft"
        self._fixed_response = response
        self._review_response = review_response
        self.calls: list[dict[str, str]] = []

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        if self._fixed_response is not None:
            return self._fixed_response
        if "lesson-review-v1" in system_prompt:
            if self._review_response is not None:
                return self._review_response
            return json.dumps(example_lesson_review_dict())
        return json.dumps(example_lesson_draft_dict())


class OpenAIProvider(AIProvider):
    """Online provider that calls OpenAI through the official Python SDK."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: OpenAI | None = None,
    ):
        self._api_key = (
            api_key if api_key is not None else getattr(settings, "OPENAI_API_KEY", "")
        ).strip()
        configured_model = (
            model
            if model is not None
            else (
                getattr(settings, "OPENAI_MODEL", "")
                or getattr(settings, "AI_MODEL", "")
                or DEFAULT_OPENAI_MODEL
            )
        )
        self.model = str(configured_model).strip() or DEFAULT_OPENAI_MODEL
        self.timeout = _coerce_timeout(timeout)
        self._client = client

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        if not self._api_key:
            raise AIProviderError("OPENAI_API_KEY is not configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=messages,
            )
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(_safe_provider_message(exc, self._api_key)) from exc

        content = _completion_text(response)
        if not content:
            raise AIProviderError("OpenAI provider returned an empty response.")
        return content

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key, timeout=self.timeout)
        return self._client


def get_ai_provider() -> AIProvider:
    """Return the configured provider implementation."""

    provider_name = (getattr(settings, "AI_PROVIDER", "fake") or "fake").strip().lower()
    model = (getattr(settings, "AI_MODEL", "") or "").strip()

    if provider_name == "fake":
        return FakeAIProvider(model=model or "fake-lesson-draft")

    if provider_name == "openai":
        return OpenAIProvider()

    if provider_name in RESERVED_PROVIDERS:
        raise UnsupportedAIProviderError(
            f"The '{provider_name}' provider is reserved but not implemented yet."
        )

    raise UnsupportedAIProviderError(f"Unknown AI provider '{provider_name}'.")


def _coerce_timeout(timeout: float | None) -> float:
    if timeout is None:
        timeout = getattr(settings, "OPENAI_TIMEOUT", DEFAULT_OPENAI_TIMEOUT)
    try:
        value = float(timeout)
    except (TypeError, ValueError):
        return DEFAULT_OPENAI_TIMEOUT
    return value if value > 0 else DEFAULT_OPENAI_TIMEOUT


def _completion_text(response) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str):
        return ""
    return content.strip()


def _safe_provider_message(exc: Exception, secret: str) -> str:
    text = str(exc)
    if secret:
        text = text.replace(secret, "[redacted]")
    return f"OpenAI provider request failed: {text}"
