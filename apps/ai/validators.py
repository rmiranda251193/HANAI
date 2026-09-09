"""Deterministic, review-only validators for a generated lesson draft.

Nothing here rewrites, grades, or authorises content. Each validator returns
conservative ``ReviewIssue`` findings that the existing review pipeline
persists as ``PersistedReviewIssue`` rows for the teacher to decide on. The AI
is never the authoritative Physics engine -- the numeric checks below are pure
arithmetic on values the model itself stated.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Protocol

from .requests import LessonReviewRequest
from .schemas import ReviewIssue

# Relative tolerance for "the stated number matches the computed number".
_REL_TOL = 0.02
_ABS_TOL = 0.05

_NUM = r"[-+]?\d+(?:\.\d+)?"

_FORCE_UNITS = {"n", "newton", "newtons"}
_MASS_UNITS = {"kg", "kilogram", "kilograms", "g", "gram", "grams"}
_ACCEL_UNITS = {"m/s^2", "m/s²", "m/s/s", "ms^-2", "m·s^-2"}
_VELOCITY_UNITS = {"m/s", "ms^-1", "m·s^-1", "km/h"}
_TIME_UNITS = {"s", "sec", "secs", "second", "seconds"}
_LENGTH_UNITS = {"m", "metre", "metres", "meter", "meters", "km", "cm"}


class LessonReviewValidator(Protocol):
    """Extension point for deterministic, review-only lesson checks."""

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        """Return conservative findings without modifying the lesson or draft."""


# --- helpers -----------------------------------------------------------


def _issue(category, severity, issue, explanation, section, revision, confidence) -> ReviewIssue:
    return ReviewIssue(
        category=category,
        severity=severity,
        issue=issue[:400],
        explanation=explanation[:600],
        affected_section=section[:100],
        suggested_revision=revision[:600],
        confidence=confidence,
    )


def _find_one(text: str, symbol_pattern: str):
    """Return (value: float, unit: str) for a single unambiguous 'symbol = num unit'.

    Returns None if there is not exactly one clear match, so an ambiguous
    example produces no finding rather than a fragile one.
    """

    # The trailing unit token must allow digits so exponent forms like
    # "m/s^2" / "ms^-2" / "s^2" parse whole -- without them the arithmetic
    # checks silently skip any example that writes acceleration in ASCII.
    pat = re.compile(
        symbol_pattern + r"\s*(?:=|is|of)\s*(" + _NUM + r")\s*([A-Za-z0-9²/·^\-]+)",
        re.IGNORECASE,
    )
    matches = pat.findall(text)
    if len(matches) != 1:
        return None
    raw_value, raw_unit = matches[0]
    try:
        value = float(raw_value)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value, raw_unit.strip().lower().rstrip(".")


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(abs(b) * _REL_TOL, _ABS_TOL)


def _catalogs():
    """(concept_names, misconception_codes, usable_sim_types) from the DB.

    Returns empty sets if the catalogs cannot be read (no DB, empty install).
    A validator that has no catalog to compare against simply stays silent --
    the same philosophy as the reserved ``PhysicsValidator``.
    """

    try:
        from apps.physics.models import (
            PhysicsConcept,
            PhysicsMisconception,
            PhysicsSimulation,
        )
        from apps.physics.simulation_registry import get_simulation_definition

        concept_names = {
            n.lower()
            for n in PhysicsConcept.objects.filter(is_active=True).values_list(
                "name", flat=True
            )
        }
        misconception_codes = {
            c.upper()
            for c in PhysicsMisconception.objects.filter(is_active=True).values_list(
                "code", flat=True
            )
        }
        active_sim_types = set(
            PhysicsSimulation.objects.filter(is_active=True).values_list(
                "simulation_type", flat=True
            )
        )
        usable_sim_types = {
            t for t in active_sim_types if get_simulation_definition(t) is not None
        }
        return concept_names, misconception_codes, usable_sim_types
    except Exception:  # pragma: no cover - defensive; never break review
        return set(), set(), set()


# --- Physics numeric / unit consistency ------------------------------


class PhysicsExampleValidator:
    """Pure-arithmetic checks on numbers the draft itself states.

    Deliberately conservative: only fires when a worked example clearly names
    force, mass and acceleration (or v0, a, t and v) with a single value each.
    """

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        findings: list[ReviewIssue] = []
        for i, ex in enumerate(request.draft.worked_examples):
            text = f"{ex.problem}\n{ex.solution}"
            findings.extend(self._check_newtons_second_law(text, ex.title, i))
            findings.extend(self._check_kinematics(text, ex.title, i))
        return tuple(findings)

    def _check_newtons_second_law(self, text, title, index) -> list[ReviewIssue]:
        force = _find_one(text, r"\b(?:F_net|F net|net force|force|F)\b")
        mass = _find_one(text, r"\b(?:mass|m)\b")
        accel = _find_one(text, r"\b(?:acceleration|a)\b")
        if not (force and mass and accel):
            return []
        f_val, f_unit = force
        m_val, m_unit = mass
        a_val, a_unit = accel

        out: list[ReviewIssue] = []
        # Unit sanity first.
        if f_unit in _MASS_UNITS or f_unit in _ACCEL_UNITS:
            out.append(_issue("units", "warning",
                f"Worked example {index + 1} states force with unit '{f_unit}'.",
                "Force should be given in newtons (N).", f"Worked example: {title}",
                "State the force in newtons.", "high"))
        if m_unit in _FORCE_UNITS or m_unit in _ACCEL_UNITS:
            out.append(_issue("units", "warning",
                f"Worked example {index + 1} states mass with unit '{m_unit}'.",
                "Mass should be given in kilograms (kg).", f"Worked example: {title}",
                "State the mass in kilograms.", "high"))
        if a_unit in _VELOCITY_UNITS or a_unit in _LENGTH_UNITS:
            out.append(_issue("units", "warning",
                f"Worked example {index + 1} states acceleration with unit '{a_unit}'.",
                "Acceleration should be in m/s^2, not a velocity or length unit.",
                f"Worked example: {title}", "State the acceleration in m/s^2.", "high"))

        # Arithmetic only when units are the expected kinds.
        if (
            f_unit in _FORCE_UNITS
            and m_unit in _MASS_UNITS
            and a_unit in _ACCEL_UNITS
            and m_val > 0
        ):
            expected = f_val / m_val
            if not _close(a_val, expected):
                out.append(_issue("calculation", "error",
                    f"Worked example {index + 1}: stated a = {a_val} m/s^2 is inconsistent "
                    f"with F/m = {expected:.3g} m/s^2.",
                    "For a constant net force, a = F_net / m. The stated acceleration does "
                    "not match the stated force and mass.",
                    f"Worked example: {title}",
                    f"Recompute: a = {f_val} N / {m_val} kg = {expected:.3g} m/s^2.",
                    "high"))
        return out

    def _check_kinematics(self, text, title, index) -> list[ReviewIssue]:
        v0 = _find_one(text, r"\b(?:initial velocity|v0|v₀)\b")
        acc = _find_one(text, r"\b(?:acceleration|a)\b")
        t = _find_one(text, r"\b(?:time|t)\b")
        v = _find_one(text, r"\b(?:final velocity|velocity|v)\b")
        if not (v0 and acc and t and v):
            return []
        (v0_val, v0_u), (a_val, a_u), (t_val, t_u), (v_val, v_u) = v0, acc, t, v
        if not (
            v0_u in _VELOCITY_UNITS and a_u in _ACCEL_UNITS and t_u in _TIME_UNITS
            and v_u in _VELOCITY_UNITS
        ):
            return []
        expected = v0_val + a_val * t_val
        if _close(v_val, expected):
            return []
        return [_issue("calculation", "error",
            f"Worked example {index + 1}: stated v = {v_val} m/s is inconsistent with "
            f"v0 + a*t = {expected:.3g} m/s.",
            "For constant acceleration, v = v0 + a*t. The stated final velocity does not "
            "match the stated initial velocity, acceleration and time.",
            f"Worked example: {title}",
            f"Recompute: v = {v0_val} + {a_val} * {t_val} = {expected:.3g} m/s.",
            "high")]


# --- structured-plan catalog / alignment checks --------------------


class StructuredPlanValidator:
    """Alignment + catalog resolution for the v2 structured fields."""

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        draft = request.draft
        if not draft.is_v2 and not (
            draft.activity_plan
            or draft.practice_suggestions
            or draft.assessment_suggestions
            or draft.misconception_awareness
        ):
            return ()

        concept_names, misconception_codes, usable_sim_types = _catalogs()
        objective_count = len(draft.learning_objectives)
        out: list[ReviewIssue] = []

        for i, act in enumerate(draft.activity_plan):
            bad = [n for n in act.objective_alignment if n >= objective_count]
            if bad:
                out.append(_issue("alignment", "error",
                    f"Activity {i + 1} ('{act.title}') aligns to objective index "
                    f"{bad[0]}, but there are only {objective_count} objectives.",
                    "objective_alignment indices must point at real learning objectives.",
                    "Generated activity plan",
                    "Align this activity to an existing objective, or remove the reference.",
                    "high"))
            elif not act.objective_alignment:
                out.append(_issue("alignment", "warning",
                    f"Activity {i + 1} ('{act.title}') is not aligned to any learning objective.",
                    "Every activity should support at least one objective so the teacher "
                    "can see the objective -> activity -> assessment chain.",
                    "Generated activity plan",
                    "Add an objective_alignment entry or reconsider the activity.",
                    "medium"))
            if act.activity_type == "physics_lab" and usable_sim_types:
                if not act.simulation_type:
                    out.append(_issue("alignment", "info",
                        f"Activity {i + 1} ('{act.title}') is a Physics Lab activity with no "
                        "simulation_type.",
                        "A Physics Lab activity should name an existing simulation type so the "
                        "teacher can wire it up.",
                        "Generated activity plan",
                        "Suggest a simulation_type or change the activity type.", "low"))
                elif act.simulation_type not in usable_sim_types:
                    out.append(_issue("alignment", "warning",
                        f"Activity {i + 1} ('{act.title}') references simulation_type "
                        f"'{act.simulation_type}', which is not an available Physics Lab simulation.",
                        "Only active, registered simulation types can be used in a lesson.",
                        "Generated activity plan",
                        "Use one of the available simulation types, or drop the reference.",
                        "high"))

        for i, p in enumerate(draft.practice_suggestions):
            if concept_names and p.concept.lower() not in concept_names:
                out.append(_issue("alignment", "warning",
                    f"Practice suggestion {i + 1} references concept '{p.concept}', "
                    "which is not in the Physics concept catalog.",
                    "The teacher cannot link a practice item to a concept that does not exist.",
                    "Practice suggestions",
                    "Use an existing PhysicsConcept name.", "medium"))

        for i, a in enumerate(draft.assessment_suggestions):
            if concept_names and a.concept.lower() not in concept_names:
                out.append(_issue("alignment", "warning",
                    f"Assessment suggestion {i + 1} references concept '{a.concept}', "
                    "which is not in the Physics concept catalog.",
                    "The teacher cannot link an assessment item to a concept that does not exist.",
                    "Assessment suggestions",
                    "Use an existing PhysicsConcept name.", "medium"))

        for i, m in enumerate(draft.misconception_awareness):
            if misconception_codes and m.misconception_code.upper() not in misconception_codes:
                out.append(_issue("misconception", "warning",
                    f"Misconception awareness {i + 1} references code "
                    f"'{m.misconception_code}', which is not in the misconception catalog "
                    "and will be ignored.",
                    "The AI must reference existing PhysicsMisconception codes; unknown codes "
                    "are never created automatically.",
                    "Misconception awareness",
                    "Reference an existing misconception code, or remove this entry.",
                    "high"))

        return tuple(out)


class PhysicsValidator:
    """Reserved no-op kept for backward compatibility with older configs."""

    def validate(self, request: LessonReviewRequest) -> tuple[ReviewIssue, ...]:
        return ()


DEFAULT_REVIEW_VALIDATORS: tuple[LessonReviewValidator, ...] = (
    PhysicsValidator(),
    PhysicsExampleValidator(),
    StructuredPlanValidator(),
)


def run_deterministic_review_validators(
    request: LessonReviewRequest,
    validators: Iterable[LessonReviewValidator],
) -> tuple[ReviewIssue, ...]:
    """Run configured deterministic validators and combine their findings."""

    return tuple(
        issue
        for validator in validators
        for issue in validator.validate(request)
    )
