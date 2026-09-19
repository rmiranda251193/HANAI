import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_particle_physics import (
    DEFAULT_MOMENTUM_MEV_C,
    DEFAULT_REST_ENERGY_MEV,
    MAX_MOMENTUM_MEV_C,
    MAX_REST_ENERGY_MEV,
    MIN_MOMENTUM_MEV_C,
    MIN_REST_ENERGY_MEV,
    SimulationError,
    clamp_momentum,
    clamp_rest_energy,
    particle_physics_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _particle_physics_concept():
    return PhysicsConcept.objects.create(
        name="Relativistic energy and momentum",
        description=(
            "A particle's total energy, momentum and rest mass are related "
            "by E^2 = (pc)^2 + (mc^2)^2."
        ),
        topic="Particle Physics",
        equations=["E^2 = (pc)^2 + (mc^2)^2"],
        si_units=["MeV"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _particle_physics_concept(),
        title="Relativistic Energy and Momentum Lab",
        simulation_type=PhysicsSimulation.SimulationType.PARTICLE_PHYSICS,
        description="Explore E^2 = (pc)^2 + (mc^2)^2.",
    )


# --- DOMAIN -----------------------------------------------------------------


class ParticlePhysicsSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_particle_physics_concept(self):
        concept = _particle_physics_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.PARTICLE_PHYSICS,
        )

    def test_seed_simulations_creates_particle_physics_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="particle-physics").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="particle-physics")
        self.assertEqual(sim.simulation_type, "particle_physics")
        self.assertEqual(sim.concept.name, "Relativistic energy and momentum")

    def test_seed_simulations_is_idempotent_for_particle_physics(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="particle-physics").count(), 1
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
            "bohr-model", "hubbles-law",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class ParticlePhysicsMathTests(TestCase):
    def test_default_state_is_a_valid_worked_example(self):
        state = particle_physics_state(
            rest_energy_mev=DEFAULT_REST_ENERGY_MEV,
            momentum_mev_c=DEFAULT_MOMENTUM_MEV_C,
        )
        expected_energy = math.sqrt(DEFAULT_MOMENTUM_MEV_C ** 2 + DEFAULT_REST_ENERGY_MEV ** 2)
        self.assertAlmostEqual(state["total_energy_mev"], expected_energy, places=6)
        self.assertAlmostEqual(
            state["kinetic_energy_mev"], expected_energy - DEFAULT_REST_ENERGY_MEV, places=6
        )
        self.assertAlmostEqual(
            state["velocity_fraction_c"], DEFAULT_MOMENTUM_MEV_C / expected_energy, places=6
        )

    def test_clean_3_4_5_triangle_worked_example(self):
        """300 MeV rest energy and 400 MeV/c momentum is a scaled 3-4-5
        triangle in energy-momentum space: total energy comes out to
        exactly 500 MeV, the same style of clean hand-checkable example
        Time Dilation's own beta=0.6/gamma=1.25 case uses."""

        state = particle_physics_state(rest_energy_mev=300, momentum_mev_c=400)
        self.assertAlmostEqual(state["total_energy_mev"], 500.0, places=6)
        self.assertAlmostEqual(state["kinetic_energy_mev"], 200.0, places=6)
        self.assertAlmostEqual(state["velocity_fraction_c"], 0.8, places=6)

    def test_zero_momentum_gives_exactly_the_rest_energy(self):
        state = particle_physics_state(rest_energy_mev=250, momentum_mev_c=0)
        self.assertAlmostEqual(state["total_energy_mev"], 250.0, places=6)
        self.assertAlmostEqual(state["kinetic_energy_mev"], 0.0, places=6)
        self.assertAlmostEqual(state["velocity_fraction_c"], 0.0, places=6)

    def test_kinetic_energy_is_never_negative(self):
        for mc2, pc in ((0.1, 0), (105.66, 200), (1000, 0), (0.1, 2000)):
            state = particle_physics_state(rest_energy_mev=mc2, momentum_mev_c=pc)
            self.assertGreaterEqual(state["kinetic_energy_mev"], 0)

    def test_velocity_fraction_is_always_strictly_less_than_one(self):
        for mc2, pc in ((MIN_REST_ENERGY_MEV, MAX_MOMENTUM_MEV_C), (1000, 2000), (0.1, 0.1)):
            state = particle_physics_state(rest_energy_mev=mc2, momentum_mev_c=pc)
            self.assertLess(state["velocity_fraction_c"], 1.0)

    def test_total_energy_and_beta_increase_monotonically_with_momentum(self):
        previous_energy = None
        previous_beta = None
        for pc in (0, 100, 500, 1000, 2000):
            state = particle_physics_state(rest_energy_mev=100, momentum_mev_c=pc)
            if previous_energy is not None:
                self.assertGreater(state["total_energy_mev"], previous_energy)
                self.assertGreater(state["velocity_fraction_c"], previous_beta)
            previous_energy = state["total_energy_mev"]
            previous_beta = state["velocity_fraction_c"]

    def test_multiple_parameter_sets_are_deterministic(self):
        for mc2, pc in ((105.66, 200), (300, 400), (1000, 0)):
            first = particle_physics_state(rest_energy_mev=mc2, momentum_mev_c=pc)
            second = particle_physics_state(rest_energy_mev=mc2, momentum_mev_c=pc)
            self.assertEqual(first, second)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_rest_energy(99999), MAX_REST_ENERGY_MEV)
        self.assertEqual(clamp_rest_energy(0.00001), MIN_REST_ENERGY_MEV)
        self.assertEqual(clamp_momentum(99999), MAX_MOMENTUM_MEV_C)
        self.assertEqual(clamp_momentum(0), MIN_MOMENTUM_MEV_C)

    def test_non_positive_rest_energy_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_rest_energy(0)
        with self.assertRaises(SimulationError):
            clamp_rest_energy(-10)

    def test_zero_momentum_is_accepted_but_negative_is_rejected(self):
        self.assertEqual(clamp_momentum(0), 0.0)
        with self.assertRaises(SimulationError):
            clamp_momentum(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_rest_energy("heavy")
        with self.assertRaises(SimulationError):
            clamp_momentum("fast")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_rest_energy(math.nan)
        with self.assertRaises(SimulationError):
            clamp_momentum(math.inf)


class JsParticlePhysicsConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "particle-physics.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "particle-physics.js").read_text(encoding="utf-8")
        self.assertIn("Math.sqrt(pc * pc + mc2 * mc2)", source)
        for bound in ("1000.0", "0.1", "2000.0"):
            self.assertIn(bound, source)
        self.assertIn('register("particle_physics"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class ParticlePhysicsLabViewTests(TestCase):
    def setUp(self):
        self.concept = _particle_physics_concept()
        self.simulation = _make_simulation(self.concept)

    def test_particle_physics_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relativistic Energy and Momentum Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/particle-physics.js")

    def test_particle_physics_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-rest-energy")
        self.assertContains(response, "data-input-momentum")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_particle_physics(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_particle_physics_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_particle_physics(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Relativistic Energy and Momentum Lab", body)


class ParticlePhysicsExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _particle_physics_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Total energy came out to 500 MeV.",
                "rest_energy_mev": "300", "momentum_mev_c": "400",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_energy_mev"], 500.0, places=1)
        self.assertAlmostEqual(data["velocity_fraction_c"], 0.8, places=3)

    def test_zero_momentum_is_a_valid_observation(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "At rest, total energy equals rest energy.",
                "rest_energy_mev": "250", "momentum_mev_c": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_energy_mev"], 250.0, places=1)
        self.assertAlmostEqual(data["velocity_fraction_c"], 0.0, places=3)

    def test_browser_submitted_total_energy_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated",
                "rest_energy_mev": "300", "momentum_mev_c": "400",
                "total_energy_mev": "1", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["total_energy_mev"], 500.0, places=1)

    def test_observe_endpoint_rejects_non_positive_rest_energy(self):
        base = {
            "observation": "x",
            "rest_energy_mev": "300", "momentum_mev_c": "400",
        }
        for override in ({"rest_energy_mev": "0"}, {"rest_energy_mev": "-5"}):
            payload = dict(base, **override)
            response = self.client.post(self.observe_url, payload)
            self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_negative_momentum(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "rest_energy_mev": "300", "momentum_mev_c": "-1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_non_numeric_input(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "rest_energy_mev": "heavy", "momentum_mev_c": "400"},
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


class ParticlePhysicsTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _particle_physics_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Particles at High Speed", topic="Particle Physics", grade_level="12",
            duration_minutes=45,
            learning_objectives=["Relate a particle's momentum and rest energy to its total energy and speed."],
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
            observation="x", rest_energy_mev=300, momentum_mev_c=400,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "particle_physics")
        self.assertAlmostEqual(ctx.rest_energy_mev, 300.0, places=2)
        self.assertAlmostEqual(ctx.total_energy_mev, 500.0, places=1)
        self.assertAlmostEqual(ctx.velocity_fraction_c, 0.8, places=3)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("rest energy mc^2 = 300.00 MeV", prompt.user)
        self.assertIn("total energy", prompt.user)


# --- accessibility -------------------------------------------------------


class ParticlePhysicsAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _particle_physics_concept()
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
        self.assertIn('<label for="lab-rest-energy">', self.body)
        self.assertIn('<label for="lab-momentum">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class ParticlePhysicsXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _particle_physics_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Particles at High Speed", topic="Particle Physics", grade_level="12",
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
