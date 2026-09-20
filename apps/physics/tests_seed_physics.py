"""``seed_physics`` PHYSICS_TOPICS -- content, not architecture.

Verifies the topic-population half of the existing ``seed_physics`` command
is idempotent, spans domains well beyond Kinematics/Dynamics, never executes
an equation string, and that the Physics Library actually surfaces the
result honestly (concepts vs. interactive labs are reported separately).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.physics.domain_catalog import domain_for_topic
from apps.physics.models import PhysicsConcept

COMMAND_FILE = (
    Path(__file__).resolve().parent / "management" / "commands" / "seed_physics.py"
)


class SeedPhysicsTopicsTests(TestCase):
    def test_seeds_a_large_set_of_concepts_across_many_domains(self):
        before = PhysicsConcept.objects.count()
        call_command("seed_physics")
        after = PhysicsConcept.objects.count()
        self.assertGreaterEqual(after - before, 70)

        seen_domains = {
            domain_for_topic(topic).key
            for topic in PhysicsConcept.objects.values_list("topic", flat=True)
        }
        # Well beyond just Kinematics/Dynamics -- most of the 23-domain catalog.
        for expected in ("thermodynamics", "waves", "optics", "circuits",
                          "relativity", "quantum", "nuclear", "astrophysics"):
            self.assertIn(expected, seen_domains)

    def test_is_idempotent(self):
        call_command("seed_physics")
        first_count = PhysicsConcept.objects.count()
        call_command("seed_physics")
        second_count = PhysicsConcept.objects.count()
        self.assertEqual(first_count, second_count)

    def test_reruns_update_rather_than_duplicate_a_known_row(self):
        call_command("seed_physics")
        call_command("seed_physics")
        self.assertEqual(
            PhysicsConcept.objects.filter(name="Time dilation").count(), 1
        )

    def test_every_seeded_row_has_a_valid_difficulty_and_nonempty_description(self):
        call_command("seed_physics")
        valid = {c[0] for c in PhysicsConcept.Difficulty.choices}
        for concept in PhysicsConcept.objects.all():
            self.assertIn(concept.difficulty, valid)
            self.assertTrue(concept.description.strip())

    def test_command_never_executes_an_equation_string(self):
        src = COMMAND_FILE.read_text(encoding="utf-8")
        for sink in (r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(", r"\bnew\s+Function"):
            self.assertNotRegex(src, sink)


class LibraryReflectsSeededTopicsTests(TestCase):
    def setUp(self):
        call_command("seed_physics")
        self.url = reverse("physics_lab:library")

    def test_previously_empty_domains_now_render(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("Astrophysics and Space Physics</h2>", body)
        self.assertIn("Black holes</h4>", body)
        self.assertIn("Time dilation</h4>", body)

    def test_plain_formula_and_si_units_render_for_a_seeded_concept(self):
        body = self.client.get(self.url, {"q": "kinetic energy"}).content.decode()
        self.assertIn("Kinetic energy</h4>", body)
        self.assertIn("KE = 1/2 m v^2", body)
        self.assertIn("SI units:", body)

    def test_coverage_counts_most_of_the_curriculum(self):
        from apps.physics.domain_catalog import all_domains

        total = len(all_domains(include_other=False))
        body = self.client.get(self.url).content.decode()
        self.assertIn(f"of {total} curriculum domains", body)
        # At least half the real domains now have content (was 2 of 23 before
        # the curriculum grew from 23 to 31 domains).
        match = re.search(rf"covers\s+(\d+)\s+of {total}", body)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 15)
        # Interactive labs are honestly reported as a smaller, separate count.
        labs_match = re.search(r"interactive labs exist for\s+(\d+)\s+of them", body)
        self.assertIsNotNone(labs_match)
        self.assertLess(int(labs_match.group(1)), int(match.group(1)))
