"""Step 19 -- deterministic evidence-based learning patterns.

No AI provider is used anywhere in this module: the pattern engine is pure
synthesis of existing records. Timestamps are always controlled, never the real
clock, so the 14-day recency window is exercised deterministically.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation

from .models import (
    ExperimentAttempt,
    PracticeAttempt,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from .pattern_services import (
    RECENT_WINDOW_DAYS,
    SIGNAL_INQUIRY_SEQUENCE,
    SIGNAL_PRACTICE_AND_LAB,
    SIGNAL_REPEATED_PRACTICE,
    SIGNAL_RETRY_CORRECT,
    SIGNAL_TUTOR_AND_LAB,
    build_student_learning_patterns,
)

LEARNING_URL = reverse("students:learning")


class PatternDataMixin:
    seq = 0

    def setUp(self):
        self.now = timezone.now()
        self.recent = self.now - timedelta(days=2)
        self.older = self.now - timedelta(days=RECENT_WINDOW_DAYS + 10)

    def make_user(self, *, staff=False):
        PatternDataMixin.seq += 1
        return get_user_model().objects.create_user(
            f"u{PatternDataMixin.seq}", password="pw", is_staff=staff
        )

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name="Newton's Second Law", topic="Dynamics"):
        return PhysicsConcept.objects.create(name=name, description="c", topic=topic)

    def make_lesson(self, *concepts, title="Forces and Motion"):
        lesson = Lesson.objects.create(
            title=title, topic="Dynamics", grade_level="11", duration_minutes=45,
            learning_objectives=["Relate force, mass and acceleration."],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept, title="Newton's Second Law Lab"):
        return PhysicsSimulation.objects.create(
            concept=concept, title=title,
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def add_practice(
        self, student, lesson, *, concept=None, question_key="q1",
        is_correct=True, when=None, attempt_number=1, answer="10",
    ):
        row = PracticeAttempt.objects.create(
            student=student, lesson=lesson, concept=concept,
            question_key=question_key,
            question_type=PracticeAttempt.QuestionType.NUMERIC,
            question_prompt="What is the acceleration?",
            answer_text=answer, is_correct=is_correct, attempt_number=attempt_number,
        )
        if when is not None:
            PracticeAttempt.objects.filter(pk=row.pk).update(created_at=when)
            row.refresh_from_db()
        return row

    def add_experiment(
        self, student, simulation, *, lesson=None, completed=False,
        prediction="", observation="", explanation="",
        mass=None, force=None, accel=None, when=None,
    ):
        row = ExperimentAttempt.objects.create(
            student=student, simulation=simulation, lesson=lesson,
            prediction=prediction, observation=observation, explanation=explanation,
            mass_kg=mass, force_n=force, acceleration_m_s2=accel,
            completed_at=timezone.now() if completed else None,
        )
        if when is not None:
            ExperimentAttempt.objects.filter(pk=row.pk).update(
                started_at=when, updated_at=when
            )
            row.refresh_from_db()
        return row

    def add_tutor(self, student, lesson, *, student_turns=1, tutor_turns=1, when=None):
        session = TutorSession.objects.create(student=student, lesson=lesson)
        made = []
        for i in range(student_turns):
            made.append(TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.STUDENT, content=f"student q{i}"
            ))
        for i in range(tutor_turns):
            made.append(TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.TUTOR, content=f"tutor a{i}",
                mode="explain",
            ))
        if when is not None:
            for m in made:
                TutorMessage.objects.filter(pk=m.pk).update(created_at=when)
        return session

    def patterns(self, student, **kw):
        kw.setdefault("now", self.now)
        return build_student_learning_patterns(student=student, **kw)


# --- SERVICE (49.1-20) --------------------------------------------------


class PatternServiceTests(PatternDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = self.make_student()
        self.nsl = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.nsl)
        self.sim = self.make_simulation(self.nsl)

    def test_empty_student_is_honest(self):
        data = self.patterns(self.make_student("Empty"))
        self.assertFalse(data["has_activity"])
        self.assertEqual(data["recent_concepts"], [])
        self.assertEqual(data["concept_activity"], [])
        self.assertEqual(data["signals"], [])
        self.assertIsNotNone(data["next_investigation"])

    def test_recent_concepts_deduplicated(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        self.add_experiment(self.student, self.sim, lesson=self.lesson, when=self.recent)
        self.add_tutor(self.student, self.lesson, when=self.recent)
        data = self.patterns(self.student)
        self.assertEqual(data["recent_concepts"], ["Newton's Second Law"])

    def test_only_touched_concepts_appear(self):
        self.make_concept("Momentum", topic="Mechanics")  # never touched
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        data = self.patterns(self.student)
        names = [c["concept"] for c in data["concept_activity"]]
        self.assertEqual(names, ["Newton's Second Law"])

    def test_recency_window_is_deterministic(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.older)
        data = self.patterns(self.student)
        # historical total still counted
        self.assertEqual(data["practice_patterns"][0]["attempts"], 1)
        # but not "recent"
        self.assertEqual(data["recent_concepts"], [])

    def test_practice_counts_are_correct(self):
        for key, ok in [("q1", True), ("q2", False), ("q3", True)]:
            self.add_practice(
                self.student, self.lesson, concept=self.nsl,
                question_key=key, is_correct=ok, when=self.recent,
            )
        p = self.patterns(self.student)["practice_patterns"][0]
        self.assertEqual(p["attempts"], 3)
        self.assertEqual(p["correct"], 2)
        self.assertEqual(p["incorrect"], 1)
        self.assertEqual(p["questions"], 3)

    def test_retry_correct_detection(self):
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        p = self.patterns(self.student)["practice_patterns"][0]
        self.assertEqual(p["retry_correct"], 1)

    def test_first_try_correct_is_not_a_retry(self):
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, when=self.recent,
        )
        p = self.patterns(self.student)["practice_patterns"][0]
        self.assertEqual(p["retry_correct"], 0)

    def test_same_question_key_in_two_lessons_does_not_collide(self):
        # Default question keys are positional ("q1"...) and only unique per
        # lesson. An incorrect "q1" in lesson A and a correct "q1" in lesson B
        # (both teaching the same concept) must NOT read as a retry, and the
        # two "q1"s must count as two distinct questions.
        lesson_b = self.make_lesson(self.nsl, title="Forces and Motion II")
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            self.student, lesson_b, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=1, when=self.recent,
        )
        p = self.patterns(self.student)["practice_patterns"][0]
        self.assertEqual(p["attempts"], 2)
        self.assertEqual(p["questions"], 2)
        self.assertEqual(p["retry_correct"], 0)
        self.assertNotIn(
            SIGNAL_RETRY_CORRECT, [s["code"] for s in self.patterns(self.student)["signals"]]
        )

    def test_practice_read_keeps_the_newest_attempts(self):
        from unittest import mock

        # With a tiny cap, only the two most recent attempts survive the read;
        # the retry walk still sees them oldest-first.
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=1, when=self.older,
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q2",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q2",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        with mock.patch("apps.students.pattern_services.MAX_PRACTICE_ROWS", 2):
            p = self.patterns(self.student)["practice_patterns"][0]
        self.assertEqual(p["attempts"], 2)  # oldest "q1" dropped, newest two kept
        self.assertEqual(p["retry_correct"], 1)  # q2 incorrect -> later correct

    def test_tutor_question_in_multi_concept_lesson_is_not_attributed(self):
        acceleration = self.make_concept("Acceleration", topic="Kinematics")
        multi = self.make_lesson(self.nsl, acceleration, title="Force and Acceleration")
        self.add_tutor(self.student, multi, student_turns=2, when=self.recent)
        data = self.patterns(self.student)
        self.assertEqual(data["tutor_patterns"], [])
        self.assertEqual(data["concept_activity"], [])

    def test_experiment_counts_are_correct(self):
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True,
            prediction="p", observation="o", explanation="e", when=self.recent,
        )
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=False,
            prediction="p2", when=self.recent,
        )
        x = self.patterns(self.student)["experiment_patterns"][0]
        self.assertEqual(x["attempted"], 2)
        self.assertEqual(x["completed"], 1)
        self.assertEqual(x["predictions"], 2)
        self.assertEqual(x["observations"], 1)
        self.assertEqual(x["explanations"], 1)

    def test_tutor_student_message_count_only(self):
        self.add_tutor(
            self.student, self.lesson, student_turns=2, tutor_turns=5, when=self.recent
        )
        t = self.patterns(self.student)["tutor_patterns"][0]
        self.assertEqual(t["student_messages"], 2)

    def test_other_students_tutor_messages_excluded(self):
        other = self.make_student("Bob")
        self.add_tutor(self.student, self.lesson, student_turns=1, when=self.recent)
        self.add_tutor(other, self.lesson, student_turns=9, when=self.recent)
        t = self.patterns(self.student)["tutor_patterns"][0]
        self.assertEqual(t["student_messages"], 1)

    def test_same_concept_merges_across_modes(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        self.add_experiment(self.student, self.sim, lesson=self.lesson, when=self.recent)
        self.add_tutor(self.student, self.lesson, when=self.recent)
        activity = self.patterns(self.student)["concept_activity"]
        self.assertEqual(len(activity), 1)
        self.assertEqual(
            sorted(activity[0]["modes"]), ["experiment", "practice", "tutor"]
        )

    def test_signals_are_deterministic(self):
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=3),
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        first = self.patterns(self.student)["signals"]
        second = self.patterns(self.student)["signals"]
        self.assertEqual(first, second)
        self.assertEqual(first[0]["code"], SIGNAL_RETRY_CORRECT)

    def test_signal_limit_is_respected(self):
        # Enough conditions to trip several signals for one concept.
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=3),
        )
        for i in range(3):
            self.add_practice(
                self.student, self.lesson, concept=self.nsl, question_key="q1",
                is_correct=True, attempt_number=2 + i, when=self.recent,
            )
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True,
            prediction="p", observation="o", explanation="e", when=self.recent,
        )
        self.add_tutor(self.student, self.lesson, student_turns=1, when=self.recent)
        signals = self.patterns(self.student)["signals"]
        self.assertLessEqual(len(signals), 3)

    def test_next_incomplete_experiment_takes_priority(self):
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=False,
            prediction="I think it doubles", when=self.recent,
        )
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(step["text"], "Return to the Physics Lab and record what happened.")

    def test_next_observation_without_explanation(self):
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=False,
            prediction="p", observation="it sped up", when=self.recent,
        )
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(step["text"], "Explain what you think caused the result.")

    def test_next_practice_without_lab_suggests_lab(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(
            step["text"], "Investigate Newton's Second Law in the Physics Lab."
        )
        self.assertEqual(step["url"], reverse("physics_lab:index"))

    def test_next_lab_without_practice_suggests_practice(self):
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True,
            prediction="p", observation="o", explanation="e", when=self.recent,
        )
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(
            step["text"], "Try a practice problem about Newton's Second Law."
        )
        self.assertEqual(step["url"], reverse("students:practice", args=[self.lesson.slug]))

    def test_next_lab_and_practice_without_recent_tutor_suggests_tutor(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True, when=self.recent
        )
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(step["text"], "Discuss your result with the Physics Tutor.")

    def test_next_default_fallback(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True, when=self.recent
        )
        self.add_tutor(self.student, self.lesson, student_turns=1, when=self.recent)
        step = self.patterns(self.student)["next_investigation"]
        self.assertEqual(
            step["text"], "Choose another Physics activity and keep investigating."
        )

    def test_pending_recommendation_is_offered_as_next_step(self):
        from apps.teachers.models import TeacherIntervention

        TeacherIntervention.objects.create(
            student=self.student,
            action_type=TeacherIntervention.ActionType.RECOMMEND_LESSON,
            lesson=self.lesson, status=TeacherIntervention.Status.PENDING,
        )
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        step = self.patterns(self.student)["next_investigation"]
        self.assertIn("teacher", step["text"].lower())
        self.assertEqual(step["url"], reverse("students:recommendations"))

    def test_no_next_investigation_flag(self):
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        data = self.patterns(self.student, include_next_investigation=False)
        self.assertIsNone(data["next_investigation"])


# --- STUDENT PAGE (49.21-33) -----------------------------------------


class LearningPageTests(PatternDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.student = self.make_student("Alex", user=self.user)
        self.nsl = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.nsl)
        self.sim = self.make_simulation(self.nsl)
        self.client.force_login(self.user)

    def _seed_rich(self):
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True,
            prediction="p", observation="o", explanation="e",
            mass=2.0, force=20.0, accel=10.0, when=self.recent,
        )
        self.add_tutor(self.student, self.lesson, student_turns=2, when=self.recent)

    def test_page_loads(self):
        response = self.client.get(LEARNING_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Learning Patterns")

    def test_empty_state_is_honest(self):
        response = self.client.get(LEARNING_URL)
        self.assertContains(response, "will appear here as you explore Physics")
        self.assertNotContains(response, "0%")
        self.assertNotContains(response, "mastery")

    def test_rich_activity_renders_all_sections(self):
        self._seed_rich()
        response = self.client.get(LEARNING_URL)
        self.assertContains(response, "Recently explored")
        self.assertContains(response, "Newton&#x27;s Second Law")
        self.assertContains(response, "Physics practice")
        self.assertContains(response, "Physics Lab")
        self.assertContains(response, "Physics Tutor")
        self.assertContains(response, "returned to a practice question")
        self.assertContains(response, "Suggested next investigation")

    def test_practice_and_experiment_counts_shown(self):
        self._seed_rich()
        response = self.client.get(LEARNING_URL)
        self.assertContains(response, "2 attempts")
        self.assertContains(response, "1 experiment completed")

    def test_student_id_query_is_ignored(self):
        self._seed_rich()
        other = self.make_student("Bob")
        self.add_practice(
            other, self.lesson, concept=self.nsl, question_key="zzz",
            answer="BOBSECRET", is_correct=True, when=self.recent,
        )
        response = self.client.get(LEARNING_URL, {"student_id": other.pk})
        self.assertNotContains(response, "BOBSECRET")

    def test_other_students_data_absent(self):
        alice_only = self.make_concept("Kinematics", topic="Motion")
        alice_lesson = self.make_lesson(alice_only, title="Kinematics")
        self.add_tutor(self.student, alice_lesson, student_turns=1, when=self.recent)

        bob = self.make_student("Bob")
        bob_concept = self.make_concept("Momentum", topic="Mechanics")
        bob_lesson = self.make_lesson(bob_concept, title="Momentum")
        self.add_tutor(bob, bob_lesson, student_turns=1, when=self.recent)

        response = self.client.get(LEARNING_URL)
        self.assertContains(response, "Kinematics")
        self.assertNotContains(response, "Momentum")

    def test_untrusted_text_is_escaped(self):
        xss_concept = self.make_concept("<script>alert(1)</script>", topic="x")
        xss_lesson = self.make_lesson(xss_concept, title="XSS lesson")
        session = TutorSession.objects.create(student=self.student, lesson=xss_lesson)
        msg = TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT,
            content="<img src=x onerror=alert(2)>",
        )
        TutorMessage.objects.filter(pk=msg.pk).update(created_at=self.recent)

        response = self.client.get(LEARNING_URL)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<img src=x onerror=alert(2)>")
        self.assertContains(response, "&lt;script&gt;")

    def test_no_internal_misconception_labels(self):
        from apps.physics.models import PhysicsMisconception
        from apps.students.models import StudentMisconception

        catalog = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION", title="Force and acceleration confusion",
            description="d", physics_concept=self.nsl,
        )
        StudentMisconception.objects.create(student=self.student, misconception=catalog)
        self._seed_rich()
        response = self.client.get(LEARNING_URL)
        self.assertNotContains(response, "FORCE_VS_ACCELERATION")
        self.assertNotContains(response, "misconception")
        self.assertNotContains(response, "candidate")

    def test_no_mastery_or_score_language(self):
        self._seed_rich()
        body = self.client.get(LEARNING_URL).content.decode().lower()
        for banned in ("mastery", "proficiency", "ability score", "risk score",
                       "performance rating", "you are weak", "low performing"):
            self.assertNotIn(banned, body)

    def test_progress_page_links_to_learning_patterns(self):
        self._seed_rich()
        response = self.client.get(reverse("students:progress"))
        self.assertContains(response, LEARNING_URL)
        self.assertContains(response, "Learning patterns")

    def test_nav_has_learning_patterns_link(self):
        response = self.client.get(LEARNING_URL)
        self.assertContains(response, ">Learning Patterns<")


# --- TEACHER PAGE (49.34-39) ----------------------------------------


class TeacherPatternTests(PatternDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student("Alex")
        self.nsl = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.nsl)
        self.sim = self.make_simulation(self.nsl)
        self.client.force_login(self.teacher)
        self.url = reverse("teachers:student_detail", args=[self.student.pk])

    def _seed(self):
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            self.student, self.lesson, concept=self.nsl, question_key="q1",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True, when=self.recent
        )
        self.add_tutor(self.student, self.lesson, student_turns=2, when=self.recent)

    def test_teacher_sees_learning_patterns_section(self):
        self._seed()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Learning patterns")
        self.assertContains(response, "Recently explored")

    def test_teacher_sees_objective_counts(self):
        self._seed()
        response = self.client.get(self.url)
        self.assertContains(response, "2 attempt")
        self.assertContains(response, "1 correct attempt")
        self.assertContains(response, "1 incorrect attempt")
        self.assertContains(response, "1 completed of 1 attempted")
        self.assertContains(response, "2 student question")

    def test_teacher_sees_observed_activity_signals(self):
        self._seed()
        response = self.client.get(self.url)
        self.assertContains(response, "returned to a practice question")

    def test_other_students_data_isolated(self):
        self._seed()
        bob = self.make_student("Bob")
        bob_concept = self.make_concept("Torque", topic="Rotation")
        bob_lesson = self.make_lesson(bob_concept, title="Torque")
        self.add_practice(
            bob, bob_lesson, concept=bob_concept, question_key="bq1",
            is_correct=False, attempt_number=1, when=self.recent - timedelta(hours=2),
        )
        self.add_practice(
            bob, bob_lesson, concept=bob_concept, question_key="bq1",
            is_correct=True, attempt_number=2, when=self.recent,
        )
        response = self.client.get(self.url)
        # Alex's own retry signal is present; Bob's (about Torque) never is.
        self.assertContains(response, "returned to a practice question about Newton")
        self.assertNotContains(response, "about Torque")

        from apps.teachers.services import build_teacher_student_evidence

        ctx = build_teacher_student_evidence(student=self.student)
        names = [c["concept"] for c in ctx["learning_patterns"]["concept_activity"]]
        self.assertEqual(names, ["Newton's Second Law"])

    def test_no_ai_or_provider_information(self):
        self._seed()
        body = self.client.get(self.url).content.decode()
        for banned in ("api_key", "OPENAI", "provider_metadata", "raw model response",
                       "mastery score", "weakness score", "risk score"):
            self.assertNotIn(banned, body)

    def test_pattern_output_is_deterministic(self):
        self._seed()
        first = build_student_learning_patterns(
            student=self.student, now=self.now, include_next_investigation=False
        )
        second = build_student_learning_patterns(
            student=self.student, now=self.now, include_next_investigation=False
        )
        self.assertEqual(first, second)


# --- SECURITY (49.40-42) -------------------------------------------


class PatternSecurityTests(PatternDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.nsl = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.nsl)

    def test_student_cannot_reach_teacher_workspace(self):
        student_user = self.make_user(staff=False)
        self.client.force_login(student_user)
        victim = self.make_student("Victim")
        response = self.client.get(
            reverse("teachers:student_detail", args=[victim.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_reach_teacher_workspace(self):
        victim = self.make_student("Victim")
        response = self.client.get(
            reverse("teachers:student_detail", args=[victim.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_get_is_read_only(self):
        student_user = self.make_user()
        student = self.make_student("Alex", user=student_user)
        self.add_practice(student, self.lesson, concept=self.nsl, when=self.recent)
        self.client.force_login(student_user)

        before = PracticeAttempt.objects.count()
        self.client.get(LEARNING_URL)
        self.client.get(LEARNING_URL)
        self.assertEqual(PracticeAttempt.objects.count(), before)

    def test_learning_page_uses_the_shared_guest_for_anonymous(self):
        self.client.get(LEARNING_URL)
        self.client.get(LEARNING_URL)
        self.assertEqual(
            StudentProfile.objects.filter(user__isnull=True).count(), 1
        )


# --- ACCESSIBILITY (49.43-47) ------------------------------------


class PatternAccessibilityTests(PatternDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.student = self.make_student("Alex", user=self.user)
        self.nsl = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.nsl)
        self.sim = self.make_simulation(self.nsl)
        self.add_practice(self.student, self.lesson, concept=self.nsl, when=self.recent)
        self.add_experiment(
            self.student, self.sim, lesson=self.lesson, completed=True, when=self.recent
        )
        self.client.force_login(self.user)

    def test_semantic_headings_and_real_controls(self):
        body = self.client.get(LEARNING_URL).content.decode()
        self.assertIn("<h1>", body)
        self.assertIn("<h2", body)
        self.assertIn('aria-labelledby="patterns', body)
        self.assertIn('href="', body)

    def test_next_step_is_a_real_link_with_text_label(self):
        response = self.client.get(LEARNING_URL)
        self.assertContains(response, "Go to Physics Tutor")

    def test_meaning_is_textual_not_color_only(self):
        response = self.client.get(LEARNING_URL)
        # counts + signal text carry the meaning, not a colour swatch
        self.assertContains(response, "attempt")


# --- QUERY BUDGET (49.50) --------------------------------------


class PatternQueryBudgetTests(PatternDataMixin, TestCase):
    def test_build_student_learning_patterns_is_bounded(self):
        student = self.make_student("Alex")
        nsl = self.make_concept("Newton's Second Law")
        momentum = self.make_concept("Momentum", topic="Mechanics")
        lesson = self.make_lesson(nsl, momentum)
        sim = self.make_simulation(nsl)
        for i in range(15):
            self.add_practice(
                student, lesson, concept=nsl, question_key=f"q{i}",
                is_correct=(i % 2 == 0), when=self.recent,
            )
        for _ in range(6):
            self.add_experiment(
                student, sim, lesson=lesson, completed=True, when=self.recent
            )
        self.add_tutor(student, lesson, student_turns=8, when=self.recent)

        # Fixed cost: practice(+prefetch), experiments(+prefetch), tutor(+prefetch),
        # simulation concept names, pending-recommendation count. No per-row queries.
        with self.assertNumQueries(8):
            build_student_learning_patterns(student=student, now=self.now)

    def test_budget_does_not_grow_with_history(self):
        student = self.make_student("Alex")
        nsl = self.make_concept("Newton's Second Law")
        lesson = self.make_lesson(nsl)
        sim = self.make_simulation(nsl)
        for i in range(3):
            self.add_practice(
                student, lesson, concept=nsl, question_key=f"q{i}", when=self.recent
            )
        self.add_experiment(student, sim, lesson=lesson, completed=True, when=self.recent)
        self.add_tutor(student, lesson, student_turns=2, when=self.recent)
        with self.assertNumQueries(8):
            build_student_learning_patterns(student=student, now=self.now)

        for i in range(3, 40):
            self.add_practice(
                student, lesson, concept=nsl, question_key=f"q{i}", when=self.recent
            )
        for _ in range(10):
            self.add_experiment(
                student, sim, lesson=lesson, completed=True, when=self.recent
            )
        self.add_tutor(student, lesson, student_turns=12, when=self.recent)
        with self.assertNumQueries(8):
            build_student_learning_patterns(student=student, now=self.now)


# --- REGRESSION (49.48-55) -----------------------------------


class PatternRegressionTests(PatternDataMixin, TestCase):
    def test_no_new_recommendation_action_type(self):
        from apps.teachers.models import TeacherIntervention

        self.assertNotIn("recommend_practice", TeacherIntervention.ActionType.values)
        self.assertNotIn("pattern", " ".join(TeacherIntervention.ActionType.values))

    def test_pattern_engine_creates_no_records(self):
        from apps.students.models import LearningEvidence
        from apps.teachers.models import TeacherIntervention

        student = self.make_student("Alex")
        nsl = self.make_concept("Newton's Second Law")
        lesson = self.make_lesson(nsl)
        self.add_practice(student, lesson, concept=nsl, when=self.recent)

        ev_before = LearningEvidence.objects.count()
        iv_before = TeacherIntervention.objects.count()
        build_student_learning_patterns(student=student, now=self.now)
        self.assertEqual(LearningEvidence.objects.count(), ev_before)
        self.assertEqual(TeacherIntervention.objects.count(), iv_before)

    def test_progress_page_still_renders(self):
        user = self.make_user()
        student = self.make_student("Alex", user=user)
        self.client.force_login(user)
        response = self.client.get(reverse("students:progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My learning journey")
