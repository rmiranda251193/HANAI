"""Generalized Physics Scenario Platform -- architecture tests.

Teacher Scenario Studio, the deterministic checker, and the simulation
registry were generalized so ANY deterministic Physics simulation can become
scenario-capable by registering its own ``ScenarioCapability`` (see
``apps.physics.simulation_registry``), with zero changes to Scenario Studio,
the checker (``apps.physics.lab_scenarios.evaluate_scenario``), the
experiment lifecycle, evidence, or ``LessonActivity`` integration.

This file proves that generality with a from-scratch, test-only mock
simulation ("test_mock_pendulum") that is never registered outside these
tests -- a real but deliberately simple physical relationship (a simple
pendulum's period, T = 2*pi*sqrt(L/g)), not fabricated Physics. Registration
and teardown are scoped per test via ``addCleanup`` so the mock never leaks
into another test module.

Kinematics- and Newton's-Second-Law-specific behavior is covered in
``tests_scenario_studio.py``; this file is about the *platform*, not any one
simulation's Physics.
"""

from __future__ import annotations

import json
import math

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai.providers import FakeAIProvider
from apps.physics import scenario_services as services
from apps.physics.lab_scenarios import (
    TEACHER_SCENARIO_PREFIX,
    allowed_target_kinds,
    evaluate_scenario,
    get_scenario,
    scenarios_for,
    value_fields_for,
)
from apps.physics.models import PhysicsConcept, PhysicsScenario, PhysicsSimulation
from apps.physics.simulation_registry import (
    ScenarioCapability,
    SimulationDefinition,
    get_simulation_definition,
    is_scenario_capable,
    register,
    registered_simulation_types,
    scenario_capable_simulation_types,
    unregister,
)
from apps.students.models import ExperimentAttempt, LearningEvidence, StudentProfile

User = get_user_model()
PW = "pw12345"

MOCK_TYPE = "test_mock_pendulum"
MOCK_LENGTH_BOUNDS = (0.1, 5.0)
MOCK_GRAVITY_BOUNDS = (1.0, 20.0)


def _mock_state_at(parameters: dict, at_time_s: float) -> dict:
    """A real, deterministic relationship (small-angle simple pendulum
    period) -- deliberately simple, never registered outside tests, and
    time-independent (a pendulum's period does not depend on when you ask)."""

    lo, hi = MOCK_LENGTH_BOUNDS
    length = max(lo, min(hi, float(parameters.get("length_m", 1.0))))
    lo, hi = MOCK_GRAVITY_BOUNDS
    gravity = max(lo, min(hi, float(parameters.get("gravity_m_s2", 9.8))))
    return {"period_s": 2 * math.pi * math.sqrt(length / gravity)}


def _mock_definition(*, scenario_capable=True) -> SimulationDefinition:
    return SimulationDefinition(
        simulation_type=MOCK_TYPE,
        template="physics/kinematics.html",  # reused only for the Lab to render; not under test
        equations=("T = 2π√(L/g)",),
        units={"length_m": "m", "gravity_m_s2": "m/s^2", "period_s": "s"},
        bounds={"length_m": MOCK_LENGTH_BOUNDS, "gravity_m_s2": MOCK_GRAVITY_BOUNDS},
        default_state={"length_m": 1.0, "gravity_m_s2": 9.8},
        input_fields=("length_m", "gravity_m_s2"),
        scenario=(
            ScenarioCapability(observable_fields=frozenset({"period_s"}), state_at=_mock_state_at)
            if scenario_capable
            else None
        ),
    )


class MockSimulationTestCase(TestCase):
    """Common setup for the mock-simulation tests: register it, guarantee
    teardown, and create one active ``PhysicsSimulation`` row of that type."""

    def setUp(self):
        register(_mock_definition())
        self.addCleanup(lambda: unregister(MOCK_TYPE))
        self.concept = PhysicsConcept.objects.create(
            name="Test Mock Pendulum", description="d", topic="Oscillations"
        )
        self.sim = PhysicsSimulation.objects.create(
            concept=self.concept, title="Mock Pendulum", simulation_type=MOCK_TYPE,
        )
        self.teacher = User.objects.create_user("teach_mock", password=PW, is_staff=True)


class ScenarioPlatformArchitectureTests(MockSimulationTestCase):
    """Phase 12's six demonstration points."""

    def _create_and_activate(self, **overrides):
        fields = dict(
            teacher=self.teacher, title="Tune the pendulum", simulation_id=self.sim.pk,
            instructions="Choose a length and gravity so the period is about 2 s.",
            initial_state={"length_m": 1.0, "gravity_m_s2": 9.8},
            target_condition={
                "kind": "value", "field": "period_s", "at_time_s": 0,
                "target": 2.006, "tolerance": 0.01,
            },
        )
        fields.update(overrides)
        scenario = services.create_scenario(**fields)
        services.set_scenario_status(
            scenario_id=scenario.pk, teacher=self.teacher, status=PhysicsScenario.Status.ACTIVE
        )
        scenario.refresh_from_db()
        return scenario

    def test_1_scenario_studio_accepts_the_new_simulation(self):
        from apps.physics.scenario_views import _simulation_choices

        scenario = services.create_scenario(
            teacher=self.teacher, title="Tune the pendulum", simulation_id=self.sim.pk,
            instructions="x", initial_state={"length_m": 1.0, "gravity_m_s2": 9.8},
            target_condition={"kind": "value", "field": "period_s", "target": 2.0, "tolerance": 0.1},
        )
        self.assertEqual(scenario.simulation_id, self.sim.pk)
        # Discovered generically -- Scenario Studio's own UI never lists
        # simulation types by name, it asks the registry.
        self.assertIn(self.sim.pk, [pk for pk, _, _ in _simulation_choices()])

    def test_2_state_validation_comes_from_the_simulation_definition(self):
        cleaned = services._validate_initial_state(MOCK_TYPE, {"length_m": "2.0", "gravity_m_s2": "9.8"})
        self.assertEqual(cleaned, {"length_m": 2.0, "gravity_m_s2": 9.8})
        with self.assertRaises(services.ScenarioError):
            services._validate_initial_state(MOCK_TYPE, {"length_m": "999"})  # out of the mock's own bounds

    def test_3_scenario_evaluation_uses_the_generic_checker(self):
        scenario = self._create_and_activate()
        lab_scenario = get_scenario(f"{TEACHER_SCENARIO_PREFIX}{scenario.slug}")
        result = evaluate_scenario(lab_scenario, parameters={"length_m": 1.0, "gravity_m_s2": 9.8})
        self.assertTrue(result["met"])
        # a forged huge length cannot cheat -- clamped inside the mock's own state_at
        bad = evaluate_scenario(lab_scenario, parameters={"length_m": 9e9, "gravity_m_s2": 9.8})
        self.assertFalse(bad["met"])

    def test_4_experiment_lifecycle_is_unchanged(self):
        scenario = self._create_and_activate()
        url = reverse(
            "physics_lab:experiment_scenario_check",
            args=[self.sim.slug, f"{TEACHER_SCENARIO_PREFIX}{scenario.slug}"],
        )
        before = ExperimentAttempt.objects.count()
        response = self.client.post(url, {"length_m": "1.0", "gravity_m_s2": "9.8"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["met"])
        self.assertEqual(ExperimentAttempt.objects.count(), before)  # no new/second persistence path

    def test_5_evidence_is_unchanged(self):
        scenario = self._create_and_activate()
        student = StudentProfile.objects.create(display_name="Mock Student")
        services.record_scenario_check(student=student, scenario=scenario, met=True, checks=[])
        rows = LearningEvidence.objects.filter(student=student)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().kind, LearningEvidence.Kind.EXPERIMENT_OBSERVED)
        self.assertEqual(rows.first().context["scenario"], scenario.slug)

    def test_6_lesson_activity_integration_is_unchanged(self):
        from apps.lessons.authoring_services import _student_launch, create_activity
        from apps.lessons.models import Lesson

        scenario = self._create_and_activate()
        lesson = Lesson.objects.create(
            title="Pendulums", topic="Oscillations", grade_level="11",
            duration_minutes=45, learning_objectives=["x"],
        )
        activity = create_activity(
            lesson=lesson, teacher=self.teacher, activity_type="scenario",
            title="Try the pendulum challenge", reference_id=scenario.pk,
        )
        self.assertEqual(activity.scenario_id, scenario.pk)
        url, label = _student_launch(activity, lesson)
        self.assertEqual(label, "Open the Scenario")
        self.assertIn(f"scenario={scenario.slug}", url)


class RegistryArchitectureTests(TestCase):
    def test_registration_and_lookup_round_trip(self):
        register(_mock_definition())
        try:
            found = get_simulation_definition(MOCK_TYPE)
            self.assertIsNotNone(found)
            self.assertEqual(found.simulation_type, MOCK_TYPE)
        finally:
            unregister(MOCK_TYPE)
        self.assertIsNone(get_simulation_definition(MOCK_TYPE))

    def test_duplicate_registration_is_handled_safely_last_one_wins(self):
        register(_mock_definition())
        try:
            register(SimulationDefinition(
                simulation_type=MOCK_TYPE, template="physics/kinematics.html",
                equations=("replaced",), units={}, bounds={}, default_state={},
                input_fields=(), scenario=None,
            ))
            found = get_simulation_definition(MOCK_TYPE)
            self.assertEqual(found.equations, ("replaced",))
            self.assertFalse(is_scenario_capable(MOCK_TYPE))  # the replacement dropped scenario support
        finally:
            unregister(MOCK_TYPE)

    def test_scenario_capable_simulations_are_discoverable(self):
        self.assertNotIn(MOCK_TYPE, scenario_capable_simulation_types())
        register(_mock_definition())
        try:
            self.assertIn(MOCK_TYPE, scenario_capable_simulation_types())
            self.assertTrue(is_scenario_capable(MOCK_TYPE))
        finally:
            unregister(MOCK_TYPE)

    def test_non_scenario_simulation_is_not_exposed_as_scenario_capable(self):
        register(_mock_definition(scenario_capable=False))
        try:
            self.assertNotIn(MOCK_TYPE, scenario_capable_simulation_types())
            self.assertFalse(is_scenario_capable(MOCK_TYPE))
        finally:
            unregister(MOCK_TYPE)

    def test_at_least_one_already_registered_simulation_is_not_scenario_capable(self):
        # Proves the platform does not silently make everything scenario-capable.
        others = set(registered_simulation_types()) - scenario_capable_simulation_types()
        self.assertTrue(others, "expected at least one registered simulation with no ScenarioCapability")
        self.assertIn("projectile_motion", others)

    def test_unregister_of_an_unknown_type_does_not_raise(self):
        unregister("does-not-exist")  # no-op, no exception


class GenericValidationTests(MockSimulationTestCase):
    """Generic initial-state validation using the mock type -- proves nothing
    in ``scenario_services.py`` is hard-coded to a particular topic."""

    def test_registered_fields_are_accepted(self):
        cleaned = services._validate_initial_state(MOCK_TYPE, {"length_m": 2, "gravity_m_s2": 5})
        self.assertEqual(cleaned, {"length_m": 2.0, "gravity_m_s2": 5.0})

    def test_unknown_field_is_dropped_not_stored(self):
        cleaned = services._validate_initial_state(MOCK_TYPE, {"length_m": 2, "warp_factor": 9})
        self.assertNotIn("warp_factor", cleaned)

    def test_bounds_are_enforced(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_initial_state(MOCK_TYPE, {"gravity_m_s2": 999})

    def test_nan_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_initial_state(MOCK_TYPE, {"length_m": "nan"})

    def test_infinity_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_initial_state(MOCK_TYPE, {"length_m": "inf"})

    def test_invalid_type_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_initial_state(MOCK_TYPE, {"length_m": "<script>x</script>"})

    def test_unregistered_simulation_type_is_rejected_by_resolve(self):
        with self.assertRaises(services.ScenarioError):
            services._resolve_simulation(999999)


class GenericTargetConditionTests(MockSimulationTestCase):
    def test_valid_observable_quantity_is_accepted(self):
        cleaned = services._validate_target_condition(
            MOCK_TYPE, {"kind": "value", "field": "period_s", "target": 2.0, "tolerance": 0.1}
        )
        self.assertEqual(cleaned["field"], "period_s")

    def test_unknown_quantity_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_target_condition(
                MOCK_TYPE, {"kind": "value", "field": "velocity_m_s", "target": 0, "tolerance": 1}
            )

    def test_invalid_operator_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_target_condition(
                MOCK_TYPE, {"kind": "does_not_exist", "field": "period_s", "target": 0}
            )

    def test_malformed_condition_missing_kind_is_rejected(self):
        with self.assertRaises(services.ScenarioError):
            services._validate_target_condition(MOCK_TYPE, {"field": "period_s", "target": 0})

    def test_condition_outside_simulation_capability_reverses_is_rejected(self):
        # The mock never declared supports_reverses -- "reverses" must not be
        # offered for it, even though it is a globally-known kind.
        self.assertNotIn("reverses", allowed_target_kinds(MOCK_TYPE))
        with self.assertRaises(services.ScenarioError):
            services._validate_target_condition(MOCK_TYPE, {"kind": "reverses"})

    def test_target_condition_dataclass_itself_rejects_a_field_outside_capability(self):
        from apps.physics.lab_scenarios import TargetCondition

        with self.assertRaises(ValueError):
            TargetCondition(
                kind="value", simulation_type=MOCK_TYPE, field="velocity_m_s",
                target=0, tolerance=1, description="x",
            )

    def test_value_fields_for_unregistered_type_is_empty(self):
        self.assertEqual(value_fields_for("does-not-exist"), frozenset())


class PersistenceArchitectureTests(MockSimulationTestCase):
    """No second experiment or evidence system was created for scenarios."""

    def test_no_scenario_specific_model_exists(self):
        from apps.physics import models as physics_models
        from apps.students import models as student_models

        for banned in ("ScenarioEvidence", "ScenarioAttempt", "ScenarioExperimentEngine"):
            self.assertFalse(hasattr(physics_models, banned))
            self.assertFalse(hasattr(student_models, banned))

    def test_experiment_attempt_is_the_only_experiment_model_touched(self):
        scenario = services.create_scenario(
            teacher=self.teacher, title="x", simulation_id=self.sim.pk, instructions="x",
            initial_state={"length_m": 1.0, "gravity_m_s2": 9.8},
            target_condition={"kind": "value", "field": "period_s", "target": 2.0, "tolerance": 1.0},
        )
        services.set_scenario_status(
            scenario_id=scenario.pk, teacher=self.teacher, status=PhysicsScenario.Status.ACTIVE
        )
        scenario.refresh_from_db()
        student = StudentProfile.objects.create(display_name="Alex")
        before = ExperimentAttempt.objects.count()
        services.record_scenario_check(student=student, scenario=scenario, met=True, checks=[])
        self.assertEqual(ExperimentAttempt.objects.count(), before)
        self.assertEqual(LearningEvidence.objects.filter(student=student).count(), 1)


class OwnershipArchitectureTests(MockSimulationTestCase):
    """Ownership/security protections are simulation-independent."""

    def setUp(self):
        super().setUp()
        self.other = User.objects.create_user("other_mock", password=PW, is_staff=True)
        self.scenario = services.create_scenario(
            teacher=self.teacher, title="x", simulation_id=self.sim.pk, instructions="x",
            initial_state={"length_m": 1.0, "gravity_m_s2": 9.8},
            target_condition={"kind": "value", "field": "period_s", "target": 2.0, "tolerance": 1.0},
        )

    def test_forged_created_by_is_ignored_regardless_of_simulation(self):
        self.assertEqual(self.scenario.created_by_id, self.teacher.id)

    def test_cross_owner_update_is_a_permission_error(self):
        with self.assertRaises(services.ScenarioPermissionError):
            services.update_scenario(scenario_id=self.scenario.pk, teacher=self.other, title="Hijacked")

    def test_cross_owner_edit_view_is_404(self):
        self.client.login(username=self.other.username, password=PW)
        response = self.client.get(reverse("teachers:scenario_edit", args=[self.scenario.slug]))
        self.assertEqual(response.status_code, 404)

    def test_lesson_activity_ownership_is_enforced_for_any_simulation(self):
        from apps.lessons.authoring_services import LessonAuthoringError, create_activity
        from apps.lessons.models import Lesson

        services.set_scenario_status(
            scenario_id=self.scenario.pk, teacher=self.teacher, status=PhysicsScenario.Status.ACTIVE
        )
        lesson = Lesson.objects.create(
            title="L", topic="Oscillations", grade_level="11",
            duration_minutes=45, learning_objectives=["x"],
        )
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=lesson, teacher=self.other, activity_type="scenario",
                title="Try it", reference_id=self.scenario.pk,
            )

    def test_lock_after_use_is_simulation_independent(self):
        services.set_scenario_status(
            scenario_id=self.scenario.pk, teacher=self.teacher, status=PhysicsScenario.Status.ACTIVE
        )
        self.scenario.refresh_from_db()
        student = StudentProfile.objects.create(display_name="Alex")
        services.record_scenario_check(student=student, scenario=self.scenario, met=True, checks=[])
        with self.assertRaises(services.ScenarioError):
            services.update_scenario(
                scenario_id=self.scenario.pk, teacher=self.teacher,
                initial_state={"length_m": 4.9},
            )
        # presentation fields remain editable
        updated = services.update_scenario(
            scenario_id=self.scenario.pk, teacher=self.teacher, title="Still editable"
        )
        self.assertEqual(updated.title, "Still editable")


@override_settings(AI_PROVIDER="fake")
class AiDraftingArchitectureTests(MockSimulationTestCase):
    def test_ai_prompt_uses_the_simulations_own_capability_metadata(self):
        from apps.physics.scenario_prompts import build_scenario_suggestion_prompt

        prompt = build_scenario_suggestion_prompt(teacher_request="x", simulation=self.sim)
        self.assertIn("length_m", prompt.system)
        self.assertIn("gravity_m_s2", prompt.system)
        self.assertIn("period_s", prompt.system)
        self.assertNotIn("velocity_m_s", prompt.system)  # not one of the mock's own fields

    def test_invalid_ai_output_is_rejected_by_the_generic_validator(self):
        bad_provider = FakeAIProvider(response=json.dumps({
            "title": "Bad", "description": "d", "instructions": "i",
            "initial_state": {"length_m": 999},  # out of the mock's own bounds
            "target_kind": "value", "target_field": "period_s",
            "target_value": 2, "tolerance": 0.1, "at_time_s": 0,
        }))
        with self.assertRaises(services.ScenarioError):
            services.suggest_scenario_draft(
                teacher_request="x", simulation_id=self.sim.pk, provider=bad_provider
            )

    def test_ai_suggestion_is_never_persisted_automatically(self):
        provider = FakeAIProvider(response=json.dumps({
            "title": "Tuned pendulum", "description": "d", "instructions": "i",
            "initial_state": {"length_m": 2.0, "gravity_m_s2": 9.8},
            "target_kind": "value", "target_field": "period_s",
            "target_value": 2.837, "tolerance": 0.05, "at_time_s": 0,
        }))
        before = PhysicsScenario.objects.count()
        draft = services.suggest_scenario_draft(
            teacher_request="x", simulation_id=self.sim.pk, provider=provider
        )
        self.assertEqual(PhysicsScenario.objects.count(), before)
        self.assertEqual(draft["initial_state"]["length_m"], 2.0)


class RegressionTests(TestCase):
    """The generalization must not change built-in or existing behaviour."""

    def test_built_in_kinematics_scenarios_are_unaffected(self):
        s = get_scenario("reach-20-at-4")
        self.assertTrue(
            evaluate_scenario(
                s, parameters={"initial_position_m": 0, "initial_velocity_m_s": 3, "acceleration_m_s2": 1}
            )["met"]
        )

    def test_kinematics_and_newtons_second_law_remain_scenario_capable(self):
        self.assertIn("kinematics", scenario_capable_simulation_types())
        self.assertIn("newtons_second_law", scenario_capable_simulation_types())
