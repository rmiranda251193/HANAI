"""Step 24 -- Kinematics experiment flow, reusing the generic experiment
architecture proven by Step 13/14's Newton's Second Law lab.

Mirrors apps/students/tests_experiments.py's ExperimentDataMixin pattern.
"""

from __future__ import annotations

import math

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation

from .experiment_services import (
    ExperimentValidationError,
    complete_experiment,
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
    validate_kinematics,
)
from .models import ExperimentAttempt, LearningEvidence, StudentProfile

NEUTRAL_EXPLANATION = (
    "The velocity increased steadily because the acceleration stayed constant "
    "and positive over the whole run."
)


class KinematicsExperimentDataMixin:
    def seed(self):
        self.concept = PhysicsConcept.objects.create(
            name="Acceleration",
            description="The rate of change of velocity.",
            topic="Kinematics",
        )
        self.simulation = PhysicsSimulation.objects.create(
            concept=self.concept,
            title="Kinematics -- Straight-Line Motion",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        self.lesson = Lesson.objects.create(
            title="Motion on a Line",
            topic="Kinematics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate position, velocity, acceleration and time."],
        )
        self.lesson.physics_concepts.add(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")

    def predict(self, text="If acceleration is positive, velocity keeps increasing."):
        return record_experiment_prediction(
            student=self.student, simulation=self.simulation, lesson=self.lesson,
            prediction=text,
        )

    def observe(self, text="After 5 s the position was about 22.5 m.", x0=0, v0=2, a=1, t=5):
        return record_experiment_observation(
            student=self.student, simulation=self.simulation, lesson=self.lesson,
            observation=text,
            initial_position_m=x0, initial_velocity_m_s=v0,
            acceleration_m_s2=a, time_s=t,
        )

    def explain(self, text=NEUTRAL_EXPLANATION, x0=0, v0=2, a=1, t=5):
        return record_experiment_explanation(
            student=self.student, simulation=self.simulation, lesson=self.lesson,
            explanation=text,
            initial_position_m=x0, initial_velocity_m_s=v0,
            acceleration_m_s2=a, time_s=t,
        )


class KinematicsExperimentModelTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_experiment_attempt_can_be_created(self):
        attempt, _ = self.observe()
        self.assertIsInstance(attempt, ExperimentAttempt)
        self.assertEqual(attempt.student, self.student)
        self.assertEqual(attempt.simulation, self.simulation)

    def test_experiment_stores_deterministic_values(self):
        attempt, validated = self.observe(x0=0, v0=2, a=1, t=5)
        self.assertEqual(validated.position_m, 22.5)
        self.assertEqual(validated.velocity_m_s, 7.0)
        self.assertEqual(attempt.acceleration_m_s2, 1.0)
        self.assertEqual(attempt.parameters["initial_position_m"], 0.0)
        self.assertEqual(attempt.parameters["initial_velocity_m_s"], 2.0)
        self.assertEqual(attempt.parameters["observed_position_m"], 22.5)
        self.assertEqual(attempt.parameters["observed_velocity_m_s"], 7.0)

    def test_negative_acceleration_is_stored_correctly(self):
        # x0=10, v0=5, a=-2, t=2 -> v=1, x=16 (Section 32).
        attempt, validated = self.observe(x0=10, v0=5, a=-2, t=2)
        self.assertEqual(validated.position_m, 16.0)
        self.assertEqual(validated.velocity_m_s, 1.0)

    def test_reusing_the_same_active_attempt_across_phases(self):
        self.predict()
        attempt, _ = self.observe()
        attempt2, _ = self.explain()
        self.assertEqual(attempt.pk, attempt2.pk)

    def test_explanation_with_a_fresh_setup_refreshes_stored_parameters(self):
        """Regression: explain must not leave attempt.parameters frozen at a
        stale observe-time snapshot when the student re-ran the sim with a
        different setup before explaining (Section 26/35 -- the evidence
        context is read from attempt.parameters for Kinematics, so a stale
        snapshot there would misreport the actual experiment)."""

        self.observe(x0=0, v0=2, a=1, t=5)
        attempt, _outcomes = self.explain(x0=10, v0=5, a=-2, t=2)
        self.assertEqual(attempt.parameters["initial_position_m"], 10.0)
        self.assertEqual(attempt.parameters["observed_position_m"], 16.0)
        self.assertEqual(attempt.parameters["observed_velocity_m_s"], 1.0)
        self.assertEqual(attempt.acceleration_m_s2, -2.0)


class KinematicsEvidenceTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_prediction_records_evidence(self):
        self.predict("My prediction text.")
        self.assertTrue(
            LearningEvidence.objects.filter(
                student=self.student, kind=LearningEvidence.Kind.PREDICTION_SUBMITTED
            ).exists()
        )

    def test_observation_records_evidence_with_authoritative_context(self):
        self.observe(x0=0, v0=2, a=1, t=5)
        evidence = LearningEvidence.objects.get(
            student=self.student, kind=LearningEvidence.Kind.EXPERIMENT_OBSERVED
        )
        self.assertEqual(evidence.context["simulation"], "kinematics")
        self.assertEqual(evidence.context["initial_position_m"], 0.0)
        self.assertEqual(evidence.context["initial_velocity_m_s"], 2.0)
        self.assertEqual(evidence.context["acceleration_m_s2"], 1.0)
        self.assertEqual(evidence.context["time_s"], 5.0)
        self.assertEqual(evidence.context["position_m"], 22.5)
        self.assertEqual(evidence.context["velocity_m_s"], 7.0)

    def test_explanation_records_evidence(self):
        self.observe()
        self.explain("Because the acceleration was positive the whole time.")
        self.assertTrue(
            LearningEvidence.objects.filter(
                student=self.student, kind=LearningEvidence.Kind.EXPLANATION_SUBMITTED
            ).exists()
        )

    def test_student_text_is_preserved_verbatim(self):
        text = "I saw the marker move steadily to the right."
        attempt, _ = self.observe(text=text)
        self.assertEqual(attempt.observation, text)

    def test_no_answer_key_or_private_metadata_in_context(self):
        self.observe()
        evidence = LearningEvidence.objects.get(
            student=self.student, kind=LearningEvidence.Kind.EXPERIMENT_OBSERVED
        )
        for banned in ("api_key", "prompt", "teacher_note", "misconception"):
            self.assertNotIn(banned, evidence.context)


class KinematicsValidationTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_server_recomputes_position_and_velocity(self):
        validated = validate_kinematics(0, 2, 1, 5)
        self.assertEqual(validated.position_m, 22.5)
        self.assertEqual(validated.velocity_m_s, 7.0)

    def test_browser_position_and_velocity_values_are_never_used(self):
        # validate_kinematics has no position/velocity parameters at all --
        # only the raw setup + time are accepted; the result is always derived.
        import inspect

        params = inspect.signature(validate_kinematics).parameters
        self.assertNotIn("position_m", params)
        self.assertNotIn("velocity_m_s", params)

    def test_nan_and_infinity_are_rejected(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ExperimentValidationError):
                validate_kinematics(bad, 2, 1, 5)
            with self.assertRaises(ExperimentValidationError):
                validate_kinematics(0, 2, 1, bad)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_kinematics(0, 2, 1, -1)

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_kinematics("far", 2, 1, 5)

    def test_absurd_values_are_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_kinematics(0, 2, 1, 99999)

    def test_slightly_out_of_range_is_clamped_to_lab_bounds(self):
        validated = validate_kinematics(21, 2, 1, 0)
        self.assertEqual(validated.initial_position_m, 20.0)  # clamped to MAX


class KinematicsExperimentFlowTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_prediction_saves(self):
        attempt = self.predict()
        self.assertTrue(attempt.prediction)

    def test_observation_saves(self):
        attempt, _ = self.observe()
        self.assertTrue(attempt.observation)

    def test_explanation_saves_and_completes(self):
        self.observe()
        attempt, _ = self.explain()
        completed = complete_experiment(attempt)
        self.assertIsNotNone(completed.completed_at)

    def test_empty_submissions_are_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            self.predict("   ")

    def test_completion_starts_a_fresh_attempt(self):
        self.observe()
        attempt, _ = self.explain()
        complete_experiment(attempt)
        new_attempt = self.predict("A new run.")
        self.assertNotEqual(attempt.pk, new_attempt.pk)


class KinematicsTutorTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_experiment_context_reaches_the_tutor_prompt(self):
        from .prompts import build_tutor_prompt
        from .requests import ConceptContext, ExperimentContext, TutorRequest

        attempt, _ = self.observe(x0=0, v0=2, a=1, t=5)
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "kinematics")
        self.assertEqual(ctx.initial_position_m, 0.0)
        self.assertEqual(ctx.position_m, 22.5)

        request = TutorRequest(
            lesson_title=self.lesson.title, topic=self.lesson.topic,
            grade_level=self.lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("Kinematics", prompt.user)
        self.assertIn("22.50 m", prompt.user)
        self.assertIn("v = v0 + at", prompt.user)

    def test_newtons_second_law_prompt_still_unaffected(self):
        """Regression: the N2L experiment block must render exactly as before."""

        from .prompts import build_tutor_prompt
        from .requests import ConceptContext, ExperimentContext, TutorRequest

        n2l_concept = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="d", topic="Dynamics"
        )
        n2l_sim = PhysicsSimulation.objects.create(
            concept=n2l_concept, title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        attempt = ExperimentAttempt.objects.create(
            student=self.student, simulation=n2l_sim,
            mass_kg=2.0, force_n=10.0, acceleration_m_s2=5.0,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        request = TutorRequest(
            lesson_title=self.lesson.title, topic=self.lesson.topic,
            grade_level=self.lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("mass = 2.00 kg", prompt.user)
        self.assertIn("a = F / m", prompt.user)


@override_settings(AI_PROVIDER="fake")
class KinematicsEndpointTests(KinematicsExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.predict_url = reverse("physics_lab:experiment_predict", args=[self.simulation.slug])
        self.observe_url = reverse("physics_lab:experiment_observe", args=[self.simulation.slug])
        self.explain_url = reverse("physics_lab:experiment_explain", args=[self.simulation.slug])

    def test_predict_endpoint_records_and_returns_json(self):
        response = self.client.post(self.predict_url, {"prediction": "It will speed up."})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "It moved forward.",
                "initial_position_m": "0", "initial_velocity_m_s": "2",
                "acceleration_m_s2": "1", "time_s": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["position_m"], 22.5)
        self.assertEqual(data["velocity_m_s"], 7.0)

    def test_browser_position_and_velocity_values_are_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated",
                "initial_position_m": "0", "initial_velocity_m_s": "2",
                "acceleration_m_s2": "1", "time_s": "5",
                "position_m": "999999", "velocity_m_s": "999999",
                "is_correct": "true", "score": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["position_m"], 22.5)
        self.assertEqual(data["velocity_m_s"], 7.0)
        attempt = ExperimentAttempt.objects.get(student=self.student, simulation=self.simulation)
        self.assertEqual(attempt.parameters["observed_position_m"], 22.5)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "initial_position_m": "0",
                "initial_velocity_m_s": "2", "acceleration_m_s2": "1", "time_s": "-5",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_explain_endpoint_returns_tutor_link(self):
        self.client.post(
            self.observe_url,
            {
                "observation": "x", "initial_position_m": "0",
                "initial_velocity_m_s": "2", "acceleration_m_s2": "1", "time_s": "5",
            },
        )
        response = self.client.post(
            self.explain_url,
            {
                "explanation": NEUTRAL_EXPLANATION, "initial_position_m": "0",
                "initial_velocity_m_s": "2", "acceleration_m_s2": "1", "time_s": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("experiment=", data["tutor_url"])
        self.assertIn("prefill=", data["tutor_url"])

    def test_cannot_submit_newtons_second_law_fields_to_kinematics_endpoint(self):
        """Wrong-simulation-shaped fields are simply not among this
        simulation's input_fields, so they are never read at all."""

        response = self.client.post(
            self.observe_url,
            {
                "observation": "x",
                "mass_kg": "2", "force_n": "10",  # N2L-shaped, irrelevant here
                "initial_position_m": "0", "initial_velocity_m_s": "2",
                "acceleration_m_s2": "1", "time_s": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("mass_kg", data)
        self.assertEqual(data["position_m"], 22.5)

    def test_cross_simulation_endpoint_rejects_the_other_type(self):
        """Posting to the Kinematics endpoint with no kinematics fields at all
        (e.g. only N2L fields) is cleanly rejected, not silently accepted."""

        response = self.client.post(
            self.observe_url,
            {"observation": "x", "mass_kg": "2", "force_n": "10"},
        )
        self.assertEqual(response.status_code, 400)

    def test_another_students_experiment_is_not_modified(self):
        from django.contrib.auth import get_user_model

        # A distinct, user-bound "other" student -- never confusable with the
        # shared anonymous guest identity ``self.client`` resolves to.
        other_user = get_user_model().objects.create_user("intruder", password="pw")
        other_client = Client()
        other_client.force_login(other_user)

        self.client.post(
            self.observe_url,
            {
                "observation": "student A", "initial_position_m": "0",
                "initial_velocity_m_s": "2", "acceleration_m_s2": "1", "time_s": "5",
            },
        )
        attempt = ExperimentAttempt.objects.get(student=self.student, simulation=self.simulation)

        # A smuggled student_id is not among the fields any endpoint reads --
        # the acting student always comes from the session.
        other_client.post(
            self.observe_url,
            {
                "observation": "intruder", "initial_position_m": "5",
                "initial_velocity_m_s": "5", "acceleration_m_s2": "5", "time_s": "1",
                "student_id": str(self.student.pk),
            },
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.observation, "student A")
        self.assertEqual(
            ExperimentAttempt.objects.filter(simulation=self.simulation).count(), 2
        )

    def test_get_does_not_mutate(self):
        before = ExperimentAttempt.objects.count()
        self.client.get(reverse("physics_lab:detail", args=[self.simulation.slug]))
        self.assertEqual(ExperimentAttempt.objects.count(), before)

    def test_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(self.predict_url, {"prediction": "x"})
        self.assertEqual(response.status_code, 403)


# --- 54-60: cross-system integration (no simulation-type-specific code) ----


class KinematicsIntegrationTests(KinematicsExperimentDataMixin, TestCase):
    """None of these reuse points know "kinematics" exists -- they all resolve
    PhysicsSimulation generically, which is the whole point of Section 8's
    "one generic PhysicsSimulation model" architecture."""

    def setUp(self):
        self.seed()

    def test_progress_shows_kinematics_activity(self):
        from .progress_services import build_student_learning_progress

        self.observe(x0=0, v0=2, a=1, t=5)
        progress = build_student_learning_progress(student=self.student)
        self.assertEqual(progress["experiment_summary"]["attempted"], 1)

    def test_learning_patterns_counts_kinematics_activity(self):
        from .pattern_services import build_student_learning_patterns

        self.observe(x0=0, v0=2, a=1, t=5)
        patterns = build_student_learning_patterns(student=self.student)
        concept_names = {row["concept"] for row in patterns["concept_activity"]}
        self.assertIn("Acceleration", concept_names)

    def test_concept_graph_remains_valid_with_kinematics_concepts(self):
        from apps.physics.concept_graph import build_physics_concept_graph

        graph = build_physics_concept_graph()
        self.assertTrue(graph.has(self.concept.slug))

    def test_activity_planner_can_resolve_the_kinematics_lab(self):
        from apps.teachers.goal_services import create_learning_goal

        from .activity_planner import build_adaptive_activity_plan
        from django.contrib.auth import get_user_model

        teacher = get_user_model().objects.create_user("teach1", password="pw", is_staff=True)
        create_learning_goal(
            student=self.student, teacher=teacher, concept_id=self.concept.pk,
            simulation_id=self.simulation.pk,
        )
        plan = build_adaptive_activity_plan(student=self.student)
        self.assertIsNotNone(plan["next_activity"])
        self.assertEqual(plan["next_activity"]["type"], "lab")
        self.assertIn(str(self.simulation.slug), plan["next_activity"]["url"])

    def test_teacher_learning_goal_can_target_kinematics(self):
        from apps.teachers.goal_services import create_learning_goal
        from django.contrib.auth import get_user_model

        teacher = get_user_model().objects.create_user("teach2", password="pw", is_staff=True)
        goal = create_learning_goal(
            student=self.student, teacher=teacher, concept_id=self.concept.pk,
            simulation_id=self.simulation.pk,
        )
        self.assertEqual(goal.simulation, self.simulation)
        self.assertIn("Physics Lab", goal.target_label)

    def test_teacher_recommendation_can_target_kinematics(self):
        from apps.teachers.models import TeacherIntervention
        from apps.teachers.services import create_teacher_intervention, open_recommendation
        from django.contrib.auth import get_user_model

        teacher = get_user_model().objects.create_user("teach3", password="pw", is_staff=True)
        intervention = create_teacher_intervention(
            student=self.student, teacher=teacher,
            action_type=TeacherIntervention.ActionType.RECOMMEND_EXPERIMENT,
            simulation_id=self.simulation.pk, note="Try the kinematics lab.",
        )
        destination = open_recommendation(intervention_id=intervention.pk, student=self.student)
        self.assertEqual(
            destination, reverse("physics_lab:detail", args=[self.simulation.slug])
        )
