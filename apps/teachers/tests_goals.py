"""Step 21 -- teacher-guided learning goals. No AI provider is used anywhere."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation
from apps.students.models import (
    ExperimentAttempt,
    PracticeAttempt,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from apps.physics.models import PhysicsMisconception

from .goal_services import (
    GoalError,
    close_learning_goal,
    create_learning_goal,
    list_student_visible_goals,
)
from .models import TeacherLearningGoal

D = PhysicsConcept.Difficulty


class GoalMixin:
    seq = 0

    def setUp(self):
        self.now = timezone.now()

    def uid(self):
        GoalMixin.seq += 1
        return GoalMixin.seq

    def make_teacher(self):
        return get_user_model().objects.create_user(
            f"teach{self.uid()}", password="pw", is_staff=True
        )

    def make_student_user(self):
        return get_user_model().objects.create_user(f"stud{self.uid()}", password="pw")

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name=None, difficulty=D.INTERMEDIATE):
        return PhysicsConcept.objects.create(
            name=name or f"Concept {self.uid()}", description="d",
            topic="Dynamics", difficulty=difficulty,
        )

    def make_lesson(self, *concepts, title=None, problems=None):
        lesson = Lesson.objects.create(
            title=title or f"Lesson {self.uid()}", topic="Dynamics",
            grade_level="11", duration_minutes=45, learning_objectives=["x"],
            problems=problems or [],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept, title=None):
        return PhysicsSimulation.objects.create(
            concept=concept, title=title or f"Sim {self.uid()}",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def numeric_problems(self, *keys):
        return [
            {"key": k, "type": "numeric", "prompt": f"Question {k}?", "answer": 5}
            for k in keys
        ]

    def add_practice(self, student, lesson, key, *, when=None):
        row = PracticeAttempt.objects.create(
            student=student, lesson=lesson, question_key=key,
            question_type=PracticeAttempt.QuestionType.NUMERIC,
            question_prompt="p", answer_text="5", is_correct=True, attempt_number=1,
        )
        if when is not None:
            PracticeAttempt.objects.filter(pk=row.pk).update(created_at=when)
        return row

    def complete_experiment(self, student, simulation, *, lesson=None):
        return ExperimentAttempt.objects.create(
            student=student, simulation=simulation, lesson=lesson,
            prediction="p", observation="o", explanation="e",
            completed_at=timezone.now(),
        )

    def goal(self, student, teacher, concept, **kw):
        return create_learning_goal(
            student=student, teacher=teacher, concept_id=concept.pk,
            lesson_id=kw.get("lesson").pk if kw.get("lesson") else None,
            simulation_id=kw.get("simulation").pk if kw.get("simulation") else None,
            misconception_id=kw.get("misconception").pk if kw.get("misconception") else None,
            teacher_note=kw.get("teacher_note", ""),
        )


# --- MODEL (51.1-10) --------------------------------------------------


class GoalModelTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.student = self.make_student()
        self.concept = self.make_concept("Newton's Third Law")
        self.lesson = self.make_lesson(self.concept)
        self.sim = self.make_simulation(self.concept)

    def test_goal_can_be_created_with_all_targets(self):
        g = self.goal(self.student, self.teacher, self.concept,
                      lesson=self.lesson, simulation=self.sim,
                      teacher_note="Investigate action and reaction.")
        self.assertEqual(g.teacher, self.teacher)
        self.assertEqual(g.student, self.student)
        self.assertEqual(g.concept, self.concept)
        self.assertEqual(g.lesson, self.lesson)
        self.assertEqual(g.simulation, self.sim)
        self.assertEqual(g.teacher_note, "Investigate action and reaction.")
        self.assertEqual(g.status, TeacherLearningGoal.Status.ACTIVE)
        self.assertIsNotNone(g.created_at)
        self.assertIsNone(g.completed_at)
        self.assertIsNone(g.closed_at)

    def test_concept_only_goal_is_allowed(self):
        g = self.goal(self.student, self.teacher, self.concept)
        self.assertEqual(g.concept, self.concept)
        self.assertIsNone(g.lesson)
        self.assertIsNone(g.simulation)

    def test_closing_records_closed_at_and_status(self):
        g = self.goal(self.student, self.teacher, self.concept)
        close_learning_goal(goal_id=g.pk, student=self.student)
        g.refresh_from_db()
        self.assertEqual(g.status, TeacherLearningGoal.Status.CLOSED)
        self.assertIsNotNone(g.closed_at)
        self.assertIsNone(g.completed_at)


# --- VALIDATION (51.11-20) -----------------------------------------


class GoalValidationTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.student = self.make_student()
        self.concept = self.make_concept("Force")
        self.other_concept = self.make_concept("Momentum")
        self.lesson = self.make_lesson(self.concept)
        self.sim = self.make_simulation(self.concept)

    def test_missing_concept_rejected(self):
        with self.assertRaises(GoalError):
            create_learning_goal(student=self.student, teacher=self.teacher, concept_id=None)

    def test_invalid_concept_rejected(self):
        with self.assertRaises(GoalError):
            create_learning_goal(student=self.student, teacher=self.teacher, concept_id=99999)
        with self.assertRaises(GoalError):
            create_learning_goal(student=self.student, teacher=self.teacher, concept_id="abc")

    def test_invalid_lesson_rejected(self):
        with self.assertRaises(GoalError):
            create_learning_goal(
                student=self.student, teacher=self.teacher,
                concept_id=self.concept.pk, lesson_id=99999,
            )

    def test_invalid_simulation_rejected(self):
        with self.assertRaises(GoalError):
            create_learning_goal(
                student=self.student, teacher=self.teacher,
                concept_id=self.concept.pk, simulation_id=99999,
            )

    def test_mismatched_lesson_concept_rejected(self):
        wrong_lesson = self.make_lesson(self.other_concept)
        with self.assertRaises(GoalError):
            create_learning_goal(
                student=self.student, teacher=self.teacher,
                concept_id=self.concept.pk, lesson_id=wrong_lesson.pk,
            )

    def test_mismatched_simulation_concept_rejected(self):
        wrong_sim = self.make_simulation(self.other_concept)
        with self.assertRaises(GoalError):
            create_learning_goal(
                student=self.student, teacher=self.teacher,
                concept_id=self.concept.pk, simulation_id=wrong_sim.pk,
            )

    def test_duplicate_active_goal_rejected(self):
        self.goal(self.student, self.teacher, self.concept, lesson=self.lesson)
        with self.assertRaises(GoalError):
            self.goal(self.student, self.teacher, self.concept, lesson=self.lesson)
        # a different target is fine
        self.goal(self.student, self.teacher, self.concept, simulation=self.sim)

    def test_duplicate_concept_only_active_goal_rejected(self):
        # The partial DB constraint can't catch NULL/NULL targets on SQLite;
        # the service-level check must.
        self.goal(self.student, self.teacher, self.concept)
        with self.assertRaises(GoalError):
            self.goal(self.student, self.teacher, self.concept)
        self.assertEqual(
            TeacherLearningGoal.objects.filter(concept=self.concept).count(), 1
        )
        # a different concept is still fine
        self.goal(self.student, self.teacher, self.other_concept)

    def test_duplicate_allowed_after_close(self):
        g = self.goal(self.student, self.teacher, self.concept)
        close_learning_goal(goal_id=g.pk, student=self.student)
        self.goal(self.student, self.teacher, self.concept)  # no error

    def test_cross_student_misconception_rejected(self):
        other_student = self.make_student("Bob")
        catalog = PhysicsMisconception.objects.create(
            code="X", title="t", description="d", physics_concept=self.concept
        )
        foreign = StudentMisconception.objects.create(
            student=other_student, misconception=catalog
        )
        with self.assertRaises(GoalError):
            create_learning_goal(
                student=self.student, teacher=self.teacher,
                concept_id=self.concept.pk, misconception_id=foreign.pk,
            )
        self.assertEqual(TeacherLearningGoal.objects.count(), 0)


# --- AUTHORIZATION + HTTP (51.21-27, 55-57) ---------------------


class GoalHttpTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.student = self.make_student("Alex")
        self.concept = self.make_concept("Newton's Third Law")
        self.lesson = self.make_lesson(self.concept)
        self.create_url = reverse("teachers:create_goal", args=[self.student.pk])

    def test_teacher_can_create_goal_via_post(self):
        self.client.force_login(self.teacher)
        r = self.client.post(self.create_url, {
            "concept_id": self.concept.pk, "lesson_id": self.lesson.pk,
            "teacher_note": "focus here",
        })
        self.assertEqual(r.status_code, 200)
        g = TeacherLearningGoal.objects.get()
        self.assertEqual(g.concept, self.concept)
        self.assertEqual(g.teacher, self.teacher)

    def test_teacher_can_close_goal_via_post(self):
        self.client.force_login(self.teacher)
        g = self.goal(self.student, self.teacher, self.concept)
        r = self.client.post(
            reverse("teachers:close_goal", args=[self.student.pk, g.pk])
        )
        self.assertEqual(r.status_code, 200)
        g.refresh_from_db()
        self.assertEqual(g.status, TeacherLearningGoal.Status.CLOSED)

    def test_student_cannot_create_goal(self):
        self.client.force_login(self.make_student_user())
        r = self.client.post(self.create_url, {"concept_id": self.concept.pk})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(TeacherLearningGoal.objects.count(), 0)

    def test_student_cannot_close_goal(self):
        g = self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.make_student_user())
        r = self.client.post(
            reverse("teachers:close_goal", args=[self.student.pk, g.pk])
        )
        self.assertEqual(r.status_code, 403)
        g.refresh_from_db()
        self.assertEqual(g.status, TeacherLearningGoal.Status.ACTIVE)

    def test_anonymous_denied(self):
        r = self.client.post(self.create_url, {"concept_id": self.concept.pk})
        self.assertEqual(r.status_code, 403)

    def test_get_cannot_create_or_close(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.create_url).status_code, 405)
        g = self.goal(self.student, self.teacher, self.concept)
        self.assertEqual(
            self.client.get(
                reverse("teachers:close_goal", args=[self.student.pk, g.pk])
            ).status_code,
            405,
        )
        g.refresh_from_db()
        self.assertEqual(g.status, TeacherLearningGoal.Status.ACTIVE)

    def test_smuggled_authority_fields_are_ignored(self):
        self.client.force_login(self.teacher)
        other_student = self.make_student("Bob")
        other_teacher = self.make_teacher()
        other_concept = self.make_concept("Momentum")
        r = self.client.post(self.create_url, {
            "concept_id": self.concept.pk,
            "student_id": other_student.pk,
            "teacher_id": other_teacher.pk,
            "teacher": other_teacher.pk,
            "status": "completed",
            "created_at": "2000-01-01",
        })
        self.assertEqual(r.status_code, 200)
        g = TeacherLearningGoal.objects.get()
        self.assertEqual(g.student, self.student)       # URL wins
        self.assertEqual(g.teacher, self.teacher)       # request.user wins
        self.assertEqual(g.status, TeacherLearningGoal.Status.ACTIVE)  # server default
        self.assertGreater(g.created_at.year, 2020)

    def test_csrf_is_enforced(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.teacher)
        r = csrf_client.post(self.create_url, {"concept_id": self.concept.pk})
        self.assertEqual(r.status_code, 403)


# --- STUDENT VISIBILITY (51.28-35) ----------------------------


class GoalStudentVisibilityTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.user = self.make_student_user()
        self.student = self.make_student("Alex", user=self.user)
        self.concept = self.make_concept("Newton's Third Law")
        self.lesson = self.make_lesson(self.concept)
        self.url = reverse("students:goals")

    def test_student_sees_own_active_and_history(self):
        g1 = self.goal(self.student, self.teacher, self.concept, lesson=self.lesson,
                       teacher_note="PRIVATE-NOTE-XYZZY")
        g2 = self.goal(self.student, self.teacher, self.make_concept("Velocity"))
        close_learning_goal(goal_id=g2.pk, student=self.student)

        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "Your Learning Goals")
        self.assertContains(r, "Newton&#x27;s Third Law")
        self.assertContains(r, "Past goals")
        self.assertContains(r, "Closed")

    def test_teacher_note_never_reaches_student(self):
        self.goal(self.student, self.teacher, self.concept, teacher_note="PRIVATE-NOTE-XYZZY")
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertNotContains(r, "PRIVATE-NOTE-XYZZY")
        data = list_student_visible_goals(student=self.student)
        self.assertNotIn("PRIVATE-NOTE-XYZZY", str(data))
        for row in data["goals_active"]:
            self.assertNotIn("teacher_note", row)
            self.assertNotIn("id", row)
            self.assertNotIn("misconception", row)

    def test_misconception_never_reaches_student(self):
        catalog = PhysicsMisconception.objects.create(
            code="FORCE_X", title="Force confusion", description="d",
            physics_concept=self.concept,
        )
        obs = StudentMisconception.objects.create(
            student=self.student, misconception=catalog
        )
        self.goal(self.student, self.teacher, self.concept, misconception=obs)
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertNotContains(r, "FORCE_X")
        self.assertNotContains(r, "Force confusion")
        self.assertNotContains(r, "misconception")

    def test_student_cannot_see_another_students_goals(self):
        bob = self.make_student("Bob")
        self.goal(bob, self.teacher, self.make_concept("Bob Only Concept"))
        self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "Newton&#x27;s Third Law")
        self.assertNotContains(r, "Bob Only Concept")

    def test_student_id_query_is_ignored(self):
        bob = self.make_student("Bob")
        self.goal(bob, self.teacher, self.make_concept("Bob Only Concept"))
        self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"student_id": bob.pk})
        self.assertContains(r, "Newton&#x27;s Third Law")
        self.assertNotContains(r, "Bob Only Concept")

    def test_empty_state_when_no_goals(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "hasn&rsquo;t set a learning goal")
        self.assertNotContains(r, "mastery")

    def test_guest_fallback_for_anonymous(self):
        self.client.get(self.url)
        self.client.get(self.url)
        self.assertEqual(StudentProfile.objects.filter(user__isnull=True).count(), 1)


# --- DESTINATIONS (51.36-39) --------------------------------


class GoalDestinationTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.student = self.make_student()
        self.concept = self.make_concept("Newton's Third Law")

    def test_lesson_goal_links_to_lesson_route(self):
        lesson = self.make_lesson(self.concept, title="N3L Lesson")
        self.goal(self.student, self.teacher, self.concept, lesson=lesson)
        row = list_student_visible_goals(student=self.student)["goals_active"][0]
        self.assertEqual(row["primary_url"], reverse("students:tutor", args=[lesson.slug]))
        self.assertEqual(row["secondary_url"], reverse("students:practice", args=[lesson.slug]))

    def test_simulation_goal_links_to_physics_lab(self):
        sim = self.make_simulation(self.concept, title="N3L Sim")
        self.goal(self.student, self.teacher, self.concept, simulation=sim)
        row = list_student_visible_goals(student=self.student)["goals_active"][0]
        self.assertEqual(row["primary_url"], reverse("physics_lab:detail", args=[sim.slug]))

    def test_concept_only_goal_resolves_deterministically(self):
        lesson = self.make_lesson(self.concept, title="Concept Lesson")
        self.goal(self.student, self.teacher, self.concept)
        row = list_student_visible_goals(student=self.student)["goals_active"][0]
        self.assertEqual(row["primary_url"], reverse("students:tutor", args=[lesson.slug]))

    def test_concept_only_goal_with_no_targets_falls_back_to_lessons(self):
        self.goal(self.student, self.teacher, self.concept)
        row = list_student_visible_goals(student=self.student)["goals_active"][0]
        self.assertEqual(row["primary_url"], reverse("students:lessons"))

    def test_all_destination_urls_are_reversed_named_routes(self):
        self.make_lesson(self.concept)
        self.goal(self.student, self.teacher, self.concept)
        row = list_student_visible_goals(student=self.student)["goals_active"][0]
        self.assertTrue(row["primary_url"].startswith("/"))


# --- COMPLETION (51.40-47) ---------------------------------


class GoalCompletionTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.student = self.make_student("Alex")
        self.concept = self.make_concept("Newton's Second Law")
        self.sim = self.make_simulation(self.concept)
        self.other_sim = self.make_simulation(self.make_concept("Velocity"))

    def _status(self, goal):
        goal.refresh_from_db()
        return goal.status

    def test_experiment_completion_completes_the_matching_goal(self):
        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        self.complete_experiment(self.student, self.sim)
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.COMPLETED)
        goal.refresh_from_db()
        self.assertIsNotNone(goal.completed_at)

    def test_unrelated_experiment_does_not_complete_goal(self):
        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        self.complete_experiment(self.student, self.other_sim)
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.ACTIVE)

    def test_other_students_experiment_does_not_complete_goal(self):
        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        bob = self.make_student("Bob")
        self.complete_experiment(bob, self.sim)
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.ACTIVE)

    def test_pre_existing_completed_experiment_does_not_retro_complete(self):
        old = ExperimentAttempt.objects.create(
            student=self.student, simulation=self.sim,
            prediction="p", observation="o", explanation="e",
            completed_at=timezone.now(),
        )
        ExperimentAttempt.objects.filter(pk=old.pk).update(
            completed_at=self.now - timedelta(days=2)
        )
        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        goal.refresh_from_db()
        self.assertEqual(goal.status, TeacherLearningGoal.Status.ACTIVE)

    def test_practice_completion_is_honest(self):
        lesson = self.make_lesson(self.concept, problems=self.numeric_problems("q1", "q2"))
        goal = self.goal(self.student, self.teacher, self.concept, lesson=lesson)
        self.add_practice(self.student, lesson, "q1")
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.ACTIVE)
        self.add_practice(self.student, lesson, "q2")
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.COMPLETED)

    def test_lesson_without_practice_questions_stays_active(self):
        lesson = self.make_lesson(self.concept, problems=[])
        goal = self.goal(self.student, self.teacher, self.concept, lesson=lesson)
        # tutor + experiment activity, but no stable lesson-completion signal
        session = TutorSession.objects.create(student=self.student, lesson=lesson)
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="q"
        )
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.ACTIVE)

    def test_concept_only_goal_never_auto_completes(self):
        goal = self.goal(self.student, self.teacher, self.concept)
        self.complete_experiment(self.student, self.sim)
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.ACTIVE)

    def test_dual_target_goal_completes_via_either_activity(self):
        lesson = self.make_lesson(self.concept, problems=self.numeric_problems("q1"))
        # goal targets BOTH a lesson (practice) and a simulation (experiment)
        practice_goal = self.goal(
            self.student, self.teacher, self.concept, lesson=lesson, simulation=self.sim
        )
        self.add_practice(self.student, lesson, "q1")
        self.assertEqual(self._status(practice_goal), TeacherLearningGoal.Status.COMPLETED)

        # a second dual-target goal (different concept) completes via the lab
        c2 = self.make_concept("Force")
        lesson2 = self.make_lesson(c2, problems=self.numeric_problems("q1"))
        sim2 = self.make_simulation(c2)
        lab_goal = self.goal(
            self.student, self.teacher, c2, lesson=lesson2, simulation=sim2
        )
        self.complete_experiment(self.student, sim2)
        self.assertEqual(self._status(lab_goal), TeacherLearningGoal.Status.COMPLETED)

    def test_teacher_close_wins_a_race_with_completion(self):
        # A close that lands first must not be flipped to completed by a later
        # sync working from a stale in-memory instance (the write is conditional
        # on status=active at the database).
        from .goal_services import sync_learning_goal_completion

        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        close_learning_goal(goal_id=goal.pk, student=self.student)
        # The target activity does finish afterwards (signal is a no-op: goal not active).
        self.complete_experiment(self.student, self.sim)
        goal.refresh_from_db()
        self.assertEqual(goal.status, TeacherLearningGoal.Status.CLOSED)

        goal.status = TeacherLearningGoal.Status.ACTIVE  # pretend the caller is stale
        changed = sync_learning_goal_completion(goal)
        self.assertFalse(changed)
        goal.refresh_from_db()
        self.assertEqual(goal.status, TeacherLearningGoal.Status.CLOSED)
        self.assertIsNone(goal.completed_at)

    def test_closed_goal_does_not_auto_reopen(self):
        goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        close_learning_goal(goal_id=goal.pk, student=self.student)
        self.complete_experiment(self.student, self.sim)
        self.assertEqual(self._status(goal), TeacherLearningGoal.Status.CLOSED)

    def test_multiple_goals_do_not_all_complete(self):
        sim_goal = self.goal(self.student, self.teacher, self.concept, simulation=self.sim)
        concept_goal = self.goal(
            self.student, self.teacher, self.make_concept("Force"),
        )
        self.complete_experiment(self.student, self.sim)
        self.assertEqual(self._status(sim_goal), TeacherLearningGoal.Status.COMPLETED)
        self.assertEqual(self._status(concept_goal), TeacherLearningGoal.Status.ACTIVE)


# --- INTEGRATION + XSS (51.48-54) --------------------------


class GoalIntegrationTests(GoalMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_teacher()
        self.user = self.make_student_user()
        self.student = self.make_student("Alex", user=self.user)
        self.concept = self.make_concept("Newton's Third Law")
        self.lesson = self.make_lesson(self.concept)

    def test_progress_page_shows_active_goal_count(self):
        self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.user)
        r = self.client.get(reverse("students:progress"))
        self.assertContains(r, "active learning goal")
        self.assertContains(r, reverse("students:goals"))

    def test_learning_path_shows_teacher_selected_goal(self):
        self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.user)
        r = self.client.get(reverse("students:path"))
        self.assertContains(r, "Teacher-selected goal")
        self.assertContains(r, "Newton&#x27;s Third Law")

    def test_learning_patterns_distinguishes_goal_from_observed_activity(self):
        self.goal(self.student, self.teacher, self.concept)
        self.client.force_login(self.user)
        r = self.client.get(reverse("students:learning"))
        self.assertContains(r, "Teacher-selected goal")
        self.assertContains(r, "separate from the observed activity")

    def test_teacher_workspace_shows_goal_and_activity_summary(self):
        self.goal(self.student, self.teacher, self.concept, lesson=self.lesson,
                  teacher_note="TEACHER-PRIVATE-NOTE")
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("teachers:student_detail", args=[self.student.pk]))
        self.assertContains(r, "Learning goals")
        self.assertContains(r, "Explore Newton&#x27;s Third Law")
        self.assertContains(r, "Student activity for")
        self.assertContains(r, "TEACHER-PRIVATE-NOTE")  # teacher-visible

    def test_teacher_note_and_lesson_title_are_escaped_on_teacher_page(self):
        xss_concept = self.make_concept("<script>alert('c')</script>")
        xss_lesson = self.make_lesson(xss_concept, title="<script>alert('l')</script>")
        self.goal(self.student, self.teacher, xss_concept, lesson=xss_lesson,
                  teacher_note="<script>alert('n')</script>")
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("teachers:student_detail", args=[self.student.pk]))
        self.assertNotContains(r, "<script>alert('n')</script>")
        self.assertNotContains(r, "<script>alert('l')</script>")
        self.assertContains(r, "&lt;script&gt;")

    def test_concept_name_escaped_on_student_page(self):
        xss_concept = self.make_concept("<script>alert('c')</script>")
        self.goal(self.student, self.teacher, xss_concept)
        self.client.force_login(self.user)
        r = self.client.get(reverse("students:goals"))
        self.assertNotContains(r, "<script>alert('c')</script>")
        self.assertContains(r, "&lt;script&gt;")


# --- QUERY BUDGET (51.52) ---------------------------------


class GoalQueryBudgetTests(GoalMixin, TestCase):
    def test_goal_list_with_explicit_targets_is_one_query(self):
        teacher = self.make_teacher()
        student = self.make_student()
        for i in range(12):
            c = self.make_concept(f"Concept {i}")
            les = self.make_lesson(c)
            g = self.goal(student, teacher, c, lesson=les)
            if i % 2:
                close_learning_goal(goal_id=g.pk, student=student)
        with self.assertNumQueries(1):
            list_student_visible_goals(student=student)

    def test_concept_only_goals_do_not_scale_query_count(self):
        teacher = self.make_teacher()
        student = self.make_student()

        def count():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as ctx:
                list_student_visible_goals(student=student)
            return len(ctx)

        for i in range(3):
            self.goal(student, teacher, self.make_concept(f"C{i}"))
        few = count()
        for i in range(3, 15):
            self.goal(student, teacher, self.make_concept(f"C{i}"))
        many = count()
        self.assertEqual(few, many)  # bounded: does not grow per concept-only goal
