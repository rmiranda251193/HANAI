import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_energy_incline import (
    DEFAULT_ANGLE_DEG,
    DEFAULT_HEIGHT_M,
    DEFAULT_MASS_KG,
    GRAVITY_MS2,
    MAX_ANGLE_DEG,
    MAX_HEIGHT_M,
    MAX_MASS_KG,
    MAX_TIME_S,
    MIN_ANGLE_DEG,
    MIN_HEIGHT_M,
    MIN_MASS_KG,
    SimulationError,
    clamp_angle,
    clamp_height,
    clamp_mass,
    clamp_time,
    energy_incline_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _energy_concept():
    return PhysicsConcept.objects.create(
        name="Conservation of mechanical energy",
        description="Total mechanical energy stays constant with no friction.",
        topic="Work and Energy",
        equations=["KE_i + PE_i = KE_f + PE_f (no friction)"],
        si_units=["J"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _energy_concept(),
        title="Energy on an Incline Lab",
        simulation_type=PhysicsSimulation.SimulationType.ENERGY_INCLINE,
        description="Explore KE + PE = mgh on a frictionless ramp.",
    )


# --- DOMAIN -----------------------------------------------------------------


class EnergyInclineSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_energy_concept(self):
        concept = _energy_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.ENERGY_INCLINE,
        )

    def test_seed_simulations_creates_energy_incline_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="energy-incline").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="energy-incline")
        self.assertEqual(sim.simulation_type, "energy_incline")
        self.assertEqual(sim.concept.name, "Conservation of mechanical energy")

    def test_seed_simulations_is_idempotent_for_energy_incline(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="energy-incline").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class EnergyInclineMathTests(TestCase):
    def test_starts_at_rest_with_all_potential_energy(self):
        state = energy_incline_state(height=5, angle=30, mass=2, time=0)
        self.assertAlmostEqual(state["speed_m_s"], 0.0, places=6)
        self.assertAlmostEqual(state["kinetic_energy_j"], 0.0, places=6)
        self.assertAlmostEqual(state["potential_energy_j"], 2 * GRAVITY_MS2 * 5, places=6)
        self.assertFalse(state["reached_bottom"])

    def test_energy_is_conserved_at_every_instant(self):
        expected_total = 2 * GRAVITY_MS2 * 5  # m*g*h
        for t in (0, 0.5, 1, 1.5, 2, 5, 10, 15):
            state = energy_incline_state(height=5, angle=30, mass=2, time=t)
            self.assertAlmostEqual(state["total_energy_j"], expected_total, places=4)

    def test_speed_at_the_bottom_matches_sqrt_2gh_independent_of_angle(self):
        expected_v = math.sqrt(2 * GRAVITY_MS2 * 5)
        for angle in (15, 30, 45, 60, 75):
            state = energy_incline_state(height=5, angle=angle, mass=2, time=100)
            self.assertAlmostEqual(state["speed_m_s"], expected_v, places=5)
            self.assertTrue(state["reached_bottom"])

    def test_all_potential_becomes_kinetic_at_the_bottom(self):
        state = energy_incline_state(height=5, angle=30, mass=2, time=100)
        self.assertAlmostEqual(state["potential_energy_j"], 0.0, places=4)
        self.assertAlmostEqual(state["kinetic_energy_j"], 2 * GRAVITY_MS2 * 5, places=4)

    def test_after_the_bottom_speed_stays_constant(self):
        # height=5, angle=30 reaches the bottom at t_end ~= 2.02s -- both of
        # these times are safely past that and within MAX_TIME_S (15s).
        state_at_bottom = energy_incline_state(height=5, angle=30, mass=2, time=5)
        state_later = energy_incline_state(height=5, angle=30, mass=2, time=12)
        self.assertAlmostEqual(state_at_bottom["speed_m_s"], state_later["speed_m_s"], places=5)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 2, 5, 12):
            first = energy_incline_state(height=6, angle=40, mass=3, time=t)
            second = energy_incline_state(height=6, angle=40, mass=3, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_height(999), MAX_HEIGHT_M)
        self.assertEqual(clamp_height(0), MIN_HEIGHT_M)
        self.assertEqual(clamp_angle(999), MAX_ANGLE_DEG)
        self.assertEqual(clamp_angle(0), MIN_ANGLE_DEG)
        self.assertEqual(clamp_mass(999), MAX_MASS_KG)
        self.assertEqual(clamp_mass(0), MIN_MASS_KG)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_height("tall")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_height(math.nan)
        with self.assertRaises(SimulationError):
            clamp_angle(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = energy_incline_state(
            height=DEFAULT_HEIGHT_M, angle=DEFAULT_ANGLE_DEG, mass=DEFAULT_MASS_KG, time=0
        )
        self.assertAlmostEqual(state["speed_m_s"], 0.0, places=6)
        self.assertAlmostEqual(
            state["total_energy_j"], DEFAULT_MASS_KG * GRAVITY_MS2 * DEFAULT_HEIGHT_M, places=4
        )


class JsEnergyInclineConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "energy-incline.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "energy-incline.js").read_text(encoding="utf-8")
        self.assertIn("GRAVITY_MS2", source)
        self.assertIn("Math.sin(theta)", source)
        for bound in ("1.0", "10.0", "80.0", "0.5", "15.0"):
            self.assertIn(bound, source)
        self.assertIn('register("energy_incline"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class EnergyInclineLabViewTests(TestCase):
    def setUp(self):
        self.concept = _energy_concept()
        self.simulation = _make_simulation(self.concept)

    def test_energy_incline_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Energy on an Incline Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/energy-incline.js")

    def test_energy_incline_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Height")
        self.assertContains(response, "Incline angle")
        self.assertContains(response, "data-input-height")
        self.assertContains(response, "data-input-angle")
        self.assertContains(response, "data-input-mass")

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
        self.assertContains(response, "Race a ball down a book ramp")

    def test_other_simulations_still_load_alongside_energy_incline(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_energy_incline_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_energy_incline(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Energy on an Incline Lab", body)


class EnergyInclineExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _energy_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "It sped up.", "height_m": "5", "angle_deg": "30",
                "mass_kg": "2", "time_s": "10",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["speed_m_s"], math.sqrt(2 * GRAVITY_MS2 * 5), places=4)

    def test_browser_submitted_energy_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "height_m": "5", "angle_deg": "30",
                "mass_kg": "2", "time_s": "10", "total_energy_j": "999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_energy_j"], 2 * GRAVITY_MS2 * 5, places=4)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "height_m": "5", "angle_deg": "30",
                "mass_kg": "2", "time_s": "-1",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_a_flat_or_vertical_angle(self):
        for bad_angle in ("0", "90"):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "height_m": "5", "angle_deg": bad_angle,
                    "mass_kg": "2", "time_s": "1",
                },
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


class EnergyInclineTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _energy_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Down the Ramp", topic="Work and Energy", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate height and speed through energy conservation."],
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
            observation="x", height_m=5, angle_deg=30, mass_kg=2, time_s=10,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "energy_incline")
        self.assertEqual(ctx.height_m, 5.0)
        self.assertEqual(ctx.mass_kg, 2.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("starting height = 5.00 m", prompt.user)
        self.assertIn("total mechanical energy", prompt.user)


# --- accessibility -------------------------------------------------------


class EnergyInclineAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _energy_concept()
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
        self.assertIn('<label for="lab-height">', self.body)
        self.assertIn('<label for="lab-angle">', self.body)
        self.assertIn('<label for="lab-mass">', self.body)
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


class EnergyInclineXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _energy_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Down the Ramp", topic="Work and Energy", grade_level="11",
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
