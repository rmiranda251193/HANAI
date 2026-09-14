import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_coulombs_law import (
    COULOMB_K,
    DEFAULT_CHARGE1_UC,
    DEFAULT_CHARGE2_UC,
    DEFAULT_SEPARATION_M,
    MAX_CHARGE_UC,
    MAX_SEPARATION_M,
    MIN_CHARGE_UC,
    MIN_SEPARATION_M,
    SimulationError,
    clamp_charge,
    clamp_separation,
    coulombs_law_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _coulomb_concept():
    return PhysicsConcept.objects.create(
        name="Electric charge and Coulomb's law",
        description=(
            "Electric charge comes in two types, positive and negative; "
            "like charges repel and opposite charges attract. Coulomb's "
            "law gives the force between two point charges, which falls "
            "off with the square of the distance between them, just like "
            "gravity."
        ),
        topic="Charge",
        equations=["F = k q1 q2 / r^2"],
        si_units=["C", "N"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _coulomb_concept(),
        title="Coulomb's Law Lab",
        simulation_type=PhysicsSimulation.SimulationType.COULOMBS_LAW,
        description="Explore F = k|q1 q2| / r^2 between two point charges.",
    )


# --- DOMAIN -----------------------------------------------------------------


class CoulombSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_coulomb_concept(self):
        concept = _coulomb_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.COULOMBS_LAW,
        )

    def test_seed_simulations_creates_coulomb_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="coulombs-law").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="coulombs-law")
        self.assertEqual(sim.simulation_type, "coulombs_law")
        self.assertEqual(sim.concept.name, "Electric charge and Coulomb's law")

    def test_seed_simulations_is_idempotent_for_coulomb(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="coulombs-law").count(), 1
        )

    def test_other_simulations_still_seed_alongside_it(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        for slug in (
            "kinematics", "newtons-second-law", "projectile-motion",
            "circular-motion", "simple-harmonic-motion", "momentum-collision",
            "energy-incline", "orbital-motion", "series-parallel-circuit",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class CoulombMathTests(TestCase):
    def test_worked_example(self):
        state = coulombs_law_state(charge1=3, charge2=-2, separation=1)
        expected_force = COULOMB_K * abs(3e-6 * -2e-6) / 1.0
        expected_pe = COULOMB_K * 3e-6 * -2e-6 / 1.0
        self.assertAlmostEqual(state["force_n"], expected_force, places=8)
        self.assertAlmostEqual(state["potential_energy_j"], expected_pe, places=8)
        self.assertTrue(state["is_attractive"])
        self.assertLess(state["potential_energy_j"], 0)

    def test_like_charges_always_repel(self):
        for q1, q2 in ((3, 5), (-3, -5), (1, 1), (-1, -1)):
            state = coulombs_law_state(charge1=q1, charge2=q2, separation=1)
            self.assertFalse(state["is_attractive"])
            self.assertGreater(state["potential_energy_j"], 0)

    def test_opposite_charges_always_attract(self):
        for q1, q2 in ((3, -5), (-3, 5), (1, -1), (-1, 1)):
            state = coulombs_law_state(charge1=q1, charge2=q2, separation=1)
            self.assertTrue(state["is_attractive"])
            self.assertLess(state["potential_energy_j"], 0)

    def test_zero_charge_gives_zero_force_and_zero_energy(self):
        state = coulombs_law_state(charge1=0, charge2=5, separation=1)
        self.assertAlmostEqual(state["force_n"], 0.0, places=10)
        self.assertAlmostEqual(state["potential_energy_j"], 0.0, places=10)
        self.assertFalse(state["is_attractive"])

    def test_force_is_symmetric_in_the_two_charges(self):
        state_ab = coulombs_law_state(charge1=4, charge2=-3, separation=2)
        state_ba = coulombs_law_state(charge1=-3, charge2=4, separation=2)
        self.assertAlmostEqual(state_ab["force_n"], state_ba["force_n"], places=10)

    def test_inverse_square_law_quarters_force_when_distance_doubles(self):
        near = coulombs_law_state(charge1=4, charge2=4, separation=1)
        far = coulombs_law_state(charge1=4, charge2=4, separation=2)
        self.assertAlmostEqual(far["force_n"], near["force_n"] / 4.0, places=10)

    def test_force_equals_charge_times_the_others_field(self):
        state = coulombs_law_state(charge1=5, charge2=-3, separation=1.5)
        q1_c = abs(5e-6)
        q2_c = abs(-3e-6)
        self.assertAlmostEqual(
            state["force_n"], q1_c * state["field_2_at_1_n_per_c"], places=10
        )
        self.assertAlmostEqual(
            state["force_n"], q2_c * state["field_1_at_2_n_per_c"], places=10
        )

    def test_multiple_parameter_sets_are_deterministic(self):
        for q1, q2, r in ((3, -2, 1), (8, 8, 0.1), (-1, -1, 5)):
            first = coulombs_law_state(charge1=q1, charge2=q2, separation=r)
            second = coulombs_law_state(charge1=q1, charge2=q2, separation=r)
            self.assertEqual(first, second)

    def test_out_of_range_charges_are_clamped_not_rejected(self):
        self.assertEqual(clamp_charge(999), MAX_CHARGE_UC)
        self.assertEqual(clamp_charge(-999), MIN_CHARGE_UC)

    def test_zero_and_negative_charge_are_not_rejected(self):
        # Unlike mass/resistance/voltage, charge is genuinely allowed to be
        # zero or negative -- this is the one deliberate difference from
        # every other clamp_* function in this project.
        self.assertEqual(clamp_charge(0), 0.0)
        self.assertEqual(clamp_charge(-3.5), -3.5)

    def test_separation_is_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_separation(999), MAX_SEPARATION_M)
        self.assertEqual(clamp_separation(0.0001), MIN_SEPARATION_M)

    def test_non_positive_separation_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_separation(0)
        with self.assertRaises(SimulationError):
            clamp_separation(-1)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_charge("heavy")
        with self.assertRaises(SimulationError):
            clamp_separation("far")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_charge(math.nan)
        with self.assertRaises(SimulationError):
            clamp_separation(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = coulombs_law_state(
            charge1=DEFAULT_CHARGE1_UC, charge2=DEFAULT_CHARGE2_UC, separation=DEFAULT_SEPARATION_M
        )
        self.assertGreater(state["force_n"], 0)
        # The default is opposite-signed on purpose -- it shows the one
        # behaviour gravity (Orbital Motion) can never show.
        self.assertTrue(state["is_attractive"])


class JsCoulombConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "coulombs-law.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "coulombs-law.js").read_text(encoding="utf-8")
        self.assertIn("8.99e9", source)
        self.assertIn("Math.abs(q1 * q2)", source)
        for bound in ("-8.0", "8.0", "0.1", "5.0"):
            self.assertIn(bound, source)
        self.assertIn('register("coulombs_law"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class CoulombLabViewTests(TestCase):
    def setUp(self):
        self.concept = _coulomb_concept()
        self.simulation = _make_simulation(self.concept)

    def test_coulomb_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coulomb&#x27;s Law Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/coulombs-law.js")

    def test_coulomb_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-charge1")
        self.assertContains(response, "data-input-charge2")
        self.assertContains(response, "data-input-separation")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_coulomb(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_coulomb_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_coulomb(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Coulomb", body)


class CoulombExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _coulomb_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "They pulled toward each other.", "charge1_uc": "3",
                "charge2_uc": "-2", "separation_m": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_force = COULOMB_K * abs(3e-6 * -2e-6) / 1.0
        # The JSON response rounds to 4 decimal places for display -- see
        # views.py's experiment_observe; CoulombMathTests above checks full
        # precision directly against coulombs_law_state().
        self.assertAlmostEqual(data["force_n"], expected_force, places=4)
        self.assertTrue(data["is_attractive"])

    def test_browser_submitted_force_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "charge1_uc": "3", "charge2_uc": "-2",
                "separation_m": "1", "force_n": "999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_force = COULOMB_K * abs(3e-6 * -2e-6) / 1.0
        self.assertAlmostEqual(data["force_n"], expected_force, places=4)

    def test_observe_endpoint_accepts_zero_charge(self):
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "charge1_uc": "0", "charge2_uc": "5", "separation_m": "1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["force_n"], 0.0, places=6)

    def test_observe_endpoint_labels_zero_charge_as_no_force_not_repulsive(self):
        # A zero force is neither attractive nor repulsive -- calling it
        # "repulsive" (the bare is_attractive=False case) would be wrong,
        # not just imprecise, since there's no force pushing anything apart.
        response = self.client.post(
            self.observe_url,
            {"observation": "x", "charge1_uc": "0", "charge2_uc": "5", "separation_m": "1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("no force", data["message"])
        self.assertNotIn("repulsive", data["message"])

    def test_observe_endpoint_rejects_non_positive_separation(self):
        for bad_separation in ("0", "-1"):
            response = self.client.post(
                self.observe_url,
                {
                    "observation": "x", "charge1_uc": "3", "charge2_uc": "-2",
                    "separation_m": bad_separation,
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


class CoulombTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _coulomb_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Attract or Repel", topic="Charge", grade_level="10",
            duration_minutes=45,
            learning_objectives=["Relate charge sign and separation to the Coulomb force."],
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
            observation="x", charge1_uc=3, charge2_uc=-2, separation_m=1,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "coulombs_law")
        self.assertEqual(ctx.charge1_uc, 3.0)
        self.assertTrue(ctx.is_attractive)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("charge 1 = 3.00 uC", prompt.user)
        self.assertIn("attractive", prompt.user)


# --- accessibility -------------------------------------------------------


class CoulombAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _coulomb_concept()
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
        self.assertIn('<label for="lab-charge1">', self.body)
        self.assertIn('<label for="lab-charge2">', self.body)
        self.assertIn('<label for="lab-separation">', self.body)

    def test_real_labels_for_text_areas(self):
        self.assertIn('<label for="exp-prediction">', self.body)
        self.assertIn('<label for="exp-observation">', self.body)
        self.assertIn('<label for="exp-explanation">', self.body)

    def test_svg_has_role_and_description(self):
        self.assertIn('role="img"', self.body)
        self.assertIn("<desc", self.body)

    def test_aria_live_regions_present(self):
        self.assertIn('aria-live="polite"', self.body)


class CoulombXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _coulomb_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Attract or Repel", topic="Charge", grade_level="10",
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
