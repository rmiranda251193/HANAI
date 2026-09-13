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

    def test_hero_has_the_physics_headline_and_subline(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('<h1 class="hero-headline">PHYSICS</h1>', body)
        self.assertIn('class="hero-subline">Explore. Experiment. Understand.<', body)

    def test_hero_visual_illustration_is_decorative(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="hero-visual" aria-hidden="true"', body)
        self.assertIn('class="hero-atom"', body)


class TopbarTests(TestCase):
    def test_search_form_targets_the_real_physics_library_search(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="topbar-search"', body)
        self.assertIn(f'action="{reverse("physics_lab:library")}"', body)
        self.assertIn('name="q"', body)
        # a real, working destination -- not a decorative dead form
        response = self.client.get(reverse("physics_lab:library"), {"q": "velocity"})
        self.assertEqual(response.status_code, 200)

    def test_notification_button_has_no_fabricated_unread_badge(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="topbar-icon-button" aria-label="Notifications"', body)
        # no invented "you have unread notifications" claim with nothing behind it
        self.assertNotIn("topbar-badge", body)

    def test_avatar_uses_initials_not_a_fabricated_photo(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="topbar-avatar"', body)
        self.assertNotIn("<img", body)


class FeatureGridTests(TestCase):
    """The 6 homepage capability cards -- every link is a real, working
    destination; the one genuinely staff-gated capability (Teacher
    Analytics) never becomes a 403 dead end for a non-staff viewer."""

    _TITLES = (
        "AI Lesson Assistant", "Interactive Physics Lab", "AI Tutor",
        "Misconception Recovery", "Learning Evidence", "Teacher Analytics",
    )

    def test_all_six_cards_render_for_an_anonymous_session(self):
        body = self.client.get(reverse("home")).content.decode()
        for title in self._TITLES:
            self.assertIn(f"<h2>{title}</h2>", body)

    def test_teacher_analytics_card_is_not_a_clickable_dead_end_for_a_student(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('class="surface-card feature-card feature-card-static"', body)
        self.assertNotIn(reverse("teachers:analytics"), body)

    def test_teacher_analytics_card_links_out_for_staff(self):
        staff = get_user_model().objects.create_user("home_teacher", password="pw", is_staff=True)
        self.client.force_login(staff)
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn(reverse("teachers:analytics"), body)

    def test_every_card_link_resolves_without_a_403_for_an_anonymous_session(self):
        response = self.client.get(reverse("home"))
        body = response.content.decode()
        checked = 0
        for url in (
            reverse("lessons:create"), reverse("physics_lab:index"),
            reverse("students:home"), reverse("students:recommendations"),
            reverse("students:progress"),
        ):
            if url in body:
                checked += 1
                self.assertNotEqual(self.client.get(url).status_code, 403)
        self.assertEqual(checked, 5)


class DesignSystemTests(TestCase):
    """Design tokens exist and hard-coded semantic colours were consolidated
    onto them (spec: do not scatter hard-coded colors throughout templates)."""

    def test_no_root_token_is_self_referential(self):
        """Regression: a blanket find-and-replace once turned
        `--success: #8be7af;` into `--success: var(--success);` by matching
        the token's own definition line along with every usage site. A
        self-referential custom property is invalid CSS -- the browser
        drops the whole declaration, so anything using var(--success) (or
        --danger, etc.) silently renders as whatever it would without that
        declaration (usually an inherited or default color), with no error
        anywhere. This was live for a while before being caught by reading
        the file, not by any test -- so it's a test now."""

        root_match = re.search(r":root\s*\{(.*?)\}", APP_CSS, re.S)
        self.assertIsNotNone(root_match, "no :root block found in app.css")
        for line in root_match.group(1).splitlines():
            decl = re.match(r"\s*(--[\w-]+)\s*:\s*(.+?);", line)
            if not decl:
                continue
            name, value = decl.group(1), decl.group(2)
            self.assertNotIn(
                "var(" + name + ")", value,
                f"{name} is defined in terms of itself: {name}: {value};",
            )

    def test_design_tokens_are_declared(self):
        for token in (
            "--surface-elevated", "--text-secondary", "--success", "--warning",
            "--danger", "--focus", "--physics-accent", "--shadow-soft",
        ):
            self.assertIn(token + ":", APP_CSS)

    def test_semantic_colors_route_through_tokens_not_bare_hex(self):
        # Each hex value legitimately appears exactly once: the :root
        # definition of its token. Every other occurrence must be var(...).
        # (Values updated for the premium-light-scientific palette; the
        # invariant under test -- routed through tokens, not scattered -- is
        # unchanged.)
        css_outside_root = re.sub(r":root\s*\{.*?\}", "", APP_CSS, count=1, flags=re.S)
        for bare_hex in ("#1f8a4c", "#c22e22", "#a3251b", "#9c2a1f", "#2f7a4c"):
            self.assertNotIn(bare_hex, css_outside_root)
            self.assertIn(bare_hex, APP_CSS)  # still defined, just once, in :root
        self.assertIn("var(--success)", APP_CSS)
        self.assertIn("var(--danger)", APP_CSS)

    def test_repeated_field_and_text_colors_route_through_tokens(self):
        """--field-bg (form input background, ~16 identical literal
        occurrences), --text and --text-secondary were each already declared
        as tokens but the literal hex kept being used instead almost
        everywhere. Consolidated onto the tokens -- same exact colors, zero
        visual change, but now defined in exactly one place each. (Hex
        values updated for the premium-light-scientific palette.)"""

        css_outside_root = re.sub(r":root\s*\{.*?\}", "", APP_CSS, count=1, flags=re.S)
        for bare_hex in ("#f6faff", "#0c1b33", "#33455f"):
            self.assertNotIn(bare_hex, css_outside_root)
            self.assertIn(bare_hex, APP_CSS)
        self.assertIn("var(--field-bg)", APP_CSS)
        self.assertIn("var(--text-secondary)", APP_CSS)

    def test_instrument_screens_stay_dark_by_design(self):
        """The Physics Lab's SVG scene/graph and the 3D canvas are
        deliberately kept as dark "instrument readout" screens against the
        light workspace (Section 13/17 of the light-scientific-UI brief) --
        not an oversight left over from the old dark theme."""

        for selector in (".lab-scene", ".lab-graph-svg", ".physics3d-canvas"):
            self.assertIn(selector + " {", APP_CSS.replace("\n", " "))
        self.assertEqual(APP_CSS.count("background: rgba(9, 18, 29, .5);"), 3)

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


class PremiumLightThemeTests(TestCase):
    """"HANAI premium light scientific workspace" pass: the workspace moved
    from a dark theme to a light one, while the sidebar/nav stays dark navy
    on purpose for contrast and brand identity (design brief Section 2)."""

    def test_root_declares_a_light_color_scheme(self):
        root_match = re.search(r":root\s*\{(.*?)\}", APP_CSS, re.S)
        self.assertIsNotNone(root_match)
        self.assertIn("color-scheme: light", root_match.group(1))

    def test_nav_tokens_are_distinct_from_the_light_workspace_tokens(self):
        for token in ("--nav-bg", "--nav-text", "--nav-text-muted", "--nav-line", "--nav-accent"):
            self.assertIn(token + ":", APP_CSS)
        # the sidebar routes through the nav-* tokens, not the (now light)
        # generic --background/--text/--line tokens, so it stays dark navy
        self.assertIn(".sidebar { padding:", APP_CSS)
        sidebar_rule = re.search(r"\.sidebar \{[^}]*\}", APP_CSS).group(0)
        self.assertIn("var(--nav-bg)", sidebar_rule)
        self.assertIn("var(--nav-text)", sidebar_rule)
        self.assertNotIn("var(--background)", sidebar_rule)

    def test_no_dark_glass_surface_literals_remain_outside_instrument_screens(self):
        """Regression guard for the systematic pass that replaced the old
        dark-theme "glass card" literals (rgba(17,31,46,*) / rgba(9,18,29,.42))
        with light surface tokens across every template's shared CSS classes.
        Only the three deliberately-dark instrument screens keep a literal
        rgba(9,18,29,.5) background (see test_instrument_screens_stay_dark_by_design)."""

        self.assertNotIn("rgba(17, 31, 46", APP_CSS)
        self.assertNotIn("rgba(9, 18, 29, .42)", APP_CSS)
        self.assertIn("var(--surface-inset)", APP_CSS)

    def test_brand_reads_hanai_not_the_old_project_codename(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn('<span class="brand-name">HANAI</span>', body)
        self.assertIn("AI Physics Learning System", body)
        self.assertIn("<title>HANAI</title>", body)

    def test_primary_button_text_is_readable_on_the_new_accent(self):
        # var(--cyan) is now a saturated "electric physics blue" used as a
        # solid button fill -- its text must be light, not the old
        # near-black tuned for a pale cyan fill.
        self.assertIn(".button-primary { color: #ffffff; background: var(--cyan); }", APP_CSS)


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
        # the 6 feature cards and the home-flow section reveal in
        self.assertEqual(body.count("data-reveal"), 7)
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

    def test_newtons_second_law_lab_has_the_same_progress_bar(self):
        """Parity: both registered simulation templates share .lab-flow, so
        both should carry the same scroll-progress bar, not just Kinematics."""

        concept = PhysicsConcept.objects.create(
            name="Force", description="A push or a pull.", topic="Dynamics"
        )
        sim = PhysicsSimulation.objects.create(
            concept=concept, title="Newton's Second Law Lab",
            simulation_type="newtons_second_law",
        )
        body = self.client.get(reverse("physics_lab:detail", args=[sim.slug])).content.decode()
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
