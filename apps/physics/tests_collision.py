import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_collision import (
    DEFAULT_ELASTIC,
    DEFAULT_INITIAL_VELOCITY_MS,
    DEFAULT_MASS1_KG,
    DEFAULT_MASS2_KG,
    MAX_INITIAL_VELOCITY_MS,
    MAX_MASS_KG,
    MAX_TIME_S,
    MIN_INITIAL_VELOCITY_MS,
    MIN_MASS_KG,
    SEPARATION_M,
    SimulationError,
    clamp_elastic,
    clamp_initial_velocity,
    clamp_mass,
    clamp_time,
    collision_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _collision_concept():
    return PhysicsConcept.objects.create(
        name="Elastic and inelastic collisions",
        description="Momentum is conserved in every collision; kinetic energy only in an elastic one.",
        topic="Collisions",
        equations=["p_before = p_after"],
        si_units=["kg m/s"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _collision_concept(),
        title="Momentum and Collisions Lab",
        simulation_type=PhysicsSimulation.SimulationType.MOMENTUM_COLLISION,
        description="Explore momentum conservation in elastic and inelastic collisions.",
    )


# --- DOMAIN -----------------------------------------------------------------


class CollisionSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_collision_concept(self):
        concept = _collision_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.MOMENTUM_COLLISION,
        )

    def test_seed_simulations_creates_collision_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="momentum-collision").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="momentum-collision")
        self.assertEqual(sim.simulation_type, "momentum_collision")
        self.assertEqual(sim.concept.name, "Elastic and inelastic collisions")

    def test_seed_simulations_is_idempotent_for_collision(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="momentum-collision").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class CollisionMathTests(TestCase):
    def test_before_collision_cart2_is_stationary(self):
        # v0=4 -> t_c = 8/4 = 2s. At t=1 (before collision):
        state = collision_state(mass1=2, mass2=2, initial_velocity=4, elastic=1, time=1)
        self.assertAlmostEqual(state["position_1_m"], 4.0, places=6)
        self.assertAlmostEqual(state["position_2_m"], SEPARATION_M, places=6)
        self.assertAlmostEqual(state["velocity_1_m_s"], 4.0, places=6)
        self.assertAlmostEqual(state["velocity_2_m_s"], 0.0, places=6)
        self.assertFalse(state["has_collided"])

    def test_equal_mass_elastic_collision_is_a_full_transfer(self):
        # Classic "Newton's cradle": cart 1 stops, cart 2 takes off at v0.
        state = collision_state(mass1=2, mass2=2, initial_velocity=4, elastic=1, time=100)
        self.assertAlmostEqual(state["velocity_1_m_s"], 0.0, places=6)
        self.assertAlmostEqual(state["velocity_2_m_s"], 4.0, places=6)
        self.assertTrue(state["has_collided"])

    def test_equal_mass_perfectly_inelastic_collision_shares_the_speed(self):
        state = collision_state(mass1=2, mass2=2, initial_velocity=4, elastic=0, time=100)
        self.assertAlmostEqual(state["velocity_1_m_s"], 2.0, places=6)
        self.assertAlmostEqual(state["velocity_2_m_s"], 2.0, places=6)

    def test_lighter_cart_bounces_back_off_a_heavier_one_elastically(self):
        state = collision_state(mass1=1, mass2=3, initial_velocity=6, elastic=1, time=100)
        self.assertLess(state["velocity_1_m_s"], 0.0)
        self.assertGreater(state["velocity_2_m_s"], 0.0)

    def test_momentum_is_conserved_in_both_collision_types(self):
        for elastic in (0, 1):
            state = collision_state(mass1=1.5, mass2=3.5, initial_velocity=5, elastic=elastic, time=100)
            momentum_before = 1.5 * 5
            self.assertAlmostEqual(state["momentum_total_kg_m_s"], momentum_before, places=6)

    def test_kinetic_energy_is_conserved_only_in_the_elastic_case(self):
        m1, m2, v0 = 1.0, 3.0, 5.0
        ke_before = 0.5 * m1 * v0 * v0
        elastic_state = collision_state(mass1=m1, mass2=m2, initial_velocity=v0, elastic=1, time=100)
        inelastic_state = collision_state(mass1=m1, mass2=m2, initial_velocity=v0, elastic=0, time=100)
        self.assertAlmostEqual(elastic_state["kinetic_energy_total_j"], ke_before, places=5)
        self.assertLess(inelastic_state["kinetic_energy_total_j"], ke_before)

    def test_collision_time_matches_separation_over_speed(self):
        state = collision_state(mass1=2, mass2=2, initial_velocity=4, elastic=1, time=0)
        self.assertAlmostEqual(state["collision_time_s"], SEPARATION_M / 4, places=6)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 2, 5, 15):
            first = collision_state(mass1=2, mass2=3, initial_velocity=4, elastic=1, time=t)
            second = collision_state(mass1=2, mass2=3, initial_velocity=4, elastic=1, time=t)
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_non_positive_mass_is_clamped_up_to_the_minimum(self):
        self.assertEqual(clamp_mass(0), MIN_MASS_KG)
        self.assertEqual(clamp_mass(-2), MIN_MASS_KG)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_mass(999), MAX_MASS_KG)
        self.assertEqual(clamp_initial_velocity(999), MAX_INITIAL_VELOCITY_MS)
        self.assertEqual(clamp_initial_velocity(0), MIN_INITIAL_VELOCITY_MS)

    def test_elastic_flag_rounds_to_zero_or_one(self):
        self.assertEqual(clamp_elastic(1), 1.0)
        self.assertEqual(clamp_elastic(0.7), 1.0)
        self.assertEqual(clamp_elastic(0.49), 0.0)
        self.assertEqual(clamp_elastic(0), 0.0)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass("heavy")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(math.nan)
        with self.assertRaises(SimulationError):
            clamp_initial_velocity(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = collision_state(
            mass1=DEFAULT_MASS1_KG, mass2=DEFAULT_MASS2_KG,
            initial_velocity=DEFAULT_INITIAL_VELOCITY_MS, elastic=DEFAULT_ELASTIC, time=0,
        )
        self.assertAlmostEqual(state["position_1_m"], 0.0, places=6)
        self.assertFalse(state["has_collided"])


class JsCollisionConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "collision.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "collision.js").read_text(encoding="utf-8")
        self.assertIn("mass1 - mass2", source)
        self.assertIn("SEPARATION_M", source)
        for bound in ("0.5", "10.0", "8.0", "20.0"):
            self.assertIn(bound, source)
        self.assertIn('register("momentum_collision"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class CollisionLabViewTests(TestCase):
    def setUp(self):
        self.concept = _collision_concept()
        self.simulation = _make_simulation(self.concept)

    def test_collision_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Momentum and Collisions Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/collision.js")

    def test_collision_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Mass 1")
        self.assertContains(response, "Mass 2")
        self.assertContains(response, "data-input-mass1")
        self.assertContains(response, "data-input-mass2")
        self.assertContains(response, "Elastic")
        self.assertContains(response, "Perfectly inelastic")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_hands_on_companion_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Try this with real materials:")
        self.assertContains(response, "Roll two coins or marbles")

    def test_other_simulations_still_load_alongside_collision(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_collision_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_collision(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Momentum and Collisions Lab", body)


class CollisionExperimentFlowTests(TestCase):
    """Server-authoritative recomputation via the shared experiment
    endpoints -- exactly the coverage gap that let two pre-existing bugs
    (views.py's _observation_message, prompts.py's build_tutor_prompt) hide
    in Projectile Motion until Circular Motion's own tests were written."""

    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _collision_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Cart 1 stopped.", "mass1_kg": "2", "mass2_kg": "2",
                "initial_velocity_m_s": "4", "elastic": "1", "time_s": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["velocity_1_m_s"], 0.0, places=4)
        self.assertAlmostEqual(data["velocity_2_m_s"], 4.0, places=4)

    def test_browser_submitted_velocity_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "mass1_kg": "2", "mass2_kg": "2",
                "initial_velocity_m_s": "4", "elastic": "1", "time_s": "100",
                "velocity_1_m_s": "999", "velocity_2_m_s": "999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["velocity_2_m_s"], 4.0, places=4)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "mass1_kg": "2", "mass2_kg": "2",
                "initial_velocity_m_s": "4", "elastic": "1", "time_s": "-1",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_positive_initial_velocity(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "mass1_kg": "2", "mass2_kg": "2",
                "initial_velocity_m_s": "0", "elastic": "1", "time_s": "1",
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


class CollisionTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _collision_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Crash Course", topic="Collisions", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate mass and collision type to post-collision velocities."],
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
        """Regression coverage for the exact bug class found in Projectile
        Motion: the tutor prompt must actually contain this simulation's own
        setup/observed values, not silently fall into another type's branch."""

        from apps.students.experiment_services import record_experiment_observation
        from apps.students.models import StudentProfile
        from apps.students.prompts import build_tutor_prompt
        from apps.students.requests import ConceptContext, ExperimentContext, TutorRequest

        lesson = self._lesson_with_concept()
        student = StudentProfile.objects.create(display_name="Sam")
        attempt, _ = record_experiment_observation(
            student=student, simulation=self.simulation, lesson=lesson,
            observation="x", mass1_kg=2, mass2_kg=2, initial_velocity_m_s=4,
            elastic=1, time_s=100,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "momentum_collision")
        self.assertEqual(ctx.mass1_kg, 2.0)
        self.assertEqual(ctx.mass2_kg, 2.0)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("mass 1 = 2.00 kg", prompt.user)
        self.assertIn("mass 2 = 2.00 kg", prompt.user)
        self.assertIn("elastic", prompt.user)


# --- accessibility -------------------------------------------------------


class CollisionAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _collision_concept()
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
        self.assertIn('<label for="lab-mass2">', self.body)
        self.assertIn('<label for="lab-v0">', self.body)
        self.assertIn('<label for="lab-time">', self.body)

    def test_collision_type_choice_has_a_real_legend_and_labels(self):
        self.assertIn("<legend>Collision type</legend>", self.body)
        self.assertIn('type="radio"', self.body)

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


class CollisionXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _collision_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Crash Course", topic="Collisions", grade_level="11",
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
