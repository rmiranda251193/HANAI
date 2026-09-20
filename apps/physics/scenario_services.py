"""Teacher Scenario Studio: an authoring/orchestration layer over the
existing Physics Lab architecture.

This module creates and validates ``PhysicsScenario`` rows -- it does not
compute Physics itself. A scenario converts to the exact same
``lab_scenarios.LabScenario`` shape the two built-in, code-defined
challenges already use (``lab_scenarios.to_lab_scenario``), and student
checks are evaluated by the exact same ``lab_scenarios.evaluate_scenario``,
unchanged. There is no second experiment engine, no second grading engine,
and nothing here ever stores or executes a formula: ``initial_state`` and
``target_condition`` are plain, server-validated JSON, checked against the
selected simulation's own registered bounds
(``apps.physics.simulation_registry``) and the checker's own allow-listed
target kinds (``apps.physics.lab_scenarios.allowed_target_kinds`` /
``value_fields_for``).

Deliberately scoped to the simulation types ``lab_scenarios.py``'s
deterministic checker actually supports -- see
``TEACHER_SCENARIO_SUPPORTED_TYPES`` (Kinematics and Newton's Second Law so
far). Extending this to another simulation type means teaching
``lab_scenarios.py`` that type's own state fields first, via its
``_STATE_BUILDERS`` registry -- the same "grown one at a time" discipline
``hands_on_experiments.py``/``depth_layers.py`` already use.
"""

from __future__ import annotations

import math
import re

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils.text import slugify

from .lab_scenarios import (
    TargetCondition,
    allowed_target_kinds,
    evaluate_scenario as _evaluate_scenario,
    get_scenario,
    value_fields_for,
)
from .models import PhysicsScenario, PhysicsSimulation
from .simulation_registry import get_simulation_definition

# The simulation types the deterministic checker actually understands today.
# A teacher may only build a scenario for one of these -- extended one type
# at a time as lab_scenarios.py's own state-builder registry grows.
TEACHER_SCENARIO_SUPPORTED_TYPES = frozenset({"kinematics", "newtons_second_law"})

TITLE_MAX = 200
DESCRIPTION_MAX = 2000
INSTRUCTIONS_MAX = 2000
PROMPT_MAX = 1000
MAX_AT_TIME_S = 20.0
MAX_TOLERANCE = 1_000_000.0

_Status = PhysicsScenario.Status
_Difficulty = PhysicsScenario.Difficulty
_Category = PhysicsScenario.Category

TARGET_KIND_LABELS = {
    "value": "Equals (within a tolerance)",
    "greater_than": "Greater than",
    "less_than": "Less than",
    "within_range": "Within a range",
    "reverses": "Reverses direction",
}

# Human labels for the fields a target may name, per supported simulation
# type. Kept here (display metadata only) rather than in lab_scenarios.py,
# which owns the authoritative *set* of valid fields via value_fields_for.
TARGET_FIELD_LABELS = {
    "kinematics": {
        "position_m": "Position (m)",
        "velocity_m_s": "Velocity (m/s)",
        "acceleration_m_s2": "Acceleration (m/s²)",
    },
    "newtons_second_law": {
        "acceleration_m_s2": "Acceleration (m/s²)",
        "velocity_m_s": "Velocity (m/s)",
        "position_m": "Position (m)",
    },
}


class ScenarioError(ValueError):
    """A teacher scenario submission was missing, malformed, or unsafe."""


class ScenarioNotFound(ScenarioError):
    """The scenario does not exist, or is not available in this context."""


class ScenarioPermissionError(ScenarioError):
    """A teacher tried to act on a scenario they do not own."""


# --- small helpers -----------------------------------------------------


def _clip(text, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _clean_required(text, *, limit: int, label: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        raise ScenarioError(f"Enter {label}.")
    if len(value) > limit:
        raise ScenarioError(f"That {label} is too long.")
    return value


def _as_float(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ScenarioError(f"{label} must be a number.")
    if math.isnan(number) or math.isinf(number):
        raise ScenarioError(f"{label} must be a finite number.")
    return number


def _resolve_simulation(simulation_id) -> PhysicsSimulation:
    """Server-side resolution only -- never trust a raw id from the client
    beyond looking it up. Only an active simulation of a scenario-studio-
    supported type may be chosen."""

    try:
        simulation = PhysicsSimulation.objects.filter(pk=int(simulation_id)).first()
    except (TypeError, ValueError):
        simulation = None
    if simulation is None:
        raise ScenarioError("That simulation could not be found.")
    if not simulation.is_active:
        raise ScenarioError("That simulation is not active.")
    if get_simulation_definition(simulation.simulation_type) is None:
        raise ScenarioError("That simulation type is not available yet.")
    if simulation.simulation_type not in TEACHER_SCENARIO_SUPPORTED_TYPES:
        raise ScenarioError(
            "Scenario authoring is not available for this simulation type yet."
        )
    return simulation


def _validate_initial_state(simulation_type: str, raw) -> dict:
    """Only the simulation's own registered input fields, each clamped to
    its own registered bounds -- never an arbitrary field, never executed."""

    definition = get_simulation_definition(simulation_type)
    if definition is None:
        raise ScenarioError("That simulation type is not available yet.")
    if not isinstance(raw, dict):
        raw = {}

    cleaned: dict[str, float] = {}
    for field in definition.input_fields:
        if field not in raw or raw[field] in (None, ""):
            continue
        value = _as_float(raw[field], field.replace("_", " "))
        lo, hi = definition.bounds.get(field, (float("-inf"), float("inf")))
        if value < lo or value > hi:
            raise ScenarioError(
                f"{field.replace('_', ' ')} must be between {lo:g} and {hi:g}."
            )
        cleaned[field] = value
    return cleaned


def _validate_target_condition(simulation_type: str, raw) -> dict:
    """Build and validate a target_condition dict -- an explicit allow-list
    of kinds/fields, numeric-only, no formulas. Constructing the real
    ``TargetCondition`` dataclass is the final check, so this can never
    drift from what ``evaluate_scenario`` actually accepts."""

    if not isinstance(raw, dict):
        raise ScenarioError("Choose a success condition.")

    kind = str(raw.get("kind", "")).strip()
    if kind not in allowed_target_kinds(simulation_type):
        raise ScenarioError("Choose a valid success condition type.")

    at_time_s = _as_float(raw.get("at_time_s", 0), "the target time")
    if at_time_s < 0 or at_time_s > MAX_AT_TIME_S:
        raise ScenarioError(f"The target time must be between 0 and {MAX_AT_TIME_S:g} seconds.")

    data = {"kind": kind, "at_time_s": at_time_s}

    if kind == "reverses":
        data["description"] = "The object moves forward, stops, then reverses direction."
    else:
        field = str(raw.get("field", "")).strip()
        if field not in value_fields_for(simulation_type):
            raise ScenarioError("Choose a valid variable for the success condition.")
        data["field"] = field
        label = TARGET_FIELD_LABELS.get(simulation_type, {}).get(field, field.replace("_", " "))

        if kind == "within_range":
            range_min = _as_float(raw.get("range_min", 0), "the minimum value")
            range_max = _as_float(raw.get("range_max", 0), "the maximum value")
            if range_min > range_max:
                raise ScenarioError("The minimum value cannot be greater than the maximum.")
            data.update(range_min=range_min, range_max=range_max)
            data["description"] = (
                f"{label} is between {range_min:g} and {range_max:g} at t = {at_time_s:g} s."
            )
        else:
            target = _as_float(raw.get("target", 0), "the target value")
            data["target"] = target
            if kind == "value":
                tolerance = _as_float(raw.get("tolerance", 0), "the tolerance")
                if tolerance < 0 or tolerance > MAX_TOLERANCE:
                    raise ScenarioError("Enter a sensible, non-negative tolerance.")
                data["tolerance"] = tolerance
                data["description"] = f"{label} is {target:g} ± {tolerance:g} at t = {at_time_s:g} s."
            elif kind == "greater_than":
                data["description"] = f"{label} is greater than {target:g} at t = {at_time_s:g} s."
            else:  # less_than
                data["description"] = f"{label} is less than {target:g} at t = {at_time_s:g} s."

    try:
        TargetCondition(**data)
    except (TypeError, ValueError) as exc:
        raise ScenarioError(str(exc))
    return data


def is_used(scenario: PhysicsScenario) -> bool:
    """True once a real student check exists against this scenario, ever --
    the same "locked after use" idea ``apps.assessments.services.is_used``
    already uses for a question's trusted answer definition."""

    from apps.students.models import LearningEvidence

    return LearningEvidence.objects.filter(context__scenario=scenario.slug).exists()


def _teacher_scenario(scenario_id) -> PhysicsScenario:
    scenario = (
        PhysicsScenario.objects.select_related("simulation", "created_by")
        .filter(pk=scenario_id)
        .first()
    )
    if scenario is None:
        raise ScenarioNotFound("That scenario could not be found.")
    return scenario


def _require_owner(scenario: PhysicsScenario, teacher) -> None:
    """A scenario belongs to exactly the teacher who created it. A legacy
    scenario with no recorded creator (created_by is null, e.g. from the
    admin) is editable by any teacher, mirroring
    ``apps.lessons``'s own "created_by is None -> open to any teacher" rule."""

    if scenario.created_by_id is not None and scenario.created_by_id != getattr(teacher, "id", None):
        raise ScenarioPermissionError("You can only change your own scenarios.")


# --- teacher: create / update / status / delete -------------------------


@transaction.atomic
def create_scenario(
    *,
    teacher,
    title,
    simulation_id,
    description="",
    instructions,
    prediction_prompt="",
    reflection_prompt="",
    initial_state=None,
    target_condition=None,
    difficulty=_Difficulty.INTRODUCTORY,
    category="",
) -> PhysicsScenario:
    clean_title = _clean_required(title, limit=TITLE_MAX, label="a title")
    clean_instructions = _clean_required(instructions, limit=INSTRUCTIONS_MAX, label="the student task")
    simulation = _resolve_simulation(simulation_id)
    clean_initial_state = _validate_initial_state(simulation.simulation_type, initial_state)
    clean_target = _validate_target_condition(simulation.simulation_type, target_condition)
    diff = difficulty if difficulty in _Difficulty.values else _Difficulty.INTRODUCTORY
    cat = category if category in _Category.values else ""

    return PhysicsScenario.objects.create(
        title=clean_title,
        simulation=simulation,
        description=_clip(description, DESCRIPTION_MAX),
        instructions=clean_instructions,
        prediction_prompt=_clip(prediction_prompt, PROMPT_MAX),
        reflection_prompt=_clip(reflection_prompt, PROMPT_MAX),
        initial_state=clean_initial_state,
        target_condition=clean_target,
        difficulty=diff,
        category=cat,
        created_by=teacher if getattr(teacher, "is_authenticated", False) else None,
    )


@transaction.atomic
def update_scenario(*, scenario_id, teacher, **fields) -> PhysicsScenario:
    """Edit a scenario. Once it has a real student check against it, its
    Physics identity (simulation/initial_state/target_condition) is locked
    -- a teacher cannot silently rewrite what a past result meant. Only
    presentation fields (title, description, instructions, prompts,
    difficulty, category) can still change."""

    scenario = PhysicsScenario.objects.select_for_update().select_related("simulation").get(pk=scenario_id)
    _require_owner(scenario, teacher)
    locked = is_used(scenario)

    update_fields = []
    if "title" in fields:
        scenario.title = _clean_required(fields["title"], limit=TITLE_MAX, label="a title")
        update_fields.append("title")
    if "description" in fields:
        scenario.description = _clip(fields["description"], DESCRIPTION_MAX)
        update_fields.append("description")
    if "instructions" in fields:
        scenario.instructions = _clean_required(
            fields["instructions"], limit=INSTRUCTIONS_MAX, label="the student task"
        )
        update_fields.append("instructions")
    if "prediction_prompt" in fields:
        scenario.prediction_prompt = _clip(fields["prediction_prompt"], PROMPT_MAX)
        update_fields.append("prediction_prompt")
    if "reflection_prompt" in fields:
        scenario.reflection_prompt = _clip(fields["reflection_prompt"], PROMPT_MAX)
        update_fields.append("reflection_prompt")
    if "difficulty" in fields and fields["difficulty"] in _Difficulty.values:
        scenario.difficulty = fields["difficulty"]
        update_fields.append("difficulty")
    if "category" in fields:
        scenario.category = fields["category"] if fields["category"] in _Category.values else ""
        update_fields.append("category")

    if not locked:
        if "simulation_id" in fields:
            scenario.simulation = _resolve_simulation(fields["simulation_id"])
            update_fields.append("simulation")
        if "initial_state" in fields:
            scenario.initial_state = _validate_initial_state(
                scenario.simulation.simulation_type, fields["initial_state"]
            )
            update_fields.append("initial_state")
        if "target_condition" in fields:
            scenario.target_condition = _validate_target_condition(
                scenario.simulation.simulation_type, fields["target_condition"]
            )
            update_fields.append("target_condition")
    else:
        if {"simulation_id", "initial_state", "target_condition"} & set(fields):
            raise ScenarioError(
                "A student has already run this scenario, so its simulation, "
                "starting values and success condition are locked. Create a "
                "new scenario instead."
            )

    if update_fields:
        update_fields.append("updated_at")
        scenario.save(update_fields=update_fields)
    return scenario


@transaction.atomic
def set_scenario_status(*, scenario_id, teacher, status) -> PhysicsScenario:
    scenario = PhysicsScenario.objects.select_for_update().get(pk=scenario_id)
    _require_owner(scenario, teacher)
    if status not in _Status.values:
        raise ScenarioError("Choose a valid status.")
    scenario.status = status
    scenario.save(update_fields=["status", "updated_at"])
    return scenario


@transaction.atomic
def delete_scenario(*, scenario_id, teacher) -> None:
    scenario = PhysicsScenario.objects.select_for_update().get(pk=scenario_id)
    _require_owner(scenario, teacher)
    if is_used(scenario):
        raise ScenarioError(
            "This scenario already has student results against it and cannot "
            "be deleted -- archive it instead."
        )
    try:
        scenario.delete()
    except ProtectedError:
        raise ScenarioError(
            "This scenario is linked to a lesson activity and cannot be "
            "deleted -- remove it from the lesson first."
        )


def list_teacher_scenarios(*, teacher):
    """"My Scenarios": only the ones this teacher created. Unlike the shared
    Question Bank/Assessments (any teacher may edit any of those), a
    scenario is single-owner -- see ``_require_owner``."""

    return (
        PhysicsScenario.objects.filter(created_by=teacher)
        .select_related("simulation")
        .order_by("-updated_at", "-id")
    )


def get_scenario_detail(scenario_id) -> PhysicsScenario:
    return _teacher_scenario(scenario_id)


# --- student: launch + evidence -------------------------------------------


def record_scenario_check(*, student, scenario: PhysicsScenario, met: bool, checks, lesson=None):
    """One compact LearningEvidence row per check of a teacher-authored
    scenario -- reusing the existing evidence model exactly, never a second
    one. The built-in, code-defined challenges are deliberately left
    unchanged (still zero-persistence, per lab_scenarios.py's own
    docstring); this only applies to PhysicsScenario rows, which is why it
    lives here and not in lab_scenarios.evaluate_scenario itself (which
    stays a pure function)."""

    from apps.students.models import LearningEvidence

    attempt_number = (
        LearningEvidence.objects.filter(student=student, context__scenario=scenario.slug).count() + 1
    )
    context = {
        "scenario": scenario.slug,
        "scenario_title": scenario.title,
        "simulation": scenario.simulation.simulation_type,
        "target_type": scenario.target_condition.get("kind", ""),
        "target_field": scenario.target_condition.get("field", ""),
        "result": bool(met),
        "attempt_number": attempt_number,
    }
    return LearningEvidence.objects.create(
        student=student,
        lesson=lesson,
        kind=LearningEvidence.Kind.EXPERIMENT_OBSERVED,
        detail=f"Scenario check: {scenario.title} -- {'target achieved' if met else 'target not yet reached'}.",
        context=context,
    )


# --- AI-assisted drafting -------------------------------------------------


def suggest_scenario_draft(*, teacher_request: str, simulation_id, provider=None) -> dict:
    """Ask the AI for a scenario draft. Returns a plain dict for the teacher
    to review and edit -- NOTHING is persisted here. Reuses
    ``_validate_initial_state``/``_validate_target_condition`` so an
    AI-suggested value is rejected by the exact same rules a teacher's own
    typo would be; an invalid suggestion is surfaced as a clear error, not
    silently coerced into something plausible-looking."""

    from apps.ai.providers import get_ai_provider
    from apps.ai.schemas import parse_model_json

    from .scenario_prompts import build_scenario_suggestion_prompt

    clean_request = _clean_required(teacher_request, limit=1000, label="what you want the scenario to do")
    simulation = _resolve_simulation(simulation_id)

    prompt = build_scenario_suggestion_prompt(teacher_request=clean_request, simulation=simulation)
    active_provider = provider or get_ai_provider()
    raw = active_provider.generate(prompt.user, system_prompt=prompt.system)
    payload = parse_model_json(raw, error_class=ScenarioError)
    if not isinstance(payload, dict):
        raise ScenarioError("The AI response was not a usable scenario draft.")

    initial_state = _validate_initial_state(simulation.simulation_type, payload.get("initial_state"))
    target_raw = {
        "kind": payload.get("target_kind", ""),
        "field": payload.get("target_field", ""),
        "at_time_s": payload.get("at_time_s", 0),
        "target": payload.get("target_value", 0),
        "tolerance": payload.get("tolerance", 0),
        "range_min": payload.get("range_min", 0),
        "range_max": payload.get("range_max", 0),
    }
    target_condition = _validate_target_condition(simulation.simulation_type, target_raw)

    return {
        "title": _clip(payload.get("title", ""), TITLE_MAX),
        "description": _clip(payload.get("description", ""), DESCRIPTION_MAX),
        "instructions": _clip(payload.get("instructions", ""), INSTRUCTIONS_MAX),
        "reflection_prompt": _clip(payload.get("reflection_prompt", ""), PROMPT_MAX),
        "simulation_id": simulation.pk,
        "initial_state": initial_state,
        "target_condition": target_condition,
    }


def get_teacher_scenario_evidence(student) -> list[dict]:
    """Compact, factual per-scenario record for the teacher workspace page --
    mirrors ``apps.assessments.services.get_teacher_assessment_evidence`` in
    shape and tone: attempts/result, never a score or mastery claim."""

    from apps.students.models import LearningEvidence

    rows = list(
        LearningEvidence.objects.filter(
            student=student,
            kind=LearningEvidence.Kind.EXPERIMENT_OBSERVED,
            context__has_key="scenario",
        ).order_by("-created_at")
    )
    by_scenario: dict[str, dict] = {}
    for row in rows:
        slug = row.context.get("scenario", "")
        entry = by_scenario.setdefault(
            slug,
            {
                "scenario": row.context.get("scenario_title", slug),
                "attempts": 0,
                "latest_result": None,
                "latest_when": row.created_at,
            },
        )
        entry["attempts"] += 1
        if entry["latest_result"] is None:
            entry["latest_result"] = "Target achieved" if row.context.get("result") else "Target not yet reached"
    return list(by_scenario.values())
