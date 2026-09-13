"""The student Experiment Notebook -- a read-only projection over the
student's own ExperimentAttempt rows, reusing ExperimentContext so a new
simulation type needs only its field list added, nothing else."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation

from .experiment_services import (
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
)
from .models import StudentProfile
from .notebook_services import build_student_notebook


class NotebookDataMixin:
    def seed(self):
        self.kin_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="d", topic="Kinematics",
        )
        self.kin_sim = PhysicsSimulation.objects.create(
            concept=self.kin_concept, title="Kinematics -- Straight-Line Motion",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        self.n2l_concept = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="d", topic="Dynamics",
        )
        self.n2l_sim = PhysicsSimulation.objects.create(
            concept=self.n2l_concept, title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        self.lesson = Lesson.objects.create(
            title="Motion on a Line", topic="Kinematics", grade_level="11",
            duration_minutes=45, learning_objectives=["Relate motion quantities."],
        )
        self.student = StudentProfile.objects.create(display_name="Alex")

    def observe_kinematics(self, x0=0, v0=2, a=1, t=5, text="It sped up."):
        return record_experiment_observation(
            student=self.student, simulation=self.kin_sim, lesson=self.lesson,
            observation=text, initial_position_m=x0, initial_velocity_m_s=v0,
            acceleration_m_s2=a, time_s=t,
        )

    def explain_kinematics(self, text="Because acceleration was constant.", **kw):
        defaults = dict(x0=0, v0=2, a=1, t=5)
        defaults.update(kw)
        return record_experiment_explanation(
            student=self.student, simulation=self.kin_sim, lesson=self.lesson,
            explanation=text,
            initial_position_m=defaults["x0"], initial_velocity_m_s=defaults["v0"],
            acceleration_m_s2=defaults["a"], time_s=defaults["t"],
        )


class NotebookServiceTests(NotebookDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_empty_for_a_student_with_no_attempts(self):
        entries = build_student_notebook(student=self.student)
        self.assertEqual(entries, [])

    def test_an_attempt_with_only_a_prediction_appears(self):
        record_experiment_prediction(
            student=self.student, simulation=self.kin_sim, lesson=self.lesson,
            prediction="It will speed up.",
        )
        entries = build_student_notebook(student=self.student)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].prediction, "It will speed up.")

    def test_kinematics_entry_has_variables_and_measurements(self):
        self.observe_kinematics(x0=0, v0=2, a=1, t=5)
        entries = build_student_notebook(student=self.student)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.simulation_title, "Kinematics -- Straight-Line Motion")
        self.assertEqual(entry.concept_name, "Acceleration")
        self.assertEqual(entry.lesson_title, "Motion on a Line")
        var_labels = {label for label, _, _ in entry.variables}
        self.assertEqual(var_labels, {"Initial position", "Initial velocity", "Acceleration"})
        meas_labels = {label for label, _, _ in entry.measurements}
        self.assertEqual(meas_labels, {"Time", "Position", "Velocity"})
        position_row = next(r for r in entry.measurements if r[0] == "Position")
        self.assertEqual(position_row[1], 22.5)
        self.assertEqual(position_row[2], "m")

    def test_newtons_second_law_entry_uses_its_own_field_set(self):
        from apps.students.models import ExperimentAttempt

        ExperimentAttempt.objects.create(
            student=self.student, simulation=self.n2l_sim,
            mass_kg=2.0, force_n=10.0, acceleration_m_s2=5.0,
            observation="It accelerated.",
        )
        entries = build_student_notebook(student=self.student)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        var_labels = {label for label, _, _ in entry.variables}
        self.assertEqual(var_labels, {"Mass", "Net force"})
        meas_labels = {label for label, _, _ in entry.measurements}
        self.assertEqual(meas_labels, {"Acceleration"})

    def test_attempt_with_no_content_at_all_is_skipped(self):
        from apps.students.models import ExperimentAttempt

        ExperimentAttempt.objects.create(student=self.student, simulation=self.kin_sim)
        entries = build_student_notebook(student=self.student)
        self.assertEqual(entries, [])

    def test_newest_first(self):
        self.observe_kinematics()
        second, _ = self.explain_kinematics()
        # explain reuses the same active attempt while unstarted, so start a
        # genuinely second attempt by completing the first, then observing again.
        from .experiment_services import complete_experiment

        complete_experiment(second)
        third, _ = self.observe_kinematics(text="Second run.")
        entries = build_student_notebook(student=self.student)
        self.assertEqual(entries[0].attempt_id, third.pk)

    def test_another_students_attempts_never_appear(self):
        other = StudentProfile.objects.create(display_name="Sam")
        record_experiment_observation(
            student=other, simulation=self.kin_sim, lesson=self.lesson,
            observation="Someone else's run.", initial_position_m=0,
            initial_velocity_m_s=2, acceleration_m_s2=1, time_s=5,
        )
        entries = build_student_notebook(student=self.student)
        self.assertEqual(entries, [])
        other_entries = build_student_notebook(student=other)
        self.assertEqual(len(other_entries), 1)

    def test_lab_url_resolves_to_the_real_simulation(self):
        self.observe_kinematics()
        entries = build_student_notebook(student=self.student)
        self.assertEqual(
            entries[0].lab_url,
            reverse("physics_lab:detail", args=[self.kin_sim.slug]),
        )


class NotebookViewTests(NotebookDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.url = reverse("students:notebook")

    def test_empty_state_for_a_fresh_session(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Your notebook is empty.", body)
        self.assertIn(reverse("physics_lab:index"), body)

    def test_entry_renders_all_recorded_sections(self):
        self.observe_kinematics(text="The cart moved faster over time.")
        self.explain_kinematics(text="Because the acceleration kept adding speed.")
        body = self.client.get(self.url).content.decode()
        self.assertIn("Kinematics -- Straight-Line Motion", body)
        self.assertIn("The cart moved faster over time.", body)
        self.assertIn("Because the acceleration kept adding speed.", body)
        self.assertIn("22.50", body)
        self.assertIn("Open this lab again", body)
        self.assertIn(reverse("physics_lab:detail", args=[self.kin_sim.slug]), body)

    def test_one_h1_and_page_landmarks(self):
        body = self.client.get(self.url).content.decode()
        self.assertEqual(body.count("<h1"), 1)
        self.assertIn(">Experiment Notebook<", body)
        self.assertIn('id="main-content"', body)

    def test_headings_are_real_not_bold_text(self):
        self.observe_kinematics()
        body = self.client.get(self.url).content.decode()
        self.assertIn("<h2>Kinematics", body)
        self.assertIn("<h3>Variables</h3>", body)

    def test_get_does_not_mutate_or_require_csrf(self):
        from .models import ExperimentAttempt

        before = ExperimentAttempt.objects.count()
        strict = Client(enforce_csrf_checks=True)
        response = strict.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExperimentAttempt.objects.count(), before)

    def test_another_students_notebook_stays_private(self):
        other_user = get_user_model().objects.create_user("intruder", password="pw")
        other_client = Client()
        other_client.force_login(other_user)

        self.observe_kinematics(text="My private observation.")
        intruder_body = other_client.get(self.url).content.decode()
        self.assertNotIn("My private observation.", intruder_body)

    def test_prediction_and_explanation_text_is_escaped(self):
        record_experiment_prediction(
            student=self.student, simulation=self.kin_sim, lesson=self.lesson,
            prediction="<script>alert('x')</script> it will speed up",
        )
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("<script>alert('x')</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_nav_link_present(self):
        body = self.client.get(reverse("home")).content.decode()
        self.assertIn(reverse("students:notebook"), body)
        self.assertIn(">Notebook<", body)
