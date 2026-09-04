import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_kinematics import (
    DEFAULT_ACCELERATION_MS2,
    DEFAULT_INITIAL_POSITION_M,
    DEFAULT_INITIAL_VELOCITY_MS,
    MAX_ACCELERATION_MS2,
    MAX_INITIAL_POSITION_M,
    MAX_INITIAL_VELOCITY_MS,
    MAX_TIME_S,
    SimulationError,
    clamp_acceleration,
    clamp_initial_position,
    clamp_initial_velocity,
    clamp_time,
    kinematics_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _acceleration_concept():
    return PhysicsConcept.objects.create(
        name="Acceleration",
        description="The rate of change of velocity.",
        topic="Kinematics",
        equations=["a = Δv / Δt"],
        si_units=["m/s^2"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _acceleration_concept(),
        title="Kinematics -- Straight-Line Motion",
        simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        description="Explore v = v0 + at and x = x0 + v0t + 1/2at^2.",
    )


# --- DOMAIN -----------------------------------------------------------------


class KinematicsSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_acceleration(self):
        concept = _acceleration_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type, PhysicsSimulation.SimulationType.KINEMATICS
        )

    def test_seed_simulations_creates_kinematics_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="kinematics").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="kinematics")
        self.assertEqual(sim.simulation_type, "kinematics")
        self.assertEqual(sim.concept.name, "Acceleration")

    def test_seed_simulations_is_idempotent_for_kinematics(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="kinematics").count(), 1
        )


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class KinematicsMathTests(TestCase):
    def test_zero_acceleration_holds_velocity_constant(self):
        state = kinematics_state(
            initial_position=0, initial_velocity=3, acceleration=0, time=10
        )
        self.assertEqual(state["velocity_m_s"], 3.0)
        self.assertEqual(state["position_m"], 30.0)

    def test_positive_acceleration_worked_example(self):
        # x0=0, v0=2, a=1, t=5 -> v=7, x=22.5 (Section 31).
        state = kinematics_state(
            initial_position=0, initial_velocity=2, acceleration=1, time=5
        )
        self.assertEqual(state["velocity_m_s"], 7.0)
        self.assertEqual(state["position_m"], 22.5)

    def test_negative_acceleration_worked_example(self):
        # x0=10, v0=5, a=-2, t=2 -> v=1, x=16 (Section 32).
        state = kinematics_state(
            initial_position=10, initial_velocity=5, acceleration=-2, time=2
        )
        self.assertEqual(state["velocity_m_s"], 1.0)
        self.assertEqual(state["position_m"], 16.0)

    def test_zero_initial_velocity(self):
        state = kinematics_state(
            initial_position=0, initial_velocity=0, acceleration=2, time=3
        )
        self.assertEqual(state["velocity_m_s"], 6.0)
        self.assertEqual(state["position_m"], 9.0)

    def test_negative_initial_velocity(self):
        state = kinematics_state(
            initial_position=0, initial_velocity=-4, acceleration=1, time=4
        )
        self.assertEqual(state["velocity_m_s"], 0.0)
        self.assertEqual(state["position_m"], -8.0)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 1, 2.5, 5, 10, 20):
            first = kinematics_state(
                initial_position=1, initial_velocity=2, acceleration=-1, time=t
            )
            second = kinematics_state(
                initial_position=1, initial_velocity=2, acceleration=-1, time=t
            )
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        state = kinematics_state(
            initial_position=0, initial_velocity=1, acceleration=0, time=999
        )
        # Clamped to MAX_TIME_S=20 -> position = 0 + 1*20 = 20.
        self.assertEqual(state["position_m"], 20.0)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_position("fast")

    def test_nan_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_initial_velocity(math.nan)

    def test_infinity_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_acceleration(math.inf)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_initial_position(999), MAX_INITIAL_POSITION_M)
        self.assertEqual(clamp_initial_velocity(999), MAX_INITIAL_VELOCITY_MS)
        self.assertEqual(clamp_acceleration(999), MAX_ACCELERATION_MS2)

    def test_default_state_is_a_valid_worked_example(self):
        state = kinematics_state(
            initial_position=DEFAULT_INITIAL_POSITION_M,
            initial_velocity=DEFAULT_INITIAL_VELOCITY_MS,
            acceleration=DEFAULT_ACCELERATION_MS2,
            time=0,
        )
        self.assertEqual(state["position_m"], DEFAULT_INITIAL_POSITION_M)
        self.assertEqual(state["velocity_m_s"], DEFAULT_INITIAL_VELOCITY_MS)


class JsKinematicsConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "kinematics.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "kinematics.js").read_text(encoding="utf-8")
        self.assertIn("v0 + a * t", source)
        self.assertIn("x0 + v0 * t + 0.5 * a * t * t", source)
        for bound in ("-20.0", "20.0", "-10.0", "10.0"):
            self.assertIn(bound, source)
        self.assertIn('register("kinematics"', source)
        # The values must be computed in the browser, not fetched.
        self.assertNotIn("fetch(", source)


# --- VIEWS -------------------------------------------------------------------


class KinematicsLabViewTests(TestCase):
    def setUp(self):
        self.concept = _acceleration_concept()
        self.simulation = _make_simulation(self.concept)

    def test_kinematics_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kinematics")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/kinematics.js")

    def test_kinematics_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Initial position")
        self.assertContains(response, "Initial velocity")
        self.assertContains(response, "Acceleration")
        self.assertContains(response, 'data-input-x0')
        self.assertContains(response, 'data-input-v0')
        self.assertContains(response, 'data-input-accel')

    def test_newtons_second_law_lab_still_loads_alongside_kinematics(self):
        n2l_concept = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="d", topic="Dynamics"
        )
        n2l = PhysicsSimulation.objects.create(
            concept=n2l_concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[n2l.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "a = F &divide; m")

    def test_inactive_kinematics_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)


class KinematicsTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _acceleration_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Motion on a Line",
            topic="Kinematics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate position, velocity and acceleration."],
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

    def test_lab_never_creates_a_tutor_conversation(self):
        from apps.students.models import TutorMessage, TutorSession

        self._lesson_with_concept()
        self.client.get(reverse("physics_lab:index"))
        self.client.get(reverse("physics_lab:detail", args=[self.simulation.slug]))
        self.assertEqual(TutorSession.objects.count(), 0)
        self.assertEqual(TutorMessage.objects.count(), 0)


# --- 79: query performance ------------------------------------------------


class LabQueryBudgetTests(TestCase):
    def test_lab_index_query_count_does_not_grow_with_simulation_count(self):
        n2l_concept = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="d", topic="Dynamics"
        )
        PhysicsSimulation.objects.create(
            concept=n2l_concept, title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        kin_concept = _acceleration_concept()
        _make_simulation(kin_concept)
        for i in range(10):
            c = PhysicsConcept.objects.create(name=f"Concept {i}", description="d", topic="Kinematics")
            PhysicsSimulation.objects.create(
                concept=c, title=f"Sim {i}",
                simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
            )
        with self.assertNumQueries(1):
            self.client.get(reverse("physics_lab:index"))

    def test_kinematics_detail_query_count_is_bounded(self):
        concept = _acceleration_concept()
        simulation = _make_simulation(concept)
        # A handful of queries: simulation lookup, tutor-lesson lookup, guest
        # student get_or_create on first-ever visit (a SELECT, then an
        # INSERT wrapped in its own SAVEPOINT/RELEASE SAVEPOINT pair -- 4
        # queries total), and the latest-attempt lookup. Bounded, not
        # per-control.
        with self.assertNumQueries(7):
            self.client.get(reverse("physics_lab:detail", args=[simulation.slug]))


# --- 61: accessibility structure -------------------------------------------


class KinematicsAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _acceleration_concept()
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
        self.assertIn('<label for="lab-x0">', self.body)
        self.assertIn('<label for="lab-v0">', self.body)
        self.assertIn('<label for="lab-accel">', self.body)

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

    def test_reduced_motion_note_present_in_markup(self):
        self.assertIn("data-motion-note", self.body)
        self.assertIn("Reduced motion is on", self.body)

    def test_no_color_only_status_text(self):
        # The scene/graph status is conveyed as text content, not just a CSS
        # color class.
        self.assertIn("data-scene-status", self.body)


# --- XSS ---------------------------------------------------------------


class KinematicsXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _acceleration_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Motion", topic="Kinematics", grade_level="11",
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
