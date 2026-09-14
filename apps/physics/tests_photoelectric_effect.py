import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_photoelectric_effect import (
    DEFAULT_INTENSITY,
    DEFAULT_WAVELENGTH_NM,
    DEFAULT_WORK_FUNCTION_EV,
    MAX_INTENSITY,
    MAX_WAVELENGTH_NM,
    MAX_WORK_FUNCTION_EV,
    MIN_INTENSITY,
    MIN_WAVELENGTH_NM,
    MIN_WORK_FUNCTION_EV,
    PLANCK_CONSTANT_EV_S,
    SPEED_OF_LIGHT_M_S,
    SimulationError,
    clamp_intensity,
    clamp_wavelength,
    clamp_work_function,
    photoelectric_effect_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _photoelectric_concept():
    return PhysicsConcept.objects.create(
        name="The photoelectric effect",
        description=(
            "Light striking a metal surface can eject electrons, but only "
            "if its frequency exceeds a threshold value -- increasing the "
            "light's intensity alone cannot cause emission below that "
            "threshold."
        ),
        topic="Photoelectric Effect",
        equations=["KE_max = h f - phi"],
        si_units=["J", "Hz"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _photoelectric_concept(),
        title="The Photoelectric Effect Lab",
        simulation_type=PhysicsSimulation.SimulationType.PHOTOELECTRIC_EFFECT,
        description="Explore KE_max = hf - phi.",
    )


# --- DOMAIN -----------------------------------------------------------------


class PhotoelectricSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_photoelectric_concept(self):
        concept = _photoelectric_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.PHOTOELECTRIC_EFFECT,
        )

    def test_seed_simulations_creates_photoelectric_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="photoelectric-effect").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="photoelectric-effect")
        self.assertEqual(sim.simulation_type, "photoelectric_effect")
        self.assertEqual(sim.concept.name, "The photoelectric effect")

    def test_seed_simulations_is_idempotent_for_photoelectric(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="photoelectric-effect").count(), 1
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
            "time-dilation",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class PhotoelectricMathTests(TestCase):
    def test_worked_example_matches_the_closed_form(self):
        state = photoelectric_effect_state(wavelength_nm=400, work_function_ev=2.3, intensity=5)
        frequency = SPEED_OF_LIGHT_M_S / (400e-9)
        expected_energy = PLANCK_CONSTANT_EV_S * frequency
        self.assertAlmostEqual(state["photon_energy_ev"], expected_energy, places=6)
        self.assertAlmostEqual(state["ke_max_ev"], expected_energy - 2.3, places=6)
        self.assertTrue(state["ejects_electrons"])

    def test_below_threshold_no_ejection_regardless_of_intensity(self):
        # A long wavelength (low photon energy) below a high work function.
        low_intensity = photoelectric_effect_state(
            wavelength_nm=700, work_function_ev=5.0, intensity=1
        )
        high_intensity = photoelectric_effect_state(
            wavelength_nm=700, work_function_ev=5.0, intensity=10
        )
        self.assertFalse(low_intensity["ejects_electrons"])
        self.assertFalse(high_intensity["ejects_electrons"])
        self.assertAlmostEqual(low_intensity["ke_max_ev"], 0.0, places=8)
        self.assertAlmostEqual(high_intensity["ke_max_ev"], 0.0, places=8)
        self.assertAlmostEqual(low_intensity["photoelectron_rate"], 0.0, places=8)
        self.assertAlmostEqual(high_intensity["photoelectron_rate"], 0.0, places=8)

    def test_intensity_never_changes_max_kinetic_energy_when_ejecting(self):
        # The exact misconception this lab's concept names.
        low = photoelectric_effect_state(wavelength_nm=300, work_function_ev=2.0, intensity=1)
        high = photoelectric_effect_state(wavelength_nm=300, work_function_ev=2.0, intensity=10)
        self.assertTrue(low["ejects_electrons"])
        self.assertTrue(high["ejects_electrons"])
        self.assertAlmostEqual(low["ke_max_ev"], high["ke_max_ev"], places=8)

    def test_intensity_scales_the_photoelectron_rate_when_ejecting(self):
        low = photoelectric_effect_state(wavelength_nm=300, work_function_ev=2.0, intensity=2)
        high = photoelectric_effect_state(wavelength_nm=300, work_function_ev=2.0, intensity=8)
        self.assertGreater(high["photoelectron_rate"], low["photoelectron_rate"])

    def test_shorter_wavelength_gives_higher_max_kinetic_energy(self):
        longer = photoelectric_effect_state(wavelength_nm=300, work_function_ev=2.0, intensity=5)
        shorter = photoelectric_effect_state(wavelength_nm=200, work_function_ev=2.0, intensity=5)
        self.assertGreater(shorter["ke_max_ev"], longer["ke_max_ev"])

    def test_threshold_wavelength_matches_the_work_function(self):
        state = photoelectric_effect_state(wavelength_nm=400, work_function_ev=3.0, intensity=5)
        threshold_frequency = SPEED_OF_LIGHT_M_S / (state["threshold_wavelength_nm"] * 1e-9)
        self.assertAlmostEqual(
            PLANCK_CONSTANT_EV_S * threshold_frequency, 3.0, places=6
        )

    def test_multiple_parameter_sets_are_deterministic(self):
        for wl, phi, i in ((400, 2.3, 5), (200, 4.0, 8), (650, 1.5, 1)):
            first = photoelectric_effect_state(wavelength_nm=wl, work_function_ev=phi, intensity=i)
            second = photoelectric_effect_state(wavelength_nm=wl, work_function_ev=phi, intensity=i)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_wavelength(9999), MAX_WAVELENGTH_NM)
        self.assertEqual(clamp_wavelength(0.001), MIN_WAVELENGTH_NM)
        self.assertEqual(clamp_work_function(999), MAX_WORK_FUNCTION_EV)
        self.assertEqual(clamp_work_function(0.001), MIN_WORK_FUNCTION_EV)
        self.assertEqual(clamp_intensity(999), MAX_INTENSITY)
        self.assertEqual(clamp_intensity(0.001), MIN_INTENSITY)

    def test_non_positive_wavelength_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_wavelength(0)
        with self.assertRaises(SimulationError):
            clamp_wavelength(-1)

    def test_non_positive_work_function_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_work_function(0)

    def test_non_positive_intensity_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_intensity(0)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_wavelength("bright")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_wavelength(math.nan)
        with self.assertRaises(SimulationError):
            clamp_work_function(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = photoelectric_effect_state(
            wavelength_nm=DEFAULT_WAVELENGTH_NM,
            work_function_ev=DEFAULT_WORK_FUNCTION_EV,
            intensity=DEFAULT_INTENSITY,
        )
        self.assertTrue(state["ejects_electrons"])
        self.assertGreater(state["ke_max_ev"], 0)


class JsPhotoelectricConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "photoelectric-effect.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "photoelectric-effect.js").read_text(encoding="utf-8")
        self.assertIn("4.135667696e-15", source)
        self.assertIn("3.0e8", source)
        self.assertIn("photonEnergy - phi", source)
        for bound in ("100.0", "700.0", "1.0", "6.0", "10.0"):
            self.assertIn(bound, source)
        self.assertIn('register("photoelectric_effect"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class PhotoelectricLabViewTests(TestCase):
    def setUp(self):
        self.concept = _photoelectric_concept()
        self.simulation = _make_simulation(self.concept)

    def test_photoelectric_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Photoelectric Effect Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/photoelectric-effect.js")

    def test_photoelectric_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-wavelength")
        self.assertContains(response, "data-input-work-function")
        self.assertContains(response, "data-input-intensity")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_photoelectric(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_photoelectric_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_photoelectric(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("The Photoelectric Effect Lab", body)


class PhotoelectricExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _photoelectric_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Electrons ejected.", "wavelength_nm": "400",
                "work_function_ev": "2.3", "intensity": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ejects_electrons"])
        self.assertGreater(data["ke_max_ev"], 0)

    def test_browser_submitted_kinetic_energy_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "wavelength_nm": "700",
                "work_function_ev": "5.0", "intensity": "10",
                "ke_max_ev": "999", "ejects_electrons": "true", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["ejects_electrons"])
        self.assertAlmostEqual(data["ke_max_ev"], 0.0, places=4)

    def test_observe_endpoint_rejects_non_positive_wavelength_work_function_or_intensity(self):
        base = {
            "observation": "x", "wavelength_nm": "400",
            "work_function_ev": "2.3", "intensity": "5",
        }
        for override in (
            {"wavelength_nm": "0"}, {"work_function_ev": "0"}, {"intensity": "0"},
        ):
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


class PhotoelectricTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _photoelectric_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Light and Electrons", topic="Photoelectric Effect", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate photon energy to whether electrons are ejected from a metal."],
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
            observation="x", wavelength_nm=400, work_function_ev=2.3, intensity=5,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "photoelectric_effect")
        self.assertEqual(ctx.wavelength_nm, 400.0)
        self.assertTrue(ctx.ejects_electrons)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("light wavelength = 400 nm", prompt.user)
        self.assertIn("electrons ejected", prompt.user)


# --- accessibility -------------------------------------------------------


class PhotoelectricAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _photoelectric_concept()
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
        self.assertIn('<label for="lab-wavelength">', self.body)
        self.assertIn('<label for="lab-work-function">', self.body)
        self.assertIn('<label for="lab-intensity">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class PhotoelectricXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _photoelectric_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Light and Electrons", topic="Photoelectric Effect", grade_level="12",
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
