import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_projectile import (
    DEFAULT_INITIAL_HEIGHT_M,
    DEFAULT_INITIAL_SPEED_MS,
    DEFAULT_LAUNCH_ANGLE_DEG,
    GRAVITY_MS2,
    MAX_INITIAL_HEIGHT_M,
    MAX_INITIAL_SPEED_MS,
    MAX_LAUNCH_ANGLE_DEG,
    MAX_TIME_S,
    SimulationError,
    clamp_initial_height,
    clamp_initial_speed,
    clamp_launch_angle,
    clamp_time,
    projectile_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _projectile_concept():
    return PhysicsConcept.objects.create(
        name="Projectile motion",
        description="Motion of an object launched into the air, under gravity alone.",
        topic="Projectile Motion",
        equations=["x = v0 cos(theta) t", "y = y0 + v0 sin(theta) t - 1/2 g t^2"],
        si_units=["m", "m/s", "degrees"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _projectile_concept(),
        title="Projectile Motion Lab",
        simulation_type=PhysicsSimulation.SimulationType.PROJECTILE_MOTION,
        description="Explore x = v0*cos(theta)*t and y = y0 + v0*sin(theta)*t - 1/2*g*t^2.",
    )


# --- DOMAIN -----------------------------------------------------------------


class ProjectileSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_projectile_motion_concept(self):
        concept = _projectile_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.PROJECTILE_MOTION,
        )

    def test_seed_simulations_creates_projectile_motion_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="projectile-motion").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="projectile-motion")
        self.assertEqual(sim.simulation_type, "projectile_motion")
        self.assertEqual(sim.concept.name, "Projectile motion")

    def test_seed_simulations_is_idempotent_for_projectile_motion(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="projectile-motion").count(), 1
        )

    def test_kinematics_and_newtons_second_law_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(PhysicsSimulation.objects.filter(slug="kinematics").count(), 1)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="newtons-second-law").count(), 1
        )


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class ProjectileMathTests(TestCase):
    def test_horizontal_launch_worked_example(self):
        # v0=10 m/s, angle=0 (purely horizontal), y0=20 m, t=1 s.
        # x = 10*1 = 10; y = 20 + 0 - 0.5*9.8*1 = 15.1
        state = projectile_state(
            initial_speed=10, launch_angle=0, initial_height=20, time=1
        )
        self.assertAlmostEqual(state["position_x_m"], 10.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], 15.1, places=6)
        self.assertAlmostEqual(state["velocity_x_m_s"], 10.0, places=6)
        self.assertAlmostEqual(state["velocity_y_m_s"], -9.8, places=6)

    def test_forty_five_degree_launch_worked_example(self):
        # v0=20, angle=45, y0=0, t=1.
        v0 = 20.0
        theta = math.radians(45.0)
        vx0 = v0 * math.cos(theta)
        vy0 = v0 * math.sin(theta)
        expected_x = vx0 * 1
        expected_y = vy0 * 1 - 0.5 * GRAVITY_MS2 * 1
        state = projectile_state(
            initial_speed=20, launch_angle=45, initial_height=0, time=1
        )
        self.assertAlmostEqual(state["position_x_m"], expected_x, places=6)
        self.assertAlmostEqual(state["position_y_m"], expected_y, places=6)

    def test_range_formula_at_time_of_flight_for_level_ground(self):
        # Classic range formula: R = v0^2 * sin(2*theta) / g, for y0=0.
        v0, angle_deg = 20.0, 30.0
        theta = math.radians(angle_deg)
        t_flight = 2 * v0 * math.sin(theta) / GRAVITY_MS2
        expected_range = (v0 ** 2) * math.sin(2 * theta) / GRAVITY_MS2
        state = projectile_state(
            initial_speed=v0, launch_angle=angle_deg, initial_height=0, time=t_flight
        )
        self.assertAlmostEqual(state["position_x_m"], expected_range, places=4)
        self.assertAlmostEqual(state["position_y_m"], 0.0, places=4)

    def test_zero_speed_stays_at_the_launch_point(self):
        state = projectile_state(
            initial_speed=0, launch_angle=45, initial_height=5, time=3
        )
        self.assertAlmostEqual(state["position_x_m"], 0.0, places=6)
        # Still falls under gravity from the initial height.
        self.assertAlmostEqual(
            state["position_y_m"], 5 - 0.5 * GRAVITY_MS2 * 9, places=6
        )

    def test_ninety_degree_launch_has_no_horizontal_motion(self):
        state = projectile_state(
            initial_speed=15, launch_angle=90, initial_height=0, time=1
        )
        self.assertAlmostEqual(state["position_x_m"], 0.0, places=6)
        self.assertGreater(state["position_y_m"], 0.0)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 3, 8, 12):
            first = projectile_state(
                initial_speed=18, launch_angle=35, initial_height=4, time=t
            )
            second = projectile_state(
                initial_speed=18, launch_angle=35, initial_height=4, time=t
            )
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        clamped = clamp_time(999)
        self.assertEqual(clamped, MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_speed("fast")

    def test_nan_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_launch_angle(math.nan)

    def test_infinity_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_height(math.inf)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_initial_speed(999), MAX_INITIAL_SPEED_MS)
        self.assertEqual(clamp_launch_angle(999), MAX_LAUNCH_ANGLE_DEG)
        self.assertEqual(clamp_initial_height(999), MAX_INITIAL_HEIGHT_M)
        self.assertEqual(clamp_initial_speed(-5), 0.0)

    def test_default_state_is_a_valid_worked_example(self):
        state = projectile_state(
            initial_speed=DEFAULT_INITIAL_SPEED_MS,
            launch_angle=DEFAULT_LAUNCH_ANGLE_DEG,
            initial_height=DEFAULT_INITIAL_HEIGHT_M,
            time=0,
        )
        self.assertAlmostEqual(state["position_x_m"], 0.0, places=6)
        self.assertAlmostEqual(state["position_y_m"], DEFAULT_INITIAL_HEIGHT_M, places=6)


class JsProjectileConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "projectile.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "projectile.js").read_text(encoding="utf-8")
        self.assertIn("vx0 * t", source)
        self.assertIn("GRAVITY_MS2", source)
        self.assertIn("9.8", source)
        for bound in ("0.0", "40.0", "90.0", "50.0", "12.0"):
            self.assertIn(bound, source)
        self.assertIn('register("projectile_motion"', source)
        # The values must be computed in the browser, not fetched.
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class ProjectileLabViewTests(TestCase):
    def setUp(self):
        self.concept = _projectile_concept()
        self.simulation = _make_simulation(self.concept)

    def test_projectile_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projectile Motion Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/projectile.js")

    def test_projectile_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Initial speed")
        self.assertContains(response, "Launch angle")
        self.assertContains(response, "Initial height")
        self.assertContains(response, "data-input-speed")
        self.assertContains(response, "data-input-angle")
        self.assertContains(response, "data-input-height")

    def test_progress_bar_present(self):
        """Parity with Kinematics/Newton's Second Law (both already have it)."""

        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_projectile_motion(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_projectile_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_projectile_motion(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Projectile Motion Lab", body)


class ProjectileTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _projectile_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Motion Through the Air",
            topic="Kinematics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate launch angle and speed to range and height."],
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


# --- accessibility -------------------------------------------------------


class ProjectileAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _projectile_concept()
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
        self.assertIn('<label for="lab-speed">', self.body)
        self.assertIn('<label for="lab-angle">', self.body)
        self.assertIn('<label for="lab-height">', self.body)

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


class ProjectileXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _projectile_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Air Motion", topic="Kinematics", grade_level="11",
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
