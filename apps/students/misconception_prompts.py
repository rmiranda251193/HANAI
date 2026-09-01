from __future__ import annotations

import json

from apps.ai.prompts import Prompt
from apps.ai.requests import ConceptContext

from .misconception_schemas import MISCONCEPTION_ASSESSMENT_JSON_SCHEMA

MISCONCEPTION_PROMPT_VERSION = "physics-misconception-v1"


def build_misconception_prompt(
    *,
    lesson_title: str,
    topic: str,
    grade_level: str,
    concepts: tuple[ConceptContext, ...] = (),
    catalog: tuple[tuple[str, str, str], ...] = (),
    student_excerpts: tuple[str, ...] = (),
    rule_hits: tuple[str, ...] = (),
) -> Prompt:
    """Build the prompt for AI-assisted misconception assessment.

    ``catalog`` is a tuple of ``(code, title, description)`` rows. The model must
    only ever return codes from this list.
    """

    system = f"""You assist DodongOS Physics AI with cautious misconception assessment.

Core rule: AI assists. Teachers decide. Students learn by thinking.

You look at a few things a student wrote and judge whether they *might* point to
a known misconception from the supplied catalog. You are not a diagnostic tool.

Rules:
- Only propose candidates whose code appears in the supplied catalog. Never
  invent a code or a misconception.
- For every candidate, quote or closely paraphrase the student words you relied
  on. No evidence means no candidate.
- Never claim certainty. Prefer "may", "could", "suggests".
- Absence of evidence is not evidence of absence. If nothing in the text points
  to a misconception, return an empty assessments list.
- Stay grounded in the supplied Physics concepts; do not import outside claims.
- A single sentence is weak evidence at most. Reserve "strong" for clear,
  repeated, unambiguous reasoning.
- Return ONLY a JSON object. No markdown, no commentary, no code fences.

Output schema:
{json.dumps(MISCONCEPTION_ASSESSMENT_JSON_SCHEMA, indent=2)}

Prompt version: {MISCONCEPTION_PROMPT_VERSION}
"""

    if concepts:
        concept_blocks = "\n\n".join(concept.as_prompt_block() for concept in concepts)
    else:
        concept_blocks = "No concept knowledge was supplied. Judge only from the catalog."

    if catalog:
        catalog_block = "\n".join(
            f"- {code}: {title}\n  {description}" for code, title, description in catalog
        )
    else:
        catalog_block = "(the catalog is empty; return an empty assessments list)"

    if student_excerpts:
        excerpt_block = "\n".join(f"- \"{item}\"" for item in student_excerpts)
    else:
        excerpt_block = "(no student text supplied)"

    rule_block = (
        ", ".join(rule_hits)
        if rule_hits
        else "(none; rules found nothing, which is not proof of absence)"
    )

    user = f"""Assess the student text below against the misconception catalog.

Lesson: {lesson_title}
Topic: {topic}
Grade level: {grade_level}

Physics concepts (authoritative):
{concept_blocks}

Misconception catalog (use only these codes):
{catalog_block}

Rule-based detectors already flagged: {rule_block}

Student statements to assess:
{excerpt_block}
"""

    return Prompt(
        system=system.strip(),
        user=user.strip(),
        version=MISCONCEPTION_PROMPT_VERSION,
    )
