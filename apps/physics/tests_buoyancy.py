import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_buoyancy import (
    DEFAULT_FLUID_DENSITY_KG_M3,
    DEFAULT_OBJECT_DENSITY_KG_M3,
    DEFAULT_VOLUME_M3,
    GRAVITY_MS2,
    MAX_DENSITY_KG_M3,
    MAX_VOLUME_M3,
    MIN_DENSITY_KG_M3,
    MIN_VOLUME_M3,
    SimulationError,
    buoyancy_state,
    clamp_density,
    clamp_volume,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _buoyancy_concept():
    return PhysicsConcept.objects.create(
        name="Archimedes' principle and buoyancy",
        description=(
            "An object submerged, fully or partly, in a fluid experiences "
            "an upward buoyant force equal to the weight of the fluid it "
            "displaces. Whether the object floats or sinks depends on how "
            "this compares to its own weight."
        ),
        topic="Buoyancy",
        equations=["F_b = rho g V"],
        si_units=["N"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _buoyancy_concept(),
        title="Buoyancy Lab",
        simulation_type=PhysicsSimulation.SimulationType.BUOYANCY,
        description="Explore whether an object floats or sinks through Archimedes' principle.",
    )


# --- DOMAIN -----------------------------------------------------------------


class BuoyancySimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_buoyancy_concept(self):
        concept = _buoyancy_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.BUOYANCY,
        )

    def test_seed_simulations_creates_buoyancy_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="buoyancy").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="buoyancy")
        self.assertEqual(sim.simulation_type, "buoyancy")
        self.assertEqual(sim.concept.name, "Archimedes' principle and buoyancy")

    def test_seed_simulations_is_idempotent_for_buoyancy(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="buoyancy").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion", "series-parallel-circuit",
            "coulombs-law", "radioactive-decay",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class BuoyancyMathTests(TestCase):
    def test_less_dense_object_floats(self):
        state = buoyancy_state(object_density=600, fluid_density=1000, volume=0.05)
        self.assertTrue(state["floats"])
        self.assertAlmostEqual(state["net_force_n"], 0.0, places=8)

    def test_more_dense_object_sinks(self):
        state = buoyancy_state(object_density=8000, fluid_density=1000, volume=0.05)
        self.assertFalse(state["floats"])
        self.assertGreater(state["net_force_n"], 0.0)
        self.assertAlmostEqual(state["submerged_fraction"], 1.0, places=8)

    def test_equal_density_floats_fully_submerged_at_equilibrium(self):
        # A genuine physics edge case: neutrally buoyant.
        state = buoyancy_state(object_density=1000, fluid_density=1000, volume=0.05)
        self.assertTrue(state["floats"])
        self.assertAlmostEqual(state["submerged_fraction"], 1.0, places=8)
        self.assertAlmostEqual(state["net_force_n"], 0.0, places=8)

    def test_submerged_fraction_when_floating_equals_density_ratio(self):
        state = buoyancy_state(object_density=700, fluid_density=1000, volume=0.05)
        self.assertAlmostEqual(state["submerged_fraction"], 0.7, places=6)

    def test_buoyant_force_equals_weight_when_floating(self):
        state = buoyancy_state(object_density=500, fluid_density=1000, volume=0.02)
        expected_weight = 500 * 0.02 * GRAVITY_MS2
        self.assertAlmostEqual(state["weight_n"], expected_weight, places=6)
        self.assertAlmostEqual(state["buoyant_force_n"], expected_weight, places=6)

    def test_a_large_low_density_object_floats_even_though_it_weighs_more(self):
        # The exact misconception this lab's concept names: "believing
        # heavier objects always sink ... rather than it depending on
        # density relative to the fluid". A big foam block is heavier in
        # absolute terms than a small pebble, yet the foam floats and the
        # pebble sinks.
        foam = buoyancy_state(object_density=200, fluid_density=1000, volume=1.0)
        pebble = buoyancy_state(object_density=3000, fluid_density=1000, volume=0.001)
        self.assertGreater(foam["weight_n"], pebble["weight_n"])
        self.assertTrue(foam["floats"])
        self.assertFalse(pebble["floats"])

    def test_weight_and_buoyant_force_scale_linearly_with_volume(self):
        small = buoyancy_state(object_density=600, fluid_density=1000, volume=0.01)
        big = buoyancy_state(object_density=600, fluid_density=1000, volume=0.02)
        self.assertAlmostEqual(big["weight_n"], small["weight_n"] * 2, places=6)
        self.assertAlmostEqual(
            big["max_buoyant_force_n"], small["max_buoyant_force_n"] * 2, places=6
        )

    def test_multiple_parameter_sets_are_deterministic(self):
        for rho_o, rho_f, v in ((600, 1000, 0.05), (9000, 1000, 0.02), (300, 800, 0.5)):
            first = buoyancy_state(object_density=rho_o, fluid_density=rho_f, volume=v)
            second = buoyancy_state(object_density=rho_o, fluid_density=rho_f, volume=v)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_density(999999), MAX_DENSITY_KG_M3)
        self.assertEqual(clamp_density(1), MIN_DENSITY_KG_M3)
        self.assertEqual(clamp_volume(999), MAX_VOLUME_M3)
        self.assertEqual(clamp_volume(0.00001), MIN_VOLUME_M3)

    def test_non_positive_density_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_density(0)
        with self.assertRaises(SimulationError):
            clamp_density(-10)

    def test_non_positive_volume_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_volume(0)
        with self.assertRaises(SimulationError):
            clamp_volume(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_density("heavy")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_density(math.nan)
        with self.assertRaises(SimulationError):
            clamp_volume(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = buoyancy_state(
            object_density=DEFAULT_OBJECT_DENSITY_KG_M3,
            fluid_density=DEFAULT_FLUID_DENSITY_KG_M3,
            volume=DEFAULT_VOLUME_M3,
        )
        self.assertTrue(state["floats"])
        self.assertGreater(state["weight_n"], 0)


class JsBuoyancyConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "buoyancy.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "buoyancy.js").read_text(encoding="utf-8")
        self.assertIn("GRAVITY_MS2", source)
        self.assertIn("rhoObject * v * GRAVITY_MS2", source)
        for bound in ("100.0", "12000.0", "0.001", "1.0"):
            self.assertIn(bound, source)
        self.assertIn('register("buoyancy"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class BuoyancyLabViewTests(TestCase):
    def setUp(self):
        self.concept = _buoyancy_concept()
        self.simulation = _make_simulation(self.concept)

    def test_buoyancy_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Buoyancy Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/buoyancy.js")

    def test_buoyancy_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-object-density")
        self.assertContains(response, "data-input-fluid-density")
        self.assertContains(response, "data-input-volume")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_buoyancy(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_buoyancy_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_buoyancy(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Buoyancy Lab", body)


class BuoyancyExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _buoyancy_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "It floated.", "object_density_kg_m3": "600",
                "fluid_density_kg_m3": "1000", "volume_m3": "0.05",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["floats"])
        expected_weight = 600 * 0.05 * GRAVITY_MS2
        self.assertAlmostEqual(data["weight_n"], expected_weight, places=2)

    def test_browser_submitted_verdict_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "object_density_kg_m3": "9000",
                "fluid_density_kg_m3": "1000", "volume_m3": "0.05",
                "floats": "true", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["floats"])

    def test_observe_endpoint_rejects_non_positive_density_or_volume(self):
        for object_density, fluid_density, volume in (
            ("0", "1000", "0.05"), ("600", "0", "0.05"), ("600", "1000", "0"),
        ):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "object_density_kg_m3": object_density,
                    "fluid_density_kg_m3": fluid_density, "volume_m3": volume,
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


class BuoyancyTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _buoyancy_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Float or Sink", topic="Buoyancy", grade_level="9",
            duration_minutes=45,
            learning_objectives=["Relate density to whether an object floats or sinks."],
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
            observation="x", object_density_kg_m3=600, fluid_density_kg_m3=1000, volume_m3=0.05,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "buoyancy")
        self.assertEqual(ctx.object_density_kg_m3, 600.0)
        self.assertTrue(ctx.floats)
        self.assertEqual(ctx.force_n, 0.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("object density = 600 kg/m^3", prompt.user)
        self.assertIn("the object floats", prompt.user)


# --- accessibility -------------------------------------------------------


class BuoyancyAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _buoyancy_concept()
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
        self.assertIn('<label for="lab-object-density">', self.body)
        self.assertIn('<label for="lab-fluid-density">', self.body)
        self.assertIn('<label for="lab-volume">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class BuoyancyXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _buoyancy_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Float or Sink", topic="Buoyancy", grade_level="9",
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
