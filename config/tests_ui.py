"""Aura-level UI/UX transformation -- regression tests.

This is a visual/navigation refinement pass over the existing product, not a
rebuild: no new frontend framework, no new backend architecture. These tests
pin the parts that actually changed -- the app-shell navigation (teacher-only
links must not be exposed to a student/anonymous session), the design-token
system, and the small CSS/markup additions (hero CTAs, button variants, the
Physics Lab step timeline, a no-JS collapsible mobile nav) -- plus the
accessibility landmarks every page already relies on.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.physics.models import PhysicsConcept, PhysicsSimulation

User = get_user_model()
BASE_DIR = Path(__file__).resolve().parent.parent
APP_CSS = (BASE_DIR / "static" / "css" / "app.css").read_text(encoding="utf-8")


def _primary_nav(body: str) -> str:
    match = re.search(r'<nav class="navigation" aria-label="Primary">.*?</nav>', body, re.S)
    assert match, "primary nav landmark not found"
    return match.group(0)


class NavigationRoleGatingTests(TestCase):
    """Do not expose teacher functionality to students (spec: no dead links,
    no leaked authority surfaces in the UI)."""

    def setUp(self):
        self.staff = User.objects.create_user("nav_teacher", password="pw", is_staff=True)

    def test_anonymous_session_sees_only_the_learn_group(self):
        nav = _primary_nav(self.client.get(reverse("home")).content.decode())
        self.assertIn("My Lessons", nav)
        self.assertIn("Physics Lab", nav)
        self.assertIn("Physics Library", nav)
        for teach_only in ("Create Lesson", "Students", "Question Bank", "Assessment Builder", "Admin", "Health"):
            self.assertNotIn(teach_only, nav)
        # the teacher-facing "Lessons" list link is not offered to a student session
        self.assertNotIn('href="' + reverse("lessons:list") + '"', nav)
        self.assertNotIn('href="' + reverse("lessons:create") + '"', nav)

    def test_staff_session_sees_the_teach_and_system_groups_too(self):
        self.client.force_login(self.staff)
        nav = _primary_nav(self.client.get(reverse("home")).content.decode())
        self.assertIn("Lessons", nav)
        self.assertIn("Create Lesson", nav)
        self.assertIn("Students", nav)
        self.assertIn("Analytics", nav)
        self.assertIn("Question Bank", nav)
        self.assertIn("Assessment Builder", nav)
        self.assertIn("Admin", nav)
        self.assertIn("Health", nav)
        # still has everything a student has -- staff can preview the learner side
        self.assertIn("My Lessons", nav)
        self.assertIn("Physics Lab", nav)

    def test_backend_access_to_lesson_create_is_unchanged(self):
        """The nav stops advertising it; the existing (backward-compatible,
        anonymous-allowed) view behaviour is untouched -- this is a UI-only
        change, not an authorization change."""
        self.assertEqual(self.client.get(reverse("lessons:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("lessons:create")).status_code, 200)

    def test_stale_physics_tutor_nav_label_is_gone(self):
        nav = _primary_nav(self.client.get(reverse("home")).content.decode())
        self.assertNotIn("Physics Tutor", nav)

    def test_role_indicator_shown_in_topbar(self):
        anon_body = self.client.get(reverse("home")).content.decode()
        self.assertIn("role-badge-student", anon_body)
        self.client.force_login(self.staff)
        staff_body = self.client.get(reverse("home")).content.decode()
        self.assertIn("role-badge-teacher", staff_body)
        self.assertIn("nav_teacher", staff_body)


class AccessibilityLandmarkTests(TestCase):
    def test_home_has_skip_link_main_landmark_and_one_h1(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="skip-link"', body)
        self.assertIn('href="#main-content"', body)
        self.assertIn('id="main-content"', body)
        self.assertIn('<nav class="navigation" aria-label="Primary">', body)
        self.assertEqual(body.count("<h1"), 1)

    def test_lessons_list_has_the_same_landmarks(self):
        body = self.client.get(reverse("lessons:list")).content.decode()
        self.assertIn('class="skip-link"', body)
        self.assertIn('id="main-content"', body)
        self.assertEqual(body.count("<h1"), 1)


class MobileNavCollapsibleTests(TestCase):
    def test_nav_is_wrapped_in_a_no_js_details_toggle(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('<details class="nav-toggle" open>', body)
        self.assertIn('class="nav-toggle-summary"', body)
        # the toggle needs no JavaScript -- native <details>/<summary> semantics
        self.assertNotIn("nav-toggle.js", body)


class HomeHeroTests(TestCase):
    def test_hero_has_two_clear_calls_to_action(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="hero-actions"', body)
        self.assertIn(">Explore Physics Lab<", body)
        self.assertIn(">Teacher Workspace<", body)
        self.assertIn(reverse("physics_lab:index"), body)
        self.assertIn(reverse("lessons:list"), body)


class DesignSystemTests(TestCase):
    """Design tokens exist and hard-coded semantic colours were consolidated
    onto them (spec: do not scatter hard-coded colors throughout templates)."""

    def test_design_tokens_are_declared(self):
        for token in (
            "--surface-elevated", "--text-secondary", "--success", "--warning",
            "--danger", "--focus", "--physics-accent", "--shadow-soft",
        ):
            self.assertIn(token + ":", APP_CSS)

    def test_semantic_colors_route_through_tokens_not_bare_hex(self):
        for bare_hex in ("#8be7af", "#ffad9f", "#ff8e7d", "#ffcabf", "#b8f1cb"):
            self.assertNotIn(bare_hex, APP_CSS)
        self.assertIn("var(--success)", APP_CSS)
        self.assertIn("var(--danger)", APP_CSS)

    def test_button_hierarchy_includes_ghost_and_danger(self):
        self.assertIn(".button-ghost", APP_CSS)
        self.assertIn(".button-danger", APP_CSS)

    def test_destructive_actions_use_the_danger_button(self):
        build = (BASE_DIR / "templates" / "lessons" / "build.html").read_text(encoding="utf-8")
        detail = (BASE_DIR / "templates" / "lessons" / "detail.html").read_text(encoding="utf-8")
        self.assertIn('class="button button-danger">Delete<', build)
        self.assertIn('class="button button-danger" type="submit">Reject<', detail)

    def test_cards_have_a_hover_and_focus_treatment(self):
        self.assertIn(".surface-card:hover", APP_CSS)
        self.assertIn(":focus-visible", APP_CSS)

    def test_reduced_motion_still_respected_for_new_hover_transforms(self):
        self.assertIn("@media (prefers-reduced-motion: no-preference) { .surface-card:hover", APP_CSS)


class PhysicsLabTimelineTests(TestCase):
    def test_step_timeline_connector_css_exists(self):
        self.assertIn(".lab-flow .lab-step-num::before", APP_CSS)
        self.assertIn(".lab-flow .lab-step:not(:last-child)::after", APP_CSS)


class HomeMotionTests(TestCase):
    """Restrained scroll-parallax + reveal-on-scroll for the home page
    (static/js/home-motion.js) -- HANAI's own palette/stack, no Tailwind.
    Every element must be fully visible without JavaScript."""

    def test_parallax_layers_and_reveal_targets_are_present(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="home-parallax"', body)
        self.assertIn("data-parallax-depth=", body)
        # both foundation-grid cards and the home-flow section reveal in
        self.assertEqual(body.count("data-reveal"), 3)
        self.assertIn("js/home-motion.js", body)
        # the hero's own copy is never gated behind a reveal (visible at rest)
        self.assertNotIn('<h1 data-reveal', body)

    def test_reveal_elements_default_to_visible_without_js(self):
        self.assertIn("[data-reveal] { opacity: 1; transform: none; }", APP_CSS)
        # only the JS-added class hides them pending reveal
        self.assertIn(".js-reveal-ready [data-reveal] {", APP_CSS)

    def test_reduced_motion_disables_parallax(self):
        src = (BASE_DIR / "static" / "js" / "home-motion.js").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", src)
        self.assertIn("reduced", src)

    def test_home_motion_script_has_no_unsafe_sinks(self):
        src = (BASE_DIR / "static" / "js" / "home-motion.js").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"\beval\s*\(")
        self.assertNotRegex(src, r"\bnew\s+Function\s*\(")
        self.assertNotIn("innerHTML", src)


class LabProgressBarTests(TestCase):
    """A presentation-only scroll-progress bar for the Kinematics step flow
    (static/js/physics/lab-progress.js) -- shares no DOM or events with the
    five existing Physics Lab scripts."""

    def setUp(self):
        concept = PhysicsConcept.objects.create(
            name="Velocity", description="Rate of change of position.", topic="Kinematics"
        )
        self.sim = PhysicsSimulation.objects.create(
            concept=concept, title="Kinematics Lab", simulation_type="kinematics"
        )
        self.url = reverse("physics_lab:detail", args=[self.sim.slug])

    def test_progress_bar_markup_and_script_present(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('class="lab-progress"', body)
        self.assertIn('id="labProgressFill"', body)
        self.assertIn("js/physics/lab-progress.js", body)

    def test_script_touches_only_its_own_elements(self):
        src = (BASE_DIR / "static" / "js" / "physics" / "lab-progress.js").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"\beval\s*\(")
        self.assertNotRegex(src, r"\bnew\s+Function\s*\(")
        self.assertNotIn("innerHTML", src)
        # only reads the flow container's geometry and writes its own bar
        self.assertIn('getElementById("labProgressFill")', src)
        self.assertIn('querySelector(".lab.lab-flow")', src)
