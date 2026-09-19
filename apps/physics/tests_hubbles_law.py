import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_hubbles_law import (
    DEFAULT_DISTANCE_MPC,
    DEFAULT_HUBBLE_CONSTANT_KM_S_MPC,
    MAX_DISTANCE_MPC,
    MAX_HUBBLE_CONSTANT_KM_S_MPC,
    MIN_DISTANCE_MPC,
    MIN_HUBBLE_CONSTANT_KM_S_MPC,
    SPEED_OF_LIGHT_KM_S,
    SimulationError,
    clamp_distance,
    clamp_hubble_constant,
    hubbles_law_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _cosmology_concept():
    return PhysicsConcept.objects.create(
        name="Cosmology and the expanding universe",
        description=(
            "Observations show distant galaxies receding from us, with "
            "recession speed roughly proportional to distance (Hubble's "
            "law) -- evidence that space itself is expanding."
        ),
        topic="Cosmology",
        equations=["v = H0 d"],
        si_units=["m/s", "m"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _cosmology_concept(),
        title="Hubble's Law Lab",
        simulation_type=PhysicsSimulation.SimulationType.HUBBLES_LAW,
        description="Explore v = H0 d.",
    )


# --- DOMAIN -----------------------------------------------------------------


class HubblesLawSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_cosmology_concept(self):
        concept = _cosmology_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.HUBBLES_LAW,
        )

    def test_seed_simulations_creates_hubbles_law_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="hubbles-law").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="hubbles-law")
        self.assertEqual(sim.simulation_type, "hubbles_law")
        self.assertEqual(sim.concept.name, "Cosmology and the expanding universe")

    def test_seed_simulations_is_idempotent_for_hubbles_law(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="hubbles-law").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion", "series-parallel-circuit",
            "coulombs-law", "radioactive-decay", "buoyancy", "refraction",
            "calorimetry", "ideal-gas-law", "doppler-effect", "magnetic-force",
            "time-dilation", "photoelectric-effect", "electromagnetic-induction",
            "bohr-model",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class HubblesLawMathTests(TestCase):
    def test_default_state_is_a_valid_worked_example(self):
        state = hubbles_law_state(
            distance_mpc=DEFAULT_DISTANCE_MPC,
            hubble_constant_km_s_mpc=DEFAULT_HUBBLE_CONSTANT_KM_S_MPC,
        )
        self.assertAlmostEqual(state["recession_velocity_km_s"], 7000.0, places=6)
        self.assertAlmostEqual(
            state["redshift_z"], 7000.0 / SPEED_OF_LIGHT_KM_S, places=9
        )

    def test_recession_velocity_scales_linearly_with_distance(self):
        base = hubbles_law_state(distance_mpc=50, hubble_constant_km_s_mpc=70)
        doubled = hubbles_law_state(distance_mpc=100, hubble_constant_km_s_mpc=70)
        self.assertAlmostEqual(
            doubled["recession_velocity_km_s"], 2 * base["recession_velocity_km_s"], places=6
        )

    def test_recession_velocity_is_proportional_to_hubble_constant(self):
        low = hubbles_law_state(distance_mpc=100, hubble_constant_km_s_mpc=60)
        high = hubbles_law_state(distance_mpc=100, hubble_constant_km_s_mpc=80)
        ratio = high["recession_velocity_km_s"] / low["recession_velocity_km_s"]
        self.assertAlmostEqual(ratio, 80.0 / 60.0, places=6)

    def test_redshift_always_equals_velocity_over_c(self):
        for d, h0 in ((1, 60), (50, 70), (100, 70), (200, 80)):
            state = hubbles_law_state(distance_mpc=d, hubble_constant_km_s_mpc=h0)
            self.assertAlmostEqual(
                state["redshift_z"],
                state["recession_velocity_km_s"] / SPEED_OF_LIGHT_KM_S,
                places=9,
            )

    def test_recession_velocity_and_redshift_are_always_positive(self):
        for d, h0 in ((MIN_DISTANCE_MPC, MIN_HUBBLE_CONSTANT_KM_S_MPC), (100, 70), (MAX_DISTANCE_MPC, MAX_HUBBLE_CONSTANT_KM_S_MPC)):
            state = hubbles_law_state(distance_mpc=d, hubble_constant_km_s_mpc=h0)
            self.assertGreater(state["recession_velocity_km_s"], 0)
            self.assertGreater(state["redshift_z"], 0)

    def test_worst_case_corner_stays_well_under_the_speed_of_light(self):
        """Regression pin: an earlier draft allowed MAX_DISTANCE_MPC=5000,
        which at MAX_HUBBLE_CONSTANT_KM_S_MPC produced v > c -- a direct
        contradiction of this lab's own "non-relativistic, z = v/c is an
        accurate approximation" framing. The UI-facing distance bound is
        deliberately capped so even the worst-case corner stays well under
        the speed of light."""

        state = hubbles_law_state(
            distance_mpc=MAX_DISTANCE_MPC,
            hubble_constant_km_s_mpc=MAX_HUBBLE_CONSTANT_KM_S_MPC,
        )
        self.assertLess(state["recession_velocity_km_s"], 0.1 * SPEED_OF_LIGHT_KM_S)
        self.assertLess(state["redshift_z"], 0.1)

    def test_multiple_parameter_sets_are_deterministic(self):
        for d, h0 in ((100, 70), (50, 65), (200, 80)):
            first = hubbles_law_state(distance_mpc=d, hubble_constant_km_s_mpc=h0)
            second = hubbles_law_state(distance_mpc=d, hubble_constant_km_s_mpc=h0)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_distance(99999), MAX_DISTANCE_MPC)
        self.assertEqual(clamp_distance(0.0001), MIN_DISTANCE_MPC)
        self.assertEqual(clamp_hubble_constant(999), MAX_HUBBLE_CONSTANT_KM_S_MPC)
        self.assertEqual(clamp_hubble_constant(0.0001), MIN_HUBBLE_CONSTANT_KM_S_MPC)

    def test_non_positive_distance_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_distance(0)
        with self.assertRaises(SimulationError):
            clamp_distance(-10)

    def test_non_positive_hubble_constant_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_hubble_constant(0)
        with self.assertRaises(SimulationError):
            clamp_hubble_constant(-70)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_distance("far")
        with self.assertRaises(SimulationError):
            clamp_hubble_constant("fast")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_distance(math.nan)
        with self.assertRaises(SimulationError):
            clamp_hubble_constant(math.inf)


class JsHubblesLawConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "hubbles-law.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "hubbles-law.js").read_text(encoding="utf-8")
        self.assertIn("h0 * d", source)
        for bound in ("299792.458", "200.0", "60.0", "80.0"):
            self.assertIn(bound, source)
        self.assertIn('register("hubbles_law"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class HubblesLawLabViewTests(TestCase):
    def setUp(self):
        self.concept = _cosmology_concept()
        self.simulation = _make_simulation(self.concept)

    def test_hubbles_law_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hubble&#x27;s Law Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/hubbles-law.js")

    def test_hubbles_law_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-distance")
        self.assertContains(response, "data-input-hubble-constant")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_hubbles_law(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_hubbles_law_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_hubbles_law(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Hubble", body)


class HubblesLawExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _cosmology_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "It receded at 7000 km/s.",
                "distance_mpc": "100", "hubble_constant_km_s_mpc": "70",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["recession_velocity_km_s"], 7000.0, places=1)

    def test_browser_submitted_recession_velocity_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated",
                "distance_mpc": "100", "hubble_constant_km_s_mpc": "70",
                "recession_velocity_km_s": "1", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["recession_velocity_km_s"], 7000.0, places=1)

    def test_observe_endpoint_rejects_non_positive_distance_or_hubble_constant(self):
        base = {
            "observation": "x",
            "distance_mpc": "100", "hubble_constant_km_s_mpc": "70",
        }
        for override in ({"distance_mpc": "0"}, {"hubble_constant_km_s_mpc": "0"},
                          {"distance_mpc": "-5"}, {"hubble_constant_km_s_mpc": "-70"}):
            payload = dict(base, **override)
            response = self.client.post(self.observe_url, payload)
            self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_numeric_input(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "distance_mpc": "far", "hubble_constant_km_s_mpc": "70"},
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


class HubblesLawTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _cosmology_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="The Expanding Universe", topic="Cosmology", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate a galaxy's distance to its recession speed and redshift."],
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
            observation="x", distance_mpc=100, hubble_constant_km_s_mpc=70,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "hubbles_law")
        self.assertAlmostEqual(ctx.distance_mpc, 100.0, places=2)
        self.assertAlmostEqual(ctx.recession_velocity_km_s, 7000.0, places=1)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("distance = 100.0 Mpc", prompt.user)
        self.assertIn("recession", prompt.user)


# --- accessibility -------------------------------------------------------


class HubblesLawAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _cosmology_concept()
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
        self.assertIn('<label for="lab-distance">', self.body)
        self.assertIn('<label for="lab-hubble-constant">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class HubblesLawXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _cosmology_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="The Expanding Universe", topic="Cosmology", grade_level="12",
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
