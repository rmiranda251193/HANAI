"""The inline icon set used by the premium light UI (base.html nav, topbar,
home.html hero/cards) -- a fixed, hand-authored SVG dict, not an icon-font
or CDN dependency."""

from __future__ import annotations

from django.template import Context, Template
from django.test import TestCase

from apps.physics.templatetags.icons import _ICONS, icon


class IconTagTests(TestCase):
    def test_known_icon_renders_an_svg(self):
        for name in _ICONS:
            markup = icon(name)
            self.assertTrue(markup.startswith("<svg"))
            self.assertIn("viewBox=\"0 0 24 24\"", markup)
            self.assertIn("</svg>", markup)

    def test_unknown_icon_renders_nothing(self):
        self.assertEqual(icon("no-such-icon"), "")

    def test_class_attribute_is_applied(self):
        markup = icon("home", cls="nav-icon")
        self.assertIn('class="nav-icon"', markup)

    def test_no_icon_contains_an_unsafe_sink(self):
        for name, inner in _ICONS.items():
            self.assertNotIn("<script", inner)
            self.assertNotIn("javascript:", inner)
            self.assertNotIn("onerror", inner)
            self.assertNotIn("onload", inner)

    def test_tag_loads_and_renders_in_a_real_template(self):
        tpl = Template("{% load icons %}{% icon 'flask' %}")
        rendered = tpl.render(Context({}))
        self.assertIn("<svg", rendered)
        self.assertIn("</svg>", rendered)

    def test_icons_are_aria_hidden_decorative_glyphs(self):
        # These render alongside real text labels (nav links, card titles) --
        # they must never be the only accessible name for a control.
        for name in _ICONS:
            self.assertIn('aria-hidden="true"', icon(name))
