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
        if experiment.simulation_type == "kinematics":
            if (
                experiment.initial_position_m is not None
                and experiment.initial_velocity_m_s is not None
            ):
                setup = (
                    f"- setup: initial position = {experiment.initial_position_m:.2f} m, "
                    f"initial velocity = {experiment.initial_velocity_m_s:.2f} m/s"
                )
                if experiment.acceleration_m_s2 is not None:
                    setup += f", acceleration = {experiment.acceleration_m_s2:.2f} m/s^2"
                exp_lines.append(setup)
            if (
                experiment.time_s is not None
                and experiment.position_m is not None
                and experiment.velocity_m_s is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "v = v0 + at and x = x0 + v0*t + 1/2*a*t^2, computed by the app): "
                    f"position = {experiment.position_m:.2f} m, "
                    f"velocity = {experiment.velocity_m_s:.2f} m/s"
                )
        elif experiment.simulation_type == "projectile_motion":
            if (
                experiment.initial_speed_m_s is not None
                and experiment.launch_angle_deg is not None
            ):
                setup = (
                    f"- setup: initial speed = {experiment.initial_speed_m_s:.2f} m/s, "
                    f"launch angle = {experiment.launch_angle_deg:.0f} degrees"
                )
                if experiment.initial_height_m is not None:
                    setup += f", initial height = {experiment.initial_height_m:.2f} m"
                exp_lines.append(setup)
            if (
                experiment.time_s is not None
                and experiment.position_x_m is not None
                and experiment.position_y_m is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "x = v0*cos(theta)*t and y = y0 + v0*sin(theta)*t - 1/2*g*t^2, "
                    f"computed by the app): horizontal distance = {experiment.position_x_m:.2f} m, "
                    f"height = {experiment.position_y_m:.2f} m"
                )
        elif experiment.simulation_type == "circular_motion":
            if experiment.radius_m is not None and experiment.period_s is not None:
                exp_lines.append(
                    f"- setup: radius = {experiment.radius_m:.2f} m, "
                    f"period = {experiment.period_s:.2f} s"
                )
            if experiment.time_s is not None and experiment.velocity_m_s is not None:
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "v = 2*pi*r/T, computed by the app): speed = "
                    f"{experiment.velocity_m_s:.2f} m/s"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    "- centripetal acceleration (deterministic a_c = v^2 / r, "
                    f"computed by the app): {experiment.acceleration_m_s2:.2f} m/s^2"
                )
        elif experiment.simulation_type == "simple_harmonic_motion":
            if experiment.amplitude_m is not None and experiment.period_s is not None:
                exp_lines.append(
                    f"- setup: amplitude = {experiment.amplitude_m:.2f} m, "
                    f"period = {experiment.period_s:.2f} s"
                )
            if (
                experiment.time_s is not None
                and experiment.position_m is not None
                and experiment.velocity_m_s is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "x = A*cos(omega*t), computed by the app): "
                    f"position = {experiment.position_m:.2f} m, "
                    f"velocity = {experiment.velocity_m_s:.2f} m/s"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    "- acceleration (deterministic a = -omega^2 * x, "
                    f"computed by the app): {experiment.acceleration_m_s2:.2f} m/s^2"
                )
        elif experiment.simulation_type == "momentum_collision":
            if experiment.mass1_kg is not None and experiment.mass2_kg is not None:
                exp_lines.append(
                    f"- setup: mass 1 = {experiment.mass1_kg:.2f} kg, "
                    f"mass 2 = {experiment.mass2_kg:.2f} kg, cart 1's initial speed = "
                    f"{experiment.initial_velocity_m_s:.2f} m/s (cart 2 starts at rest), "
                    "collision type = "
                    + ("elastic" if (experiment.elastic or 0) >= 0.5 else "perfectly inelastic")
                )
            if (
                experiment.velocity_1_m_s is not None
                and experiment.velocity_2_m_s is not None
            ):
                exp_lines.append(
                    "- after the collision (deterministic, momentum always "
                    f"conserved, computed by the app): velocity 1 = "
                    f"{experiment.velocity_1_m_s:.2f} m/s, velocity 2 = "
                    f"{experiment.velocity_2_m_s:.2f} m/s"
                )
            if experiment.momentum_total_kg_m_s is not None:
                exp_lines.append(
                    f"- total momentum: {experiment.momentum_total_kg_m_s:.2f} kg m/s"
                )
            if experiment.kinetic_energy_total_j is not None:
                exp_lines.append(
                    f"- total kinetic energy: {experiment.kinetic_energy_total_j:.2f} J"
                )
        else:
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
