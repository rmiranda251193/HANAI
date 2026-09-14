import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_time_dilation import (
    DEFAULT_PROPER_LENGTH_M,
    DEFAULT_PROPER_TIME_S,
    DEFAULT_VELOCITY_FRACTION_C,
    MAX_PROPER_LENGTH_M,
    MAX_PROPER_TIME_S,
    MAX_VELOCITY_FRACTION_C,
    MIN_PROPER_LENGTH_M,
    MIN_PROPER_TIME_S,
    MIN_VELOCITY_FRACTION_C,
    SimulationError,
    clamp_proper_length,
    clamp_proper_time,
    clamp_velocity_fraction,
    time_dilation_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _time_dilation_concept():
    return PhysicsConcept.objects.create(
        name="Time dilation",
        description=(
            "A clock moving relative to an observer runs slower, as "
            "measured by that observer, than an identical clock at rest "
            "relative to them. The effect becomes significant only as "
            "relative speed approaches the speed of light."
        ),
        topic="Special Relativity",
        equations=["delta t = delta t0 / sqrt(1 - v^2/c^2)"],
        si_units=["s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _time_dilation_concept(),
        title="Time Dilation and Length Contraction Lab",
        simulation_type=PhysicsSimulation.SimulationType.TIME_DILATION,
        description="Explore gamma = 1 / sqrt(1 - v^2/c^2).",
    )


# --- DOMAIN -----------------------------------------------------------------


class TimeDilationSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_time_dilation_concept(self):
        concept = _time_dilation_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.TIME_DILATION,
        )

    def test_seed_simulations_creates_time_dilation_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="time-dilation").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="time-dilation")
        self.assertEqual(sim.simulation_type, "time_dilation")
        self.assertEqual(sim.concept.name, "Time dilation")

    def test_seed_simulations_is_idempotent_for_time_dilation(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="time-dilation").count(), 1
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
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class TimeDilationMathTests(TestCase):
    def test_at_rest_there_is_no_relativistic_effect(self):
        state = time_dilation_state(velocity_fraction_c=0, proper_time=10, proper_length=100)
        self.assertAlmostEqual(state["lorentz_factor"], 1.0, places=8)
        self.assertAlmostEqual(state["dilated_time_s"], 10.0, places=6)
        self.assertAlmostEqual(state["contracted_length_m"], 100.0, places=6)

    def test_classic_worked_example_beta_0_6_gives_gamma_1_25(self):
        state = time_dilation_state(velocity_fraction_c=0.6, proper_time=10, proper_length=100)
        self.assertAlmostEqual(state["lorentz_factor"], 1.25, places=6)
        self.assertAlmostEqual(state["dilated_time_s"], 12.5, places=6)
        self.assertAlmostEqual(state["contracted_length_m"], 80.0, places=6)

    def test_gamma_is_always_at_least_one(self):
        for beta in (0, 0.1, 0.5, 0.9, 0.99):
            state = time_dilation_state(velocity_fraction_c=beta, proper_time=10, proper_length=100)
            self.assertGreaterEqual(state["lorentz_factor"], 1.0)

    def test_dilated_time_never_shorter_than_proper_time(self):
        for beta in (0.1, 0.5, 0.9):
            state = time_dilation_state(velocity_fraction_c=beta, proper_time=10, proper_length=100)
            self.assertGreaterEqual(state["dilated_time_s"], state["proper_time_s"])

    def test_contracted_length_never_longer_than_proper_length(self):
        for beta in (0.1, 0.5, 0.9):
            state = time_dilation_state(velocity_fraction_c=beta, proper_time=10, proper_length=100)
            self.assertLessEqual(state["contracted_length_m"], state["proper_length_m"])

    def test_both_effects_scale_by_the_same_gamma(self):
        state = time_dilation_state(velocity_fraction_c=0.8, proper_time=5, proper_length=50)
        time_ratio = state["dilated_time_s"] / state["proper_time_s"]
        length_ratio = state["proper_length_m"] / state["contracted_length_m"]
        self.assertAlmostEqual(time_ratio, state["lorentz_factor"], places=6)
        self.assertAlmostEqual(length_ratio, state["lorentz_factor"], places=6)

    def test_gamma_increases_monotonically_with_velocity(self):
        previous = None
        for beta in (0, 0.2, 0.4, 0.6, 0.8, 0.95):
            state = time_dilation_state(velocity_fraction_c=beta, proper_time=10, proper_length=100)
            if previous is not None:
                self.assertGreater(state["lorentz_factor"], previous)
            previous = state["lorentz_factor"]

    def test_multiple_parameter_sets_are_deterministic(self):
        for beta, t0, l0 in ((0.6, 10, 100), (0.2, 5, 50), (0.9, 1, 1000)):
            first = time_dilation_state(velocity_fraction_c=beta, proper_time=t0, proper_length=l0)
            second = time_dilation_state(velocity_fraction_c=beta, proper_time=t0, proper_length=l0)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_velocity_fraction(0.999999), MAX_VELOCITY_FRACTION_C)
        self.assertEqual(clamp_proper_time(999), MAX_PROPER_TIME_S)
        self.assertEqual(clamp_proper_time(0.0001), MIN_PROPER_TIME_S)
        self.assertEqual(clamp_proper_length(9999), MAX_PROPER_LENGTH_M)
        self.assertEqual(clamp_proper_length(0.0001), MIN_PROPER_LENGTH_M)

    def test_negative_velocity_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_velocity_fraction(-0.1)

    def test_reaching_or_exceeding_light_speed_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_velocity_fraction(1.0)
        with self.assertRaises(SimulationError):
            clamp_velocity_fraction(1.5)

    def test_non_positive_proper_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_proper_time(0)
        with self.assertRaises(SimulationError):
            clamp_proper_time(-1)

    def test_non_positive_proper_length_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_proper_length(0)
        with self.assertRaises(SimulationError):
            clamp_proper_length(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_velocity_fraction("fast")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_velocity_fraction(math.nan)
        with self.assertRaises(SimulationError):
            clamp_proper_time(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = time_dilation_state(
            velocity_fraction_c=DEFAULT_VELOCITY_FRACTION_C,
            proper_time=DEFAULT_PROPER_TIME_S,
            proper_length=DEFAULT_PROPER_LENGTH_M,
        )
        self.assertAlmostEqual(state["lorentz_factor"], 1.25, places=6)


class JsTimeDilationConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "time-dilation.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "time-dilation.js").read_text(encoding="utf-8")
        self.assertIn("1 / Math.sqrt(1 - beta * beta)", source)
        for bound in ("0.99", "0.1", "100.0", "1000.0"):
            self.assertIn(bound, source)
        self.assertIn('register("time_dilation"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class TimeDilationLabViewTests(TestCase):
    def setUp(self):
        self.concept = _time_dilation_concept()
        self.simulation = _make_simulation(self.concept)

    def test_time_dilation_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Time Dilation and Length Contraction Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/time-dilation.js")

    def test_time_dilation_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-beta")
        self.assertContains(response, "data-input-proper-time")
        self.assertContains(response, "data-input-proper-length")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_time_dilation(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_time_dilation_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_time_dilation(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Time Dilation and Length Contraction Lab", body)


class TimeDilationExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _time_dilation_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Gamma was 1.25.", "velocity_fraction_c": "0.6",
                "proper_time_s": "10", "proper_length_m": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["lorentz_factor"], 1.25, places=3)

    def test_browser_submitted_lorentz_factor_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "velocity_fraction_c": "0.6",
                "proper_time_s": "10", "proper_length_m": "100",
                "lorentz_factor": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["lorentz_factor"], 1.25, places=3)

    def test_observe_endpoint_rejects_light_speed_or_beyond(self):
        for bad_beta in ("1.0", "1.2"):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "velocity_fraction_c": bad_beta,
                    "proper_time_s": "10", "proper_length_m": "100",
                },
            )
            self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_positive_proper_time_or_length(self):
        base = {
            "observation": "x", "velocity_fraction_c": "0.6",
            "proper_time_s": "10", "proper_length_m": "100",
        }
        for override in ({"proper_time_s": "0"}, {"proper_length_m": "0"}):
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


class TimeDilationTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _time_dilation_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Near Light Speed", topic="Special Relativity", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate relative velocity to time dilation and length contraction."],
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
            observation="x", velocity_fraction_c=0.6, proper_time_s=10, proper_length_m=100,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "time_dilation")
        self.assertAlmostEqual(ctx.velocity_fraction_c, 0.6, places=2)
        self.assertAlmostEqual(ctx.lorentz_factor, 1.25, places=3)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("relative velocity = 0.60c", prompt.user)
        self.assertIn("Lorentz factor", prompt.user)


# --- accessibility -------------------------------------------------------


class TimeDilationAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _time_dilation_concept()
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
        self.assertIn('<label for="lab-beta">', self.body)
        self.assertIn('<label for="lab-proper-time">', self.body)
        self.assertIn('<label for="lab-proper-length">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class TimeDilationXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _time_dilation_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Near Light Speed", topic="Special Relativity", grade_level="12",
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
