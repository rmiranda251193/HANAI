class AIError(Exception):
    """Base error for the AI layer."""


class AIProviderError(AIError):
    """The configured provider failed to produce a usable response."""


class UnsupportedAIProviderError(AIError):
    """The requested provider name is unknown or not implemented yet."""


class InvalidLessonDraftError(AIError):
    """AI output did not match the lesson generation contract."""

    def __init__(self, message: str, reasons: list[str] | None = None):
        super().__init__(message)
        self.reasons = reasons or [message]
