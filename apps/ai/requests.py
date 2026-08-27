from __future__ import annotations

from dataclasses import dataclass

from apps.physics.models import PhysicsConcept

from .schemas import LessonDraft


def _string_tuple(value, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of strings.")
    return tuple(item.strip() for item in value if str(item).strip())


@dataclass(frozen=True)
class ConceptContext:
    """Physics concept snapshot used as authoritative generation context."""

    name: str
    description: str
    topic: str
    difficulty: str
    equations: tuple[str, ...] = ()
    si_units: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    common_misconceptions: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("concept name is required")
        object.__setattr__(self, "equations", _string_tuple(self.equations, "equations"))
        object.__setattr__(self, "si_units", _string_tuple(self.si_units, "si_units"))
        object.__setattr__(
            self, "prerequisites", _string_tuple(self.prerequisites, "prerequisites")
        )
        object.__setattr__(
            self,
            "common_misconceptions",
            _string_tuple(self.common_misconceptions, "common_misconceptions"),
        )

    @classmethod
    def from_concept(cls, concept: PhysicsConcept) -> ConceptContext:
        return cls(
            name=concept.name,
            description=concept.description,
            topic=concept.topic,
            difficulty=concept.difficulty,
            equations=tuple(concept.equations or []),
            si_units=tuple(concept.si_units or []),
            prerequisites=tuple(concept.prerequisites or []),
            common_misconceptions=tuple(concept.common_misconceptions or []),
        )

    def as_prompt_block(self) -> str:
        def bullets(items: tuple[str, ...], empty_label: str) -> str:
            if not items:
                return f"- {empty_label}"
            return "\n".join(f"- {item}" for item in items)

        return "\n".join(
            [
                f"### {self.name}",
                f"Topic: {self.topic}",
                f"Difficulty: {self.difficulty}",
                f"Definition: {self.description}",
                "Equations:",
                bullets(self.equations, "None provided. Do not invent equations."),
                "SI units:",
                bullets(self.si_units, "None provided. Do not invent SI units."),
                "Prerequisites:",
                bullets(self.prerequisites, "None listed."),
                "Common misconceptions:",
                bullets(self.common_misconceptions, "None listed."),
            ]
        )


@dataclass(frozen=True)
class LessonGenerationRequest:
    """Teacher-authored inputs for a structured Physics lesson draft."""

    title: str
    topic: str
    grade_level: str
    duration_minutes: int
    learning_objectives: tuple[str, ...]
    common_misconceptions: tuple[str, ...]
    concepts: tuple[ConceptContext, ...]

    def __post_init__(self):
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "grade_level", str(self.grade_level).strip())
        object.__setattr__(
            self,
            "learning_objectives",
            _string_tuple(self.learning_objectives, "learning_objectives"),
        )
        object.__setattr__(
            self,
            "common_misconceptions",
            _string_tuple(self.common_misconceptions, "common_misconceptions"),
        )
        object.__setattr__(self, "concepts", tuple(self.concepts))

        if not self.title:
            raise ValueError("title is required")
        if not self.topic:
            raise ValueError("topic is required")
        if not self.grade_level:
            raise ValueError("grade_level is required")
        if not isinstance(self.duration_minutes, int) or self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be a positive integer")
        if not self.learning_objectives:
            raise ValueError("at least one learning objective is required")
        if not self.concepts:
            raise ValueError("at least one Physics concept is required")
        if not all(isinstance(concept, ConceptContext) for concept in self.concepts):
            raise ValueError("concepts must be ConceptContext instances")

    @classmethod
    def from_lesson(cls, lesson) -> LessonGenerationRequest:
        return cls(
            title=lesson.title,
            topic=lesson.topic,
            grade_level=lesson.grade_level,
            duration_minutes=lesson.duration_minutes,
            learning_objectives=tuple(lesson.learning_objectives or []),
            common_misconceptions=tuple(lesson.common_misconceptions or []),
            concepts=tuple(
                ConceptContext.from_concept(concept)
                for concept in lesson.physics_concepts.all()
            ),
        )


@dataclass(frozen=True)
class LessonReviewRequest:
    """Immutable teacher context and draft snapshot for AI lesson review."""

    original_lesson: LessonGenerationRequest
    draft: LessonDraft

    def __post_init__(self):
        if not isinstance(self.original_lesson, LessonGenerationRequest):
            raise ValueError("original_lesson must be a LessonGenerationRequest instance")
        if not isinstance(self.draft, LessonDraft):
            raise ValueError("draft must be a LessonDraft instance")

    @property
    def title(self) -> str:
        return self.original_lesson.title

    @property
    def topic(self) -> str:
        return self.original_lesson.topic

    @property
    def grade_level(self) -> str:
        return self.original_lesson.grade_level

    @property
    def duration_minutes(self) -> int:
        return self.original_lesson.duration_minutes

    @property
    def learning_objectives(self) -> tuple[str, ...]:
        return self.original_lesson.learning_objectives

    @property
    def common_misconceptions(self) -> tuple[str, ...]:
        return self.original_lesson.common_misconceptions

    @property
    def concepts(self) -> tuple[ConceptContext, ...]:
        return self.original_lesson.concepts

    @classmethod
    def from_lesson(cls, lesson, draft: LessonDraft) -> LessonReviewRequest:
        return cls(
            original_lesson=LessonGenerationRequest.from_lesson(lesson),
            draft=draft,
        )
