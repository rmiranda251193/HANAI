from __future__ import annotations

import json
from dataclasses import dataclass

from .requests import LessonGenerationRequest
from .schemas import LESSON_DRAFT_JSON_SCHEMA

LESSON_GENERATION_PROMPT_VERSION = "lesson-generation-v1"


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    version: str = LESSON_GENERATION_PROMPT_VERSION


def build_lesson_generation_prompt(request: LessonGenerationRequest) -> Prompt:
    """Build the system and user prompts for structured lesson generation."""

    system = f"""You are the lesson-draft generator for DodongOS Physics AI.

Core rule: AI assists. Teachers decide. Students learn by thinking.

Your job is to draft instructional material for a teacher to review. The teacher remains the final authority. Do not treat this draft as published classroom content.

Physics-first rules:
- Use the provided Physics concept knowledge as the source of truth.
- Do not invent equations, SI units, or definitions that contradict the provided concepts.
- If a needed fact is missing, record the gap in teacher_notes instead of guessing.
- Prefer scientifically precise language appropriate to the stated grade level.

Pedagogy:
- Address the teacher-listed misconceptions explicitly in the explanation and activities.
- Worked examples must show reasoning, not only a final answer.
- Assessment questions should probe understanding, not only recall.
- Do not write as if you are chatting with a student.

Output contract:
- Return ONLY a JSON object. No markdown, no commentary, no code fences.
- Match this schema exactly:
{json.dumps(LESSON_DRAFT_JSON_SCHEMA, indent=2)}
- Prompt version: {LESSON_GENERATION_PROMPT_VERSION}
"""

    objectives = "\n".join(f"- {item}" for item in request.learning_objectives)
    misconceptions = (
        "\n".join(f"- {item}" for item in request.common_misconceptions)
        if request.common_misconceptions
        else "- None listed by the teacher."
    )
    concept_blocks = "\n\n".join(concept.as_prompt_block() for concept in request.concepts)

    user = f"""Generate a Physics lesson draft from this teacher request.

Title: {request.title}
Topic: {request.topic}
Grade level: {request.grade_level}
Duration (minutes): {request.duration_minutes}

Learning objectives:
{objectives}

Teacher-listed misconceptions:
{misconceptions}

Physics concepts (authoritative):
{concept_blocks}
"""

    return Prompt(system=system.strip(), user=user.strip())
