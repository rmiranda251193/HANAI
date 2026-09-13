import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_circular_motion import (
    DEFAULT_PERIOD_S,
    DEFAULT_RADIUS_M,
    MAX_PERIOD_S,
    MAX_RADIUS_M,
    MAX_TIME_S,
    MIN_PERIOD_S,
    MIN_RADIUS_M,
    SimulationError,
    circular_motion_state,
    clamp_period,
    clamp_radius,
    clamp_time,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _circular_motion_concept():
    return PhysicsConcept.objects.create(
        name="Uniform circular motion",
        description="An object moving at constant speed around a circle is still accelerating.",
        topic="Circular Motion",
        equations=["v = 2 pi r / T"],
        si_units=["m/s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _circular_motion_concept(),
        title="Circular Motion Lab",
        simulation_type=PhysicsSimulation.SimulationType.CIRCULAR_MOTION,
        description="Explore v = 2*pi*r/T and a_c = v^2/r.",
    )


# --- DOMAIN -----------------------------------------------------------------


class CircularMotionSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_circular_motion_concept(self):
        concept = _circular_motion_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.CIRCULAR_MOTION,
        )

    def test_seed_simulations_creates_circular_motion_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="circular-motion").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="circular-motion")
        self.assertEqual(sim.simulation_type, "circular_motion")
        self.assertEqual(sim.concept.name, "Uniform circular motion")

    def test_seed_simulations_is_idempotent_for_circular_motion(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="circular-motion").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in ("kinematics", "newtons-second-law", "projectile-motion"):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class CircularMotionMathTests(TestCase):
    def test_starts_at_radius_zero_angle(self):
        state = circular_motion_state(radius=2, period=4, time=0)
        self.assertAlmostEqual(state["position_x_m"], 2.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=6)
        self.assertAlmostEqual(state["angle_deg"], 0.0, places=6)

    def test_quarter_period_worked_example(self):
        # r=2, T=4 -> omega=pi/2. At t=1 (T/4): theta=pi/2 -> (0, r).
        state = circular_motion_state(radius=2, period=4, time=1)
        self.assertAlmostEqual(state["position_x_m"], 0.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], 2.0, places=6)
        self.assertAlmostEqual(state["angle_deg"], 90.0, places=4)

    def test_half_period_reaches_the_opposite_side(self):
        state = circular_motion_state(radius=2, period=4, time=2)
        self.assertAlmostEqual(state["position_x_m"], -2.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=6)

    def test_full_period_returns_to_the_start(self):
        state = circular_motion_state(radius=3, period=5, time=5)
        self.assertAlmostEqual(state["position_x_m"], 3.0, places=5)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=5)

    def test_speed_matches_the_classic_formula(self):
        radius, period = 2.5, 6.0
        expected_speed = 2 * math.pi * radius / period
        state = circular_motion_state(radius=radius, period=period, time=1.3)
        self.assertAlmostEqual(state["speed_m_s"], expected_speed, places=6)

    def test_centripetal_acceleration_matches_v_squared_over_r(self):
        radius, period = 4.0, 3.0
        state = circular_motion_state(radius=radius, period=period, time=0.7)
        expected = state["speed_m_s"] ** 2 / radius
        self.assertAlmostEqual(state["centripetal_acceleration_m_s2"], expected, places=6)

    def test_speed_is_constant_regardless_of_time(self):
        speeds = {
            circular_motion_state(radius=2, period=4, time=t)["speed_m_s"]
            for t in (0, 0.5, 1, 2, 3.7)
        }
        self.assertEqual(len(speeds), 1)

    def test_bigger_radius_same_period_means_faster_speed(self):
        small = circular_motion_state(radius=1, period=4, time=0.5)
        big = circular_motion_state(radius=5, period=4, time=0.5)
        self.assertGreater(big["speed_m_s"], small["speed_m_s"])

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 3, 8, 20):
            first = circular_motion_state(radius=2, period=4, time=t)
            second = circular_motion_state(radius=2, period=4, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_non_positive_radius_is_clamped_up_to_the_minimum(self):
        # Unlike period (where zero/negative is a division-by-zero / nonsense
        # input and is rejected outright), radius is just clamped like any
        # other UI-range value -- MIN_RADIUS_M is already > 0.
        self.assertEqual(clamp_radius(0), MIN_RADIUS_M)
        self.assertEqual(clamp_radius(-2), MIN_RADIUS_M)

    def test_non_positive_period_is_rejected(self):
        with self.assertRaises(SimulationError):
            circular_motion_state(radius=2, period=0, time=0)
        with self.assertRaises(SimulationError):
            clamp_period(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_radius("big")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_radius(math.nan)
        with self.assertRaises(SimulationError):
            clamp_period(math.inf)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_radius(999), MAX_RADIUS_M)
        self.assertEqual(clamp_period(999), MAX_PERIOD_S)
        self.assertEqual(clamp_radius(0.001), MIN_RADIUS_M)
        self.assertEqual(clamp_period(0.001), MIN_PERIOD_S)

    def test_default_state_is_a_valid_worked_example(self):
        state = circular_motion_state(
            radius=DEFAULT_RADIUS_M, period=DEFAULT_PERIOD_S, time=0
        )
        self.assertAlmostEqual(state["position_x_m"], DEFAULT_RADIUS_M, places=6)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=6)


class JsCircularMotionConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "circular-motion.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "circular-motion.js").read_text(encoding="utf-8")
        self.assertIn("omega", source)
        self.assertIn("centripetalAccel", source)
        for bound in ("0.5", "10.0", "20.0", "60.0"):
            self.assertIn(bound, source)
        self.assertIn('register("circular_motion"', source)
        # The values must be computed in the browser, not fetched.
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class CircularMotionLabViewTests(TestCase):
    def setUp(self):
        self.concept = _circular_motion_concept()
        self.simulation = _make_simulation(self.concept)

    def test_circular_motion_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Circular Motion Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/circular-motion.js")

    def test_circular_motion_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Radius")
        self.assertContains(response, "Period")
        self.assertContains(response, "data-input-radius")
        self.assertContains(response, "data-input-period")

    def test_progress_bar_present(self):
        """Parity with the other three labs (all already have it)."""

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
        self.assertContains(response, "Swing a weight in a horizontal circle")

    def test_other_simulations_still_load_alongside_circular_motion(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_circular_motion_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_circular_motion(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Circular Motion Lab", body)


class CircularMotionExperimentFlowTests(TestCase):
    """Server-authoritative recomputation via the shared experiment endpoints."""

    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _circular_motion_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "It moved steadily.", "radius_m": "2", "period_s": "4", "time_s": "1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["position_x_m"], 0.0, places=4)
        self.assertAlmostEqual(data["position_y_m"], 2.0, places=4)

    def test_browser_submitted_position_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "radius_m": "2", "period_s": "4", "time_s": "1",
                "position_x_m": "999", "position_y_m": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["position_y_m"], 2.0, places=4)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "radius_m": "2", "period_s": "4", "time_s": "-1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_zero_period(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "radius_m": "2", "period_s": "0", "time_s": "1"},
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


class CircularMotionTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _circular_motion_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Going in Circles",
            topic="Circular Motion",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate radius and period to speed and centripetal acceleration."],
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
            observation="x", radius_m=2, period_s=4, time_s=1,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "circular_motion")
        self.assertEqual(ctx.radius_m, 2.0)
        self.assertEqual(ctx.period_s, 4.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("radius = 2.00 m", prompt.user)
        self.assertIn("period = 4.00 s", prompt.user)


# --- accessibility -------------------------------------------------------


class CircularMotionAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _circular_motion_concept()
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
        self.assertIn('<label for="lab-radius">', self.body)
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


class CircularMotionXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _circular_motion_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Going in Circles", topic="Circular Motion", grade_level="11",
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
