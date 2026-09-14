import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_calorimetry import (
    DEFAULT_MASS1_KG,
    DEFAULT_MASS2_KG,
    DEFAULT_SPECIFIC_HEAT1,
    DEFAULT_SPECIFIC_HEAT2,
    DEFAULT_TEMP1_C,
    DEFAULT_TEMP2_C,
    MAX_MASS_KG,
    MAX_SPECIFIC_HEAT,
    MAX_TEMP_C,
    MIN_MASS_KG,
    MIN_SPECIFIC_HEAT,
    MIN_TEMP_C,
    SimulationError,
    calorimetry_state,
    clamp_mass,
    clamp_specific_heat,
    clamp_temp,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _calorimetry_concept():
    return PhysicsConcept.objects.create(
        name="Specific heat capacity and calorimetry",
        description=(
            "Specific heat capacity is the energy needed to raise the "
            "temperature of one kilogram of a substance by one degree. "
            "Calorimetry uses conservation of energy to relate the heat "
            "lost by a warmer substance to the heat gained by a cooler one."
        ),
        topic="Thermal Physics",
        equations=["Q = m c delta T"],
        si_units=["J/(kg K)"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _calorimetry_concept(),
        title="Calorimetry Lab",
        simulation_type=PhysicsSimulation.SimulationType.CALORIMETRY,
        description="Explore conservation of energy when mixing two substances.",
    )


# --- DOMAIN -----------------------------------------------------------------


class CalorimetrySimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_calorimetry_concept(self):
        concept = _calorimetry_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.CALORIMETRY,
        )

    def test_seed_simulations_creates_calorimetry_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="calorimetry").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="calorimetry")
        self.assertEqual(sim.simulation_type, "calorimetry")
        self.assertEqual(sim.concept.name, "Specific heat capacity and calorimetry")

    def test_seed_simulations_is_idempotent_for_calorimetry(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="calorimetry").count(), 1
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
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class CalorimetryMathTests(TestCase):
    def test_equal_heat_capacities_give_the_simple_average(self):
        state = calorimetry_state(
            mass1=1, specific_heat1=4186, temp1=80,
            mass2=1, specific_heat2=4186, temp2=20,
        )
        self.assertAlmostEqual(state["equilibrium_temp_c"], 50.0, places=6)

    def test_heat_lost_by_the_warmer_substance_equals_heat_gained_by_the_cooler(self):
        state = calorimetry_state(
            mass1=0.5, specific_heat1=4186, temp1=20,
            mass2=0.2, specific_heat2=900, temp2=100,
        )
        heat_lost_by_2 = abs(
            state["heat_capacity2_j_per_k"] * (state["temp2_c"] - state["equilibrium_temp_c"])
        )
        heat_gained_by_1 = abs(
            state["heat_capacity1_j_per_k"] * (state["equilibrium_temp_c"] - state["temp1_c"])
        )
        self.assertAlmostEqual(heat_lost_by_2, heat_gained_by_1, places=4)
        self.assertAlmostEqual(state["heat_transferred_j"], heat_gained_by_1, places=4)

    def test_equilibrium_temperature_is_always_between_the_two_starting_temperatures(self):
        for t1, t2 in ((20, 100), (100, 20), (-10, 50), (0, 0)):
            state = calorimetry_state(
                mass1=0.3, specific_heat1=2000, temp1=t1,
                mass2=0.7, specific_heat2=1000, temp2=t2,
            )
            lo, hi = min(t1, t2), max(t1, t2)
            self.assertGreaterEqual(state["equilibrium_temp_c"], lo - 1e-6)
            self.assertLessEqual(state["equilibrium_temp_c"], hi + 1e-6)

    def test_larger_heat_capacity_pulls_equilibrium_closer_to_its_own_temperature(self):
        # A big water bath (large heat capacity) barely changes temperature
        # when a small hot metal sample is dropped in.
        state = calorimetry_state(
            mass1=10, specific_heat1=4186, temp1=20,
            mass2=0.05, specific_heat2=900, temp2=200,
        )
        self.assertLess(abs(state["equilibrium_temp_c"] - 20), 5.0)

    def test_result_is_symmetric_regardless_of_which_substance_is_first(self):
        forward = calorimetry_state(
            mass1=0.4, specific_heat1=1500, temp1=10,
            mass2=0.6, specific_heat2=2500, temp2=90,
        )
        swapped = calorimetry_state(
            mass1=0.6, specific_heat1=2500, temp1=90,
            mass2=0.4, specific_heat2=1500, temp2=10,
        )
        self.assertAlmostEqual(
            forward["equilibrium_temp_c"], swapped["equilibrium_temp_c"], places=6
        )

    def test_multiple_parameter_sets_are_deterministic(self):
        for args in (
            dict(mass1=1, specific_heat1=4186, temp1=20, mass2=1, specific_heat2=4186, temp2=80),
            dict(mass1=2, specific_heat1=900, temp1=150, mass2=0.5, specific_heat2=4186, temp2=15),
        ):
            first = calorimetry_state(**args)
            second = calorimetry_state(**args)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_mass(999), MAX_MASS_KG)
        self.assertEqual(clamp_mass(0.0001), MIN_MASS_KG)
        self.assertEqual(clamp_specific_heat(99999), MAX_SPECIFIC_HEAT)
        self.assertEqual(clamp_specific_heat(1), MIN_SPECIFIC_HEAT)
        self.assertEqual(clamp_temp(9999), MAX_TEMP_C)
        self.assertEqual(clamp_temp(-9999), MIN_TEMP_C)

    def test_negative_temperature_is_not_rejected(self):
        # Celsius -- negative is a normal, valid temperature.
        self.assertEqual(clamp_temp(-10), -10.0)

    def test_non_positive_mass_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(0)
        with self.assertRaises(SimulationError):
            clamp_mass(-1)

    def test_non_positive_specific_heat_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_specific_heat(0)
        with self.assertRaises(SimulationError):
            clamp_specific_heat(-100)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass("heavy")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(math.nan)
        with self.assertRaises(SimulationError):
            clamp_temp(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = calorimetry_state(
            mass1=DEFAULT_MASS1_KG, specific_heat1=DEFAULT_SPECIFIC_HEAT1, temp1=DEFAULT_TEMP1_C,
            mass2=DEFAULT_MASS2_KG, specific_heat2=DEFAULT_SPECIFIC_HEAT2, temp2=DEFAULT_TEMP2_C,
        )
        self.assertGreater(state["equilibrium_temp_c"], DEFAULT_TEMP1_C)
        self.assertLess(state["equilibrium_temp_c"], DEFAULT_TEMP2_C)


class JsCalorimetryConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "calorimetry.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "calorimetry.js").read_text(encoding="utf-8")
        self.assertIn("heatCapacity1 * t1 + heatCapacity2 * t2", source)
        for bound in ("0.01", "10.0", "100.0", "4200.0", "-20.0", "300.0"):
            self.assertIn(bound, source)
        self.assertIn('register("calorimetry"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class CalorimetryLabViewTests(TestCase):
    def setUp(self):
        self.concept = _calorimetry_concept()
        self.simulation = _make_simulation(self.concept)

    def test_calorimetry_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calorimetry Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/calorimetry.js")

    def test_calorimetry_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-mass1")
        self.assertContains(response, "data-input-specific-heat1")
        self.assertContains(response, "data-input-temp1")
        self.assertContains(response, "data-input-mass2")
        self.assertContains(response, "data-input-specific-heat2")
        self.assertContains(response, "data-input-temp2")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_calorimetry(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_calorimetry_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_calorimetry(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Calorimetry Lab", body)


class CalorimetryExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _calorimetry_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "They met in the middle.", "mass1_kg": "1", "specific_heat1": "4186",
                "temp1_c": "80", "mass2_kg": "1", "specific_heat2": "4186", "temp2_c": "20",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["equilibrium_temp_c"], 50.0, places=2)

    def test_browser_submitted_equilibrium_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "mass1_kg": "1", "specific_heat1": "4186",
                "temp1_c": "80", "mass2_kg": "1", "specific_heat2": "4186", "temp2_c": "20",
                "equilibrium_temp_c": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["equilibrium_temp_c"], 50.0, places=2)

    def test_observe_endpoint_rejects_non_positive_mass_or_specific_heat(self):
        cases = (
            {"mass1_kg": "0"}, {"specific_heat1": "0"},
            {"mass2_kg": "-1"}, {"specific_heat2": "-100"},
        )
        base = {
            "observation": "x", "mass1_kg": "1", "specific_heat1": "4186",
            "temp1_c": "80", "mass2_kg": "1", "specific_heat2": "4186", "temp2_c": "20",
        }
        for override in cases:
            payload = dict(base, **override)
            response = self.client.post(self.observe_url, payload)
            self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_accepts_negative_temperature(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "mass1_kg": "1", "specific_heat1": "4186",
                "temp1_c": "-10", "mass2_kg": "1", "specific_heat2": "4186", "temp2_c": "20",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_csrf_is_enforced(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.post(
            reverse("physics_lab:experiment_predict", args=[self.simulation.slug]),
            {"prediction": "x"},
        )
        self.assertEqual(response.status_code, 403)


class CalorimetryTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _calorimetry_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Mixing It Up", topic="Thermal Physics", grade_level="10",
            duration_minutes=45,
            learning_objectives=["Relate heat capacity to equilibrium temperature."],
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
            observation="x", mass1_kg=1, specific_heat1=4186, temp1_c=80,
            mass2_kg=1, specific_heat2=4186, temp2_c=20,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "calorimetry")
        self.assertEqual(ctx.mass1_kg, 1.0)
        self.assertAlmostEqual(ctx.equilibrium_temp_c, 50.0, places=2)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("substance 1: mass = 1.00 kg", prompt.user)
        self.assertIn("equilibrium temperature", prompt.user)


# --- accessibility -------------------------------------------------------


class CalorimetryAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _calorimetry_concept()
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
        self.assertIn('<label for="lab-mass1">', self.body)
        self.assertIn('<label for="lab-heat1">', self.body)
        self.assertIn('<label for="lab-temp1">', self.body)
        self.assertIn('<label for="lab-mass2">', self.body)
        self.assertIn('<label for="lab-heat2">', self.body)
        self.assertIn('<label for="lab-temp2">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class CalorimetryXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _calorimetry_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Mixing It Up", topic="Thermal Physics", grade_level="10",
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
