"""Step 24 -- the reusable simulation registry itself (architecture tests)."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import PhysicsConcept, PhysicsSimulation
from .simulation_registry import get_simulation_definition, registered_simulation_types


class SimulationRegistryTests(TestCase):
    def test_newtons_second_law_definition_resolves(self):
        definition = get_simulation_definition("newtons_second_law")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.template, "physics/newtons_second_law.html")
        self.assertIn("mass_kg", definition.input_fields)
        self.assertIn("force_n", definition.input_fields)

    def test_kinematics_definition_resolves(self):
        definition = get_simulation_definition("kinematics")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.template, "physics/kinematics.html")
        self.assertIn("initial_position_m", definition.input_fields)
        self.assertIn("initial_velocity_m_s", definition.input_fields)
        self.assertIn("acceleration_m_s2", definition.input_fields)
        self.assertIn("time_s", definition.input_fields)

    def test_unknown_simulation_type_fails_safely(self):
        self.assertIsNone(get_simulation_definition("quantum_tunneling"))
        self.assertIsNone(get_simulation_definition(""))
        self.assertIsNone(get_simulation_definition(None))

    def test_registry_ordering_is_deterministic(self):
        first = registered_simulation_types()
        second = registered_simulation_types()
        self.assertEqual(first, second)
        self.assertEqual(first, tuple(sorted(first)))
        self.assertIn("newtons_second_law", first)
        self.assertIn("kinematics", first)

    def test_no_executable_expressions_are_stored_or_evaluated(self):
        """The registry is a plain Python dict of dataclasses populated at
        import time. Nothing in this module (or the modules that register into
        it) uses eval/exec, and no field is a database-stored string that gets
        executed."""

        import inspect

        from . import simulation_registry, simulations, simulations_kinematics

        for module in (simulation_registry, simulations, simulations_kinematics):
            source = inspect.getsource(module)
            self.assertNotIn("eval(", source)
            self.assertNotIn("exec(", source)

    def test_inactive_simulation_is_not_exposed_on_the_index(self):
        concept = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="d", topic="Dynamics"
        )
        sim = PhysicsSimulation.objects.create(
            concept=concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
            is_active=False,
        )
        response = self.client.get(reverse("physics_lab:index"))
        self.assertNotContains(response, sim.title)

    def test_lab_index_shows_both_active_simulations_after_seeding(self):
        out = StringIO()
        call_command("seed_physics", stdout=out)
        call_command("seed_simulations", stdout=out)
        response = self.client.get(reverse("physics_lab:index"))
        # Apostrophes are HTML-escaped by Django's autoescaping.
        self.assertContains(response, "Newton&#x27;s Second Law Lab")
        self.assertContains(response, "Kinematics")
        n2l = PhysicsSimulation.objects.get(slug="newtons-second-law")
        kin = PhysicsSimulation.objects.get(slug="kinematics")
        self.assertContains(response, reverse("physics_lab:detail", args=[n2l.slug]))
        self.assertContains(response, reverse("physics_lab:detail", args=[kin.slug]))
