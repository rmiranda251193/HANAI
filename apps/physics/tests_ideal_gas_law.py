import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_ideal_gas_law import (
    DEFAULT_MOLES,
    DEFAULT_TEMPERATURE_K,
    DEFAULT_VOLUME_M3,
    GAS_CONSTANT_J_PER_MOL_K,
    MAX_MOLES,
    MAX_TEMPERATURE_K,
    MAX_VOLUME_M3,
    MIN_MOLES,
    MIN_TEMPERATURE_K,
    MIN_VOLUME_M3,
    SimulationError,
    clamp_moles,
    clamp_temperature,
    clamp_volume,
    ideal_gas_law_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _gas_law_concept():
    return PhysicsConcept.objects.create(
        name="The ideal gas law",
        description=(
            "The ideal gas law relates the pressure, volume, amount and "
            "absolute temperature of a gas that behaves ideally (particles "
            "with negligible volume and no intermolecular forces)."
        ),
        topic="Gas Laws",
        equations=["P V = n R T"],
        si_units=["Pa", "m^3", "mol", "K"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _gas_law_concept(),
        title="The Ideal Gas Law Lab",
        simulation_type=PhysicsSimulation.SimulationType.IDEAL_GAS_LAW,
        description="Explore P V = n R T.",
    )


# --- DOMAIN -----------------------------------------------------------------


class IdealGasLawSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_gas_law_concept(self):
        concept = _gas_law_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.IDEAL_GAS_LAW,
        )

    def test_seed_simulations_creates_ideal_gas_law_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="ideal-gas-law").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="ideal-gas-law")
        self.assertEqual(sim.simulation_type, "ideal_gas_law")
        self.assertEqual(sim.concept.name, "The ideal gas law")

    def test_seed_simulations_is_idempotent_for_ideal_gas_law(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="ideal-gas-law").count(), 1
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
            "calorimetry",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class IdealGasLawMathTests(TestCase):
    def test_worked_example_lands_near_one_atmosphere(self):
        state = ideal_gas_law_state(moles=1, temperature=298, volume=0.0245)
        expected = (1 * GAS_CONSTANT_J_PER_MOL_K * 298) / 0.0245
        self.assertAlmostEqual(state["pressure_pa"], expected, places=4)
        # A real-world sanity check: this should land close to 1 atm.
        self.assertAlmostEqual(state["pressure_pa"], 101325, delta=2000)

    def test_boyles_law_halving_volume_doubles_pressure(self):
        full = ideal_gas_law_state(moles=1, temperature=300, volume=0.02)
        half = ideal_gas_law_state(moles=1, temperature=300, volume=0.01)
        self.assertAlmostEqual(half["pressure_pa"], full["pressure_pa"] * 2, places=4)

    def test_gay_lussacs_law_doubling_temperature_doubles_pressure(self):
        cool = ideal_gas_law_state(moles=1, temperature=300, volume=0.02)
        hot = ideal_gas_law_state(moles=1, temperature=600, volume=0.02)
        self.assertAlmostEqual(hot["pressure_pa"], cool["pressure_pa"] * 2, places=4)

    def test_avogadros_law_doubling_amount_doubles_pressure(self):
        one_mole = ideal_gas_law_state(moles=1, temperature=300, volume=0.02)
        two_moles = ideal_gas_law_state(moles=2, temperature=300, volume=0.02)
        self.assertAlmostEqual(two_moles["pressure_pa"], one_mole["pressure_pa"] * 2, places=4)

    def test_pv_over_nt_is_constant_across_different_states(self):
        # The most direct statement of the ideal gas law itself: PV/(nT)
        # always equals R, regardless of which state you're in.
        for n, t, v in ((1, 300, 0.02), (3, 450, 0.1), (0.5, 150, 0.005)):
            state = ideal_gas_law_state(moles=n, temperature=t, volume=v)
            self.assertAlmostEqual(
                (state["pressure_pa"] * state["volume_m3"])
                / (state["moles"] * state["temperature_k"]),
                GAS_CONSTANT_J_PER_MOL_K,
                places=6,
            )

    def test_multiple_parameter_sets_are_deterministic(self):
        for n, t, v in ((1, 298, 0.0245), (5, 500, 0.3), (0.2, 150, 0.01)):
            first = ideal_gas_law_state(moles=n, temperature=t, volume=v)
            second = ideal_gas_law_state(moles=n, temperature=t, volume=v)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_moles(999), MAX_MOLES)
        self.assertEqual(clamp_moles(0.001), MIN_MOLES)
        self.assertEqual(clamp_temperature(99999), MAX_TEMPERATURE_K)
        self.assertEqual(clamp_temperature(1), MIN_TEMPERATURE_K)
        self.assertEqual(clamp_volume(999), MAX_VOLUME_M3)
        self.assertEqual(clamp_volume(0.00001), MIN_VOLUME_M3)

    def test_non_positive_moles_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_moles(0)
        with self.assertRaises(SimulationError):
            clamp_moles(-1)

    def test_non_positive_temperature_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_temperature(0)
        with self.assertRaises(SimulationError):
            clamp_temperature(-10)

    def test_non_positive_volume_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_volume(0)
        with self.assertRaises(SimulationError):
            clamp_volume(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_moles("lots")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_moles(math.nan)
        with self.assertRaises(SimulationError):
            clamp_temperature(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = ideal_gas_law_state(
            moles=DEFAULT_MOLES, temperature=DEFAULT_TEMPERATURE_K, volume=DEFAULT_VOLUME_M3
        )
        self.assertGreater(state["pressure_pa"], 0)
        self.assertAlmostEqual(state["pressure_pa"], 101325, delta=2000)


class JsIdealGasLawConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "ideal-gas-law.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "ideal-gas-law.js").read_text(encoding="utf-8")
        self.assertIn("8.314", source)
        self.assertIn("(n * GAS_CONSTANT * t) / v", source)
        for bound in ("0.1", "10.0", "100.0", "1000.0", "0.001", "1.0"):
            self.assertIn(bound, source)
        self.assertIn('register("ideal_gas_law"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class IdealGasLawLabViewTests(TestCase):
    def setUp(self):
        self.concept = _gas_law_concept()
        self.simulation = _make_simulation(self.concept)

    def test_ideal_gas_law_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Ideal Gas Law Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/ideal-gas-law.js")

    def test_ideal_gas_law_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-moles")
        self.assertContains(response, "data-input-temperature")
        self.assertContains(response, "data-input-volume")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_ideal_gas_law(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_ideal_gas_law_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_ideal_gas_law(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("The Ideal Gas Law Lab", body)


class IdealGasLawExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _gas_law_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "Pressure went up.", "moles": "1", "temperature_k": "300", "volume_m3": "0.02"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = (1 * GAS_CONSTANT_J_PER_MOL_K * 300) / 0.02
        self.assertAlmostEqual(data["pressure_pa"], expected, places=2)

    def test_browser_submitted_pressure_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "moles": "1", "temperature_k": "300",
                "volume_m3": "0.02", "pressure_pa": "999999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = (1 * GAS_CONSTANT_J_PER_MOL_K * 300) / 0.02
        self.assertAlmostEqual(data["pressure_pa"], expected, places=2)

    def test_observe_endpoint_rejects_non_positive_moles_temperature_or_volume(self):
        base = {"observation": "x", "moles": "1", "temperature_k": "300", "volume_m3": "0.02"}
        for override in ({"moles": "0"}, {"temperature_k": "0"}, {"volume_m3": "0"}):
            payload = dict(base, **override)
            response = self.client.post(self.observe_url, payload)
            self.assertEqual(response.status_code, 400)

    def test_csrf_is_enforced(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.post(
            reverse("physics_lab:experiment_predict", args=[self.simulation.slug]),
            {"prediction": "x"},
        )
        self.assertEqual(response.status_code, 403)


class IdealGasLawTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _gas_law_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Squeeze and Heat", topic="Gas Laws", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate pressure, volume, amount and temperature for an ideal gas."],
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
            observation="x", moles=1, temperature_k=300, volume_m3=0.02,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "ideal_gas_law")
        self.assertEqual(ctx.moles, 1.0)
        self.assertGreater(ctx.pressure_pa, 0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("amount of gas = 1.00 mol", prompt.user)
        self.assertIn("P = nRT/V", prompt.user)


# --- accessibility -------------------------------------------------------


class IdealGasLawAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _gas_law_concept()
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
        self.assertIn('<label for="lab-moles">', self.body)
        self.assertIn('<label for="lab-temperature">', self.body)
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


class IdealGasLawXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _gas_law_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Squeeze and Heat", topic="Gas Laws", grade_level="11",
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
