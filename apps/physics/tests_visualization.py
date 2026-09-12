"""Post-MVP -- 3D Physics visualization (presentation layer).

These pin the visualization registry (data only, safe lookup, no code
execution), the Kinematics lab page's 2D/3D wiring, the teacher read-only
preview, that the 3D layer added no second experiment/evidence architecture and
cannot weaken server authority, that the vendored + new static assets are
collectable, and that the client modules contain no ``eval`` / ``Function`` /
remote script loading.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.physics.visualization_registry import (
    VisualizationDefinition,
    get_visualization,
    register,
    registered_visualization_types,
)
from apps.students.models import ExperimentAttempt, LearningEvidence, StudentProfile

User = get_user_model()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PHYSICS3D_DIR = BASE_DIR / "static" / "js" / "physics3d"


class VisualizationRegistryTests(TestCase):
    def test_known_type_returns_a_data_only_definition(self):
        viz = get_visualization("kinematics")
        self.assertIsInstance(viz, VisualizationDefinition)
        self.assertEqual(viz.renderer, "kinematics-3d")
        self.assertIn("2d", viz.supported_views)
        self.assertIn("3d", viz.supported_views)
        self.assertTrue(viz.has_3d)
        # data only -- no callables, no code
        for value in vars(viz).values():
            self.assertNotIn(type(value).__name__, {"function", "type", "code"})

    def test_unknown_or_garbage_type_is_none_never_raises(self):
        for bad in ("electric_field", "", None, 123, object(), "../../etc/passwd"):
            self.assertIsNone(get_visualization(bad))

    def test_registered_types_are_deterministic(self):
        self.assertEqual(registered_visualization_types(), ("kinematics",))

    def test_register_rejects_a_renderer_slug_not_on_the_allow_list(self):
        with self.assertRaises(ValueError):
            register(
                VisualizationDefinition(
                    simulation_type="made_up",
                    renderer="https://evil.example/x.js",
                    supported_views=("2d", "3d"),
                )
            )
        self.assertIsNone(get_visualization("made_up"))


class KinematicsDataMixin:
    def make_kinematics(self):
        concept = PhysicsConcept.objects.create(
            name="Kinematics", description="Straight-line motion.", topic="Kinematics"
        )
        return PhysicsSimulation.objects.create(
            concept=concept,
            title="Kinematics -- Straight-Line Motion",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )


@override_settings(AI_PROVIDER="fake")
class KinematicsLabPageTests(KinematicsDataMixin, TestCase):
    def setUp(self):
        self.sim = self.make_kinematics()
        self.url = reverse("physics_lab:detail", args=[self.sim.slug])

    def test_page_offers_2d_and_3d_with_the_allow_listed_renderer(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('data-physics3d', body)
        self.assertIn('data-renderer="kinematics-3d"', body)
        self.assertIn('name="lab-view" value="2d"', body)
        self.assertIn('name="lab-view" value="3d"', body)
        self.assertIn("data-lab-scene-2d", body)
        self.assertIn("data-physics3d-canvas", body)

    def test_page_declares_the_cart_model_url_via_static(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("data-cart-model=", body)
        self.assertIn("models/cart.json", body)
        self.assertRegex(body, r'data-cart-model="[^"]*static[^"]*models/cart\.json"')

    def test_page_declares_the_vendored_three_module_via_import_map(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn('<script type="importmap">', body)
        self.assertIn("js/vendor/three-0.160.1.module.min.js", body)
        self.assertIn('<script type="module" src=', body)
        self.assertIn("js/physics3d/kinematics-3d.js", body)
        # no external origins, no eval-ish sinks in the rendered page
        self.assertNotIn("http://", body.replace("http://127.0.0.1", "").replace("http://testserver", ""))
        self.assertNotIn("cdn.jsdelivr", body)
        self.assertNotIn("unpkg.com", body)
        for sink in ("eval(", "new Function(", " onclick=", " onload=", " onerror="):
            self.assertNotIn(sink, body)

    def test_accessible_fallback_and_summary_and_scrub_controls_present(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("data-physics3d-fallback", body)
        self.assertIn("data-physics3d-summary", body)
        self.assertIn('aria-live="polite"', body)
        self.assertIn("data-physics3d-camera-reset", body)
        self.assertIn("data-input-time", body)
        self.assertIn("data-action-step", body)
        self.assertIn('for="lab-time"', body)          # labelled control
        self.assertIn("prefers-reduced-motion", (PHYSICS3D_DIR / "webgl.js").read_text())

    def test_one_h1_and_the_2d_view_is_the_default(self):
        body = self.client.get(self.url).content.decode()
        self.assertEqual(body.count("<h1"), 1)
        # the 3D canvas wrapper starts hidden; the 2D SVG is not
        self.assertRegex(body, r'data-physics3d-canvas-wrap\s+hidden')

    def test_page_still_renders_without_a_visualization_registered(self):
        with override_settings():
            from apps.physics import visualization_registry as vr

            saved = dict(vr._REGISTRY)
            vr._REGISTRY.clear()
            try:
                body = self.client.get(self.url).content.decode()
            finally:
                vr._REGISTRY.update(saved)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertNotIn("data-physics3d", body)
        self.assertNotIn("importmap", body)
        self.assertIn("data-lab-scene", body)  # 2D still there


@override_settings(AI_PROVIDER="fake")
class TeacherPreviewTests(KinematicsDataMixin, TestCase):
    def setUp(self):
        self.sim = self.make_kinematics()
        self.url = reverse("physics_lab:detail", args=[self.sim.slug])
        self.staff = User.objects.create_user("viz_teacher", password="pw", is_staff=True)

    def test_preview_hides_predict_observe_explain_and_shows_a_banner(self):
        body = self.client.get(self.url, {"preview": "1"}).content.decode()
        self.assertIn("lab-preview-banner", body)
        self.assertIn("read-only", body.lower())
        self.assertNotIn('data-experiment-form="predict"', body)
        self.assertNotIn('data-experiment-form="observe"', body)
        self.assertNotIn('data-experiment-form="explain"', body)
        self.assertNotIn("data-tutor-link", body)
        # the interactive experiment stage (2D + 3D) is still there
        self.assertIn("data-physics3d", body)
        self.assertIn("data-lab-scene", body)

    def test_preview_get_creates_no_evidence(self):
        before = (
            ExperimentAttempt.objects.count(),
            LearningEvidence.objects.count(),
            StudentProfile.objects.count(),
        )
        self.client.get(self.url, {"preview": "1"})
        self.client.get(self.url)  # normal view too
        after = (
            ExperimentAttempt.objects.count(),
            LearningEvidence.objects.count(),
            StudentProfile.objects.count(),
        )
        # a guest StudentProfile may be created by _current_student; nothing else.
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_staff_see_the_preview_link_students_do_not(self):
        anon = self.client.get(self.url).content.decode()
        self.assertNotIn("?preview=1", anon)
        self.client.force_login(self.staff)
        staffed = self.client.get(self.url).content.decode()
        self.assertIn("?preview=1", staffed)


@override_settings(AI_PROVIDER="fake")
class ServerAuthorityRegressionTests(KinematicsDataMixin, TestCase):
    """The 3D layer must not weaken Steps 24-30 server authority."""

    def setUp(self):
        self.sim = self.make_kinematics()

    def test_forged_position_velocity_and_completion_are_ignored(self):
        observe = reverse("physics_lab:experiment_observe", args=[self.sim.slug])
        response = self.client.post(
            observe,
            {
                "observation": "It moved.",
                "initial_position_m": "0",
                "initial_velocity_m_s": "2",
                "acceleration_m_s2": "1",
                "time_s": "5",
                # forged fields the browser must never be trusted for:
                "position_m": "999999",
                "velocity_m_s": "888888",
                "is_correct": "true",
                "completed": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # server recomputed from x0=0, v0=2, a=1, t=5 -> x=22.5, v=7
        self.assertAlmostEqual(payload["position_m"], 22.5, places=2)
        self.assertAlmostEqual(payload["velocity_m_s"], 7.0, places=2)
        attempt = ExperimentAttempt.objects.get(simulation=self.sim)
        self.assertNotIn(attempt.acceleration_m_s2, (999999.0, 888888.0))

    def test_experiment_attempt_schema_is_unchanged_no_3d_model(self):
        field_names = sorted(f.name for f in ExperimentAttempt._meta.get_fields())
        self.assertEqual(
            field_names,
            sorted(
                [
                    "id", "student", "lesson", "simulation", "session",
                    "prediction", "observation", "explanation",
                    "mass_kg", "force_n", "acceleration_m_s2", "parameters",
                    "started_at", "updated_at", "completed_at",
                ]
            ),
        )
        from django.apps import apps as django_apps

        model_names = {m.__name__ for m in django_apps.get_models()}
        for banned in ("ThreeDExperimentAttempt", "ThreeDLearningEvidence", "PhysicsEngine3D"):
            self.assertNotIn(banned, model_names)


class ClientModuleSafetyTests(TestCase):
    def _js(self, name):
        return (PHYSICS3D_DIR / name).read_text(encoding="utf-8")

    _MODULES = ("scene-core.js", "kinematics-3d.js", "webgl.js", "home-motif.js", "model-loader.js")

    def test_no_eval_exec_or_dynamic_function_construction(self):
        for name in self._MODULES:
            src = self._js(name)
            self.assertNotRegex(src, r"\beval\s*\(")
            self.assertNotRegex(src, r"\bnew\s+Function\s*\(")
            self.assertNotRegex(src, r"\bdocument\.write\s*\(")

    def test_imports_are_local_or_the_import_map_alias_only(self):
        for name in self._MODULES:
            src = self._js(name)
            for match in re.findall(r'import[^;]*?from\s+["\']([^"\']+)["\']', src):
                self.assertTrue(
                    match == "three" or match.startswith("./") or match.startswith("../"),
                    f"{name} imports from a non-local specifier: {match!r}",
                )
            self.assertNotIn("import(", src.replace("prefersReducedMotion", ""))

    def test_renderer_selection_is_an_allow_list_lookup(self):
        src = self._js("kinematics-3d.js")
        self.assertIn("RENDERERS = {", src)
        self.assertIn('hasOwnProperty.call(RENDERERS', src)

    def test_disposal_is_implemented(self):
        core = self._js("scene-core.js")
        for token in ("dispose()", "geometry.dispose", "renderer.dispose", "cancelAnimationFrame", "removeEventListener"):
            self.assertIn(token, core)
        boot = self._js("kinematics-3d.js")
        self.assertIn("pagehide", boot)
        self.assertIn("core.dispose()", boot)


class HomeMotifTests(TestCase):
    def test_home_page_motif_is_decorative_and_not_required(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn("data-home-motif", body)
        self.assertIn('aria-hidden="true"', body)
        self.assertIn("js/physics3d/home-motif.js", body)
        # the page's meaning does not live in the canvas
        self.assertIn("Build understanding", body)
        self.assertEqual(body.count("<h1"), 1)
        self.assertIn("prefers-reduced-motion", (BASE_DIR / "static" / "css" / "app.css").read_text())


class StaticAssetTests(TestCase):
    def test_all_3d_assets_are_discoverable_by_the_staticfiles_finders(self):
        for path in (
            "js/vendor/three-0.160.1.module.min.js",
            "js/physics3d/scene-core.js",
            "js/physics3d/kinematics-3d.js",
            "js/physics3d/webgl.js",
            "js/physics3d/home-motif.js",
            "js/physics3d/model-loader.js",
            "models/cart.json",
        ):
            self.assertIsNotNone(finders.find(path), f"missing static asset: {path}")

    def test_vendored_three_is_the_mit_licensed_module_build(self):
        found = finders.find("js/vendor/three-0.160.1.module.min.js")
        head = Path(found).read_text(encoding="utf-8")[:400]
        self.assertIn("@license", head)
        self.assertIn("MIT", head)


class ModelAssetTests(TestCase):
    """Blender-authorable 3D model support: a validated JSON mesh format, not
    a vendored glTF/OBJ parser (see docs/BLENDER_WORKFLOW.md and
    static/js/vendor/README.md for why)."""

    def test_cart_model_json_matches_the_loaders_own_validation_rules(self):
        import json

        found = finders.find("models/cart.json")
        self.assertIsNotNone(found)
        data = json.loads(Path(found).read_text(encoding="utf-8"))

        positions = data["positions"]
        indices = data["indices"]
        self.assertGreater(len(positions), 0)
        self.assertEqual(len(positions) % 3, 0)
        self.assertTrue(all(isinstance(n, (int, float)) for n in positions))
        self.assertGreater(len(indices), 0)
        self.assertEqual(len(indices) % 3, 0)

        vertex_count = len(positions) // 3
        self.assertLessEqual(vertex_count, 20000)
        self.assertLessEqual(len(indices) // 3, 20000)
        for idx in indices:
            self.assertIsInstance(idx, int)
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, vertex_count)

        normals = data.get("normals")
        if normals is not None:
            self.assertEqual(len(normals), len(positions))

        # Matches the BoxGeometry(1.6, 1.1, 2) bounding box it replaces, so it
        # drops in without moving the track, arrows or labels.
        xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
        self.assertAlmostEqual(min(xs), -0.8)
        self.assertAlmostEqual(max(xs), 0.8)
        self.assertAlmostEqual(min(ys), -0.55)
        self.assertAlmostEqual(max(ys), 0.55)
        self.assertAlmostEqual(min(zs), -1.0)
        self.assertAlmostEqual(max(zs), 1.0)

    def test_model_loader_validates_before_building_geometry(self):
        src = (PHYSICS3D_DIR / "model-loader.js").read_text(encoding="utf-8")
        for token in (
            "positions.length % 3", "indices.length % 3", "Number.isInteger",
            "maxVertices", "maxTriangles", "credentials: \"same-origin\"",
            "computeVertexNormals",
        ):
            self.assertIn(token, src)

    def test_kinematics_scene_creates_the_fallback_box_before_loading_a_model(self):
        src = (PHYSICS3D_DIR / "kinematics-3d.js").read_text(encoding="utf-8")
        self.assertLess(
            src.index("new THREE_.BoxGeometry(1.6, 1.1, 2)"),
            src.index("loadModelGeometry("),
            "the fallback box must exist before a model load is even attempted",
        )
        self.assertIn(".catch(function ()", src)

    def test_blender_workflow_is_documented(self):
        doc = (BASE_DIR / "docs" / "BLENDER_WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn("model-loader.js", doc)
        self.assertIn("bpy", doc)
        self.assertIn("positions", doc)
        self.assertIn("indices", doc)
