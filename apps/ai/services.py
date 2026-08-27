from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from .prompts import Prompt, build_lesson_generation_prompt
from .providers import AIProvider, get_ai_provider
from .requests import LessonGenerationRequest
from .schemas import LessonDraft, parse_model_json


@dataclass(frozen=True)
class LessonGenerationResult:
    """Validated draft plus the metadata needed for later provenance."""

    draft: LessonDraft
    provider_name: str
    model: str
    prompt: Prompt
    raw_response: str
    created_at: datetime

    @property
    def prompt_version(self) -> str:
        return self.prompt.version


def generate_lesson_draft(
    request: LessonGenerationRequest,
    *,
    provider: AIProvider | None = None,
) -> LessonGenerationResult:
    """Build a prompt, call a provider, and validate the structured draft.

    This does not persist the draft, does not update a Lesson, and does not
    call a remote API unless the given provider does. The default configured
    provider is currently fake.
    """

    provider = provider or get_ai_provider()
    prompt = build_lesson_generation_prompt(request)
    raw_response = provider.generate(prompt.user, system_prompt=prompt.system)
    payload = parse_model_json(raw_response)
    draft = LessonDraft.from_dict(payload)

    return LessonGenerationResult(
        draft=draft,
        provider_name=provider.name,
        model=provider.model,
        prompt=prompt,
        raw_response=raw_response,
        created_at=timezone.now(),
    )
