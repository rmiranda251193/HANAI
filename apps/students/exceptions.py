from __future__ import annotations


class TutorError(Exception):
    """Base error for the student Physics tutor."""


class EmptyTutorMessageError(TutorError):
    """The student submitted nothing for the tutor to respond to."""


class InvalidTutorResponseError(TutorError):
    """AI output did not match the structured tutor response contract."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = reasons or [message]


class MisconceptionError(Exception):
    """Base error for the Physics misconception engine."""


class InvalidMisconceptionAssessmentError(MisconceptionError):
    """AI output did not match the misconception assessment contract."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = reasons or [message]


class MisconceptionDecisionError(MisconceptionError):
    """A requested teacher decision on an observation is not valid."""
