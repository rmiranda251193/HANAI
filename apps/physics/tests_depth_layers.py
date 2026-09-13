"""The Depth Toggle pilot -- Newton's Second Law is the ONE concept with real
multi-depth content. This module intentionally has no content for any other
concept; that is the point, not a gap to silently work around."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.physics.depth_layers import DEPTH_LAYERS, DepthLayer, depth_layers_for

MODULE_PATH = Path(settings.BASE_DIR) / "apps" / "physics" / "depth_layers.py"


class DepthLayersPilotTests(TestCase):
    def test_only_newtons_second_law_has_depth_layers_today(self):
        # A deliberate scope guard: this must not silently grow into "fake
        # depth for every concept" without a conscious decision to add it.
        self.assertEqual(set(DEPTH_LAYERS.keys()), {"newtons-second-law"})

    def test_newtons_second_law_has_all_four_layers_in_order(self):
        layers = depth_layers_for("newtons-second-law")
        self.assertEqual(len(layers), 4)
        self.assertEqual(
            [layer.key for layer in layers],
            ["understand", "derive", "explore_deeper", "advanced"],
        )
        self.assertEqual(
            [layer.label for layer in layers],
            ["Understand", "Derive", "Explore Deeper", "Advanced"],
        )

    def test_every_layer_has_real_explanation_text_and_an_equation(self):
        for layer in depth_layers_for("newtons-second-law"):
            self.assertIsInstance(layer, DepthLayer)
            self.assertGreater(len(layer.explanation.strip()), 40)
            self.assertTrue(layer.equation.strip())

    def test_lookup_is_case_insensitive_and_safe_for_garbage(self):
        self.assertEqual(len(depth_layers_for("NEWTONS-SECOND-LAW")), 4)
        for bad in (None, 1, "", "no-such-concept", object()):
            self.assertEqual(depth_layers_for(bad), ())

    def test_module_never_executes_an_expression(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        for sink in (r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(", r"sympify\("):
            self.assertNotRegex(src, sink)
