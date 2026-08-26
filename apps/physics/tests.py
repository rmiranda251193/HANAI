from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import PhysicsConcept


class PhysicsConceptTests(TestCase):
    def test_slug_is_generated_from_name(self):
        concept = PhysicsConcept.objects.create(
            name="Test Motion",
            description="A test concept.",
            topic="Kinematics",
        )

        self.assertEqual(concept.slug, "test-motion")
        self.assertEqual(str(concept), "Test Motion")

    def test_seed_command_is_idempotent(self):
        output = StringIO()

        call_command("seed_physics", stdout=output)
        call_command("seed_physics", stdout=output)

        self.assertEqual(PhysicsConcept.objects.count(), 10)
        self.assertIn("0 created, 10 updated", output.getvalue())
