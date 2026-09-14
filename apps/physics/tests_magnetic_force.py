import math
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.lessons.models import Lesson

from .models import PhysicsConcept, PhysicsSimulation
from .simulations_magnetic_force import (
    DEFAULT_CHARGE_MAGNITUDE_C,
    DEFAULT_FIELD_T,
    DEFAULT_MASS_KG,
    DEFAULT_POSITIVE_CHARGE,
    DEFAULT_SPEED_M_S,
    MAX_CHARGE_MAGNITUDE_C,
    MAX_FIELD_T,
    MAX_MASS_KG,
    MAX_SPEED_M_S,
    MAX_TIME_S,
    MIN_CHARGE_MAGNITUDE_C,
    MIN_FIELD_T,
    MIN_MASS_KG,
    MIN_SPEED_M_S,
    SimulationError,
    clamp_charge_magnitude,
    clamp_field,
    clamp_mass,
    clamp_positive_charge,
    clamp_speed,
    clamp_time,
    magnetic_force_state,
)

JS_DIR = Path(settings.BASE_DIR) / "static" / "js" / "physics"


def _magnetic_force_concept():
    return PhysicsConcept.objects.create(
        name="Magnetic force on a moving charge",
        description=(
            "A charged particle moving through a magnetic field feels a "
            "force perpendicular to both its velocity and the field, so a "
            "magnetic field can change a moving charge's direction but "
            "never its speed."
        ),
        topic="Magnetism",
        equations=["F = q v B sin(theta)"],
        si_units=["N"],
    )


def _make_simulation(concept=None):
    return PhysicsSimulation.objects.create(
        concept=concept or _magnetic_force_concept(),
        title="Magnetic Force on a Moving Charge Lab",
        simulation_type=PhysicsSimulation.SimulationType.MAGNETIC_FORCE,
        description="Explore F = |q|vB for a charge circling in a magnetic field.",
    )


# --- DOMAIN -----------------------------------------------------------------


class MagneticForceSimulationModelTests(TestCase):
    def test_simulation_can_be_created_with_generated_slug(self):
        simulation = _make_simulation()
        self.assertTrue(simulation.slug)
        self.assertTrue(simulation.is_active)

    def test_simulation_is_linked_to_magnetic_force_concept(self):
        concept = _magnetic_force_concept()
        simulation = _make_simulation(concept)
        self.assertEqual(simulation.concept, concept)
        self.assertIn(simulation, concept.simulations.all())
        self.assertEqual(
            simulation.simulation_type,
            PhysicsSimulation.SimulationType.MAGNETIC_FORCE,
        )

    def test_seed_simulations_creates_magnetic_force_row(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="magnetic-force").count(), 1
        )
        sim = PhysicsSimulation.objects.get(slug="magnetic-force")
        self.assertEqual(sim.simulation_type, "magnetic_force")
        self.assertEqual(sim.concept.name, "Magnetic force on a moving charge")

    def test_seed_simulations_is_idempotent_for_magnetic_force(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        call_command("seed_simulations", stdout=out)
        self.assertEqual(
            PhysicsSimulation.objects.filter(slug="magnetic-force").count(), 1
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
            "calorimetry", "ideal-gas-law", "doppler-effect",
        ):
            self.assertEqual(PhysicsSimulation.objects.filter(slug=slug).count(), 1)


# --- DETERMINISTIC REFERENCE PHYSICS -------------------------------------


class MagneticForceMathTests(TestCase):
    def test_speed_never_changes_even_though_direction_does(self):
        # The concept's own central claim: the magnetic force can change
        # direction but never speed.
        for t in (0, 1, 3, 5, 10, 15, 20):
            state = magnetic_force_state(
                charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=t
            )
            self.assertAlmostEqual(state["current_speed_m_s"], 10.0, places=6)

    def test_period_is_independent_of_speed(self):
        slow = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=5, field=2, time=0
        )
        fast = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=40, field=2, time=0
        )
        self.assertAlmostEqual(slow["period_s"], fast["period_s"], places=6)

    def test_radius_scales_linearly_with_speed(self):
        slow = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=5, field=2, time=0
        )
        fast = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=0
        )
        self.assertAlmostEqual(fast["radius_m"], slow["radius_m"] * 2, places=6)

    def test_positive_and_negative_charges_circle_opposite_ways(self):
        positive = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=0.01
        )
        negative = magnetic_force_state(
            charge_magnitude=1, positive_charge=0, mass=0.1, speed=10, field=2, time=0.01
        )
        # Starting on the +x axis moving toward +y, a positive charge should
        # have moved toward +y (theta > 0); a negative charge toward -y.
        self.assertGreater(positive["position_y_m"], 0)
        self.assertLess(negative["position_y_m"], 0)

    def test_orbit_stays_at_a_fixed_distance_from_the_center(self):
        for t in (0, 1, 3, 5, 10):
            state = magnetic_force_state(
                charge_magnitude=1.5, positive_charge=1, mass=0.2, speed=15, field=1.5, time=t
            )
            distance = math.hypot(state["position_x_m"], state["position_y_m"])
            self.assertAlmostEqual(distance, state["radius_m"], places=5)

    def test_force_scales_with_charge_speed_and_field(self):
        base = magnetic_force_state(
            charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=0
        )
        double_charge = magnetic_force_state(
            charge_magnitude=2, positive_charge=1, mass=0.1, speed=10, field=2, time=0
        )
        self.assertAlmostEqual(double_charge["force_n"], base["force_n"] * 2, places=6)

    def test_multiple_timestamps_are_deterministic(self):
        for t in (0, 0.5, 1, 2, 5):
            first = magnetic_force_state(
                charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=t
            )
            second = magnetic_force_state(
                charge_magnitude=1, positive_charge=1, mass=0.1, speed=10, field=2, time=t
            )
            self.assertEqual(first, second)

    def test_time_is_clamped_to_the_supported_window(self):
        self.assertEqual(clamp_time(999), MAX_TIME_S)

    def test_negative_time_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_time(-1)

    def test_out_of_range_values_are_clamped_to_ui_bounds(self):
        self.assertEqual(clamp_charge_magnitude(999), MAX_CHARGE_MAGNITUDE_C)
        self.assertEqual(clamp_charge_magnitude(0.001), MIN_CHARGE_MAGNITUDE_C)
        self.assertEqual(clamp_mass(999), MAX_MASS_KG)
        self.assertEqual(clamp_mass(0.0001), MIN_MASS_KG)
        self.assertEqual(clamp_speed(999), MAX_SPEED_M_S)
        self.assertEqual(clamp_speed(0.001), MIN_SPEED_M_S)
        self.assertEqual(clamp_field(999), MAX_FIELD_T)
        self.assertEqual(clamp_field(0.001), MIN_FIELD_T)

    def test_positive_charge_flag_rounds_to_zero_or_one(self):
        self.assertEqual(clamp_positive_charge(1), 1.0)
        self.assertEqual(clamp_positive_charge(0.9), 1.0)
        self.assertEqual(clamp_positive_charge(0.4), 0.0)
        self.assertEqual(clamp_positive_charge(0), 0.0)

    def test_non_positive_charge_magnitude_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_charge_magnitude(0)
        with self.assertRaises(SimulationError):
            clamp_charge_magnitude(-1)

    def test_non_positive_mass_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(0)

    def test_non_positive_speed_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_speed(0)

    def test_non_positive_field_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_field(0)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_charge_magnitude("lots")

    def test_nan_and_infinity_are_rejected(self):
        with self.assertRaises(SimulationError):
            clamp_mass(math.nan)
        with self.assertRaises(SimulationError):
            clamp_field(math.inf)

    def test_default_state_is_a_valid_worked_example(self):
        state = magnetic_force_state(
            charge_magnitude=DEFAULT_CHARGE_MAGNITUDE_C,
            positive_charge=DEFAULT_POSITIVE_CHARGE,
            mass=DEFAULT_MASS_KG,
            speed=DEFAULT_SPEED_M_S,
            field=DEFAULT_FIELD_T,
            time=0,
        )
        self.assertGreater(state["radius_m"], 0)
        self.assertAlmostEqual(state["current_speed_m_s"], DEFAULT_SPEED_M_S, places=6)


class JsMagneticForceConsistencyTests(TestCase):
    def test_js_file_exists(self):
        self.assertTrue((JS_DIR / "magnetic-force.js").is_file())

    def test_js_mirrors_the_python_formula_and_bounds(self):
        source = (JS_DIR / "magnetic-force.js").read_text(encoding="utf-8")
        self.assertIn("(q * b) / m", source)
        self.assertIn("v / omega", source)
        for bound in ("0.5", "3.0", "0.01", "2.0", "1.0", "50.0", "5.0"):
            self.assertIn(bound, source)
        self.assertIn('register("magnetic_force"', source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("new Function(", source)


# --- VIEWS -------------------------------------------------------------------


class MagneticForceLabViewTests(TestCase):
    def setUp(self):
        self.concept = _magnetic_force_concept()
        self.simulation = _make_simulation(self.concept)

    def test_magnetic_force_lab_loads(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Magnetic Force on a Moving Charge Lab")
        self.assertContains(response, "Idealized model")
        self.assertContains(response, "js/physics/lab.js")
        self.assertContains(response, "js/physics/magnetic-force.js")

    def test_magnetic_force_controls_render(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, "data-input-charge-magnitude")
        self.assertContains(response, "data-input-positive-charge")
        self.assertContains(response, "data-input-mass")
        self.assertContains(response, "data-input-speed")
        self.assertContains(response, "data-input-field")

    def test_progress_bar_present(self):
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertContains(response, 'class="lab-progress"')
        self.assertContains(response, "js/physics/lab-progress.js")

    def test_other_simulations_still_load_alongside_magnetic_force(self):
        kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics"
        )
        kin = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        response = self.client.get(reverse("physics_lab:detail", args=[kin.slug]))
        self.assertEqual(response.status_code, 200)

    def test_inactive_magnetic_force_simulation_is_not_found(self):
        self.simulation.is_active = False
        self.simulation.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("physics_lab:detail", args=[self.simulation.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_lab_index_lists_magnetic_force(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Magnetic Force on a Moving Charge Lab", body)


class MagneticForceExperimentFlowTests(TestCase):
    def setUp(self):
        from apps.students.models import StudentProfile

        self.concept = _magnetic_force_concept()
        self.simulation = _make_simulation(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")
        self.observe_url = reverse(
            "physics_lab:experiment_observe", args=[self.simulation.slug]
        )

    def test_observe_endpoint_recomputes_server_values(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "Perfect circle.", "charge_magnitude_c": "1",
                "positive_charge": "1", "mass_kg": "0.1", "speed_m_s": "10",
                "field_t": "2", "time_s": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(data["current_speed_m_s"], 10.0, places=2)

    def test_browser_submitted_radius_is_ignored(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "manipulated", "charge_magnitude_c": "1",
                "positive_charge": "1", "mass_kg": "0.1", "speed_m_s": "10",
                "field_t": "2", "time_s": "1", "radius_m": "999999", "is_correct": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_radius = (0.1 * 10) / (1 * 2)
        self.assertAlmostEqual(data["radius_m"], expected_radius, places=2)

    def test_observe_endpoint_rejects_non_positive_charge_mass_speed_or_field(self):
        base = {
            "observation": "x", "charge_magnitude_c": "1", "positive_charge": "1",
            "mass_kg": "0.1", "speed_m_s": "10", "field_t": "2", "time_s": "1",
        }
        for override in (
            {"charge_magnitude_c": "0"}, {"mass_kg": "0"},
            {"speed_m_s": "0"}, {"field_t": "0"},
        ):
            payload = dict(base, **override)
            response = self.client.post(self.observe_url, payload)
            self.assertEqual(response.status_code, 400)

    def test_observe_endpoint_rejects_negative_time(self):
        response = self.client.post(
            self.observe_url,
            {
                "observation": "x", "charge_magnitude_c": "1", "positive_charge": "1",
                "mass_kg": "0.1", "speed_m_s": "10", "field_t": "2", "time_s": "-1",
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


class MagneticForceTutorConnectionTests(TestCase):
    def setUp(self):
        self.concept = _magnetic_force_concept()
        self.simulation = _make_simulation(self.concept)

    def _lesson_with_concept(self):
        lesson = Lesson.objects.create(
            title="Circling Charges", topic="Magnetism", grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate magnetic force to circular motion of a charged particle."],
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
            observation="x", charge_magnitude_c=1, positive_charge=1,
            mass_kg=0.1, speed_m_s=10, field_t=2, time_s=1,
        )
        ctx = ExperimentContext.from_attempt(attempt)
        self.assertEqual(ctx.simulation_type, "magnetic_force")
        self.assertEqual(ctx.charge_magnitude_c, 1.0)
        self.assertTrue(ctx.is_positive_charge)
        self.assertAlmostEqual(ctx.velocity_m_s, 10.0, places=2)
        request = TutorRequest(
            lesson_title=lesson.title, topic=lesson.topic, grade_level=lesson.grade_level,
            concepts=(ConceptContext.from_concept(self.concept),),
            experiment=ctx, student_question="What happened?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("charge = 1.00 C", prompt.user)
        self.assertIn("does not depend on speed", prompt.user)


# --- accessibility -------------------------------------------------------


class MagneticForceAccessibilityTests(TestCase):
    def setUp(self):
        self.concept = _magnetic_force_concept()
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
        self.assertIn('<label for="lab-charge">', self.body)
        self.assertIn('<label for="lab-mass">', self.body)
        self.assertIn('<label for="lab-speed">', self.body)
        self.assertIn('<label for="lab-field">', self.body)
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


class MagneticForceXSSTests(TestCase):
    def test_xss_in_prediction_is_escaped_on_teacher_insights_page(self):
        from apps.students.experiment_services import record_experiment_prediction
        from apps.students.models import StudentProfile

        concept = _magnetic_force_concept()
        simulation = _make_simulation(concept)
        lesson = Lesson.objects.create(
            title="Circling Charges", topic="Magnetism", grade_level="11",
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
