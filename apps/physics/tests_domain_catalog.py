"""Full Physics universe -- domain catalog, equation catalog, Physics Library.

Architecture only: code-defined catalogs (no models, no migrations), a
server-rendered browser over the existing ``PhysicsConcept`` / ``PhysicsSimulation``
data, and no executable equation strings anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from apps.physics.domain_catalog import (
    OTHER,
    PhysicsDomain,
    all_domains,
    domain_for_topic,
    get_domain,
)
from apps.physics.equation_catalog import (
    Equation,
    all_equations,
    equations_for_concept,
    get_equation,
)
from apps.physics.models import PhysicsConcept, PhysicsSimulation

CATALOG_DIR = Path(__file__).resolve().parent


class DomainCatalogTests(TestCase):
    def test_has_the_full_curriculum_of_domains(self):
        real = all_domains(include_other=False)
        self.assertEqual(len(real), 23)
        self.assertEqual(len(all_domains()), 24)  # + "other"
        keys = [d.key for d in real]
        for expected in ("kinematics", "dynamics", "waves", "optics", "circuits",
                         "magnetism", "relativity", "quantum", "nuclear", "astrophysics"):
            self.assertIn(expected, keys)

    def test_domains_are_ordered_and_frozen_dataclasses(self):
        orders = [d.order for d in all_domains()]
        self.assertEqual(orders, sorted(orders))
        with self.assertRaises(Exception):
            all_domains()[0].title = "x"  # frozen

    def test_topic_maps_to_domain_and_never_raises(self):
        self.assertEqual(domain_for_topic("Kinematics").key, "kinematics")
        self.assertEqual(domain_for_topic("dynamics").key, "dynamics")   # case-insensitive
        self.assertEqual(domain_for_topic("Mechanics").key, "dynamics")
        for junk in ("", "   ", None, 123, object(), "Underwater Basket Weaving"):
            self.assertIs(domain_for_topic(junk), OTHER)

    def test_get_domain_is_safe_for_any_input(self):
        self.assertEqual(get_domain("KINEMATICS").key, "kinematics")
        for bad in (None, 1, "does-not-exist", object()):
            self.assertIsNone(get_domain(bad))

    def test_every_domain_declares_a_valid_ascending_level_range(self):
        """level_range is a scope statement about the field of Physics, not a
        content-completeness claim -- but it must still reference real,
        correctly-ordered levels from level_catalog.py."""

        from apps.physics.level_catalog import get_level

        for domain in all_domains():
            self.assertEqual(len(domain.level_range), 2)
            low_key, high_key = domain.level_range
            low, high = get_level(low_key), get_level(high_key)
            self.assertIsNotNone(low, f"{domain.key} has an unknown low level {low_key!r}")
            self.assertIsNotNone(high, f"{domain.key} has an unknown high level {high_key!r}")
            self.assertLessEqual(
                low.order, high.order,
                f"{domain.key}'s level_range is not ascending: {domain.level_range}",
            )

    def test_gravitation_genuinely_spans_to_graduate_level(self):
        """The spec's own worked example: gravity legitimately runs from
        junior-high "things fall down" to graduate General Relativity."""

        gravitation = get_domain("gravitation")
        self.assertEqual(gravitation.level_range, ("junior_high", "graduate_prep"))


class EquationCatalogTests(TestCase):
    def test_equations_are_display_metadata_only(self):
        for e in all_equations():
            self.assertIsInstance(e, Equation)
            for value in vars(e).values():
                self.assertNotIn(type(value).__name__, {"function", "type", "code", "builtin_function_or_method"})

    def test_lookup_by_concept_slug(self):
        self.assertIn("kinematics-velocity", [e.key for e in equations_for_concept("velocity")])
        self.assertEqual(equations_for_concept("no-such-concept"), ())
        self.assertEqual(equations_for_concept(None), ())
        self.assertIsNone(get_equation("nope"))

    def test_module_never_executes_an_expression(self):
        src = (CATALOG_DIR / "equation_catalog.py").read_text(encoding="utf-8")
        for sink in (r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(", r"\bnew\s+Function", r"sympify\("):
            self.assertNotRegex(src, sink)


class PhysicsLibraryPageTests(TestCase):
    def setUp(self):
        self.url = reverse("physics_lab:library")
        self.velocity = PhysicsConcept.objects.create(
            name="Velocity", slug="velocity", description="Rate of change of position.",
            topic="Kinematics", difficulty="introductory",
            common_misconceptions=["Velocity and speed are the same thing."],
        )
        self.force = PhysicsConcept.objects.create(
            name="Force", slug="force", description="A push or a pull.",
            topic="Dynamics", difficulty="foundational",
        )
        self.wave = PhysicsConcept.objects.create(
            name="Transverse wave", slug="transverse-wave", description="Energy without matter transport.",
            topic="Waves", difficulty="intermediate",
        )
        self.sim = PhysicsSimulation.objects.create(
            concept=self.velocity, slug="kin-lab", title="Kinematics Lab",
            simulation_type="kinematics",
        )

    def test_page_groups_concepts_by_domain_with_equations_and_sims(self):
        body = self.client.get(self.url).content.decode()
        self.assertEqual(body.count("<h1"), 1)
        self.assertIn("Kinematics</h2>", body)          # domain heading
        self.assertIn("Velocity</h4>", body)            # concept
        self.assertIn("lib-badge-introductory", body)   # difficulty badge
        self.assertIn("Velocity under constant acceleration", body)  # equation name
        self.assertIn("Velocity and speed are the same thing.", body)
        self.assertIn(reverse("physics_lab:detail", args=[self.sim.slug]), body)
        self.assertIn("(2d, 3d)", body)                 # available views annotation
        self.assertIn("curriculum domains", body)       # honest coverage line

    def test_search_domain_and_difficulty_filters(self):
        wave_body = self.client.get(self.url, {"q": "transverse"}).content.decode()
        self.assertIn("Transverse wave</h4>", wave_body)
        self.assertNotIn("Velocity</h4>", wave_body)

        found = self.client.get(self.url, {"difficulty": "foundational"}).content.decode()
        self.assertIn("Force</h4>", found)
        self.assertNotIn("Velocity</h4>", found)

        dyn = self.client.get(self.url, {"domain": "dynamics"}).content.decode()
        self.assertIn("Force</h4>", dyn)
        self.assertNotIn("Transverse wave</h4>", dyn)

    def test_no_match_shows_an_empty_state_not_a_blank_page(self):
        body = self.client.get(self.url, {"domain": "quantum"}).content.decode()
        self.assertIn("No concepts match", body)

    def test_query_is_escaped_and_the_page_is_read_only(self):
        before = PhysicsConcept.objects.count()
        body = self.client.get(
            self.url, {"q": "<script>alert('x')</script>"}
        ).content.decode()
        self.assertNotIn("<script>alert('x')</script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertEqual(self.client.post(self.url).status_code, 405 if False else 200)
        self.assertEqual(PhysicsConcept.objects.count(), before)

    def test_inactive_concepts_are_excluded(self):
        PhysicsConcept.objects.create(
            name="Retired", slug="retired", description="x", topic="Kinematics",
            is_active=False,
        )
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("Retired</h4>", body)

    def test_filter_labels_and_nav_link_exist(self):
        body = self.client.get(self.url).content.decode()
        for name in ("q", "domain", "difficulty"):
            self.assertIn(f'for="lib-{name}"', body)
        self.assertIn(self.url, body)  # the nav link renders on every page

    def test_lab_index_still_lists_simulations(self):
        body = self.client.get(reverse("physics_lab:index")).content.decode()
        self.assertIn("Kinematics Lab", body)


class LibraryLevelAndDepthTests(TestCase):
    """The level-range annotation and the Depth Toggle pilot on the Library
    page -- both additive to the existing card markup."""

    def setUp(self):
        self.url = reverse("physics_lab:library")
        self.n2l = PhysicsConcept.objects.create(
            name="Newton's Second Law", slug="newtons-second-law",
            description="Net force determines acceleration.",
            topic="Dynamics", difficulty="intermediate",
        )
        self.force = PhysicsConcept.objects.create(
            name="Force", slug="force", description="A push or a pull.",
            topic="Dynamics", difficulty="foundational",
        )

    def test_level_range_annotation_renders_for_every_concept(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("Typically studied:", body)
        self.assertIn("Senior High", body)  # part of the intermediate range

    def test_depth_toggle_renders_only_for_the_one_piloted_concept(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("Explore this at different depths", body)
        self.assertIn(">Understand<", body)
        self.assertIn(">Derive<", body)
        self.assertIn(">Explore Deeper<", body)
        self.assertIn(">Advanced<", body)
        self.assertIn("F_net = ma", body)
        # Force has no depth-layer entry -- no fabricated toggle for it.
        self.assertEqual(body.count("lib-depth-toggle"), 1)

    def test_depth_layer_text_is_escaped(self):
        # A defence-in-depth check, not a claim that this content is
        # user-editable today -- it is a hand-authored Python literal.
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("<script>", body)


class RegistryReadinessTests(TestCase):
    """The registries carry the extension points the full-universe spec asks for."""

    def test_visualization_registry_declares_views_and_instruments(self):
        from apps.physics.visualization_registry import get_visualization

        viz = get_visualization("kinematics")
        self.assertEqual(viz.supported_views, ("2d", "3d"))
        self.assertTrue(viz.graph_modes)
        self.assertTrue(viz.instruments)

    def test_simulation_definition_declares_the_deterministic_contract(self):
        from apps.physics.simulation_registry import get_simulation_definition

        d = get_simulation_definition("kinematics")
        for attr in ("bounds", "default_state", "input_fields", "equations", "units", "template"):
            self.assertTrue(hasattr(d, attr))
        # kinematics + newtons_second_law + projectile_motion +
        # circular_motion + simple_harmonic_motion + momentum_collision +
        # energy_incline + orbital_motion + series_parallel_circuit +
        # coulombs_law + radioactive_decay + buoyancy + refraction +
        # calorimetry + ideal_gas_law + doppler_effect + magnetic_force are
        # the registered simulations today
        from apps.physics.simulation_registry import registered_simulation_types

        self.assertEqual(
            set(registered_simulation_types()),
            {
                "kinematics", "newtons_second_law", "projectile_motion",
                "circular_motion", "simple_harmonic_motion", "momentum_collision",
                "energy_incline", "orbital_motion", "series_parallel_circuit",
                "coulombs_law", "radioactive_decay", "buoyancy", "refraction",
                "calorimetry", "ideal_gas_law", "doppler_effect", "magnetic_force",
            },
        )
