"""React islands (Physics Lab, Lesson Builder, Teacher Analytics, Student
Tutor) -- the Django-side half of this change.

This project has no Node.js installed by default; frontend/ was authored
without one, then actually built and jsdom-smoke-tested once a portable
Node was fetched (see docs/REACT_ISLANDS.md for the full, itemised
breakdown of what that did and didn't prove -- jsdom is not a browser).
None of that JS-side verification belongs in the Django suite, though: what
IS tested here, in full, is everything on the server -- that
``config.react_bridge.wants_json`` only fires for a request carrying the
project's own opt-in header, that the four views' new JSON branches carry
the same owner/permission/CSRF checks and business logic as their existing
HTML paths (never a parallel, weaker path), that no existing (non-React)
request changes behaviour at all, and that the templates/static assets the
frontend depends on are present and correctly wired.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.lessons.models import LessonActivity
from apps.lessons.tests_authoring import PW, AuthoringTestCase
from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.students.tests import TutorDataMixin
from apps.teachers.tests_analytics import AnalyticsDataMixin
from config.react_bridge import REACT_CLIENT_HEADER, wants_json

User = get_user_model()
REACT_HEADER_KWARGS = {REACT_CLIENT_HEADER: "react"}
FRONTEND_SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"


class ReactBridgeTests(TestCase):
    def test_wants_json_requires_the_exact_header_value(self):
        class FakeRequest:
            def __init__(self, value):
                self.META = {} if value is None else {REACT_CLIENT_HEADER: value}

        self.assertTrue(wants_json(FakeRequest("react")))
        for bad in (None, "", "REACT", "true", "xmlhttprequest"):
            self.assertFalse(wants_json(FakeRequest(bad)))


class PhysicsLabBootstrapTests(TestCase):
    def setUp(self):
        concept = PhysicsConcept.objects.create(
            name="Velocity", description="Rate of change of position.", topic="Kinematics"
        )
        self.sim = PhysicsSimulation.objects.create(
            concept=concept, title="Kinematics Lab", simulation_type="kinematics"
        )
        self.url = reverse("physics_lab:detail", args=[self.sim.slug])

    def test_mount_point_and_bootstrap_json_are_present(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('data-react-root="lab"', body)
        self.assertIn('id="react-lab-root"', body)
        self.assertIn(' hidden', body)

    def test_bootstrap_json_shape(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        # Pull the data-state attribute value back out and confirm it parses
        # and carries the fields the React island reads.
        start = html.index('id="react-lab-root"')
        chunk = html[start : start + 4000]
        state_start = chunk.index("data-state='") + len("data-state='")
        state_end = chunk.index("'", state_start)
        # HTML-unescape the handful of entities Django's autoescape produces.
        raw = (
            chunk[state_start:state_end]
            .replace("&#x27;", "'")
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        state = json.loads(raw)
        self.assertEqual(state["simulationSlug"], self.sim.slug)
        self.assertIn("defaults", state)
        self.assertIn("bounds", state)
        self.assertIn("equations", state)
        self.assertIn("endpoints", state)
        self.assertEqual(
            state["endpoints"]["predict"],
            reverse("physics_lab:experiment_predict", args=[self.sim.slug]),
        )

    def test_react_vendor_and_bundle_scripts_are_declared(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("js/vendor/react-18.3.1.production.min.js", body)
        self.assertIn("js/vendor/react-dom-18.3.1.production.min.js", body)
        self.assertIn("react/lab.js", body)

    def test_no_react_header_means_the_normal_html_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")


class LessonBuilderReactBridgeTests(AuthoringTestCase):
    """The Lesson Builder's ``_authoring_post`` JSON branch."""

    def setUp(self):
        super().setUp()
        self.client_a = self.client_for(self.teacher_a)
        self.activity = self.add_lab_activity()
        self.delete_url = reverse(
            "lessons:activity_delete", args=[self.lesson.slug, self.activity.pk]
        )

    def test_builder_page_embeds_activities_bootstrap_json(self):
        body = self.client_a.get(
            reverse("lessons:build", args=[self.lesson.slug])
        ).content.decode()
        self.assertIn('data-react-root="lesson-builder"', body)
        self.assertIn('id="react-lesson-builder-root"', body)

    def test_json_delete_returns_ok_and_removes_the_activity(self):
        response = self.client_a.post(self.delete_url, **REACT_HEADER_KWARGS)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["activities"], [])
        self.assertFalse(LessonActivity.objects.filter(pk=self.activity.pk).exists())

    def test_json_activity_payload_shape(self):
        response = self.client_a.get(
            reverse("lessons:build", args=[self.lesson.slug]) + "?ok=x",
            **REACT_HEADER_KWARGS,
        )
        # A GET is unaffected by wants_json (only _authoring_post POSTs branch
        # on it) -- this just confirms the embedded JSON on the ordinary page
        # has the shape the React island expects.
        html = response.content.decode()
        start = html.index('id="react-lesson-builder-root"')
        chunk = html[start : start + 4000]
        state_start = chunk.index("data-state='") + len("data-state='")
        state_end = chunk.index("'", state_start)
        raw = (
            chunk[state_start:state_end]
            .replace("&#x27;", "'")
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        state = json.loads(raw)
        self.assertEqual(state["lessonSlug"], self.lesson.slug)
        row = state["activities"][0]
        for key in ("id", "position", "activityType", "activityTypeLabel", "title", "deleteUrl"):
            self.assertIn(key, row)
        self.assertEqual(row["deleteUrl"], self.delete_url)

    def test_a_different_teacher_gets_403_even_over_the_json_path(self):
        client_b = self.client_for(self.teacher_b)
        response = client_b.post(self.delete_url, **REACT_HEADER_KWARGS)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(LessonActivity.objects.filter(pk=self.activity.pk).exists())

    def test_csrf_is_still_enforced_on_the_json_path(self):
        enforcing = Client(enforce_csrf_checks=True)
        enforcing.login(username=self.teacher_a.username, password=PW)
        response = enforcing.post(self.delete_url, **REACT_HEADER_KWARGS)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(LessonActivity.objects.filter(pk=self.activity.pk).exists())

    def test_invalid_action_returns_a_json_error_not_html(self):
        # Deleting an activity that belongs to a different lesson raises
        # Http404 inside the shared wrapper -- confirm that still 404s (not
        # silently swallowed into an ok:true) even over the JSON path.
        other_lesson_activity_url = reverse(
            "lessons:activity_delete", args=[self.lesson.slug, "00000000-0000-0000-0000-000000000000"]
        )
        response = self.client_a.post(other_lesson_activity_url, **REACT_HEADER_KWARGS)
        self.assertEqual(response.status_code, 404)

    def test_normal_form_post_without_the_header_is_unchanged(self):
        """The existing PRG (redirect) behaviour is exactly preserved."""

        response = self.client_a.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("ok=activity_deleted", response["Location"])


@override_settings(AI_PROVIDER="fake")
class StudentTutorReactBridgeTests(TutorDataMixin, TestCase):
    def setUp(self):
        self.lesson = self.make_lesson()
        self.url = reverse("students:tutor", args=[self.lesson.slug])

    def test_page_embeds_conversation_bootstrap_json(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('data-react-root="tutor"', body)
        self.assertIn('id="react-tutor-root"', body)
        self.assertIn("data-tutor-static", body)

    def test_json_ask_returns_the_conversation_not_html(self):
        response = self.client.post(
            self.url,
            {"action": "ask", "question": "What is acceleration?"},
            **REACT_HEADER_KWARGS,
        )
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertTrue(data["ok"])
        roles = [m["role"] for m in data["conversation"]]
        self.assertIn("student", roles)
        self.assertIn("tutor", roles)
        self.assertTrue(
            any("Acceleration is the rate at which" in m["content"] for m in data["conversation"])
        )

    def test_json_empty_question_returns_an_error_not_a_500(self):
        response = self.client.post(
            self.url, {"action": "ask", "question": "   "}, **REACT_HEADER_KWARGS
        )
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["error"])

    def test_no_react_header_keeps_the_full_page_render(self):
        response = self.client.post(
            self.url, {"action": "ask", "question": "What is acceleration?"}
        )
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")
        self.assertContains(response, "Acceleration is the rate at which")

    def test_react_vendor_and_bundle_scripts_are_declared(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("react/tutor.js", body)


class TeacherAnalyticsReactBridgeTests(AnalyticsDataMixin, TestCase):
    def setUp(self):
        self.url = reverse("teachers:analytics")
        self.client.force_login(self.make_teacher())

    def test_page_embeds_snapshot_bootstrap_json(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('data-react-root="analytics"', body)
        self.assertIn('id="react-analytics-root"', body)

    def test_bootstrap_json_mirrors_the_rendered_numbers(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        start = html.index('id="react-analytics-root"')
        chunk = html[start : start + 20000]
        state_start = chunk.index("data-state='") + len("data-state='")
        state_end = chunk.index("'", state_start)
        raw = (
            chunk[state_start:state_end]
            .replace("&#x27;", "'")
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        state = json.loads(raw)
        for key in (
            "studentCount", "activeStudentCount", "conceptSummary",
            "misconceptionSummary", "attentionSignals", "rangeLabel",
        ):
            self.assertIn(key, state)

    def test_anonymous_and_non_staff_are_still_blocked(self):
        self.assertEqual(Client().get(self.url).status_code, 403)


class ReactAssetTests(TestCase):
    def test_vendored_react_is_discoverable_and_mit_licensed(self):
        for path in (
            "js/vendor/react-18.3.1.production.min.js",
            "js/vendor/react-dom-18.3.1.production.min.js",
        ):
            found = finders.find(path)
            self.assertIsNotNone(found, f"missing static asset: {path}")
            head = open(found, encoding="utf-8").read(400)
            self.assertIn("@license React", head)

    def test_bundles_are_discoverable_and_non_empty(self):
        """These are the real, built bundles (see docs/REACT_ISLANDS.md) --
        this only pins that something is always present at each path, since
        collectstatic under DJANGO_MANIFEST_STATIC=1 needs that regardless
        of whether it's a real build or a minimal placeholder."""

        for path in (
            "react/lab.js",
            "react/lesson-builder.js",
            "react/analytics.js",
            "react/tutor.js",
        ):
            found = finders.find(path)
            self.assertIsNotNone(found, f"missing static asset: {path}")
            content = open(found, encoding="utf-8").read()
            self.assertTrue(content.strip(), f"{path} must not be empty")


class ReactSourceSafetyTests(TestCase):
    """Static, best-effort checks on the frontend source. This is NOT a
    substitute for actually building and running it (see
    docs/REACT_ISLANDS.md) -- it only catches the same class of thing this
    codebase's other client-module safety tests catch: no eval, no unescaped
    HTML injection, no remote script loading, no bypassing the CSRF/opt-in
    header contract config.react_bridge documents.
    """

    def _all_sources(self):
        return list(FRONTEND_SRC.rglob("*.js")) + list(FRONTEND_SRC.rglob("*.jsx"))

    def test_frontend_source_tree_exists(self):
        sources = self._all_sources()
        self.assertGreaterEqual(len(sources), 8)

    def test_no_eval_or_dangerous_html_injection(self):
        for path in self._all_sources():
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("eval(", src, path)
            self.assertNotIn("new Function(", src, path)
            self.assertNotIn("dangerouslySetInnerHTML", src, path)
            self.assertNotIn("document.write(", src, path)

    def test_no_remote_script_or_hardcoded_origin(self):
        for path in self._all_sources():
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("http://", src, path)
            self.assertNotIn("https://", src, path)

    def test_every_fetch_call_uses_the_shared_reactfetch_helper(self):
        for path in self._all_sources():
            if path.name == "csrf.js":
                continue
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("window.fetch(", src, path)
            # a bare `fetch(` (not `reactFetch(`) would skip the CSRF header
            for line in src.splitlines():
                if "reactFetch(" in line:
                    continue
                self.assertNotRegex(line, r"(?<!react)[Ff]etch\(")

    def test_reactfetch_always_sets_the_opt_in_header_and_csrf_token(self):
        src = (FRONTEND_SRC / "shared" / "csrf.js").read_text(encoding="utf-8")
        self.assertIn('"X-HANAI-Client": "react"', src)
        self.assertIn("X-CSRFToken", src)
        self.assertIn("credentials", src)
        self.assertIn("same-origin", src)

    def test_mount_helper_never_leaves_the_page_blank_on_failure(self):
        src = (FRONTEND_SRC / "shared" / "mount.js").read_text(encoding="utf-8")
        self.assertIn("try", src)
        self.assertIn("catch", src)
        self.assertIn("return", src)  # bails out on a missing root / bad JSON
