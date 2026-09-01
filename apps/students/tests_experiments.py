from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsMisconception, PhysicsSimulation

from .experiment_services import (
    ExperimentValidationError,
    complete_experiment,
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
    validate_newtons_second_law,
)
from .models import (
    ExperimentAttempt,
    LearningEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from .prompts import build_tutor_prompt
from .providers import FakeTutorProvider
from .requests import ExperimentContext, TutorRequest
from .services import run_tutor_turn

FORCE_ACCEL_CODE = "FORCE_VS_ACCELERATION"
MISCONCEPTION_EXPLANATION = (
    "Force and acceleration are the same thing, so doubling the force just "
    "doubled the acceleration."
)
NEUTRAL_EXPLANATION = (
    "The acceleration increased because the net force increased while the mass "
    "did not change."
)


class ExperimentDataMixin:
    def seed(self):
        self.concept = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass and acceleration are related by F = ma.",
            topic="Dynamics",
        )
        self.misconception = PhysicsMisconception.objects.create(
            code=FORCE_ACCEL_CODE,
            title="Force and acceleration are the same quantity",
            description="A learner may treat force and acceleration as interchangeable.",
            physics_concept=self.concept,
            intervention_guidance="Work F = ma with numbers so the two stay distinct.",
        )
        self.simulation = PhysicsSimulation.objects.create(
            concept=self.concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        self.lesson = Lesson.objects.create(
            title="Forces and Motion",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass and acceleration."],
        )
        self.lesson.physics_concepts.add(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")

    def predict(self, text="If the force doubles, the acceleration doubles."):
        return record_experiment_prediction(
            student=self.student,
            simulation=self.simulation,
            lesson=self.lesson,
            prediction=text,
        )

    def observe(self, text="Acceleration went from 5 to 10 m/s^2.", mass=2, force=20):
        return record_experiment_observation(
            student=self.student,
            simulation=self.simulation,
            lesson=self.lesson,
            observation=text,
            mass_kg=mass,
            force_n=force,
        )

    def explain(self, text=NEUTRAL_EXPLANATION, mass=2, force=20):
        return record_experiment_explanation(
            student=self.student,
            simulation=self.simulation,
            lesson=self.lesson,
            explanation=text,
            mass_kg=mass,
            force_n=force,
        )


# --- MODEL -----------------------------------------------------------------


class ExperimentModelTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_experiment_attempt_can_be_created(self):
        attempt = self.predict()
        self.assertIsInstance(attempt, ExperimentAttempt)
        self.assertFalse(attempt.is_complete)
        self.assertIn("Newton's Second Law Lab", str(attempt))

    def test_experiment_connected_to_student(self):
        attempt = self.predict()
        self.assertEqual(attempt.student, self.student)
        self.assertIn(attempt, self.student.experiment_attempts.all())

    def test_experiment_connected_to_lesson_and_simulation(self):
        attempt = self.predict()
        self.assertEqual(attempt.lesson, self.lesson)
        self.assertEqual(attempt.simulation, self.simulation)

    def test_experiment_stores_deterministic_values(self):
        _attempt, validated = self.observe(mass=2, force=20)
        attempt = ExperimentAttempt.objects.get()
        self.assertEqual(attempt.mass_kg, 2.0)
        self.assertEqual(attempt.force_n, 20.0)
        self.assertEqual(attempt.acceleration_m_s2, 10.0)
        self.assertEqual(validated.acceleration_m_s2, 10.0)


# --- EVIDENCE ----------------------------------------------------------------


class ExperimentEvidenceTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_prediction_records_evidence(self):
        self.predict("Acceleration will double.")
        row = LearningEvidence.objects.get(
            kind=LearningEvidence.Kind.PREDICTION_SUBMITTED
        )
        self.assertEqual(row.student, self.student)
        self.assertEqual(row.detail, "Acceleration will double.")
        self.assertEqual(row.context["simulation"], "newtons_second_law")

    def test_observation_records_evidence_with_deterministic_context(self):
        self.observe(mass=2, force=20)
        row = LearningEvidence.objects.get(
            kind=LearningEvidence.Kind.EXPERIMENT_OBSERVED
        )
        self.assertEqual(row.context["mass_kg"], 2.0)
        self.assertEqual(row.context["force_n"], 20.0)
        self.assertEqual(row.context["acceleration_m_s2"], 10.0)

    def test_explanation_records_evidence(self):
        self.predict()
        self.observe()
        self.explain()
        self.assertTrue(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.EXPLANATION_SUBMITTED
            ).exists()
        )

    @override_settings(AI_PROVIDER="fake")
    def test_existing_tutor_evidence_still_works(self):
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        run_tutor_turn(
            session,
            student_question="What is acceleration?",
            provider=FakeTutorProvider(),
        )
        self.assertTrue(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.QUESTION_ASKED
            ).exists()
        )


# --- PHYSICS VALIDATION -------------------------------------------------


class PhysicsValidationTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_server_recomputes_acceleration(self):
        self.assertEqual(validate_newtons_second_law(2, 20).acceleration_m_s2, 10.0)
        self.assertEqual(validate_newtons_second_law(4, 20).acceleration_m_s2, 5.0)

    def test_browser_acceleration_value_is_never_used(self):
        # The service signature has no place for a browser acceleration; the
        # stored value is always the server recompute.
        attempt, _ = self.observe(mass=2, force=20)
        self.assertEqual(attempt.acceleration_m_s2, 10.0)

    def test_zero_mass_is_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(0, 10)
        with self.assertRaises(ExperimentValidationError):
            self.observe(mass=0, force=10)

    def test_negative_mass_is_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(-2, 10)

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(float("nan"), 10)
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(2, float("inf"))

    def test_zero_force_gives_zero_acceleration(self):
        self.assertEqual(validate_newtons_second_law(2, 0).acceleration_m_s2, 0.0)

    def test_absurd_values_are_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(999, 10)
        with self.assertRaises(ExperimentValidationError):
            validate_newtons_second_law(2, 9999)

    def test_slightly_out_of_range_is_clamped_to_lab_bounds(self):
        validated = validate_newtons_second_law(25, 10)
        self.assertEqual(validated.mass_kg, 20.0)
        self.assertEqual(validated.acceleration_m_s2, 0.5)


# --- EXPERIMENT FLOW ---------------------------------------------------


class ExperimentFlowTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_prediction_saves(self):
        attempt = self.predict("Acceleration doubles.")
        self.assertEqual(attempt.prediction, "Acceleration doubles.")

    def test_observation_saves(self):
        self.predict()
        attempt, _ = self.observe("It sped up sooner.", mass=3, force=30)
        self.assertEqual(attempt.observation, "It sped up sooner.")
        self.assertEqual(attempt.acceleration_m_s2, 10.0)

    def test_explanation_saves(self):
        self.predict()
        self.observe()
        attempt, _ = self.explain("Because net force went up.")
        self.assertEqual(attempt.explanation, "Because net force went up.")

    def test_empty_submissions_are_rejected(self):
        with self.assertRaises(ExperimentValidationError):
            self.predict("   ")

    def test_completion_records_the_full_evidence_trail(self):
        attempt = self.predict()
        self.observe()
        self.explain()
        complete_experiment(attempt)
        attempt.refresh_from_db()

        self.assertTrue(attempt.is_complete)
        kinds = set(
            LearningEvidence.objects.filter(student=self.student).values_list(
                "kind", flat=True
            )
        )
        self.assertEqual(
            kinds,
            {
                LearningEvidence.Kind.PREDICTION_SUBMITTED,
                LearningEvidence.Kind.EXPERIMENT_OBSERVED,
                LearningEvidence.Kind.EXPLANATION_SUBMITTED,
            },
        )
        # A fresh prediction after completion starts a new attempt.
        second = self.predict("Another run.")
        self.assertNotEqual(second.pk, attempt.pk)
        self.assertEqual(ExperimentAttempt.objects.count(), 2)

    def test_one_active_attempt_is_reused_across_phases(self):
        a1 = self.predict()
        a2, _ = self.observe()
        a3, _ = self.explain()
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(a2.pk, a3.pk)
        self.assertEqual(ExperimentAttempt.objects.count(), 1)


# --- TUTOR INTEGRATION -----------------------------------------------


class ExperimentTutorTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_experiment_context_reaches_the_tutor_prompt(self):
        self.predict("If force doubles, acceleration doubles.")
        self.observe("Acceleration went from 5 to 10 m/s^2.", mass=2, force=20)
        attempt, _ = self.explain("Net force increased and mass was constant.")

        context = ExperimentContext.from_attempt(attempt)
        request = TutorRequest(
            lesson_title="Forces and Motion",
            topic="Dynamics",
            grade_level="11",
            experiment=context,
            student_question="Did my prediction hold up?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("Physics Lab experiment", prompt.user)
        self.assertIn("Net force increased and mass was constant.", prompt.user)
        self.assertIn("If force doubles, acceleration doubles.", prompt.user)
        self.assertIn("10.00 m/s^2", prompt.user)

    @override_settings(AI_PROVIDER="fake")
    def test_run_tutor_turn_accepts_experiment_and_stays_structured(self):
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        self.predict()
        self.observe()
        attempt, _ = self.explain("Net force went up while mass stayed the same.")
        provider = FakeTutorProvider()

        tutor_message, result = run_tutor_turn(
            session,
            student_question="I predicted acceleration would double. Did it?",
            experiment=ExperimentContext.from_attempt(attempt),
            provider=provider,
        )
        self.assertIn(
            result.response.mode,
            {"explain", "hint", "question", "feedback", "solution", "practice"},
        )
        self.assertEqual(tutor_message.role, TutorMessage.Role.TUTOR)
        self.assertIn(
            "Net force went up while mass stayed the same.",
            provider.calls[0]["prompt"],
        )

    @override_settings(AI_PROVIDER="fake")
    def test_tutor_view_attaches_experiment_context_and_reuses_session(self):
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        self.predict()
        self.observe()
        attempt, _ = self.explain("Force and acceleration are different quantities.")

        url = reverse("students:tutor", args=[self.lesson.slug])
        with patch("apps.students.views.run_tutor_turn") as mock_turn:
            response = self.client.post(
                url,
                {
                    "action": "ask",
                    "question": "Was my prediction right?",
                    "experiment": attempt.pk,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_turn.call_count, 1)
        passed = mock_turn.call_args.kwargs["experiment"]
        self.assertIsInstance(passed, ExperimentContext)
        self.assertIn("Force and acceleration are different quantities.", passed.explanation)
        # Existing session reused, no duplicate.
        self.assertEqual(
            TutorSession.objects.filter(
                student=self.student, lesson=self.lesson
            ).count(),
            1,
        )


# --- MISCONCEPTION ENGINE -------------------------------------------


@override_settings(AI_PROVIDER="fake")
class ExperimentMisconceptionTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_explanation_reaches_the_existing_engine(self):
        self.predict()
        self.observe()
        attempt, outcomes = self.explain(MISCONCEPTION_EXPLANATION)

        self.assertTrue(outcomes)
        observation = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(observation.misconception.code, FORCE_ACCEL_CODE)
        evidence_kinds = set(
            observation.evidence.values_list(
                "learning_evidence__kind", flat=True
            )
        )
        self.assertIn(LearningEvidence.Kind.EXPLANATION_SUBMITTED, evidence_kinds)

    def test_neutral_explanation_creates_no_candidate(self):
        self.predict()
        self.observe()
        self.explain(NEUTRAL_EXPLANATION)
        self.assertFalse(
            StudentMisconception.objects.filter(student=self.student).exists()
        )

    def test_candidate_is_not_auto_confirmed(self):
        self.predict()
        self.observe()
        self.explain(MISCONCEPTION_EXPLANATION)
        observation = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(
            observation.status, StudentMisconception.Status.CANDIDATE
        )


# --- HTTP ENDPOINTS + TEACHER VIEW --------------------------------


@override_settings(AI_PROVIDER="fake")
class ExperimentEndpointTests(ExperimentDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.predict_url = reverse(
            "physics_lab:experiment_predict", args=[self.simulation.slug]
        )
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )
        self.explain_url = reverse(
            "physics_lab:experiment_explain", args=[self.simulation.slug]
        )

    def test_predict_endpoint_records_and_returns_json(self):
        response = self.client.post(
            self.predict_url, {"prediction": "Acceleration will double."}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.PREDICTION_SUBMITTED
            ).count(),
            1,
        )

    def test_observe_endpoint_recomputes_and_ignores_browser_acceleration(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "It doubled.",
                "mass_kg": "2",
                "force_n": "20",
                "acceleration_m_s2": "999",  # bogus browser value
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["acceleration_m_s2"], 10.0)
        self.assertEqual(ExperimentAttempt.objects.get().acceleration_m_s2, 10.0)

    def test_observe_endpoint_rejects_zero_mass(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "mass_kg": "0", "force_n": "10"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_explain_endpoint_returns_structured_tutor_link(self):
        self.client.post(self.predict_url, {"prediction": "double"})
        self.client.post(
            self.observe_url,
            {"observation": "went up", "mass_kg": "2", "force_n": "20"},
        )
        response = self.client.post(
            self.explain_url,
            {
                "explanation": MISCONCEPTION_EXPLANATION,
                "mass_kg": "2",
                "force_n": "20",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("experiment=", payload["tutor_url"])
        self.assertIn("prefill=", payload["tutor_url"])
        # The internal code is never shipped to the student.
        self.assertNotIn(FORCE_ACCEL_CODE, response.content.decode())
        # ...but the engine still recorded a candidate for the teacher.
        self.assertTrue(
            StudentMisconception.objects.filter(student__isnull=False).exists()
        )

    def test_lab_detail_restores_in_progress_attempt(self):
        self.client.post(self.predict_url, {"prediction": "My saved prediction."})
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My saved prediction.")

    def test_teacher_sees_experiment_evidence_without_internal_labels(self):
        self.client.post(self.predict_url, {"prediction": "Force doubling doubles a."})
        self.client.post(
            self.observe_url,
            {"observation": "5 to 10 m/s^2", "mass_kg": "2", "force_n": "20"},
        )
        self.client.post(
            self.explain_url,
            {"explanation": MISCONCEPTION_EXPLANATION, "mass_kg": "2", "force_n": "20"},
        )

        response = self.client.get(
            reverse("students:insights", args=[self.lesson.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student experiment evidence")
        self.assertContains(response, "Force doubling doubles a.")
        self.assertContains(response, MISCONCEPTION_EXPLANATION)
        self.assertContains(response, "Force and acceleration are the same quantity")
        self.assertNotContains(response, FORCE_ACCEL_CODE)
