import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_shm import (
    DEFAULT_AMPLITUDE_M,
    DEFAULT_PERIOD_S,
    MAX_AMPLITUDE_M,
    MAX_PERIOD_S,
    MAX_TIME_S,
    MIN_AMPLITUDE_M,
    MIN_PERIOD_S,
    SimulationError,
    clamp_amplitude,
    clamp_period,
    clamp_time,
    shm_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _shm_concept():
    return PhysicsConcept.objects.create(
        name="Simple harmonic motion",
        description="A mass on a spring oscillates with a restoring force proportional to displacement.",
        topic="Oscillations",
        equations=["x = A cos(omega t)", "a = -omega^2 x"],
        si_units=["m", "s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _shm_concept(),
        title="Simple Harmonic Motion Lab",
        simulation_type=PhysicsSimulation.SimulationType.SIMPLE_HARMONIC_MOTION,
        description="Explore x = A*cos(omega*t) and a = -omega^2*x.",
    )


# --- DOMAIN -----------------------------------------------------------------


class ShmSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_shm_concept(self):
        concept = _shm_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.SIMPLE_HARMONIC_MOTION,
        )

    def test_seed_simulations_creates_shm_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="simple-harmonic-motion").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="simple-harmonic-motion")
        self.assertEqual(sim.simulation_type, "simple_harmonic_motion")
        self.assertEqual(sim.concept.name, "Simple harmonic motion")

    def test_seed_simulations_is_idempotent_for_shm(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="simple-harmonic-motion").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in ("kinematics", "newtons-second-law", "projectile-motion", "circular-motion"):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class ShmMathTests(TestCase):
    def test_starts_at_amplitude_at_rest(self):
        state = shm_state(amplitude=1, period=2, time=0)
        self.assertAlmostEqual(state["position_m"], 1.0, places=6)
        self.assertAlmostEqual(state["velocity_m_s"], 0.0, places=6)

    def test_quarter_period_is_fastest_through_the_centre(self):
        # A=1, T=4 -> omega=pi/2. At t=1 (T/4): x=0, |v|=A*omega (maximum speed).
        state = shm_state(amplitude=1, period=4, time=1)
        omega = 2 * math.pi / 4
        self.assertAlmostEqual(state["position_m"], 0.0, places=6)
        self.assertAlmostEqual(abs(state["velocity_m_s"]), omega, places=6)
        self.assertAlmostEqual(state["acceleration_m_s2"], 0.0, places=6)

    def test_half_period_reaches_the_opposite_extreme(self):
        state = shm_state(amplitude=2, period=4, time=2)
        self.assertAlmostEqual(state["position_m"], -2.0, places=5)
        self.assertAlmostEqual(state["velocity_m_s"], 0.0, places=5)

    def test_full_period_returns_to_the_start(self):
        state = shm_state(amplitude=1.5, period=3, time=3)
        self.assertAlmostEqual(state["position_m"], 1.5, places=5)
        self.assertAlmostEqual(state["velocity_m_s"], 0.0, places=5)

    def test_acceleration_matches_minus_omega_squared_x(self):
        amplitude, period = 1.2, 5.0
        state = shm_state(amplitude=amplitude, period=period, time=0.7)
        omega = 2 * math.pi / period
        expected = -omega * omega * state["position_m"]
        self.assertAlmostEqual(state["acceleration_m_s2"], expected, places=6)

    def test_acceleration_is_greatest_at_the_amplitude(self):
        at_amplitude = shm_state(amplitude=1, period=4, time=0)
        at_centre = shm_state(amplitude=1, period=4, time=1)
        self.assertGreater(
            abs(at_amplitude["acceleration_m_s2"]), abs(at_centre["acceleration_m_s2"])
        )

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 3, 8, 20):
            first = shm_state(amplitude=1, period=2, time=t)
            second = shm_state(amplitude=1, period=2, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_non_positive_period_is_rejected(self):
        with self.assertRaises(SimulationError):
            shm_state(amplitude=1, period=0, time=0)
        with self.assertRaises(SimulationError):
            clamp_period(-1)

    def test_non_positive_amplitude_is_clamped_up_to_the_minimum(self):
        # Like circular motion's radius, amplitude is just clamped like any
        # other UI-range value -- MIN_AMPLITUDE_M is already > 0.
        self.assertEqual(clamp_amplitude(0), MIN_AMPLITUDE_M)
        self.assertEqual(clamp_amplitude(-2), MIN_AMPLITUDE_M)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_amplitude("big")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_amplitude(math.nan)
        with self.assertRaises(SimulationError):
            clamp_period(math.inf)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_amplitude(999), MAX_AMPLITUDE_M)
        self.assertEqual(clamp_period(999), MAX_PERIOD_S)
        self.assertEqual(clamp_period(0.001), MIN_PERIOD_S)

    def test_default_state_is_a_valid_worked_example(self):
        state = shm_state(amplitude=DEFAULT_AMPLITUDE_M, period=DEFAULT_PERIOD_S, time=0)
        self.assertAlmostEqual(state["position_m"], DEFAULT_AMPLITUDE_M, places=6)


class JsShmConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "shm.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "shm.js").read_text(encoding="utf-8")
        self.assertIn("omega", source)
        self.assertIn("Math.cos", source)
        for bound in ("0.1", "2.0", "0.5", "10.0", "40.0"):
            self.assertIn(bound, source)
        self.assertIn('register("simple_harmonic_motion"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class ShmLabViewTests(TestCase):
    def setUp(self):
        self.concept = _shm_concept()
        self.simulation = _make_simulation(self.concept)

    def test_shm_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Simple Harmonic Motion Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/shm.js")

    def test_shm_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Amplitude")
        self.assertContains(response, "Period")
        self.assertContains(response, "data-input-amplitude")
        self.assertContains(response, "data-input-period")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_hands_on_companion_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Try this with real materials:")
        self.assertContains(response, "bouncing a weight")

    def test_other_simulations_still_load_alongside_shm(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_shm_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_shm(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Simple Harmonic Motion Lab", body)


class ShmExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _shm_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "It sped up.", "amplitude_m": "1", "period_s": "4", "time_s": "1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["position_m"], 0.0, places=4)

    def test_browser_submitted_position_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "amplitude_m": "1", "period_s": "4", "time_s": "0",
                "position_m": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["position_m"], 1.0, places=4)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "amplitude_m": "1", "period_s": "4", "time_s": "-1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_zero_period(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "amplitude_m": "1", "period_s": "0", "time_s": "1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_csrf_is_enforced(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.post(
            reverse("physics_lab:experiment_predict", args=[self.simulation.slug]),
            {"prediction": "x"},
        )
        self.assertEqual(response.status_code, 403)


class ShmTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _shm_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Bouncing Back", topic="Oscillations", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate amplitude and period to position, velocity and acceleration."],
        )
        lesson.physics_concepts.add(self.concept)
        return lesson

    def test_lab_links_to_existing_tutor_when_a_lesson_exists(self):
        lesson = self._lesson_with_concept()
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Ask the Tutor About This Experiment")
        self.assertContains(response, reverse("students:tutor", args=[lesson.slug]))
        self.assertContains(response, "prefill=")

    def test_lab_shows_a_note_when_no_lesson_covers_the_concept(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "connect this experiment to the Physics Tutor")
        self.assertNotContains(response, "Ask the Tutor About This Experiment")

    def test_experiment_context_reaches_the_tutor_prompt(self):
        from apps.students.experiment_services import record_experiment_observation
        from apps.students.models import StudentProfile
        from apps.students.prompts import build_tutor_prompt
        from apps.students.requests import ConceptContext, ExperimentContext, TutorRequest

        lesson = self._lesson_with_concept()
        student = StudentProfile.objects.create(display_name="Sam")
        attempt, _ = record_experiment_observation(
            student=student, simulation=self.simulation, lesson=lesson,
            observation="x", amplitude_m=1, period_s=4, time_s=1,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "simple_harmonic_motion")
        self.assertEqual(ctx.amplitude_m, 1.0)
        self.assertEqual(ctx.period_s, 4.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("amplitude = 1.00 m", prompt.user)
        self.assertIn("period = 4.00 s", prompt.user)


# --- accessibility -------------------------------------------------------


class ShmAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _shm_concept()
        self.simulation = _make_simulation(self.concept)
        self.body = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        ).content.decode()

    def test_exactly_one_h1(self):
        self.assertEqual(self.body.count("<h1>"), 1)

    def test_step_headings_are_real_h2s(self):
        for heading in ("Predict", "Experiment", "Observe", "Explain", "Talk to your tutor"):
            self.assertIn(f">{heading}<", self.body)

    def test_real_labels_for_every_range_control(self):
        self.assertIn('<label for="lab-amplitude">', self.body)
        self.assertIn('<label for="lab-period">', self.body)
        self.assertIn('<label for="lab-time">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_real_buttons_not_divs(self):
        self.assertIn("data-action-start", self.body)
        self.assertIn("data-action-pause", self.body)
        self.assertIn("data-action-reset", self.body)
        self.assertIn('<button type="button"', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class ShmXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _shm_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Bouncing Back", topic="Oscillations", grade_level="11",
            duration_minutes=30, learning_objectives=["x"],
        )
        lesson.physics_concepts.add(concept)
        student = StudentProfile.objects.create(display_name="Alex")
        record_experiment_prediction(
            student=student, simulation=simulation, lesson=lesson,
            prediction="<script>alert('p')</script>",
        )
        body = self.client.get(
            reverse("students:insights", args=[lesson.slug])
        ).content.decode()
        self.assertNotIn("<script>alert('p')</script>", body)
        self.assertIn("&lt;script&gt;", body)
