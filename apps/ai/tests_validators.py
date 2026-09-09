"""Deterministic, review-only validator tests for Step 27.

These cover the Physics arithmetic / unit checks and the v2 structured-plan
catalog / objective-alignment checks. Nothing here calls a network provider and
nothing rewrites a draft -- every finding is an advisory ``ReviewIssue``.
"""

from __future__ import annotations

import copy

from django.test import SimpleTestCase, TestCase

from apps.physics.models import (
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)

from .requests import ConceptContext, LessonGenerationRequest, LessonReviewRequest
from .schemas import LessonDraft, example_lesson_draft_dict
from .validators import (
    PhysicsExampleValidator,
    StructuredPlanValidator,
)


def _concept_context() -> ConceptContext:
    return ConceptContext(
        name="Force",
        description="An interaction that can change an object's motion.",
        topic="Dynamics",
        difficulty="introductory",
        equations=["F_net = ma"],
        si_units=["newton (N)"],
    )


def _generation_request(**overrides) -> LessonGenerationRequest:
    data = {
        "title": "Forces",
        "topic": "Dynamics",
        "grade_level": "11",
        "duration_minutes": 45,
        "learning_objectives": ["Relate net force, mass, and acceleration."],
        "common_misconceptions": ["A force always causes motion."],
        "concepts": (_concept_context(),),
    }
    data.update(overrides)
    return LessonGenerationRequest(**data)


def _draft(**overrides) -> LessonDraft:
    payload = copy.deepcopy(example_lesson_draft_dict())
    payload.update(overrides)
    return LessonDraft.from_dict(payload)


def _review_request(draft: LessonDraft, **gen_overrides) -> LessonReviewRequest:
    return LessonReviewRequest(
        original_lesson=_generation_request(**gen_overrides),
        draft=draft,
    )


class PhysicsExampleValidatorTests(SimpleTestCase):
    """Pure arithmetic / unit checks on numbers the draft itself states."""

    def _validate(self, worked_examples):
        draft = _draft(worked_examples=worked_examples)
        return PhysicsExampleValidator().validate(_review_request(draft))

    def test_inconsistent_newtons_second_law_is_flagged_as_an_error(self):
        findings = self._validate(
            [
                {
                    "title": "Bad arithmetic",
                    "problem": "A net force of 10 N acts on a mass of 2 kg.",
                    "solution": "The acceleration of 9 m/s² follows.",
                }
            ]
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "calculation")
        self.assertEqual(findings[0].severity, "error")
        self.assertIn("F/m", findings[0].issue)

    def test_inconsistent_newtons_second_law_with_ascii_units_is_also_flagged(self):
        # Regression: the ASCII caret form "m/s^2" must parse whole, otherwise
        # the arithmetic check silently skips every plain-text example.
        findings = self._validate(
            [
                {
                    "title": "ASCII units",
                    "problem": "A net force of 10 N acts on a mass of 2 kg.",
                    "solution": "The acceleration of 9 m/s^2 follows.",
                }
            ]
        )

        self.assertTrue(
            any(f.category == "calculation" and f.severity == "error" for f in findings)
        )

    def test_consistent_newtons_second_law_produces_no_finding(self):
        findings = self._validate(
            [
                {
                    "title": "Good arithmetic",
                    "problem": "A net force of 10 N acts on a mass of 2 kg.",
                    "solution": "The acceleration of 5 m/s² follows.",
                }
            ]
        )

        self.assertEqual(findings, ())

    def test_force_stated_in_mass_units_is_flagged(self):
        findings = self._validate(
            [
                {
                    "title": "Wrong units",
                    "problem": "A net force of 10 kg acts on a mass of 2 kg.",
                    "solution": "The acceleration of 5 m/s² follows.",
                }
            ]
        )

        self.assertTrue(findings)
        self.assertTrue(all(f.category == "units" for f in findings))
        self.assertTrue(any("force" in f.issue.lower() for f in findings))

    def test_inconsistent_kinematics_is_flagged_as_an_error(self):
        findings = self._validate(
            [
                {
                    "title": "Kinematics",
                    "problem": "v0 of 2 m/s, an acceleration of 3 m/s², over a time of 4 s.",
                    "solution": "The final velocity of 20 m/s results.",
                }
            ]
        )

        self.assertTrue(any(f.category == "calculation" and f.severity == "error" for f in findings))

    def test_ambiguous_example_produces_no_finding(self):
        findings = self._validate(
            [
                {
                    "title": "Prose only",
                    "problem": "Two forces act on a cart on a track.",
                    "solution": "The cart speeds up in the direction of the larger force.",
                }
            ]
        )

        self.assertEqual(findings, ())


class StructuredPlanValidatorObjectiveAlignmentTests(SimpleTestCase):
    """Objective-alignment checks work without any catalog (no DB needed)."""

    def test_objective_index_out_of_range_is_an_error(self):
        draft = _draft(
            learning_objectives=["Only objective zero."],
            activity_plan=[
                {
                    "title": "Misaligned activity",
                    "description": "Points at an objective that does not exist.",
                    "activity_type": "explanation",
                    "objective_alignment": [5],
                    "estimated_minutes": 10,
                    "instructions": "",
                    "simulation_type": "",
                }
            ],
        )

        findings = StructuredPlanValidator().validate(_review_request(draft))

        self.assertTrue(any(f.category == "alignment" and f.severity == "error" for f in findings))

    def test_activity_with_no_alignment_is_a_warning(self):
        draft = _draft(
            learning_objectives=["Only objective zero."],
            activity_plan=[
                {
                    "title": "Unaligned activity",
                    "description": "Supports no listed objective.",
                    "activity_type": "explanation",
                    "objective_alignment": [],
                    "estimated_minutes": 10,
                    "instructions": "",
                    "simulation_type": "",
                }
            ],
        )

        findings = StructuredPlanValidator().validate(_review_request(draft))

        self.assertTrue(any(f.category == "alignment" and f.severity == "warning" for f in findings))

    def test_empty_catalog_never_flags_concepts_or_misconceptions(self):
        # A SimpleTestCase cannot touch the DB, so the catalogs read as empty and
        # the concept / misconception / simulation checks must stay silent.
        draft = _draft(
            practice_suggestions=[
                {
                    "prompt": "Anything.",
                    "concept": "A concept that is not in any catalog",
                    "expected_reasoning": "Reasoning.",
                    "difficulty": "easy",
                }
            ],
            misconception_awareness=[
                {
                    "misconception_code": "NOT_A_REAL_CODE",
                    "why_relevant": "Because.",
                    "instructional_note": "Note.",
                }
            ],
        )

        findings = StructuredPlanValidator().validate(_review_request(draft))

        self.assertFalse(any(f.category == "misconception" for f in findings))
        self.assertFalse(
            any("catalog" in f.issue.lower() for f in findings)
        )


class StructuredPlanValidatorCatalogTests(TestCase):
    """Concept / misconception / simulation resolution against the live catalog."""

    def setUp(self):
        self.force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
        )
        self.misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION",
            title="A force always means acceleration",
            description="A learner may equate 'a force acts' with 'it accelerates'.",
            physics_concept=self.force,
        )
        self.simulation = PhysicsSimulation.objects.create(
            concept=self.force,
            slug="nsl-lab",
            title="Newton's Second Law Lab",
            simulation_type="newtons_second_law",
        )

    def _validate(self, **draft_overrides):
        draft = _draft(**draft_overrides)
        return StructuredPlanValidator().validate(_review_request(draft))

    def test_unknown_practice_concept_is_a_reviewable_warning(self):
        findings = self._validate(
            practice_suggestions=[
                {
                    "prompt": "Find the acceleration.",
                    "concept": "Momentum",
                    "expected_reasoning": "a = F/m.",
                    "difficulty": "easy",
                }
            ]
        )

        self.assertTrue(
            any(
                f.category == "alignment"
                and f.severity == "warning"
                and "Momentum" in f.issue
                for f in findings
            )
        )

    def test_known_practice_concept_produces_no_concept_finding(self):
        findings = self._validate(
            practice_suggestions=[
                {
                    "prompt": "Find the acceleration.",
                    "concept": "Force",
                    "expected_reasoning": "a = F/m.",
                    "difficulty": "easy",
                }
            ]
        )

        # Scoped to the practice suggestion under test -- other default v2
        # fields legitimately reference concepts this class does not seed.
        self.assertFalse(any("Practice suggestion" in f.issue for f in findings))

    def test_unknown_misconception_code_is_flagged(self):
        findings = self._validate(
            misconception_awareness=[
                {
                    "misconception_code": "MADE_UP_CODE",
                    "why_relevant": "Not real.",
                    "instructional_note": "Ignore.",
                }
            ]
        )

        self.assertTrue(
            any(f.category == "misconception" and "MADE_UP_CODE" in f.issue for f in findings)
        )

    def test_known_misconception_code_produces_no_finding(self):
        findings = self._validate(
            misconception_awareness=[
                {
                    "misconception_code": "FORCE_VS_ACCELERATION",
                    "why_relevant": "Directly relevant.",
                    "instructional_note": "Contrast balanced and unbalanced forces.",
                }
            ]
        )

        self.assertFalse(any(f.category == "misconception" for f in findings))

    def test_unknown_simulation_type_on_a_physics_lab_activity_is_flagged(self):
        findings = self._validate(
            activity_plan=[
                {
                    "title": "Lab",
                    "description": "Runs a simulation.",
                    "activity_type": "physics_lab",
                    "objective_alignment": [0],
                    "estimated_minutes": 20,
                    "instructions": "",
                    "simulation_type": "not_a_real_simulation",
                }
            ]
        )

        self.assertTrue(
            any(
                f.severity == "warning" and "not_a_real_simulation" in f.issue
                for f in findings
            )
        )

    def test_known_active_simulation_type_produces_no_simulation_finding(self):
        findings = self._validate(
            activity_plan=[
                {
                    "title": "Lab",
                    "description": "Runs a simulation.",
                    "activity_type": "physics_lab",
                    "objective_alignment": [0],
                    "estimated_minutes": 20,
                    "instructions": "",
                    "simulation_type": "newtons_second_law",
                }
            ]
        )

        self.assertFalse(any("simulation" in f.issue.lower() for f in findings))
