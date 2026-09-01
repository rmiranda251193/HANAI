from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from django.utils import timezone

from apps.ai.prompts import Prompt
from apps.ai.providers import AIProvider
from apps.ai.schemas import parse_model_json

from .exceptions import EmptyTutorMessageError, InvalidTutorResponseError
from .models import LearningEvidence, TutorMessage, TutorSession
from .prompts import build_tutor_prompt
from .providers import get_tutor_provider
from .requests import TutorRequest
from .schemas import TutorResponse


@dataclass(frozen=True)
class TutorResult:
    """Validated tutor response plus the metadata for a persisted turn."""

    response: TutorResponse
    provider_name: str
    model: str
    prompt: Prompt
    raw_response: str
    created_at: datetime

    @property
    def prompt_version(self) -> str:
        return self.prompt.version


def tutor_student(
    request: TutorRequest,
    *,
    provider: AIProvider | None = None,
) -> TutorResult:
    """Build a tutoring prompt, call a provider, and validate the reply.

    This does not touch the database and does not call a remote API unless the
    supplied provider does. The default provider is the tutor-aware fake in
    local development.
    """

    provider = provider or get_tutor_provider()
    prompt = build_tutor_prompt(request)
    raw_response = provider.generate(prompt.user, system_prompt=prompt.system)
    payload = parse_model_json(raw_response, error_class=InvalidTutorResponseError)
    response = TutorResponse.from_dict(payload)

    if not response.concept and request.concepts:
        response = replace(response, concept=request.concepts[0].name)

    return TutorResult(
        response=response,
        provider_name=provider.name,
        model=getattr(provider, "model", ""),
        prompt=prompt,
        raw_response=raw_response,
        created_at=timezone.now(),
    )


def record_learning_evidence(
    session: TutorSession,
    *,
    kind: str,
    tutor_mode: str = "",
    detail: str = "",
) -> LearningEvidence:
    """Persist one lightweight engagement record. Never infers a misconception."""

    return LearningEvidence.objects.create(
        student=session.student,
        lesson=session.lesson,
        session=session,
        kind=kind,
        tutor_mode=tutor_mode or "",
        detail=(detail or "")[:300],
    )


def run_tutor_turn(
    session: TutorSession,
    *,
    student_question: str = "",
    practice_problem: str = "",
    student_attempt: str = "",
    provider: AIProvider | None = None,
) -> tuple[TutorMessage, TutorResult]:
    """Persist the student message, call the tutor, and persist the reply.

    The student message is saved first so it stays visible even if the tutor
    call then fails; the caller shows a friendly error in that case.
    """

    student_content = (student_attempt or student_question).strip()
    if not student_content:
        raise EmptyTutorMessageError("Enter a question or an attempt for the tutor.")

    is_practice = bool(student_attempt.strip())

    TutorMessage.objects.create(
        session=session,
        role=TutorMessage.Role.STUDENT,
        content=student_content,
    )

    tutor_request = TutorRequest.from_session(
        session,
        student_question=student_question,
        practice_problem=practice_problem,
        student_attempt=student_attempt,
    )
    result = tutor_student(tutor_request, provider=provider)

    tutor_message = TutorMessage.objects.create(
        session=session,
        role=TutorMessage.Role.TUTOR,
        content=result.response.message,
        mode=result.response.mode,
        data={
            "concept": result.response.concept,
            "hint": result.response.hint,
            "next_question": result.response.next_question,
            "needs_student_attempt": result.response.needs_student_attempt,
        },
    )

    # Bump ``updated_at`` so the session reflects the latest activity.
    session.save(update_fields=["updated_at"])

    record_learning_evidence(
        session,
        kind=(
            LearningEvidence.Kind.PRACTICE_ATTEMPTED
            if is_practice
            else LearningEvidence.Kind.QUESTION_ASKED
        ),
        tutor_mode=result.response.mode,
        detail=student_content,
    )

    return tutor_message, result
