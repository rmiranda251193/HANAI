import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_electromagnetic_induction import (
    DEFAULT_AREA_M2,
    DEFAULT_FIELD_FINAL_T,
    DEFAULT_FIELD_INITIAL_T,
    DEFAULT_TIME_INTERVAL_S,
    DEFAULT_TURNS,
    MAX_AREA_M2,
    MAX_FIELD_T,
    MAX_TIME_INTERVAL_S,
    MAX_TURNS,
    MIN_AREA_M2,
    MIN_FIELD_T,
    MIN_TIME_INTERVAL_S,
    MIN_TURNS,
    SimulationError,
    clamp_area,
    clamp_field,
    clamp_time_interval,
    clamp_turns,
    electromagnetic_induction_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _induction_concept():
    return PhysicsConcept.objects.create(
        name="Electromagnetic induction and Faraday's law",
        description=(
            "A changing magnetic flux through a loop of wire induces an "
            "electromotive force in that loop -- the principle behind "
            "generators and transformers. The induced EMF is proportional "
            "to how quickly the flux changes."
        ),
        topic="Electromagnetic Induction",
        equations=["EMF = -N (delta Phi / delta t)"],
        si_units=["V", "Wb"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _induction_concept(),
        title="Electromagnetic Induction Lab",
        simulation_type=PhysicsSimulation.SimulationType.ELECTROMAGNETIC_INDUCTION,
        description="Explore EMF = N|delta Phi|/delta t.",
    )


# --- DOMAIN -----------------------------------------------------------------


class InductionSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_induction_concept(self):
        concept = _induction_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.ELECTROMAGNETIC_INDUCTION,
        )

    def test_seed_simulations_creates_induction_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="electromagnetic-induction").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="electromagnetic-induction")
        self.assertEqual(sim.simulation_type, "electromagnetic_induction")
        self.assertEqual(sim.concept.name, "Electromagnetic induction and Faraday's law")

    def test_seed_simulations_is_idempotent_for_induction(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="electromagnetic-induction").count(), 1
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
            "time-dilation", "photoelectric-effect",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class InductionMathTests(TestCase):
    def test_worked_example(self):
        state = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        self.assertAlmostEqual(state["delta_flux_wb"], 0.05, places=8)
        self.assertAlmostEqual(state["emf_v"], 10.0, places=6)
        self.assertTrue(state["flux_increasing"])

    def test_emf_scales_linearly_with_turns(self):
        base = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        doubled = electromagnetic_induction_state(
            turns=200, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        self.assertAlmostEqual(doubled["emf_v"], base["emf_v"] * 2, places=6)

    def test_emf_scales_linearly_with_area(self):
        base = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        doubled = electromagnetic_induction_state(
            turns=100, area_m2=0.1, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        self.assertAlmostEqual(doubled["emf_v"], base["emf_v"] * 2, places=6)

    def test_emf_scales_linearly_with_flux_change(self):
        base = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        doubled = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=2, time_interval_s=0.5
        )
        self.assertAlmostEqual(doubled["emf_v"], base["emf_v"] * 2, places=6)

    def test_emf_scales_inversely_with_time_interval(self):
        base = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5
        )
        faster = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.25
        )
        self.assertAlmostEqual(faster["emf_v"], base["emf_v"] * 2, places=6)

    def test_emf_magnitude_is_the_same_whether_field_rises_or_falls(self):
        rising = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0.2, field_final_t=1.0, time_interval_s=0.4
        )
        falling = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=1.0, field_final_t=0.2, time_interval_s=0.4
        )
        self.assertAlmostEqual(rising["emf_v"], falling["emf_v"], places=6)
        self.assertTrue(rising["flux_increasing"])
        self.assertFalse(falling["flux_increasing"])

    def test_no_field_change_gives_zero_emf(self):
        state = electromagnetic_induction_state(
            turns=100, area_m2=0.05, field_initial_t=0.5, field_final_t=0.5, time_interval_s=1.0
        )
        self.assertAlmostEqual(state["emf_v"], 0.0, places=8)

    def test_multiple_parameter_sets_are_deterministic(self):
        for args in (
            dict(turns=100, area_m2=0.05, field_initial_t=0, field_final_t=1, time_interval_s=0.5),
            dict(turns=250, area_m2=0.2, field_initial_t=0.5, field_final_t=1.5, time_interval_s=2),
        ):
            first = electromagnetic_induction_state(**args)
            second = electromagnetic_induction_state(**args)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_turns(9999), MAX_TURNS)
        self.assertEqual(clamp_turns(0.001), MIN_TURNS)
        self.assertEqual(clamp_area(999), MAX_AREA_M2)
        self.assertEqual(clamp_area(0.00001), MIN_AREA_M2)
        self.assertEqual(clamp_field(999), MAX_FIELD_T)
        self.assertEqual(clamp_time_interval(999), MAX_TIME_INTERVAL_S)
        self.assertEqual(clamp_time_interval(0.0001), MIN_TIME_INTERVAL_S)

    def test_zero_field_is_not_rejected(self):
        self.assertEqual(clamp_field(0), 0.0)

    def test_negative_field_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_field(-0.5)

    def test_non_positive_turns_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_turns(0)

    def test_non_positive_area_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_area(0)

    def test_non_positive_time_interval_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time_interval(0)
        with self.assertRaises(SimulationError):
            clamp_time_interval(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_turns("many")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_turns(math.nan)
        with self.assertRaises(SimulationError):
            clamp_field(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = electromagnetic_induction_state(
            turns=DEFAULT_TURNS, area_m2=DEFAULT_AREA_M2,
            field_initial_t=DEFAULT_FIELD_INITIAL_T, field_final_t=DEFAULT_FIELD_FINAL_T,
            time_interval_s=DEFAULT_TIME_INTERVAL_S,
        )
        self.assertAlmostEqual(state["emf_v"], 10.0, places=6)


class JsInductionConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "electromagnetic-induction.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "electromagnetic-induction.js").read_text(encoding="utf-8")
        self.assertIn("a * (b2 - b1)", source)
        self.assertIn("Math.abs(deltaFlux)) / dt", source)
        for bound in ("1.0", "500.0", "0.001", "2.0", "0.01", "10.0"):
            self.assertIn(bound, source)
        self.assertIn('register("electromagnetic_induction"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class InductionLabViewTests(TestCase):
    def setUp(self):
        self.concept = _induction_concept()
        self.simulation = _make_simulation(self.concept)

    def test_induction_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Electromagnetic Induction Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/electromagnetic-induction.js")

    def test_induction_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-turns")
        self.assertContains(response, "data-input-area")
        self.assertContains(response, "data-input-field-initial")
        self.assertContains(response, "data-input-field-final")
        self.assertContains(response, "data-input-interval")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_induction(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_induction_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_induction(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Electromagnetic Induction Lab", body)


class InductionExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _induction_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "10 volts induced.", "turns": "100", "area_m2": "0.05",
                "field_initial_t": "0", "field_final_t": "1", "time_interval_s": "0.5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["emf_v"], 10.0, places=2)

    def test_browser_submitted_emf_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "turns": "100", "area_m2": "0.05",
                "field_initial_t": "0", "field_final_t": "1", "time_interval_s": "0.5",
                "emf_v": "999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["emf_v"], 10.0, places=2)

    def test_observe_endpoint_rejects_zero_time_interval(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "turns": "100", "area_m2": "0.05",
                "field_initial_t": "0", "field_final_t": "1", "time_interval_s": "0",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_negative_field(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "turns": "100", "area_m2": "0.05",
                "field_initial_t": "-1", "field_final_t": "1", "time_interval_s": "0.5",
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


class InductionTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _induction_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Generators 101", topic="Electromagnetic Induction", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate changing flux to induced EMF."],
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
            observation="x", turns=100, area_m2=0.05, field_initial_t=0,
            field_final_t=1, time_interval_s=0.5,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "electromagnetic_induction")
        self.assertEqual(ctx.coil_turns, 100.0)
        self.assertAlmostEqual(ctx.induced_emf_v, 10.0, places=2)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("100 turns", prompt.user)
        self.assertIn("induced EMF", prompt.user)


# --- accessibility -------------------------------------------------------


class InductionAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _induction_concept()
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
        self.assertIn('<label for="lab-turns">', self.body)
        self.assertIn('<label for="lab-area">', self.body)
        self.assertIn('<label for="lab-field-initial">', self.body)
        self.assertIn('<label for="lab-field-final">', self.body)
        self.assertIn('<label for="lab-interval">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class InductionXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _induction_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Generators 101", topic="Electromagnetic Induction", grade_level="12",
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
