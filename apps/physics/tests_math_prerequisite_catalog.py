from __future__ import annotations

from django.test import TestCase

from apps.physics.math_prerequisite_catalog import (
    MATH_TOPICS,
    all_math_topics,
    get_math_topic,
    math_prerequisites_for_level,
)


class MathPrerequisiteCatalogTests(TestCase):
    def test_topics_are_ordered_and_frozen(self):
        topics = all_math_topics()
        self.assertGreaterEqual(len(topics), 15)
        orders = [t.order for t in topics]
        self.assertEqual(orders, sorted(orders))
        with self.assertRaises(Exception):
            all_math_topics()[0].title = "x"

    def test_get_math_topic_is_safe_for_garbage(self):
        self.assertEqual(get_math_topic("ALGEBRA").key, "algebra")
        for bad in (None, 1, "", "not-a-topic", object()):
            self.assertIsNone(get_math_topic(bad))

    def test_discovery_level_assumes_no_math(self):
        self.assertEqual(math_prerequisites_for_level("discovery"), ())

    def test_prerequisites_are_cumulative_with_level(self):
        junior_high = {t.key for t in math_prerequisites_for_level("junior_high")}
        senior_high = {t.key for t in math_prerequisites_for_level("senior_high")}
        graduate = {t.key for t in math_prerequisites_for_level("graduate_prep")}
        self.assertTrue(junior_high.issubset(senior_high))
        self.assertTrue(senior_high.issubset(graduate))
        # Genuinely more is assumed at each step -- not a no-op mapping.
        self.assertLess(len(junior_high), len(senior_high))
        self.assertLess(len(senior_high), len(graduate))

    def test_senior_high_includes_trigonometry_and_vectors(self):
        keys = {t.key for t in math_prerequisites_for_level("senior_high")}
        self.assertIn("trigonometry", keys)
        self.assertIn("vectors", keys)
        self.assertNotIn("tensor_notation", keys)

    def test_graduate_prep_includes_the_most_advanced_topics(self):
        keys = {t.key for t in math_prerequisites_for_level("graduate_prep")}
        self.assertIn("tensor_notation", keys)
        self.assertIn("variational_calculus", keys)

    def test_unknown_level_returns_empty_never_raises(self):
        for bad in (None, 1, "", "not-a-level", object()):
            self.assertEqual(math_prerequisites_for_level(bad), ())

    def test_every_level_by_key_entry_references_a_real_topic(self):
        from apps.physics.math_prerequisite_catalog import MATH_BY_LEVEL

        valid_keys = {t.key for t in MATH_TOPICS}
        for level_key, topic_keys in MATH_BY_LEVEL.items():
            for key in topic_keys:
                self.assertIn(key, valid_keys, f"{level_key} references unknown topic {key!r}")
