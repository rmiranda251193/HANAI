import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_radioactive_decay import (
    DEFAULT_HALF_LIFE_S,
    DEFAULT_INITIAL_COUNT,
    MAX_HALF_LIFE_S,
    MAX_INITIAL_COUNT,
    MAX_TIME_S,
    MIN_HALF_LIFE_S,
    MIN_INITIAL_COUNT,
    SimulationError,
    clamp_half_life,
    clamp_initial_count,
    clamp_time,
    radioactive_decay_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _decay_concept():
    return PhysicsConcept.objects.create(
        name="Half-life",
        description=(
            "The half-life of a radioactive isotope is the time it takes "
            "for half of a sample to decay. It is constant for a given "
            "isotope, regardless of the sample's size or how much has "
            "already decayed."
        ),
        topic="Nuclear Decay",
        equations=["T_half = ln(2) / lambda"],
        si_units=["s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _decay_concept(),
        title="Radioactive Decay Lab",
        simulation_type=PhysicsSimulation.SimulationType.RADIOACTIVE_DECAY,
        description="Explore N(t) = N0 * (1/2)^(t / T_half).",
    )


# --- DOMAIN -----------------------------------------------------------------


class DecaySimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_half_life_concept(self):
        concept = _decay_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.RADIOACTIVE_DECAY,
        )

    def test_seed_simulations_creates_decay_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="radioactive-decay").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="radioactive-decay")
        self.assertEqual(sim.simulation_type, "radioactive_decay")
        self.assertEqual(sim.concept.name, "Half-life")

    def test_seed_simulations_is_idempotent_for_decay(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="radioactive-decay").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion", "series-parallel-circuit",
            "coulombs-law",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class DecayMathTests(TestCase):
    def test_starts_at_full_count(self):
        state = radioactive_decay_state(initial_count=1000, half_life=5, time=0)
        self.assertAlmostEqual(state["remaining_count"], 1000.0, places=6)
        self.assertAlmostEqual(state["decayed_count"], 0.0, places=6)
        self.assertAlmostEqual(state["remaining_fraction"], 1.0, places=6)

    def test_exactly_half_remains_after_one_half_life(self):
        state = radioactive_decay_state(initial_count=1000, half_life=5, time=5)
        self.assertAlmostEqual(state["remaining_count"], 500.0, places=6)

    def test_exactly_a_quarter_remains_after_two_half_lives(self):
        state = radioactive_decay_state(initial_count=1000, half_life=5, time=10)
        self.assertAlmostEqual(state["remaining_count"], 250.0, places=6)

    def test_exactly_an_eighth_remains_after_three_half_lives(self):
        state = radioactive_decay_state(initial_count=1000, half_life=5, time=15)
        self.assertAlmostEqual(state["remaining_count"], 125.0, places=6)

    def test_remaining_plus_decayed_always_equals_initial_count(self):
        for t in (0, 1, 3, 5, 10, 15, 30, 60):
            state = radioactive_decay_state(initial_count=1000, half_life=5, time=t)
            self.assertAlmostEqual(
                state["remaining_count"] + state["decayed_count"], 1000.0, places=6
            )

    def test_remaining_count_never_increases_with_time(self):
        # The one property that distinguishes this lab from every periodic
        # one (Circular Motion, SHM, Orbital Motion): this quantity only
        # ever falls.
        previous = None
        for t in (0, 1, 2, 5, 10, 20, 40, 60):
            state = radioactive_decay_state(initial_count=1000, half_life=5, time=t)
            if previous is not None:
                self.assertLessEqual(state["remaining_count"], previous)
            previous = state["remaining_count"]

    def test_remaining_count_stays_positive_even_at_the_time_bound(self):
        state = radioactive_decay_state(
            initial_count=MIN_INITIAL_COUNT, half_life=MIN_HALF_LIFE_S, time=MAX_TIME_S
        )
        self.assertGreater(state["remaining_count"], 0.0)

    def test_activity_also_halves_every_half_life(self):
        state_0 = radioactive_decay_state(initial_count=1000, half_life=5, time=0)
        state_1 = radioactive_decay_state(initial_count=1000, half_life=5, time=5)
        self.assertAlmostEqual(state_1["activity_per_s"], state_0["activity_per_s"] / 2, places=6)

    def test_half_life_is_independent_of_initial_count(self):
        # The half-life concept's own stated property: constant regardless
        # of sample size.
        small = radioactive_decay_state(initial_count=100, half_life=5, time=5)
        large = radioactive_decay_state(initial_count=10000, half_life=5, time=5)
        self.assertAlmostEqual(small["remaining_fraction"], 0.5, places=6)
        self.assertAlmostEqual(large["remaining_fraction"], 0.5, places=6)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 1, 5, 10, 30):
            first = radioactive_decay_state(initial_count=2000, half_life=8, time=t)
            second = radioactive_decay_state(initial_count=2000, half_life=8, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_initial_count(999999), MAX_INITIAL_COUNT)
        self.assertEqual(clamp_initial_count(1), MIN_INITIAL_COUNT)
        self.assertEqual(clamp_half_life(999), MAX_HALF_LIFE_S)
        self.assertEqual(clamp_half_life(0.001), MIN_HALF_LIFE_S)

    def test_non_positive_initial_count_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_count(0)
        with self.assertRaises(SimulationError):
            clamp_initial_count(-5)

    def test_non_positive_half_life_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_half_life(0)
        with self.assertRaises(SimulationError):
            clamp_half_life(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_count("many")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_count(math.nan)
        with self.assertRaises(SimulationError):
            clamp_half_life(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = radioactive_decay_state(
            initial_count=DEFAULT_INITIAL_COUNT, half_life=DEFAULT_HALF_LIFE_S, time=0
        )
        self.assertAlmostEqual(state["remaining_count"], DEFAULT_INITIAL_COUNT, places=6)
        self.assertGreater(state["activity_per_s"], 0)


class JsDecayConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "radioactive-decay.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "radioactive-decay.js").read_text(encoding="utf-8")
        self.assertIn("Math.log(2)", source)
        self.assertIn("Math.pow(0.5, halfLivesElapsed)", source)
        for bound in ("100.0", "10000.0", "1.0", "20.0", "60.0"):
            self.assertIn(bound, source)
        self.assertIn('register("radioactive_decay"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class DecayLabViewTests(TestCase):
    def setUp(self):
        self.concept = _decay_concept()
        self.simulation = _make_simulation(self.concept)

    def test_decay_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Radioactive Decay Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/radioactive-decay.js")

    def test_decay_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-initial")
        self.assertContains(response, "data-input-half-life")
        self.assertContains(response, "data-input-time")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_decay(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_decay_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_decay(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Radioactive Decay Lab", body)


class DecayExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _decay_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Half the sample remained.", "initial_count": "1000",
                "half_life_s": "5", "time_s": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["remaining_count"], 500.0, places=2)

    def test_browser_submitted_remaining_count_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "initial_count": "1000", "half_life_s": "5",
                "time_s": "5", "remaining_count": "999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["remaining_count"], 500.0, places=2)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "initial_count": "1000", "half_life_s": "5",
                "time_s": "-1",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_positive_initial_count_or_half_life(self):
        for initial_count, half_life in (("0", "5"), ("1000", "0"), ("-5", "5")):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "initial_count": initial_count,
                    "half_life_s": half_life, "time_s": "1",
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


class DecayTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _decay_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Half of What's Left", topic="Nuclear Decay", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate elapsed time to remaining sample size through half-life."],
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
            observation="x", initial_count=1000, half_life_s=5, time_s=5,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "radioactive_decay")
        self.assertEqual(ctx.initial_count, 1000.0)
        self.assertAlmostEqual(ctx.remaining_count, 500.0, places=2)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("initial count = 1000", prompt.user)
        self.assertIn("half-life = 5.00 s", prompt.user)


# --- accessibility -------------------------------------------------------


class DecayAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _decay_concept()
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
        self.assertIn('<label for="lab-initial">', self.body)
        self.assertIn('<label for="lab-half-life">', self.body)
        self.assertIn('<label for="lab-time">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_real_buttons_not_divs(self):
        self.assertIn("data-action-start", self.body)
        self.assertIn("data-action-pause", self.body)
        self.assertIn("data-action-reset", self.body)
        self.assertIn('<button type="button"', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class DecayXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _decay_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Half of What's Left", topic="Nuclear Decay", grade_level="11",
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
