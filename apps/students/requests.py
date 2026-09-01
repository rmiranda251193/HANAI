from __future__ import annotations

from dataclasses import dataclass

from apps.ai.requests import ConceptContext

RECENT_MESSAGE_LIMIT = 6


@dataclass(frozen=True)
class TutorConversationMessage:
    """One prior turn supplied to the tutor for context."""

    role: str
    content: str

    def __post_init__(self):
        object.__setattr__(self, "role", str(self.role).strip().lower())
        object.__setattr__(self, "content", str(self.content).strip())


@dataclass(frozen=True)
class TutorRequest:
    """Immutable context passed to the tutoring service.

    Kept separate from the database models so it can be built and tested
    without persistence.
    """

    lesson_title: str
    topic: str
    grade_level: str
    learning_objectives: tuple[str, ...] = ()
    common_misconceptions: tuple[str, ...] = ()
    concepts: tuple[ConceptContext, ...] = ()
    recent_messages: tuple[TutorConversationMessage, ...] = ()
    student_question: str = ""
    practice_problem: str = ""
    student_attempt: str = ""

    def __post_init__(self):
        object.__setattr__(self, "lesson_title", self.lesson_title.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "grade_level", str(self.grade_level).strip())
        object.__setattr__(
            self,
            "learning_objectives",
            tuple(str(item).strip() for item in self.learning_objectives if str(item).strip()),
        )
        object.__setattr__(
            self,
            "common_misconceptions",
            tuple(
                str(item).strip()
                for item in self.common_misconceptions
                if str(item).strip()
            ),
        )
        object.__setattr__(self, "concepts", tuple(self.concepts))
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))
        object.__setattr__(self, "student_question", self.student_question.strip())
        object.__setattr__(self, "practice_problem", self.practice_problem.strip())
        object.__setattr__(self, "student_attempt", self.student_attempt.strip())

        if not self.lesson_title:
            raise ValueError("lesson_title is required")
        if not self.topic:
            raise ValueError("topic is required")
        if not self.grade_level:
            raise ValueError("grade_level is required")
        if not self.student_question and not self.student_attempt:
            raise ValueError("a student question or a practice attempt is required")
        if not all(isinstance(concept, ConceptContext) for concept in self.concepts):
            raise ValueError("concepts must be ConceptContext instances")

    @property
    def is_practice_turn(self) -> bool:
        return bool(self.student_attempt)

    @classmethod
    def from_session(
        cls,
        session,
        *,
        student_question: str = "",
        practice_problem: str = "",
        student_attempt: str = "",
        recent_limit: int = RECENT_MESSAGE_LIMIT,
    ) -> "TutorRequest":
        lesson = session.lesson
        messages = list(session.messages.all())
        if recent_limit:
            messages = messages[-recent_limit:]

        return cls(
            lesson_title=lesson.title,
            topic=lesson.topic,
            grade_level=lesson.grade_level,
            learning_objectives=tuple(lesson.learning_objectives or []),
            common_misconceptions=tuple(lesson.common_misconceptions or []),
            concepts=tuple(
                ConceptContext.from_concept(concept)
                for concept in lesson.physics_concepts.all()
            ),
            recent_messages=tuple(
                TutorConversationMessage(role=message.role, content=message.content)
                for message in messages
            ),
            student_question=student_question,
            practice_problem=practice_problem,
            student_attempt=student_attempt,
        )
