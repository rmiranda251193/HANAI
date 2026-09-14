import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_doppler_effect import (
    DEFAULT_OBSERVER_VELOCITY_M_S,
    DEFAULT_SOURCE_FREQ_HZ,
    DEFAULT_SOURCE_VELOCITY_M_S,
    MAX_FREQ_HZ,
    MAX_VELOCITY_M_S,
    MIN_FREQ_HZ,
    SPEED_OF_SOUND_M_S,
    SimulationError,
    clamp_freq,
    clamp_velocity,
    doppler_effect_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _doppler_concept():
    return PhysicsConcept.objects.create(
        name="The Doppler effect",
        description=(
            "The observed frequency of a wave shifts when there is "
            "relative motion between the source and the observer -- "
            "higher when approaching, lower when receding, even though "
            "the source's actual emitted frequency never changes."
        ),
        topic="Sound",
        equations=["f_observed = f_source (v +/- v_observer)/(v -/+ v_source)"],
        si_units=["Hz"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _doppler_concept(),
        title="The Doppler Effect Lab",
        simulation_type=PhysicsSimulation.SimulationType.DOPPLER_EFFECT,
        description="Explore how relative motion shifts observed frequency.",
    )


# --- DOMAIN -----------------------------------------------------------------


class DopplerSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_doppler_concept(self):
        concept = _doppler_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.DOPPLER_EFFECT,
        )

    def test_seed_simulations_creates_doppler_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="doppler-effect").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="doppler-effect")
        self.assertEqual(sim.simulation_type, "doppler_effect")
        self.assertEqual(sim.concept.name, "The Doppler effect")

    def test_seed_simulations_is_idempotent_for_doppler(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="doppler-effect").count(), 1
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
            "calorimetry", "ideal-gas-law",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class DopplerMathTests(TestCase):
    def test_no_relative_motion_leaves_frequency_unchanged(self):
        state = doppler_effect_state(source_freq=440, source_velocity=0, observer_velocity=0)
        self.assertAlmostEqual(state["observed_freq_hz"], 440.0, places=6)

    def test_worked_example(self):
        state = doppler_effect_state(source_freq=440, source_velocity=20, observer_velocity=0)
        expected = 440 * (SPEED_OF_SOUND_M_S + 0) / (SPEED_OF_SOUND_M_S - 20)
        self.assertAlmostEqual(state["observed_freq_hz"], expected, places=6)

    def test_approaching_source_raises_the_observed_frequency(self):
        state = doppler_effect_state(source_freq=440, source_velocity=30, observer_velocity=0)
        self.assertGreater(state["observed_freq_hz"], 440)

    def test_receding_source_lowers_the_observed_frequency(self):
        state = doppler_effect_state(source_freq=440, source_velocity=-30, observer_velocity=0)
        self.assertLess(state["observed_freq_hz"], 440)

    def test_approaching_observer_raises_the_observed_frequency(self):
        state = doppler_effect_state(source_freq=440, source_velocity=0, observer_velocity=30)
        self.assertGreater(state["observed_freq_hz"], 440)

    def test_receding_observer_lowers_the_observed_frequency(self):
        state = doppler_effect_state(source_freq=440, source_velocity=0, observer_velocity=-30)
        self.assertLess(state["observed_freq_hz"], 440)

    def test_source_motion_and_observer_motion_are_not_equivalent(self):
        # A genuinely non-obvious real-physics fact: the same speed gives a
        # DIFFERENT shift depending on whether it's the source or the
        # observer moving -- they enter the formula differently.
        source_moving = doppler_effect_state(source_freq=440, source_velocity=30, observer_velocity=0)
        observer_moving = doppler_effect_state(source_freq=440, source_velocity=0, observer_velocity=30)
        self.assertNotAlmostEqual(
            source_moving["observed_freq_hz"], observer_moving["observed_freq_hz"], places=4
        )

    def test_wavelength_ahead_is_shorter_than_behind_when_approaching(self):
        state = doppler_effect_state(source_freq=440, source_velocity=30, observer_velocity=0)
        self.assertLess(state["wavelength_ahead_m"], state["wavelength_behind_m"])

    def test_multiple_parameter_sets_are_deterministic(self):
        for f, vs, vo in ((440, 20, 0), (261.6, -15, 10), (1000, 0, -25)):
            first = doppler_effect_state(source_freq=f, source_velocity=vs, observer_velocity=vo)
            second = doppler_effect_state(source_freq=f, source_velocity=vs, observer_velocity=vo)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_freq(99999), MAX_FREQ_HZ)
        self.assertEqual(clamp_freq(1), MIN_FREQ_HZ)
        self.assertEqual(clamp_velocity(9999), MAX_VELOCITY_M_S)
        self.assertEqual(clamp_velocity(-9999), -MAX_VELOCITY_M_S)

    def test_negative_velocity_is_not_rejected(self):
        # Signed -- negative (receding) is a normal, valid velocity.
        self.assertEqual(clamp_velocity(-15), -15.0)

    def test_non_positive_frequency_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_freq(0)
        with self.assertRaises(SimulationError):
            clamp_freq(-100)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_freq("loud")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_freq(math.nan)
        with self.assertRaises(SimulationError):
            clamp_velocity(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = doppler_effect_state(
            source_freq=DEFAULT_SOURCE_FREQ_HZ,
            source_velocity=DEFAULT_SOURCE_VELOCITY_M_S,
            observer_velocity=DEFAULT_OBSERVER_VELOCITY_M_S,
        )
        self.assertGreater(state["observed_freq_hz"], DEFAULT_SOURCE_FREQ_HZ)


class JsDopplerConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "doppler-effect.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "doppler-effect.js").read_text(encoding="utf-8")
        self.assertIn("343.0", source)
        self.assertIn("SPEED_OF_SOUND_M_S + vObserver", source)
        for bound in ("20.0", "2000.0", "60.0"):
            self.assertIn(bound, source)
        self.assertIn('register("doppler_effect"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class DopplerLabViewTests(TestCase):
    def setUp(self):
        self.concept = _doppler_concept()
        self.simulation = _make_simulation(self.concept)

    def test_doppler_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Doppler Effect Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/doppler-effect.js")

    def test_doppler_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-source-freq")
        self.assertContains(response, "data-input-source-velocity")
        self.assertContains(response, "data-input-observer-velocity")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_doppler(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_doppler_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_doppler(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("The Doppler Effect Lab", body)


class DopplerExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _doppler_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "The pitch rose.", "source_freq_hz": "440",
                "source_velocity_m_s": "20", "observer_velocity_m_s": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = 440 * SPEED_OF_SOUND_M_S / (SPEED_OF_SOUND_M_S - 20)
        self.assertAlmostEqual(data["observed_freq_hz"], expected, places=2)

    def test_browser_submitted_observed_frequency_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "source_freq_hz": "440",
                "source_velocity_m_s": "20", "observer_velocity_m_s": "0",
                "observed_freq_hz": "99999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected = 440 * SPEED_OF_SOUND_M_S / (SPEED_OF_SOUND_M_S - 20)
        self.assertAlmostEqual(data["observed_freq_hz"], expected, places=2)

    def test_observe_endpoint_rejects_non_positive_frequency(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "source_freq_hz": "0",
                "source_velocity_m_s": "20", "observer_velocity_m_s": "0",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_accepts_negative_velocity(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "source_freq_hz": "440",
                "source_velocity_m_s": "-20", "observer_velocity_m_s": "-10",
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


class DopplerTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _doppler_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Passing Sirens", topic="Sound", grade_level="10",
            duration_minutes=45,
            learning_objectives=["Relate relative motion to the observed pitch shift."],
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
            observation="x", source_freq_hz=440, source_velocity_m_s=20, observer_velocity_m_s=0,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "doppler_effect")
        self.assertEqual(ctx.source_freq_hz, 440.0)
        self.assertGreater(ctx.observed_freq_hz, 440.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("source frequency = 440 Hz", prompt.user)
        self.assertIn("observed frequency", prompt.user)


# --- accessibility -------------------------------------------------------


class DopplerAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _doppler_concept()
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
        self.assertIn('<label for="lab-source-freq">', self.body)
        self.assertIn('<label for="lab-source-velocity">', self.body)
        self.assertIn('<label for="lab-observer-velocity">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class DopplerXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _doppler_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Passing Sirens", topic="Sound", grade_level="10",
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
