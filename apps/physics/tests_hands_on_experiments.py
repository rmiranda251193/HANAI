"""Hands-on, real-materials experiment companions -- inspired by (not copied
from) physicslab.app's pairing of virtual simulations with hands-on
experiments. Code-defined data only, no model/migration."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.physics.hands_on_experiments import (
    HANDS_ON_EXPERIMENTS,
    HandsOnExperiment,
    hands_on_experiment_for,
)
from apps.physics.models import PhysicsConcept, PhysicsSimulation

MODULE_PATH = Path(settings.BASE_DIR) / "apps" / "physics" / "hands_on_experiments.py"


class HandsOnExperimentCatalogTests(TestCase):
    def test_exactly_the_covered_simulation_types_have_an_entry(self):
        self.assertEqual(
            set(HANDS_ON_EXPERIMENTS.keys()),
            {
                "kinematics", "newtons_second_law", "projectile_motion",
                "circular_motion", "simple_harmonic_motion", "momentum_collision",
                "energy_incline", "orbital_motion", "series_parallel_circuit",
                "coulombs_law", "radioactive_decay", "buoyancy", "refraction",
                "calorimetry", "ideal_gas_law", "doppler_effect", "magnetic_force",
                "electromagnetic_induction", "bohr_model",
            },
        )

    def test_the_four_infeasible_types_deliberately_have_no_entry(self):
        """No fabricated hands-on companion for a phenomenon that genuinely
        cannot be reproduced at household/classroom scale -- see the module
        docstring for why each of these four is excluded on purpose."""

        for sim_type in (
            "time_dilation", "photoelectric_effect", "hubbles_law", "particle_physics",
        ):
            self.assertIsNone(hands_on_experiment_for(sim_type))

    def test_every_experiment_has_real_materials_steps_and_notes(self):
        for sim_type, experiment in HANDS_ON_EXPERIMENTS.items():
            self.assertIsInstance(experiment, HandsOnExperiment)
            self.assertTrue(experiment.title.strip())
            self.assertGreaterEqual(len(experiment.materials), 3)
            self.assertGreaterEqual(len(experiment.steps), 3)
            self.assertGreater(len(experiment.safety_note.strip()), 15)
            self.assertGreater(len(experiment.compare_note.strip()), 15)

    def test_lookup_is_case_insensitive_and_safe_for_garbage(self):
        self.assertIsNotNone(hands_on_experiment_for("KINEMATICS"))
        for bad in (None, 1, "", "no-such-simulation", object()):
            self.assertIsNone(hands_on_experiment_for(bad))

    def test_module_never_executes_an_expression(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for sink in (r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(", r"sympify\("):
            self.assertNotRegex(src, sink)


def _concept_and_sim(sim_type, name, title, slug):
    concept = PhysicsConcept.objects.create(
        name=name, description="d", topic="Dynamics",
    )
    return PhysicsSimulation.objects.create(
        concept=concept, title=title, slug=slug, simulation_type=sim_type,
    )


class HandsOnExperimentLabPageTests(TestCase):
    def test_kinematics_lab_shows_its_hands_on_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.KINEMATICS, "Acceleration",
            "Kinematics Lab", "kin-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("Try this with real materials: Time a ball rolling down a ramp", body)
        self.assertIn("A ball or marble", body)
        self.assertIn("Comparing with the virtual lab:", body)

    def test_newtons_second_law_lab_shows_its_own_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW, "Newton's Second Law",
            "Newton's Second Law Lab", "n2l-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("Pull a book with a rubber band", body)
        self.assertIn("A rubber band", body)

    def test_projectile_motion_lab_shows_its_own_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.PROJECTILE_MOTION, "Projectile motion",
            "Projectile Motion Lab", "proj-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("Launch a ball and measure its range", body)
        self.assertIn("open, safe outdoor space", body)

    def test_teacher_preview_still_shows_the_companion(self):
        """The hands-on companion is presentation-only reference material --
        it creates no evidence, so it stays visible in a read-only preview."""

        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.KINEMATICS, "Acceleration 2",
            "Kinematics Lab 2", "kin-lab-2",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug]), {"preview": "1"}
        ).content.decode()
        self.assertIn("Try this with real materials:", body)

    def test_orbital_motion_lab_shows_its_own_qualitative_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.ORBITAL_MOTION, "Orbital motion",
            "Orbital Motion Lab", "orbit-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("Spin a coin around the inside of a bowl", body)
        self.assertIn("QUALITATIVE analogy", body)

    def test_coulombs_law_lab_shows_its_own_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.COULOMBS_LAW, "Coulomb's law",
            "Coulomb's Law Lab", "coulomb-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("Charge a balloon", body)

    def test_bohr_model_lab_shows_its_own_companion(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.BOHR_MODEL, "The Bohr model",
            "The Bohr Model Lab", "bohr-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertIn("See real atomic spectral lines with a CD", body)

    def test_time_dilation_lab_has_no_hands_on_section(self):
        """One of the four deliberately-excluded types -- confirm the page
        simply omits the section rather than showing an empty one."""

        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.TIME_DILATION, "Time dilation",
            "Time Dilation Lab", "td-lab",
        )
        body = self.client.get(
            reverse("physics_lab:detail", args=[sim.slug])
        ).content.decode()
        self.assertNotIn("Try this with real materials:", body)

    def test_get_does_not_mutate(self):
        sim = _concept_and_sim(
            PhysicsSimulation.SimulationType.KINEMATICS, "Acceleration 3",
            "Kinematics Lab 3", "kin-lab-3",
        )
        from apps.students.models import ExperimentAttempt

        before = ExperimentAttempt.objects.count()
        self.client.get(reverse("physics_lab:detail", args=[sim.slug]))
        self.assertEqual(ExperimentAttempt.objects.count(), before)
