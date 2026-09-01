import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations import (
    DEFAULT_FORCE_N,
    DEFAULT_MASS_KG,
    MAX_FORCE_N,
    MAX_MASS_KG,
    NewtonsSecondLawSimulation,
    SimulationError,
    clamp_force,
    clamp_mass,
    make_initial_state,
    newtons_second_law_acceleration,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _newtons_concept():
    return PhysicsConcept.objects.create(
        name="Newton's Second Law",
        description="Net force, mass and acceleration are related by F = ma.",
        topic="Dynamics",
        equations=["F_net = ma"],
        si_units=["newton (N)", "kilogram (kg)", "m/s^2"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _newtons_concept(),
        title="Newton's Second Law Lab",
        simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        description="Explore a = F / m.",
    )


# --- DOMAIN -----------------------------------------------------------------


class PhysicsSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertEqual(simulation.slug, "newtons-second-law-lab")
        self.assertTrue(simulation.is_active)
        self.assertEqual(str(simulation), "Newton's Second Law Lab")

    def test_simulation_is_linked_to_newtons_second_law(self):
        concept = _newtons_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def test_seed_simulations_is_idempotent(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)

        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="newtons-second-law").count(), 1
        )
        self.assertIn("0 created, 1 updated", out.getvalue())
        simulation = PhysicsSimulation.objects.get(slug="newtons-second-law")
        self.assertEqual(simulation.concept.name, "Newton's Second Law")

    def test_seed_simulations_warns_when_concept_missing(self):
        out = StringIO()
        call_command("seed_simulations", stdout=out)
        self.assertEqual(PhysicsSimulation.objects.count(), 0)
        self.assertIn("Skipped", out.getvalue())


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class NewtonsSecondLawMathTests(TestCase):
    def test_two_kg_ten_newton_gives_five(self):
        self.assertEqual(newtons_second_law_acceleration(10, 2), 5.0)

    def test_doubling_force_doubles_acceleration(self):
        base = newtons_second_law_acceleration(10, 2)
        doubled = newtons_second_law_acceleration(20, 2)
        self.assertEqual(doubled, 2 * base)
        self.assertEqual(doubled, 10.0)

    def test_doubling_mass_halves_acceleration_when_force_constant(self):
        base = newtons_second_law_acceleration(10, 2)
        heavier = newtons_second_law_acceleration(10, 4)
        self.assertEqual(heavier, base / 2)
        self.assertEqual(heavier, 2.5)

    def test_zero_force_gives_zero_acceleration(self):
        self.assertEqual(newtons_second_law_acceleration(0, 2), 0.0)

    def test_zero_mass_is_rejected(self):
        with self.assertRaises(SimulationError):
            newtons_second_law_acceleration(10, 0)

    def test_negative_mass_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(-3)

    def test_non_numeric_and_nan_inputs_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass("heavy")
        with self.assertRaises(SimulationError):
            clamp_force(math.nan)

    def test_values_are_clamped_to_ui_range(self):
        self.assertEqual(clamp_mass(999), MAX_MASS_KG)
        self.assertEqual(clamp_force(999), MAX_FORCE_N)
        self.assertEqual(clamp_force(-5), 0.0)

    def test_calculation_is_deterministic(self):
        first = newtons_second_law_acceleration(17.5, 3.2)
        second = newtons_second_law_acceleration(17.5, 3.2)
        self.assertEqual(first, second)


class NewtonsSecondLawSimulationStateTests(TestCase):
    def test_control_surface_matches_the_js_api(self):
        sim = make_initial_state()
        for method in ("set_mass", "set_force", "start", "pause", "reset", "step", "state"):
            self.assertTrue(callable(getattr(sim, method)))

    def test_reset_returns_to_initial_state(self):
        sim = NewtonsSecondLawSimulation(mass_kg=DEFAULT_MASS_KG, force_n=DEFAULT_FORCE_N)
        sim.set_mass(5)
        sim.set_force(30)
        sim.start()
        for _ in range(20):
            sim.step()
        self.assertGreater(sim.position_m, 0)

        sim.reset()
        state = sim.state()
        self.assertEqual(state["time_s"], 0.0)
        self.assertEqual(state["velocity_ms"], 0.0)
        self.assertEqual(state["position_m"], 0.0)
        self.assertFalse(state["running"])
        # Mass and force survive a reset; only the motion is cleared.
        self.assertEqual(state["mass_kg"], 5.0)
        self.assertEqual(state["force_n"], 30.0)

    def test_stepping_builds_a_velocity_trace(self):
        sim = make_initial_state(mass_kg=2, force_n=10)
        sim.step()
        sim.step()
        # a = 5 m/s^2, dt = 0.05 -> v after two steps = 0.5 m/s
        self.assertAlmostEqual(sim.velocity_ms, 0.5, places=6)
        self.assertGreaterEqual(len(sim.trace), 3)

    def test_pause_stops_running_flag(self):
        sim = make_initial_state()
        sim.start()
        self.assertTrue(sim.state()["running"])
        sim.pause()
        self.assertFalse(sim.state()["running"])


class JsSimulationConsistencyTests(TestCase):
    def test_js_files_exist(self):
        self.assertTrue((JS_DIR / "lab.js").is_file())
        self.assertTrue((JS_DIR / "newtons-second-law.js").is_file())

    def test_lab_shell_defines_namespace_and_registry(self):
        source = (JS_DIR / "lab.js").read_text(encoding="utf-8")
        self.assertIn("window.PhysicsLab", source)
        self.assertIn("register", source)
        self.assertIn("prefers-reduced-motion", source)

    def test_js_core_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "newtons-second-law.js").read_text(encoding="utf-8")
        self.assertIn("force / mass", source)
        self.assertIn("a = F / m", source)
        for bound in ("0.1", "20.0", "50.0"):
            self.assertIn(bound, source)
        self.assertIn('register("newtons_second_law"', source)
        # The acceleration must be computed in the browser, not fetched.
        self.assertNotIn("fetch(", source)


# --- VIEWS -------------------------------------------------------------------


class PhysicsLabViewTests(TestCase):
    def setUp(self):
        self.concept = _newtons_concept()
        self.simulation = _make_simulation(self.concept)

    def test_physics_lab_index_loads_and_lists_simulations(self):
        response = self.client.get(reverse("physics_lab:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Second Law Lab")
        self.assertContains(response, reverse("physics_lab:detail", args=["newtons-second-law-lab"]))

    def test_newtons_second_law_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Second Law Lab")
        self.assertContains(response, "a = F &divide; m")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/newtons-second-law.js")
        # Default deterministic value rendered server-side: 10 / 2 = 5.
        self.assertContains(response, "5.00")

    def test_navigation_link_is_present_on_every_page(self):
        response = self.client.get(reverse("physics_lab:index"))
        self.assertContains(response, 'href="/physics-lab/"')
        self.assertContains(response, ">Physics Lab<")

    def test_inactive_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_slug_is_not_found(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=["no-such-sim"])
        )
        self.assertEqual(response.status_code, 404)


# --- TUTOR CONNECTION ---------------------------------------------------


class PhysicsLabTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _newtons_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Forces and Motion",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass and acceleration."],
        )
        lesson.physics_concepts.add(self.concept)
        return lesson

    def test_lab_links_to_existing_tutor_when_a_lesson_exists(self):
        lesson = self._lesson_with_concept()
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "Ask the Tutor About This Experiment")
        self.assertContains(
            response, reverse("students:tutor", args=[lesson.slug])
        )
        self.assertContains(response, "prefill=")

    def test_lab_shows_a_note_when_no_lesson_covers_the_concept(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "connect this experiment to the Physics Tutor")
        self.assertNotContains(response, "Ask the Tutor About This Experiment")

    def test_experiment_context_prefills_the_existing_tutor(self):
        lesson = self._lesson_with_concept()
        prefill = (
            "Physics Lab experiment - Newton's Second Law\n"
            "mass = 2.0 kg\nnet force = 10.0 N\nacceleration = 5.00 m/s^2"
        )
        response = self.client.get(
            reverse("students:tutor", args=[lesson.slug]), {"prefill": prefill}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mass = 2.0 kg")
        self.assertContains(response, "Loaded from your Physics Lab experiment")

    def test_prefill_is_escaped_and_not_executed(self):
        lesson = self._lesson_with_concept()
        response = self.client.get(
            reverse("students:tutor", args=[lesson.slug]),
            {"prefill": "<script>alert('x')</script>"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('x')</script>")

    def test_lab_never_creates_a_tutor_conversation(self):
        from apps.students.models import TutorMessage, TutorSession

        self._lesson_with_concept()
        self.client.get(reverse("physics_lab:index"))
        self.client.get(reverse("physics_lab:detail", args=[self.simulation.slug]))

        self.assertEqual(TutorSession.objects.count(), 0)
        self.assertEqual(TutorMessage.objects.count(), 0)

    def test_lab_view_does_not_import_a_second_tutor_engine(self):
        from apps.physics import views as physics_views

        self.assertFalse(hasattr(physics_views, "run_tutor_turn"))
        self.assertFalse(hasattr(physics_views, "tutor_student"))
