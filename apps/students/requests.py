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
class CandidateHint:
    """A possible misconception the tutor may gently probe.

    This is context for the tutor only. It must never be shown to the student
    as a label or verdict.
    """

    concept: str
    title: str
    description: str
    intervention_guidance: str = ""
    confidence: str = "low"

    def __post_init__(self):
        object.__setattr__(self, "concept", str(self.concept).strip())
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(
            self, "intervention_guidance", str(self.intervention_guidance).strip()
        )
        object.__setattr__(self, "confidence", str(self.confidence).strip().lower())


@dataclass(frozen=True)
class ExperimentContext:
    """A completed (or in-progress) Physics Lab experiment, as tutor context.

    The numeric fields are the server-recomputed deterministic values, so the
    tutor reasons about the same values the app computed, not a browser
    number. ``mass_kg``/``force_n`` are Newton's Second Law-specific;
    ``initial_position_m``/``initial_velocity_m_s``/``time_s``/``position_m``/
    ``velocity_m_s`` are Kinematics-specific. ``acceleration_m_s2`` is shared
    by both. A given experiment only ever populates the fields for its own
    simulation type -- the rest stay ``None``.
    """

    simulation: str = ""
    simulation_type: str = ""
    mass_kg: float | None = None
    force_n: float | None = None
    acceleration_m_s2: float | None = None
    initial_position_m: float | None = None
    initial_velocity_m_s: float | None = None
    time_s: float | None = None
    position_m: float | None = None
    velocity_m_s: float | None = None
    prediction: str = ""
    observation: str = ""
    explanation: str = ""

    def __post_init__(self):
        object.__setattr__(self, "simulation", str(self.simulation or "").strip())
        object.__setattr__(self, "simulation_type", str(self.simulation_type or "").strip())
        for name in ("prediction", "observation", "explanation"):
            object.__setattr__(self, name, str(getattr(self, name) or "").strip())

    @property
    def has_content(self) -> bool:
        return any(
            [
                self.prediction,
                self.observation,
                self.explanation,
                self.mass_kg is not None,
                self.force_n is not None,
                self.acceleration_m_s2 is not None,
                self.initial_position_m is not None,
                self.initial_velocity_m_s is not None,
                self.position_m is not None,
                self.velocity_m_s is not None,
            ]
        )

    @classmethod
    def from_attempt(cls, attempt) -> "ExperimentContext":
        simulation = getattr(attempt, "simulation", None)
        if simulation is not None and hasattr(simulation, "get_simulation_type_display"):
            label = simulation.get_simulation_type_display()
        else:
            label = str(simulation) if simulation is not None else ""
        simulation_type = getattr(simulation, "simulation_type", "") or ""

        kwargs = dict(
            simulation=label,
            simulation_type=simulation_type,
            acceleration_m_s2=attempt.acceleration_m_s2,
            prediction=attempt.prediction,
            observation=attempt.observation,
            explanation=attempt.explanation,
        )
        if simulation_type == "kinematics":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                initial_position_m=params.get("initial_position_m"),
                initial_velocity_m_s=params.get("initial_velocity_m_s"),
                time_s=params.get("observed_time_s"),
                position_m=params.get("observed_position_m"),
                velocity_m_s=params.get("observed_velocity_m_s"),
            )
        else:
            kwargs.update(mass_kg=attempt.mass_kg, force_n=attempt.force_n)
        return cls(**kwargs)


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
    candidate_misconceptions: tuple[CandidateHint, ...] = ()
    experiment: "ExperimentContext | None" = None
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
        object.__setattr__(
            self, "candidate_misconceptions", tuple(self.candidate_misconceptions)
        )
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
        if self.experiment is not None and not isinstance(
            self.experiment, ExperimentContext
        ):
            raise ValueError("experiment must be an ExperimentContext instance")

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
        candidate_misconceptions: tuple[CandidateHint, ...] = (),
        experiment: "ExperimentContext | None" = None,
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
            candidate_misconceptions=tuple(candidate_misconceptions),
            experiment=experiment,
            student_question=student_question,
            practice_problem=practice_problem,
            student_attempt=student_attempt,
        )
