import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_refraction import (
    DEFAULT_ANGLE1_DEG,
    DEFAULT_N1,
    DEFAULT_N2,
    MAX_ANGLE_DEG,
    MAX_INDEX,
    MIN_ANGLE_DEG,
    MIN_INDEX,
    SimulationError,
    clamp_angle,
    clamp_index,
    refraction_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _refraction_concept():
    return PhysicsConcept.objects.create(
        name="Refraction and Snell's law",
        description=(
            "Light bends when it passes between materials in which it "
            "travels at different speeds. Snell's law relates the angles "
            "of incidence and refraction to the refractive indices of the "
            "two materials."
        ),
        topic="Geometric Optics",
        equations=["n1 sin(theta1) = n2 sin(theta2)"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _refraction_concept(),
        title="Refraction Lab",
        simulation_type=PhysicsSimulation.SimulationType.REFRACTION,
        description="Explore n1 sin(theta1) = n2 sin(theta2).",
    )


# --- DOMAIN -----------------------------------------------------------------


class RefractionSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_refraction_concept(self):
        concept = _refraction_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.REFRACTION,
        )

    def test_seed_simulations_creates_refraction_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="refraction").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="refraction")
        self.assertEqual(sim.simulation_type, "refraction")
        self.assertEqual(sim.concept.name, "Refraction and Snell's law")

    def test_seed_simulations_is_idempotent_for_refraction(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="refraction").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion", "series-parallel-circuit",
            "coulombs-law", "radioactive-decay", "buoyancy",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class RefractionMathTests(TestCase):
    def test_normal_incidence_passes_straight_through(self):
        for n1, n2 in ((1.0, 1.5), (1.5, 1.0), (1.3, 2.0)):
            state = refraction_state(n1=n1, n2=n2, angle1_deg=0)
            self.assertAlmostEqual(state["angle2_deg"], 0.0, places=6)
            self.assertFalse(state["total_internal_reflection"])

    def test_classic_air_to_glass_worked_example(self):
        state = refraction_state(n1=1.0, n2=1.5, angle1_deg=30)
        expected = math.degrees(math.asin(math.sin(math.radians(30)) / 1.5))
        self.assertAlmostEqual(state["angle2_deg"], expected, places=6)
        self.assertFalse(state["total_internal_reflection"])

    def test_snells_law_is_reversible(self):
        # Refracting n1 -> n2 at theta1 and then reversing (n2 -> n1 at the
        # resulting theta2) must return exactly the original angle.
        forward = refraction_state(n1=1.0, n2=1.5, angle1_deg=35)
        backward = refraction_state(n1=1.5, n2=1.0, angle1_deg=forward["angle2_deg"])
        self.assertAlmostEqual(backward["angle2_deg"], 35.0, places=4)

    def test_bends_toward_the_normal_entering_a_denser_medium(self):
        state = refraction_state(n1=1.0, n2=1.5, angle1_deg=40)
        self.assertLess(state["angle2_deg"], state["angle1_deg"])

    def test_bends_away_from_the_normal_entering_a_less_dense_medium(self):
        state = refraction_state(n1=1.5, n2=1.0, angle1_deg=20)
        self.assertFalse(state["total_internal_reflection"])
        self.assertGreater(state["angle2_deg"], state["angle1_deg"])

    def test_total_internal_reflection_past_the_critical_angle(self):
        # n1=1.5, n2=1.0 -> critical angle = arcsin(1/1.5) ~= 41.81 degrees
        below = refraction_state(n1=1.5, n2=1.0, angle1_deg=30)
        above = refraction_state(n1=1.5, n2=1.0, angle1_deg=50)
        self.assertFalse(below["total_internal_reflection"])
        self.assertTrue(above["total_internal_reflection"])

    def test_critical_angle_matches_the_closed_form(self):
        state = refraction_state(n1=1.5, n2=1.0, angle1_deg=10)
        expected_critical = math.degrees(math.asin(1.0 / 1.5))
        self.assertTrue(state["has_critical_angle"])
        self.assertAlmostEqual(state["critical_angle_deg"], expected_critical, places=6)

    def test_no_critical_angle_when_entering_a_denser_or_equal_medium(self):
        for n1, n2 in ((1.0, 1.5), (1.2, 1.2)):
            state = refraction_state(n1=n1, n2=n2, angle1_deg=45)
            self.assertFalse(state["has_critical_angle"])
            self.assertFalse(state["total_internal_reflection"])

    def test_multiple_parameter_sets_are_deterministic(self):
        for n1, n2, a1 in ((1.0, 1.5, 30), (1.5, 1.0, 50), (1.33, 1.0, 45)):
            first = refraction_state(n1=n1, n2=n2, angle1_deg=a1)
            second = refraction_state(n1=n1, n2=n2, angle1_deg=a1)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_index(999), MAX_INDEX)
        self.assertEqual(clamp_index(1.0), MIN_INDEX)
        self.assertEqual(clamp_angle(999), MAX_ANGLE_DEG)
        self.assertEqual(clamp_angle(0), MIN_ANGLE_DEG)

    def test_index_below_one_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_index(0.5)
        with self.assertRaises(SimulationError):
            clamp_index(0)

    def test_negative_angle_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_angle(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_index("glassy")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_index(math.nan)
        with self.assertRaises(SimulationError):
            clamp_angle(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = refraction_state(n1=DEFAULT_N1, n2=DEFAULT_N2, angle1_deg=DEFAULT_ANGLE1_DEG)
        self.assertFalse(state["total_internal_reflection"])
        self.assertGreater(state["angle2_deg"], 0)


class JsRefractionConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "refraction.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "refraction.js").read_text(encoding="utf-8")
        self.assertIn("Math.asin", source)
        self.assertIn("sinTheta2 > 1.0", source)
        for bound in ("1.0", "2.5", "89.0"):
            self.assertIn(bound, source)
        self.assertIn('register("refraction"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class RefractionLabViewTests(TestCase):
    def setUp(self):
        self.concept = _refraction_concept()
        self.simulation = _make_simulation(self.concept)

    def test_refraction_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Refraction Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/refraction.js")

    def test_refraction_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-n1")
        self.assertContains(response, "data-input-n2")
        self.assertContains(response, "data-input-angle1")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_refraction(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_refraction_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_refraction(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Refraction Lab", body)


class RefractionExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _refraction_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "It bent toward the normal.", "n1": "1.0", "n2": "1.5", "angle1_deg": "30"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = math.degrees(math.asin(math.sin(math.radians(30)) / 1.5))
        self.assertAlmostEqual(data["angle2_deg"], expected, places=2)
        self.assertFalse(data["total_internal_reflection"])

    def test_browser_submitted_angle_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "n1": "1.0", "n2": "1.5", "angle1_deg": "30",
                "angle2_deg": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = math.degrees(math.asin(math.sin(math.radians(30)) / 1.5))
        self.assertAlmostEqual(data["angle2_deg"], expected, places=2)

    def test_observe_endpoint_reports_total_internal_reflection(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "It reflected.", "n1": "1.5", "n2": "1.0", "angle1_deg": "60"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["total_internal_reflection"])

    def test_observe_endpoint_rejects_index_below_one(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "n1": "0.5", "n2": "1.5", "angle1_deg": "30"},
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_negative_angle(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "n1": "1.0", "n2": "1.5", "angle1_deg": "-5"},
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


class RefractionTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _refraction_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Bending Light", topic="Geometric Optics", grade_level="10",
            duration_minutes=45,
            learning_objectives=["Relate refractive index to how much light bends."],
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
            observation="x", n1=1.0, n2=1.5, angle1_deg=30,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "refraction")
        self.assertEqual(ctx.n1, 1.0)
        self.assertFalse(ctx.total_internal_reflection)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("n1 = 1.00, n2 = 1.50", prompt.user)
        self.assertIn("refracts at", prompt.user)


# --- accessibility -------------------------------------------------------


class RefractionAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _refraction_concept()
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
        self.assertIn('<label for="lab-n1">', self.body)
        self.assertIn('<label for="lab-n2">', self.body)
        self.assertIn('<label for="lab-angle1">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class RefractionXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _refraction_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Bending Light", topic="Geometric Optics", grade_level="10",
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
