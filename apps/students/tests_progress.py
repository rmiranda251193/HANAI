from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import (
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)

from .models import (
    ExperimentAttempt,
    LearningEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from .progress_services import build_student_learning_progress

PROGRESS_URL = reverse("students:progress")
Kind = LearningEvidence.Kind


class ProgressDataMixin:
    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name="Newton's Second Law", topic="Dynamics"):
        return PhysicsConcept.objects.create(
            name=name, description="A concept.", topic=topic
        )

    def make_lesson(self, *concepts, title="Forces and Motion"):
        lesson = Lesson.objects.create(
            title=title,
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate force, mass and acceleration."],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept):
        return PhysicsSimulation.objects.create(
            concept=concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def add_evidence(self, student, kind, *, lesson=None, detail="", context=None, when=None):
        evidence = LearningEvidence.objects.create(
            student=student,
            lesson=lesson,
            kind=kind,
            detail=detail,
            context=context or {},
        )
        if when is not None:
            LearningEvidence.objects.filter(pk=evidence.pk).update(created_at=when)
            evidence.refresh_from_db()
        return evidence

    def add_experiment(
        self,
        student,
        simulation,
        *,
        lesson=None,
        completed=False,
        mass=None,
        force=None,
        accel=None,
        prediction="",
        observation="",
        explanation="",
    ):
        return ExperimentAttempt.objects.create(
            student=student,
            simulation=simulation,
            lesson=lesson,
            mass_kg=mass,
            force_n=force,
            acceleration_m_s2=accel,
            prediction=prediction,
            observation=observation,
            explanation=explanation,
            completed_at=timezone.now() if completed else None,
        )

    def add_tutor_messages(self, student, lesson, *, student_turns=1, tutor_turns=1):
        session = TutorSession.objects.create(student=student, lesson=lesson)
        for i in range(student_turns):
            TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.STUDENT, content=f"q{i}"
            )
        for i in range(tutor_turns):
            TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.TUTOR, content=f"a{i}", mode="explain"
            )
        return session


# --- PROGRESS PAGE ------------------------------------------------------------


class ProgressPageTests(ProgressDataMixin, TestCase):
    def test_progress_route_loads(self):
        response = self.client.get(PROGRESS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My learning journey")

    def test_anonymous_access_uses_the_shared_guest_student(self):
        self.client.get(PROGRESS_URL)
        self.client.get(PROGRESS_URL)
        self.assertEqual(StudentProfile.objects.filter(user__isnull=True).count(), 1)

    def test_empty_student_state_renders_honestly(self):
        response = self.client.get(PROGRESS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your learning journey is just beginning")
        self.assertNotContains(response, "experiments completed")

    def test_one_student_cannot_see_another_students_evidence(self):
        user_model = get_user_model()
        alice_user = user_model.objects.create_user("alice", password="pw")
        bob_user = user_model.objects.create_user("bob", password="pw")
        alice = self.make_student("Alice", user=alice_user)
        bob = self.make_student("Bob", user=bob_user)
        self.add_evidence(alice, Kind.QUESTION_ASKED, detail="ALICE ASKED THIS")
        self.add_evidence(bob, Kind.QUESTION_ASKED, detail="BOB ASKED THIS")

        self.client.force_login(alice_user)
        response = self.client.get(PROGRESS_URL)
        self.assertContains(response, "ALICE ASKED THIS")
        self.assertNotContains(response, "BOB ASKED THIS")

    def test_student_id_query_parameter_is_ignored(self):
        user_model = get_user_model()
        alice_user = user_model.objects.create_user("alice", password="pw")
        alice = self.make_student("Alice", user=alice_user)
        bob = self.make_student("Bob")
        self.add_evidence(alice, Kind.QUESTION_ASKED, detail="ALICE ONLY")
        self.add_evidence(bob, Kind.QUESTION_ASKED, detail="BOB ONLY")

        self.client.force_login(alice_user)
        response = self.client.get(PROGRESS_URL, {"student_id": bob.pk})
        self.assertContains(response, "ALICE ONLY")
        self.assertNotContains(response, "BOB ONLY")


# --- EVIDENCE TIMELINE -----------------------------------------------------


class EvidenceTimelineTests(ProgressDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept)

    def _titles(self, student=None):
        data = build_student_learning_progress(student=student or self.student)
        return [
            entry["title"]
            for day in data["recent_activity_days"]
            for entry in day["entries"]
        ]

    def test_question_asked_has_friendly_label(self):
        self.add_evidence(self.student, Kind.QUESTION_ASKED, detail="what is force")
        self.assertIn("Asked a Physics question", self._titles())
        data = build_student_learning_progress(student=self.student)
        self.assertEqual(
            data["recent_activity_days"][0]["entries"][0]["kind_label"], "Question"
        )

    def test_practice_attempted_appears(self):
        self.add_evidence(self.student, Kind.PRACTICE_ATTEMPTED, detail="my attempt")
        self.assertIn("Attempted a practice problem", self._titles())

    def test_prediction_submitted_appears(self):
        self.add_evidence(self.student, Kind.PREDICTION_SUBMITTED, detail="it doubles")
        self.assertIn("Submitted an experiment prediction", self._titles())

    def test_experiment_observed_appears(self):
        self.add_evidence(
            self.student,
            Kind.EXPERIMENT_OBSERVED,
            detail="5 to 10",
            context={"simulation": "newtons_second_law", "acceleration_m_s2": 10.0},
        )
        self.assertIn("Recorded an experiment observation", self._titles())

    def test_explanation_submitted_appears(self):
        self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="because force")
        self.assertIn("Explained the experiment", self._titles())

    def test_evidence_is_ordered_newest_first(self):
        now = timezone.now()
        self.add_evidence(self.student, Kind.QUESTION_ASKED, detail="oldest", when=now - timedelta(hours=3))
        self.add_evidence(self.student, Kind.PRACTICE_ATTEMPTED, detail="middle", when=now - timedelta(hours=2))
        self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="newest", when=now - timedelta(minutes=5))

        data = build_student_learning_progress(student=self.student)
        details = [
            entry["detail"]
            for day in data["recent_activity_days"]
            for entry in day["entries"]
        ]
        self.assertEqual(details, ["newest", "middle", "oldest"])

    def test_student_detail_is_escaped_on_the_page(self):
        self.add_evidence(
            self.student,
            Kind.EXPLANATION_SUBMITTED,
            detail="<script>alert('x')</script>",
        )
        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        self.student.user = user
        self.student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(PROGRESS_URL)
        self.assertNotContains(response, "<script>alert('x')</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_internal_enum_names_are_not_exposed(self):
        self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="x")
        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        self.student.user = user
        self.student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(PROGRESS_URL)
        self.assertNotContains(response, "explanation_submitted")
        self.assertNotContains(response, "question_asked")


# --- EXPERIMENT SUMMARY -------------------------------------------------


class ExperimentSummaryTests(ProgressDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.concept = self.make_concept()
        self.simulation = self.make_simulation(self.concept)

    def test_completed_experiments_counted_correctly(self):
        self.add_experiment(self.student, self.simulation, completed=True)
        self.add_experiment(self.student, self.simulation, completed=True)
        self.add_experiment(self.student, self.simulation, completed=False)

        data = build_student_learning_progress(student=self.student)
        self.assertEqual(data["experiment_summary"]["completed"], 2)
        self.assertEqual(data["experiment_summary"]["attempted"], 3)
        self.assertEqual(data["summary_counts"]["experiments_completed"], 2)

    def test_incomplete_experiment_is_not_completed(self):
        self.add_experiment(self.student, self.simulation, completed=False)
        data = build_student_learning_progress(student=self.student)
        self.assertEqual(data["experiment_summary"]["completed"], 0)

    def test_experiment_parameters_show_deterministic_values(self):
        self.add_experiment(
            self.student, self.simulation, completed=True,
            mass=2.0, force=20.0, accel=10.0,
        )
        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        self.student.user = user
        self.student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(PROGRESS_URL)
        self.assertContains(response, "10.00")
        self.assertContains(response, "20.0")

    def test_query_params_cannot_change_displayed_acceleration(self):
        self.add_experiment(
            self.student, self.simulation, completed=True,
            mass=2.0, force=20.0, accel=10.0,
        )
        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        self.student.user = user
        self.student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(
            PROGRESS_URL, {"acceleration_m_s2": "999", "mass_kg": "1"}
        )
        self.assertContains(response, "10.00")
        self.assertNotContains(response, "999")


# --- CONCEPTS EXPLORED -----------------------------------------------


class ConceptsExploredTests(ProgressDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.nsl = self.make_concept("Newton's Second Law")
        self.unused = self.make_concept("Momentum", topic="Mechanics")
        self.lesson = self.make_lesson(self.nsl)
        self.simulation = self.make_simulation(self.nsl)

    def test_only_interacted_concepts_appear(self):
        self.add_evidence(self.student, Kind.QUESTION_ASKED, lesson=self.lesson)
        data = build_student_learning_progress(student=self.student)
        names = [c["name"] for c in data["concepts"]]
        self.assertIn("Newton's Second Law", names)
        self.assertNotIn("Momentum", names)

    def test_duplicate_concepts_are_collapsed_with_a_count(self):
        for _ in range(3):
            self.add_evidence(self.student, Kind.PREDICTION_SUBMITTED, lesson=self.lesson)
        self.add_experiment(self.student, self.simulation, lesson=self.lesson)

        data = build_student_learning_progress(student=self.student)
        nsl_rows = [c for c in data["concepts"] if c["name"] == "Newton's Second Law"]
        self.assertEqual(len(nsl_rows), 1)
        self.assertEqual(nsl_rows[0]["count"], 4)

    def test_concept_names_render_on_the_page(self):
        self.add_evidence(self.student, Kind.QUESTION_ASKED, lesson=self.lesson)
        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        self.student.user = user
        self.student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(PROGRESS_URL)
        self.assertContains(response, "Newton&#x27;s Second Law")


# --- TUTOR ACTIVITY -----------------------------------------------


class TutorActivityTests(ProgressDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept)

    def test_student_turns_are_counted_not_assistant_turns(self):
        self.add_tutor_messages(self.student, self.lesson, student_turns=2, tutor_turns=3)
        data = build_student_learning_progress(student=self.student)
        self.assertEqual(data["tutor_activity"]["messages"], 2)

    def test_other_students_tutor_messages_are_excluded(self):
        other = self.make_student("Bob")
        self.add_tutor_messages(self.student, self.lesson, student_turns=2, tutor_turns=1)
        self.add_tutor_messages(other, self.lesson, student_turns=5, tutor_turns=1)

        data = build_student_learning_progress(student=self.student)
        self.assertEqual(data["tutor_activity"]["messages"], 2)


# --- NEXT STEP -----------------------------------------------


class NextStepTests(ProgressDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept)
        self.simulation = self.make_simulation(self.concept)

    def _next(self):
        return build_student_learning_progress(student=self.student)["next_step"]

    def test_empty_activity_suggestion(self):
        self.assertEqual(
            self._next(),
            "Start by opening a Physics lesson or asking the Physics Tutor a question.",
        )

    def test_prediction_without_observation_suggestion(self):
        self.add_experiment(
            self.student, self.simulation, prediction="it doubles", completed=False
        )
        self.assertEqual(
            self._next(), "Return to the Physics Lab and record what happened."
        )

    def test_observation_without_explanation_suggestion(self):
        self.add_experiment(
            self.student,
            self.simulation,
            prediction="it doubles",
            observation="it went to 10",
            completed=False,
        )
        self.assertEqual(
            self._next(), "Explain what you think caused the result."
        )

    def test_completed_experiment_suggestion(self):
        self.add_experiment(
            self.student,
            self.simulation,
            prediction="p",
            observation="o",
            explanation="e",
            completed=True,
        )
        self.assertEqual(
            self._next(),
            "Try the experiment again with a different mass or force, and "
            "predict what will change.",
        )

    def test_recent_tutor_question_suggestion(self):
        self.add_tutor_messages(self.student, self.lesson, student_turns=1, tutor_turns=1)
        self.assertEqual(
            self._next(),
            "Continue the investigation by running a related experiment in the "
            "Physics Lab.",
        )


# --- PRIVACY: NO INTERNAL SIGNALS ------------------------------


class ProgressPrivacyTests(ProgressDataMixin, TestCase):
    def test_no_misconception_codes_or_status_on_student_page(self):
        student = self.make_student()
        concept = self.make_concept()
        lesson = self.make_lesson(concept)
        misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION",
            title="Force and acceleration are the same quantity",
            description="A learner may treat them as interchangeable.",
            physics_concept=concept,
        )
        StudentMisconception.objects.create(student=student, misconception=misconception)
        self.add_evidence(
            student, Kind.EXPLANATION_SUBMITTED, lesson=lesson, detail="force is acceleration"
        )

        user_model = get_user_model()
        user = user_model.objects.create_user("alex", password="pw")
        student.user = user
        student.save(update_fields=["user"])
        self.client.force_login(user)

        response = self.client.get(PROGRESS_URL)
        self.assertNotContains(response, "FORCE_VS_ACCELERATION")
        self.assertNotContains(response, "misconception")
        self.assertNotContains(response, "candidate")


# --- PERFORMANCE -----------------------------------------------


class ProgressQueryBudgetTests(ProgressDataMixin, TestCase):
    def test_timeline_does_not_run_a_query_per_row(self):
        student = self.make_student()
        concept = self.make_concept()
        lesson = self.make_lesson(concept)
        simulation = self.make_simulation(concept)
        for i in range(12):
            self.add_evidence(student, Kind.QUESTION_ASKED, lesson=lesson, detail=f"q{i}")
        self.add_experiment(student, simulation, lesson=lesson, completed=True)
        self.add_tutor_messages(student, lesson, student_turns=2, tutor_turns=2)

        with self.assertNumQueries(6):
            build_student_learning_progress(student=student)
