import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_orbital_motion import (
    DEFAULT_MU,
    DEFAULT_RADIUS_M,
    MAX_MU,
    MAX_RADIUS_M,
    MAX_TIME_S,
    MIN_MU,
    MIN_RADIUS_M,
    SimulationError,
    clamp_mu,
    clamp_radius,
    clamp_time,
    orbital_motion_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _orbital_motion_concept():
    return PhysicsConcept.objects.create(
        name="Orbital motion and Kepler's laws",
        description=(
            "A satellite in a stable orbit is in continuous free fall, with "
            "gravity supplying the centripetal force."
        ),
        topic="Orbits",
        equations=["T^2 is proportional to a^3 (Kepler's third law)"],
        si_units=["m/s", "s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _orbital_motion_concept(),
        title="Orbital Motion Lab",
        simulation_type=PhysicsSimulation.SimulationType.ORBITAL_MOTION,
        description="Explore v = sqrt(mu / r) and T = 2*pi*sqrt(r^3 / mu).",
    )


# --- DOMAIN -----------------------------------------------------------------


class OrbitalMotionSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_orbital_motion_concept(self):
        concept = _orbital_motion_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.ORBITAL_MOTION,
        )

    def test_seed_simulations_creates_orbital_motion_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="orbital-motion").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="orbital-motion")
        self.assertEqual(sim.simulation_type, "orbital_motion")
        self.assertEqual(sim.concept.name, "Orbital motion and Kepler's laws")

    def test_seed_simulations_is_idempotent_for_orbital_motion(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="orbital-motion").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class OrbitalMotionMathTests(TestCase):
    def test_starts_at_periapsis_moving_purely_tangentially(self):
        # At t=0 the body sits on the +x axis, moving purely in +y --
        # exactly the same starting convention as Circular Motion.
        state = orbital_motion_state(mu=500, radius=5, time=0)
        self.assertAlmostEqual(state["position_x_m"], 5.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=6)
        self.assertAlmostEqual(state["velocity_x_m_s"], 0.0, places=6)
        expected_speed = math.sqrt(500 / 5)
        self.assertAlmostEqual(state["velocity_y_m_s"], expected_speed, places=6)

    def test_speed_is_constant_regardless_of_time(self):
        expected_speed = math.sqrt(500 / 5)
        for t in (0, 1, 5, 12.3, 30, 59):
            state = orbital_motion_state(mu=500, radius=5, time=t)
            self.assertAlmostEqual(state["speed_m_s"], expected_speed, places=6)

    def test_orbit_stays_at_a_fixed_distance_from_the_center(self):
        for t in (0, 1, 5, 12.3, 30, 59):
            state = orbital_motion_state(mu=500, radius=5, time=t)
            distance = math.hypot(state["position_x_m"], state["position_y_m"])
            self.assertAlmostEqual(distance, 5.0, places=6)

    def test_orbit_repeats_after_one_full_period(self):
        state = orbital_motion_state(mu=500, radius=5, time=0)
        period = state["period_s"]
        one_period_later = orbital_motion_state(mu=500, radius=5, time=period)
        self.assertAlmostEqual(
            one_period_later["position_x_m"], state["position_x_m"], places=4
        )
        self.assertAlmostEqual(
            one_period_later["position_y_m"], state["position_y_m"], places=4
        )

    def test_keplers_third_law_holds_for_fixed_mu(self):
        # T^2 / r^3 must be the same (= 4*pi^2/mu) for any radius, given the
        # same central body (same mu).
        mu = 800
        ratios = []
        for radius in (1.0, 2.5, 5.0, 8.0, 10.0):
            state = orbital_motion_state(mu=mu, radius=radius, time=0)
            ratios.append((state["period_s"] ** 2) / (radius ** 3))
        expected = (4 * math.pi ** 2) / mu
        for ratio in ratios:
            self.assertAlmostEqual(ratio, expected, places=6)

    def test_gravitational_acceleration_matches_v_squared_over_r(self):
        state = orbital_motion_state(mu=500, radius=5, time=3)
        expected = state["speed_m_s"] ** 2 / 5
        self.assertAlmostEqual(
            state["gravitational_acceleration_m_s2"], expected, places=6
        )
        self.assertAlmostEqual(
            state["gravitational_acceleration_m_s2"], 500 / (5 ** 2), places=6
        )

    def test_a_bigger_orbit_at_the_same_mu_has_a_longer_period(self):
        small = orbital_motion_state(mu=500, radius=2, time=0)
        big = orbital_motion_state(mu=500, radius=8, time=0)
        self.assertGreater(big["period_s"], small["period_s"])

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 2, 5, 12):
            first = orbital_motion_state(mu=600, radius=4, time=t)
            second = orbital_motion_state(mu=600, radius=4, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_mu(999999), MAX_MU)
        self.assertEqual(clamp_mu(1), MIN_MU)
        self.assertEqual(clamp_radius(999), MAX_RADIUS_M)
        self.assertEqual(clamp_radius(0.001), MIN_RADIUS_M)

    def test_non_positive_mu_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mu(0)
        with self.assertRaises(SimulationError):
            clamp_mu(-10)

    def test_non_positive_radius_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_radius(0)
        with self.assertRaises(SimulationError):
            clamp_radius(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mu("heavy")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mu(math.nan)
        with self.assertRaises(SimulationError):
            clamp_radius(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = orbital_motion_state(mu=DEFAULT_MU, radius=DEFAULT_RADIUS_M, time=0)
        expected_speed = math.sqrt(DEFAULT_MU / DEFAULT_RADIUS_M)
        self.assertAlmostEqual(state["speed_m_s"], expected_speed, places=6)
        self.assertGreater(state["period_s"], 0)


class JsOrbitalMotionConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "orbital-motion.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "orbital-motion.js").read_text(encoding="utf-8")
        self.assertIn("Math.sqrt(mu / radius)", source)
        self.assertIn("Math.pow(radius, 3)", source)
        for bound in ("50.0", "2000.0", "1.0", "10.0", "60.0"):
            self.assertIn(bound, source)
        self.assertIn('register("orbital_motion"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class OrbitalMotionLabViewTests(TestCase):
    def setUp(self):
        self.concept = _orbital_motion_concept()
        self.simulation = _make_simulation(self.concept)

    def test_orbital_motion_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Orbital Motion Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/orbital-motion.js")

    def test_orbital_motion_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-mu")
        self.assertContains(response, "data-input-radius")
        self.assertContains(response, "data-input-time")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_orbital_motion(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_orbital_motion_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_orbital_motion(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Orbital Motion Lab", body)


class OrbitalMotionExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _orbital_motion_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "It kept a constant speed.", "mu": "500", "radius_m": "5", "time_s": "10"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["speed_m_s"], math.sqrt(500 / 5), places=4)

    def test_browser_submitted_period_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "mu": "500", "radius_m": "5",
                "time_s": "10", "period_s": "0.0001", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_period = 2 * math.pi * math.sqrt((5 ** 3) / 500)
        self.assertAlmostEqual(data["period_s"], expected_period, places=4)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "mu": "500", "radius_m": "5", "time_s": "-1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_positive_mu_or_radius(self):
        for bad_mu, bad_radius in (("0", "5"), ("500", "0"), ("-100", "5")):
            response = self.client.post(
                self.observe_url,
                {"observation": "x", "mu": bad_mu, "radius_m": bad_radius, "time_s": "1"},
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


class OrbitalMotionTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _orbital_motion_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Around We Go", topic="Orbits", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate orbital radius and period through Kepler's third law."],
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
            observation="x", mu=500, radius_m=5, time_s=10,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "orbital_motion")
        self.assertEqual(ctx.mu, 500.0)
        self.assertEqual(ctx.radius_m, 5.0)
        self.assertIsNotNone(ctx.acceleration_m_s2)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("gravitational parameter (mu) = 500.00 m^3/s^2", prompt.user)
        self.assertIn("Kepler's third law", prompt.user)


# --- accessibility -------------------------------------------------------


class OrbitalMotionAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _orbital_motion_concept()
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
        self.assertIn('<label for="lab-mu">', self.body)
        self.assertIn('<label for="lab-radius">', self.body)
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


class OrbitalMotionXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _orbital_motion_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Around We Go", topic="Orbits", grade_level="11",
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
