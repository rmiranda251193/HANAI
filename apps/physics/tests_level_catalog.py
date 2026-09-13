"""The Physics level taxonomy -- code-defined data only, no model/migration.

Architecture-only tests: this pins the taxonomy's shape and the one thing
actually wired to it today (the difficulty -> level-range display mapping).
It does not test any per-concept leveled content -- see tests_depth_layers.py
for the one hand-authored pilot.
"""

from __future__ import annotations

from django.test import TestCase

from apps.physics.level_catalog import (
    LEVELS,
    PhysicsLevel,
    all_levels,
    get_level,
    level_range_for_difficulty,
)


class LevelTaxonomyTests(TestCase):
    def test_eight_levels_from_discovery_to_graduate_prep(self):
        levels = all_levels()
        self.assertEqual(len(levels), 8)
        self.assertEqual(levels[0].key, "discovery")
        self.assertEqual(levels[-1].key, "graduate_prep")

    def test_levels_are_ordered_and_frozen(self):
        orders = [lvl.order for lvl in all_levels()]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(set(orders)), len(orders))  # no duplicate order
        with self.assertRaises(Exception):
            all_levels()[0].title = "x"

    def test_every_level_has_real_text_not_placeholders(self):
        for lvl in LEVELS:
            self.assertIsInstance(lvl, PhysicsLevel)
            self.assertTrue(lvl.title.strip())
            self.assertTrue(lvl.stage.strip())
            self.assertGreater(len(lvl.blurb.strip()), 20)

    def test_get_level_is_case_insensitive_and_safe_for_garbage(self):
        self.assertEqual(get_level("SENIOR_HIGH").key, "senior_high")
        for bad in (None, 1, "", "   ", "not-a-level", object()):
            self.assertIsNone(get_level(bad))


class DifficultyToLevelRangeTests(TestCase):
    def test_every_real_difficulty_maps_to_a_valid_ascending_range(self):
        for difficulty in ("foundational", "introductory", "intermediate", "advanced"):
            result = level_range_for_difficulty(difficulty)
            self.assertIsNotNone(result)
            low, high = result
            self.assertIsInstance(low, PhysicsLevel)
            self.assertIsInstance(high, PhysicsLevel)
            self.assertLessEqual(low.order, high.order)

    def test_unknown_difficulty_returns_none_never_raises(self):
        for bad in (None, 1, "", "expert", object()):
            self.assertIsNone(level_range_for_difficulty(bad))

    def test_advanced_reaches_higher_than_foundational(self):
        found_low, found_high = level_range_for_difficulty("foundational")
        adv_low, adv_high = level_range_for_difficulty("advanced")
        self.assertLess(found_high.order, adv_high.order)
