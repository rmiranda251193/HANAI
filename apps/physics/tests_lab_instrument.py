"""Advanced interactive Physics Lab -- prediction, HUD/graphs, measurement,
comparison and scenario challenges.

Everything here stays inside the existing architecture: no new models, the
existing experiment endpoints, structured prediction stored in the existing
``ExperimentAttempt.parameters`` JSON, and a stateless server-authoritative
scenario checker that persists nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.physics.lab_scenarios import evaluate_scenario, get_scenario, scenarios_for
from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.students.experiment_services import record_experiment_prediction
from apps.students.models import ExperimentAttempt, LearningEvidence, StudentProfile

User = get_user_model()
JS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "js" / "physics"


def _kinematics_sim():
    concept = PhysicsConcept.objects.create(
        name="Kinematics", description="Straight-line motion.", topic="Kinematics"
    )
    return PhysicsSimulation.objects.create(
        concept=concept,
        title="Kinematics -- Straight-Line Motion",
        simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
    )


class StructuredPredictionTests(TestCase):
    def setUp(self):
        self.sim = _kinematics_sim()
        self.student = StudentProfile.objects.create(display_name="Pat")

    def test_structured_prediction_is_stored_in_attempt_parameters(self):
        attempt = record_experiment_prediction(
            student=self.student, simulation=self.sim,
            prediction="velocity will rise",
            structured={
                "predicted_velocity_m_s": "6", "predicted_position_m": "20",
                "predicted_direction": "speed_up",
            },
        )
        self.assertEqual(
            attempt.parameters["prediction"],
            {"velocity_m_s": 6.0, "position_m": 20.0, "direction": "speed_up"},
        )
        self.assertEqual(attempt.prediction, "velocity will rise")
        ev = LearningEvidence.objects.get(student=self.student)
        self.assertEqual(ev.kind, LearningEvidence.Kind.PREDICTION_SUBMITTED)
        self.assertEqual(ev.context["predicted"]["velocity_m_s"], 6.0)

    def test_forged_or_garbage_prediction_values_are_clamped_or_dropped(self):
        attempt = record_experiment_prediction(
            student=self.student, simulation=self.sim, prediction="x",
            structured={
                "predicted_velocity_m_s": "9e99",
                "predicted_position_m": "not a number",
                "predicted_direction": "<script>",
            },
        )
        pred = attempt.parameters["prediction"]
        self.assertLess(pred["velocity_m_s"], 1e6)  # clamped, not 9e99
        self.assertNotIn("position_m", pred)         # garbage dropped
        self.assertNotIn("direction", pred)          # not an allowed choice

    def test_prediction_without_structured_values_is_unchanged_behaviour(self):
        attempt = record_experiment_prediction(
            student=self.student, simulation=self.sim, prediction="just words"
        )
        self.assertNotIn("prediction", attempt.parameters or {})
        self.assertEqual(LearningEvidence.objects.count(), 1)


class ScenarioCheckerTests(TestCase):
    def setUp(self):
        self.sim = _kinematics_sim()
        self.url = lambda sid: reverse(
            "physics_lab:experiment_scenario_check", args=[self.sim.slug, sid]
        )

    def test_evaluate_scenario_is_deterministic_and_clamps(self):
        s = get_scenario("reach-20-at-4")
        self.assertTrue(
            evaluate_scenario(s, initial_position=0, initial_velocity=3, acceleration=1)["met"]
        )
        self.assertFalse(
            evaluate_scenario(s, initial_position=0, initial_velocity=3, acceleration=2)["met"]
        )
        # forged huge values are clamped by the model, cannot pass
        self.assertFalse(
            evaluate_scenario(s, initial_position=9e9, initial_velocity=9e9, acceleration=9e9)["met"]
        )

    def test_endpoint_is_server_authoritative_and_ignores_forged_completion(self):
        response = self.client.post(
            self.url("reach-20-at-4"),
            {
                "initial_position_m": "0", "initial_velocity_m_s": "3", "acceleration_m_s2": "2",
                "met": "true", "completed": "true", "score": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIs(payload["met"], False)  # a=2 -> x(4)=28, not 20; the body's "met=true" is ignored
        self.assertTrue(payload["checks"])

    def test_endpoint_persists_nothing(self):
        before = (ExperimentAttempt.objects.count(), LearningEvidence.objects.count())
        self.client.post(
            self.url("reach-20-at-4"),
            {"initial_position_m": "0", "initial_velocity_m_s": "3", "acceleration_m_s2": "1"},
        )
        after = (ExperimentAttempt.objects.count(), LearningEvidence.objects.count())
        self.assertEqual(before, after)

    def test_unknown_scenario_or_wrong_simulation_is_404(self):
        self.assertEqual(self.client.post(self.url("does-not-exist")).status_code, 404)
        self.assertEqual(self.client.get(self.url("reach-20-at-4")).status_code, 405)

    def test_scenarios_are_data_only(self):
        for s in scenarios_for("kinematics"):
            for value in vars(s).values():
                self.assertNotIn(type(value).__name__, {"function", "type", "code"})
            # the client dict never leaks tolerances as a cheat sheet
            self.assertNotIn("tolerance", json.dumps(s.as_client_dict))


@override_settings(AI_PROVIDER="fake")
class KinematicsInstrumentPageTests(TestCase):
    def setUp(self):
        self.sim = _kinematics_sim()
        self.url = reverse("physics_lab:detail", args=[self.sim.slug])
        self.staff = User.objects.create_user("lab_teacher", password="pw", is_staff=True)

    def _body(self, **params):
        return self.client.get(self.url, params).content.decode()

    def test_hud_graph_modes_time_controls_and_trail_are_present(self):
        body = self._body()
        for hook in (
            "data-hud-time", "data-hud-velocity", "data-hud-acceleration", "data-hud-motion",
            'name="lab-graph-mode"', "data-action-step-back", "data-lab-trail",
            "data-graph-label-y",
        ):
            self.assertIn(hook, body)

    def test_instrument_section_has_inspector_vectors_measure_compare_scenarios(self):
        body = self._body()
        self.assertIn("data-lab-instrument", body)
        for hook in (
            "data-inspect-x0", "data-inspect-v", 'name="lab-vector"', "data-vec-magnitude",
            "data-measure-capture1", "data-measure-dx", "data-compare-run", "data-compare-out",
            "data-scenario-select", "data-scenario-check", "data-scenario-check-base",
        ):
            self.assertIn(hook, body)
        self.assertIn("js/physics/lab-instrument.js", body)
        self.assertEqual(body.count("<h1"), 1)

    def test_scenarios_json_is_valid_and_check_base_has_the_placeholder(self):
        body = self._body()
        import re

        m = re.search(r"data-scenarios='([^']*)'", body)
        self.assertIsNotNone(m)
        data = json.loads(m.group(1).replace("&quot;", '"').replace("&#x27;", "'"))
        self.assertIn("reach-20-at-4", data)
        self.assertNotIn("tolerance", m.group(1))
        self.assertIn("/scenario/SCENARIO_ID/check/", body)

    def test_structured_prediction_fields_and_comparison_region(self):
        body = self._body()
        for hook in (
            'name="predicted_velocity_m_s"', 'name="predicted_position_m"',
            'name="predicted_direction"', "data-prediction-comparison",
        ):
            self.assertIn(hook, body)

    def test_preview_keeps_instruments_but_still_hides_predict_observe_explain(self):
        body = self._body(preview="1")
        self.assertIn("data-lab-instrument", body)   # instruments work read-only
        self.assertIn("data-hud-time", body)
        self.assertNotIn('data-experiment-form="predict"', body)
        self.assertNotIn('data-experiment-form="observe"', body)
        self.assertNotIn("data-prediction-comparison", body)  # lives in the hidden Observe step

    def test_no_new_experiment_model_and_endpoints_unchanged(self):
        names = sorted(f.name for f in ExperimentAttempt._meta.get_fields())
        self.assertNotIn("threed_state", names)
        self.assertIn("parameters", names)
        # the three canonical endpoints still resolve
        for name in ("experiment_predict", "experiment_observe", "experiment_explain"):
            reverse(f"physics_lab:{name}", args=[self.sim.slug])


class InstrumentJsSafetyTests(TestCase):
    def _js(self, name):
        return (JS_DIR / name).read_text(encoding="utf-8")

    def test_no_eval_function_constructor_or_innerhtml_assignment(self):
        for name in ("lab-instrument.js", "kinematics.js", "experiment-flow.js"):
            src = self._js(name)
            self.assertNotRegex(src, r"\beval\s*\(")
            self.assertNotRegex(src, r"\bnew\s+Function\s*\(")
            self.assertNotRegex(src, r"\.innerHTML\s*=")
            self.assertNotRegex(src, r"\bdocument\.write\s*\(")

    def test_scenario_check_url_is_built_by_placeholder_substitution_only(self):
        src = self._js("lab-instrument.js")
        self.assertIn('replace("SCENARIO_ID"', src)
        # no remote asset loading (the only http token is the SVG namespace URI)
        for host in ("cdn.jsdelivr", "unpkg.com", "cdnjs", "googleapis"):
            self.assertNotIn(host, src)
        self.assertNotIn("createElement('script'", src.replace(" ", ""))
        self.assertNotRegex(src, r"\bimport\s*\(")
