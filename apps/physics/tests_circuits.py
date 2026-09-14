import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_circuits import (
    DEFAULT_RESISTANCE1_OHM,
    DEFAULT_RESISTANCE2_OHM,
    DEFAULT_SERIES,
    DEFAULT_VOLTAGE_V,
    MAX_RESISTANCE_OHM,
    MAX_VOLTAGE_V,
    MIN_RESISTANCE_OHM,
    MIN_VOLTAGE_V,
    SimulationError,
    circuit_state,
    clamp_resistance,
    clamp_series,
    clamp_voltage,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _circuit_concept():
    return PhysicsConcept.objects.create(
        name="Series and parallel circuits",
        description=(
            "In a series circuit, components share the same current but "
            "divide the total voltage; resistances add directly. In a "
            "parallel circuit, components share the same voltage but "
            "divide the total current; the combined resistance is always "
            "less than the smallest individual resistor."
        ),
        topic="Circuits",
        equations=["R_series = R1 + R2 + ...", "1/R_parallel = 1/R1 + 1/R2 + ..."],
        si_units=["ohm"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _circuit_concept(),
        title="Series and Parallel Circuits Lab",
        simulation_type=PhysicsSimulation.SimulationType.SERIES_PARALLEL_CIRCUIT,
        description="Explore I = V / R in series and parallel resistor circuits.",
    )


# --- DOMAIN -----------------------------------------------------------------


class CircuitSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_circuit_concept(self):
        concept = _circuit_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.SERIES_PARALLEL_CIRCUIT,
        )

    def test_seed_simulations_creates_circuit_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="series-parallel-circuit").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="series-parallel-circuit")
        self.assertEqual(sim.simulation_type, "series_parallel_circuit")
        self.assertEqual(sim.concept.name, "Series and parallel circuits")

    def test_seed_simulations_is_idempotent_for_circuit(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="series-parallel-circuit").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class CircuitMathTests(TestCase):
    def test_series_worked_example(self):
        state = circuit_state(voltage=12, resistance1=10, resistance2=20, series=1)
        self.assertAlmostEqual(state["total_resistance_ohm"], 30.0, places=6)
        self.assertAlmostEqual(state["total_current_a"], 0.4, places=6)
        self.assertAlmostEqual(state["current_1_a"], 0.4, places=6)
        self.assertAlmostEqual(state["current_2_a"], 0.4, places=6)
        self.assertAlmostEqual(state["voltage_1_v"], 4.0, places=6)
        self.assertAlmostEqual(state["voltage_2_v"], 8.0, places=6)

    def test_parallel_worked_example(self):
        state = circuit_state(voltage=12, resistance1=10, resistance2=20, series=0)
        expected_total_r = (10 * 20) / (10 + 20)
        self.assertAlmostEqual(state["total_resistance_ohm"], expected_total_r, places=6)
        self.assertAlmostEqual(state["voltage_1_v"], 12.0, places=6)
        self.assertAlmostEqual(state["voltage_2_v"], 12.0, places=6)
        self.assertAlmostEqual(state["current_1_a"], 1.2, places=6)
        self.assertAlmostEqual(state["current_2_a"], 0.6, places=6)
        self.assertAlmostEqual(state["total_current_a"], 1.8, places=6)

    def test_series_current_is_the_same_through_both_resistors(self):
        for r1, r2 in ((5, 15), (1, 100), (50, 50)):
            state = circuit_state(voltage=9, resistance1=r1, resistance2=r2, series=1)
            self.assertAlmostEqual(state["current_1_a"], state["current_2_a"], places=6)

    def test_parallel_voltage_is_the_same_across_both_resistors(self):
        for r1, r2 in ((5, 15), (1, 100), (50, 50)):
            state = circuit_state(voltage=9, resistance1=r1, resistance2=r2, series=0)
            self.assertAlmostEqual(state["voltage_1_v"], state["voltage_2_v"], places=6)

    def test_parallel_resistance_is_always_less_than_the_smallest_resistor(self):
        # The exact misconception this lab targets (see the seeded concept's
        # own description): parallel combined resistance is always LESS than
        # even the smaller of the two individual resistors.
        for r1, r2 in ((5, 15), (1, 100), (50, 50), (2, 3)):
            state = circuit_state(voltage=9, resistance1=r1, resistance2=r2, series=0)
            self.assertLess(state["parallel_total_resistance_ohm"], min(r1, r2))

    def test_series_resistance_is_always_greater_than_either_resistor(self):
        for r1, r2 in ((5, 15), (1, 100), (50, 50)):
            state = circuit_state(voltage=9, resistance1=r1, resistance2=r2, series=1)
            self.assertGreater(state["series_total_resistance_ohm"], max(r1, r2))

    def test_power_is_conserved_in_both_modes(self):
        for series_flag in (1, 0):
            state = circuit_state(voltage=12, resistance1=10, resistance2=20, series=series_flag)
            expected_total_power = state["voltage_v"] * state["total_current_a"]
            self.assertAlmostEqual(state["total_power_w"], expected_total_power, places=6)
            self.assertAlmostEqual(
                state["total_power_w"], state["power_1_w"] + state["power_2_w"], places=6
            )

    def test_both_total_resistances_are_always_reported_for_comparison(self):
        # series_total_resistance_ohm / parallel_total_resistance_ohm are
        # always both present, regardless of which mode is active -- the
        # comparison bar chart needs both.
        series_mode = circuit_state(voltage=9, resistance1=10, resistance2=20, series=1)
        parallel_mode = circuit_state(voltage=9, resistance1=10, resistance2=20, series=0)
        self.assertAlmostEqual(
            series_mode["series_total_resistance_ohm"],
            parallel_mode["series_total_resistance_ohm"],
            places=6,
        )
        self.assertAlmostEqual(
            series_mode["parallel_total_resistance_ohm"],
            parallel_mode["parallel_total_resistance_ohm"],
            places=6,
        )

    def test_multiple_parameter_sets_are_deterministic(self):
        for v, r1, r2, series in ((5, 2, 4, 1), (20, 50, 75, 0), (12, 10, 20, 1)):
            first = circuit_state(voltage=v, resistance1=r1, resistance2=r2, series=series)
            second = circuit_state(voltage=v, resistance1=r1, resistance2=r2, series=series)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_voltage(999), MAX_VOLTAGE_V)
        self.assertEqual(clamp_voltage(0.001), MIN_VOLTAGE_V)
        self.assertEqual(clamp_resistance(999999), MAX_RESISTANCE_OHM)
        self.assertEqual(clamp_resistance(0.001), MIN_RESISTANCE_OHM)

    def test_series_flag_rounds_to_zero_or_one(self):
        self.assertEqual(clamp_series(1), 1.0)
        self.assertEqual(clamp_series(0.9), 1.0)
        self.assertEqual(clamp_series(0.4), 0.0)
        self.assertEqual(clamp_series(0), 0.0)

    def test_non_positive_voltage_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_voltage(0)
        with self.assertRaises(SimulationError):
            clamp_voltage(-5)

    def test_non_positive_resistance_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_resistance(0)
        with self.assertRaises(SimulationError):
            clamp_resistance(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_voltage("bright")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_voltage(math.nan)
        with self.assertRaises(SimulationError):
            clamp_resistance(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = circuit_state(
            voltage=DEFAULT_VOLTAGE_V,
            resistance1=DEFAULT_RESISTANCE1_OHM,
            resistance2=DEFAULT_RESISTANCE2_OHM,
            series=DEFAULT_SERIES,
        )
        self.assertGreater(state["total_current_a"], 0)
        self.assertAlmostEqual(
            state["total_power_w"], state["power_1_w"] + state["power_2_w"], places=6
        )


class JsCircuitConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "circuits.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "circuits.js").read_text(encoding="utf-8")
        self.assertIn("ra + rb", source)
        self.assertIn("(ra * rb) / (ra + rb)", source)
        for bound in ("1.0", "24.0", "100.0"):
            self.assertIn(bound, source)
        self.assertIn('register("series_parallel_circuit"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class CircuitLabViewTests(TestCase):
    def setUp(self):
        self.concept = _circuit_concept()
        self.simulation = _make_simulation(self.concept)

    def test_circuit_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Series and Parallel Circuits Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/circuits.js")

    def test_circuit_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-voltage")
        self.assertContains(response, "data-input-r1")
        self.assertContains(response, "data-input-r2")
        self.assertContains(response, "data-input-series")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_circuit(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_circuit_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_circuit(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Series and Parallel Circuits Lab", body)


class CircuitExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _circuit_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Same current through both.", "voltage_v": "12",
                "resistance1_ohm": "10", "resistance2_ohm": "20", "series": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_current_a"], 0.4, places=4)
        self.assertAlmostEqual(data["voltage_1_v"], 4.0, places=4)

    def test_browser_submitted_current_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "voltage_v": "12", "resistance1_ohm": "10",
                "resistance2_ohm": "20", "series": "1", "total_current_a": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_current_a"], 0.4, places=4)

    def test_observe_endpoint_switches_topology_via_series_flag(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Same voltage across both.", "voltage_v": "12",
                "resistance1_ohm": "10", "resistance2_ohm": "20", "series": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["voltage_1_v"], 12.0, places=4)
        self.assertAlmostEqual(data["voltage_2_v"], 12.0, places=4)

    def test_observe_endpoint_rejects_non_positive_voltage_or_resistance(self):
        for voltage, r1, r2 in (("0", "10", "20"), ("12", "0", "20"), ("-5", "10", "20")):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "voltage_v": voltage, "resistance1_ohm": r1,
                    "resistance2_ohm": r2, "series": "1",
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


class CircuitTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _circuit_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Wiring It Up", topic="Circuits", grade_level="10",
            duration_minutes=45,
            learning_objectives=["Compare current and voltage in series versus parallel circuits."],
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
            observation="x", voltage_v=12, resistance1_ohm=10, resistance2_ohm=20, series=1,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "series_parallel_circuit")
        self.assertEqual(ctx.voltage_v, 12.0)
        self.assertTrue(ctx.is_series)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("source voltage = 12.00 V", prompt.user)
        self.assertIn("wired in series", prompt.user)


# --- accessibility -------------------------------------------------------


class CircuitAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _circuit_concept()
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
        self.assertIn('<label for="lab-voltage">', self.body)
        self.assertIn('<label for="lab-r1">', self.body)
        self.assertIn('<label for="lab-r2">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_radio_choice_has_a_legend(self):
        self.assertIn("<legend>Circuit type</legend>", self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class CircuitXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _circuit_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Wiring It Up", topic="Circuits", grade_level="10",
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
