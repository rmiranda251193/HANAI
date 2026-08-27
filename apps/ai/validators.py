from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .requests import LessonReviewRequest
from .schemas import ReviewIssue


class LessonReviewValidator(Protocol):
    """Extension point for deterministic, review-only lesson checks."""

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        """Return conservative findings without modifying the lesson or draft."""


class PhysicsValidator:
    """Reserved home for deterministic Physics checks.

    It intentionally returns no findings until a reliable, domain-backed check is
    available. This avoids presenting fragile text matching as Physics validation.
    """

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        return ()


DEFAULT_REVIEW_VALIDATORS: tuple[LessonReviewValidator, ...] = (PhysicsValidator(),)


def run_deterministic_review_validators(
    request: LessonReviewRequest,
    validators: Iterable[LessonReviewValidator],
) -> tuple[ReviewIssue, ...]:
    """Run configured deterministic validators and combine their findings."""

    return tuple(
        issue
        for validator in validators
        for issue in validator.validate(request)
    )
