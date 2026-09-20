"""The Depth Toggle -- a small, hand-picked set of concepts with real
multi-depth content. This module intentionally has no content for most
other concepts; that is the point, not a gap to silently work around."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.physics.depth_layers import DEPTH_LAYERS, DepthLayer, depth_layers_for

MODULE_PATH = Path(settings.BASE_DIR) / "apps" / "physics" / "depth_layers.py"

COVERED_CONCEPTS = (
    "newtons-second-law",
    "electric-charge-and-coulombs-law",
    "conservation-of-momentum",
)


class DepthLayersPilotTests(TestCase):
    def test_exactly_the_covered_concepts_have_depth_layers_today(self):
        # A deliberate scope guard: this must not silently grow into "fake
        # depth for every concept" without a conscious decision to add it.
        self.assertEqual(set(DEPTH_LAYERS.keys()), set(COVERED_CONCEPTS))

    def test_each_covered_concept_has_all_four_layers_in_order(self):
        for slug in COVERED_CONCEPTS:
            layers = depth_layers_for(slug)
            self.assertEqual(len(layers), 4, slug)
            self.assertEqual(
                [layer.key for layer in layers],
                ["understand", "derive", "explore_deeper", "advanced"],
                slug,
            )
            self.assertEqual(
                [layer.label for layer in layers],
                ["Understand", "Derive", "Explore Deeper", "Advanced"],
                slug,
            )

    def test_every_layer_has_real_explanation_text_and_an_equation(self):
        for slug in COVERED_CONCEPTS:
            for layer in depth_layers_for(slug):
                self.assertIsInstance(layer, DepthLayer)
                self.assertGreater(len(layer.explanation.strip()), 40, slug)
                self.assertTrue(layer.equation.strip(), slug)

    def test_lookup_is_case_insensitive_and_safe_for_garbage(self):
        self.assertEqual(len(depth_layers_for("NEWTONS-SECOND-LAW")), 4)
        for bad in (None, 1, "", "no-such-concept", object()):
            self.assertEqual(depth_layers_for(bad), ())

    def test_module_never_executes_an_expression(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for sink in (r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(", r"sympify\("):
            self.assertNotRegex(src, sink)

    def test_advanced_layer_ties_into_a_real_related_lab_concept(self):
        """Each Advanced layer was chosen to connect to real physics already
        built elsewhere, not to pad out the word count."""

        coulomb_advanced = depth_layers_for("electric-charge-and-coulombs-law")[-1]
        self.assertIn("photon", coulomb_advanced.explanation.lower())

        momentum_advanced = depth_layers_for("conservation-of-momentum")[-1]
        self.assertIn("gamma", momentum_advanced.explanation.lower())
        self.assertIn("relativistic", momentum_advanced.explanation.lower())
