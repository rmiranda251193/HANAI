from __future__ import annotations

import json

from apps.ai.prompts import Prompt

from .requests import TutorRequest
from .schemas import TUTOR_RESPONSE_JSON_SCHEMA

TUTOR_PROMPT_VERSION = "physics-tutor-v1"


def _bullets(items: tuple[str, ...], empty_label: str) -> str:
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def build_tutor_prompt(request: TutorRequest) -> Prompt:
    """Build the system and user prompts for one tutoring turn."""

    system = f"""You are the Physics tutor for DodongOS Physics AI.

Core rule: AI assists. Teachers decide. Students learn by thinking.

You are helping one student understand a specific Physics lesson. You are not a
general chatbot and you are not a search engine.

Grounding rules:
- Stay inside the supplied lesson and Physics concepts. Treat the concept
  knowledge (definitions, equations, SI units) as the source of truth.
- Respect the stated grade level in vocabulary and depth.
- Use scientifically correct terminology and SI units where appropriate.
- Do not claim access to information that was not supplied. If something needed
  is missing, say so plainly instead of inventing it.
- Clearly separate what is given in the lesson from any assumption you make.

Tutoring behaviour:
- First work out what the student is actually trying to understand or do.
- Prefer a guiding question or a hint over an immediate final answer when that
  will help the student reason.
- Encourage the student to attempt the next step themselves.
- When the student asks directly for an explanation, explain (mode "explain").
- When you are reacting to a student's attempt, give specific feedback
  (mode "feedback").
- Give a full worked solution (mode "solution") only when guidance has been
  tried or the student clearly needs to see the whole method.
- Correct misconceptions directly but respectfully.
- Keep replies focused and reasonably short.

Possible misconceptions (internal context only):
- You may be told about possible misconceptions to watch for. These are guesses,
  not facts about the student.
- NEVER tell the student they "have" a misconception and never repeat an
  internal label or code.
- Instead choose an intervention: a comparison, a prediction, or a targeted
  question that lets the student test the idea for themselves.

Output contract:
- Return ONLY a JSON object. No markdown, no commentary, no code fences.
- Match this schema exactly:
{json.dumps(TUTOR_RESPONSE_JSON_SCHEMA, indent=2)}
- Valid modes: explain, hint, question, feedback, solution, practice.
- Prompt version: {TUTOR_PROMPT_VERSION}
"""

    objectives = _bullets(
        request.learning_objectives, "None recorded for this lesson."
    )
    misconceptions = _bullets(
        request.common_misconceptions, "None listed by the teacher."
    )
    if request.concepts:
        concept_blocks = "\n\n".join(
            concept.as_prompt_block() for concept in request.concepts
        )
    else:
        concept_blocks = (
            "No Physics concepts were attached to this lesson. Do not invent "
            "concept facts; work only from the lesson topic and objectives."
        )

    if request.recent_messages:
        conversation = "\n".join(
            f"{message.role}: {message.content}"
            for message in request.recent_messages
        )
    else:
        conversation = "(no earlier messages in this session)"

    if request.candidate_misconceptions:
        misconception_lines = []
        for hint in request.candidate_misconceptions:
            parts = [f"- ({hint.confidence} confidence) {hint.concept}: {hint.title}"]
            if hint.description:
                parts.append(f"  what the student may believe: {hint.description}")
            if hint.intervention_guidance:
                parts.append(f"  suggested move: {hint.intervention_guidance}")
            misconception_lines.append("\n".join(parts))
        candidate_block = (
            "Possible misconceptions to gently probe (do NOT name these to the "
            "student):\n" + "\n".join(misconception_lines)
        )
    else:
        candidate_block = (
            "Possible misconceptions to gently probe: none flagged for this student."
        )

    experiment_block = ""
    experiment = request.experiment
    if experiment is not None and experiment.has_content:
        exp_lines = [
            f"Physics Lab experiment the student just ran "
            f"({experiment.simulation or 'simulation'}):"
        ]
        if experiment.mass_kg is not None and experiment.force_n is not None:
            exp_lines.append(
                f"- setup: mass = {experiment.mass_kg:.2f} kg, "
                f"net force = {experiment.force_n:.2f} N"
            )
        if experiment.acceleration_m_s2 is not None:
            exp_lines.append(
                f"- acceleration (deterministic a = F / m, computed by the app): "
                f"{experiment.acceleration_m_s2:.2f} m/s^2"
            )
        if experiment.prediction:
            exp_lines.append(f"- their prediction beforehand: {experiment.prediction}")
        if experiment.observation:
            exp_lines.append(f"- what they observed: {experiment.observation}")
        if experiment.explanation:
            exp_lines.append(f"- their explanation: {experiment.explanation}")
        exp_lines.append(
            "Compare their prediction with what happened, respond to their "
            "reasoning, and pose a next question (for example, what if the mass "
            "changed instead)."
        )
        experiment_block = "\n".join(exp_lines) + "\n"

    practice_block = ""
    if request.practice_problem:
        practice_block = f"\nPractice problem the student is working on:\n{request.practice_problem}\n"
    if request.student_attempt:
        practice_block += (
            f"\nStudent attempt to review:\n{request.student_attempt}\n"
        )

    current_input = (
        request.student_question
        or request.student_attempt
        or "(the student has not typed anything specific)"
    )

    user = f"""Help the student with this lesson.

Lesson title: {request.lesson_title}
Topic: {request.topic}
Grade level: {request.grade_level}

Learning objectives:
{objectives}

Teacher-listed misconceptions to watch for:
{misconceptions}

Physics concepts (authoritative):
{concept_blocks}

{candidate_block}

{experiment_block}
Recent conversation (oldest first):
{conversation}
{practice_block}
Student's current message:
{current_input}
"""

    return Prompt(system=system.strip(), user=user.strip(), version=TUTOR_PROMPT_VERSION)
