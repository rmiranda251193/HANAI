import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_bohr_model import (
    DEFAULT_FINAL_LEVEL,
    DEFAULT_INITIAL_LEVEL,
    HC_EV_NM,
    MAX_LEVEL,
    MIN_LEVEL,
    RYDBERG_ENERGY_EV,
    SimulationError,
    bohr_model_state,
    clamp_level,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _bohr_concept():
    return PhysicsConcept.objects.create(
        name="The Bohr model of the atom",
        description=(
            "The Bohr model pictures electrons orbiting the nucleus only "
            "in specific, quantised energy levels. An electron can jump "
            "between levels by absorbing or emitting a photon whose "
            "energy exactly matches the gap between them."
        ),
        topic="Atomic Structure",
        equations=["delta E = h f"],
        si_units=["J"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _bohr_concept(),
        title="The Bohr Model Lab",
        simulation_type=PhysicsSimulation.SimulationType.BOHR_MODEL,
        description="Explore E_n = -13.6 eV / n^2.",
    )


# --- DOMAIN -----------------------------------------------------------------


class BohrModelSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_bohr_concept(self):
        concept = _bohr_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type, PhysicsSimulation.SimulationType.BOHR_MODEL
        )

    def test_seed_simulations_creates_bohr_model_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="bohr-model").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="bohr-model")
        self.assertEqual(sim.simulation_type, "bohr_model")
        self.assertEqual(sim.concept.name, "The Bohr model of the atom")

    def test_seed_simulations_is_idempotent_for_bohr_model(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="bohr-model").count(), 1
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
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class BohrModelMathTests(TestCase):
    def test_worked_example_matches_the_real_h_alpha_line(self):
        # The default state is the real Balmer-series H-alpha line.
        state = bohr_model_state(initial_level=3, final_level=2)
        self.assertAlmostEqual(state["photon_energy_ev"], 13.6 * (1 / 4 - 1 / 9), places=6)
        self.assertAlmostEqual(state["wavelength_nm"], 656.3, places=0)
        self.assertTrue(state["has_transition"])
        self.assertFalse(state["is_absorption"])

    def test_energy_levels_match_the_closed_form(self):
        state = bohr_model_state(initial_level=2, final_level=1)
        self.assertAlmostEqual(state["energy_initial_ev"], -RYDBERG_ENERGY_EV / 4, places=6)
        self.assertAlmostEqual(state["energy_final_ev"], -RYDBERG_ENERGY_EV / 1, places=6)

    def test_jump_to_higher_level_is_absorption(self):
        state = bohr_model_state(initial_level=1, final_level=3)
        self.assertTrue(state["is_absorption"])
        self.assertTrue(state["has_transition"])
        self.assertGreater(state["photon_energy_ev"], 0)

    def test_fall_to_lower_level_is_emission(self):
        state = bohr_model_state(initial_level=4, final_level=2)
        self.assertFalse(state["is_absorption"])
        self.assertTrue(state["has_transition"])

    def test_same_level_has_no_transition(self):
        state = bohr_model_state(initial_level=3, final_level=3)
        self.assertFalse(state["has_transition"])
        self.assertEqual(state["photon_energy_ev"], 0.0)
        self.assertEqual(state["wavelength_nm"], 0.0)

    def test_larger_gaps_release_higher_energy_shorter_wavelength_photons(self):
        adjacent = bohr_model_state(initial_level=2, final_level=1)
        distant = bohr_model_state(initial_level=6, final_level=1)
        self.assertGreater(distant["photon_energy_ev"], adjacent["photon_energy_ev"])
        self.assertLess(distant["wavelength_nm"], adjacent["wavelength_nm"])

    def test_wavelength_matches_hc_over_e(self):
        state = bohr_model_state(initial_level=3, final_level=1)
        expected = HC_EV_NM / state["photon_energy_ev"]
        self.assertAlmostEqual(state["wavelength_nm"], expected, places=6)

    def test_multiple_parameter_sets_are_deterministic(self):
        for n1, n2 in ((3, 2), (1, 4), (5, 5), (6, 1)):
            first = bohr_model_state(initial_level=n1, final_level=n2)
            second = bohr_model_state(initial_level=n1, final_level=n2)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_level(999), MAX_LEVEL)
        self.assertEqual(clamp_level(0.4), MIN_LEVEL)

    def test_non_integer_level_rounds_to_nearest(self):
        self.assertEqual(clamp_level(2.6), 3)
        self.assertEqual(clamp_level(2.4), 2)

    def test_non_positive_level_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_level(0)
        with self.assertRaises(SimulationError):
            clamp_level(-2)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_level("orbit")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_level(math.nan)
        with self.assertRaises(SimulationError):
            clamp_level(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = bohr_model_state(
            initial_level=DEFAULT_INITIAL_LEVEL, final_level=DEFAULT_FINAL_LEVEL
        )
        self.assertTrue(state["has_transition"])
        self.assertGreater(state["photon_energy_ev"], 0)


class JsBohrModelConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "bohr-model.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "bohr-model.js").read_text(encoding="utf-8")
        self.assertIn("13.6", source)
        self.assertIn("1239.84", source)
        self.assertIn("energyFinal - energyInitial", source)
        for bound in ("MIN_LEVEL = 1", "MAX_LEVEL = 6"):
            self.assertIn(bound, source)
        self.assertIn('register("bohr_model"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class BohrModelLabViewTests(TestCase):
    def setUp(self):
        self.concept = _bohr_concept()
        self.simulation = _make_simulation(self.concept)

    def test_bohr_model_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Bohr Model Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/bohr-model.js")

    def test_bohr_model_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-initial-level")
        self.assertContains(response, "data-input-final-level")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_bohr_model(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_bohr_model_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_bohr_model(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("The Bohr Model Lab", body)


class BohrModelExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _bohr_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "Photon emitted.", "initial_level": "3", "final_level": "2"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_transition"])
        self.assertFalse(data["is_absorption"])
        self.assertGreater(data["photon_energy_ev"], 0)

    def test_browser_submitted_photon_energy_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "initial_level": "3", "final_level": "3",
                "photon_energy_ev": "999", "has_transition": "true", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_transition"])
        self.assertAlmostEqual(data["photon_energy_ev"], 0.0, places=4)

    def test_same_level_observation_reports_no_transition(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "initial_level": "4", "final_level": "4"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_transition"])

    def test_observe_endpoint_rejects_non_positive_level(self):
        base = {"observation": "x", "initial_level": "3", "final_level": "2"}
        for override in ({"initial_level": "0"}, {"final_level": "-1"}):
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


class BohrModelTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _bohr_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Atomic Spectra", topic="Atomic Structure", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate photon energy to the gap between quantised energy levels."],
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
            observation="x", initial_level=3, final_level=2,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "bohr_model")
        self.assertEqual(ctx.initial_level, 3)
        self.assertEqual(ctx.final_level, 2)
        self.assertTrue(ctx.has_transition)
        self.assertFalse(ctx.is_bohr_absorption)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("n=3", prompt.user)
        self.assertIn("n=2", prompt.user)
        self.assertIn("emits", prompt.user)


# --- accessibility -------------------------------------------------------


class BohrModelAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _bohr_concept()
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
        self.assertIn('<label for="lab-initial-level">', self.body)
        self.assertIn('<label for="lab-final-level">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class BohrModelXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _bohr_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Atomic Spectra", topic="Atomic Structure", grade_level="12",
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
