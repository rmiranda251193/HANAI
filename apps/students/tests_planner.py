"""Step 22 -- adaptive student activity planner. No AI provider is used."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsMisconception, PhysicsSimulation
from apps.teachers.goal_services import create_learning_goal
from apps.teachers.models import TeacherIntervention, TeacherLearningGoal

from .activity_planner import build_adaptive_activity_plan
from .models import (
    ExperimentAttempt,
    PracticeAttempt,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)

D = PhysicsConcept.Difficulty
PLAN_URL = reverse("students:plan")


class PlannerMixin:
    seq = 0

    def setUp(self):
        self.now = timezone.now()
        self.recent = self.now - timedelta(days=1)

    def uid(self):
        PlannerMixin.seq += 1
        return PlannerMixin.seq

    def make_user(self, *, staff=False):
        return get_user_model().objects.create_user(
            f"pl{self.uid()}", password="pw", is_staff=staff
        )

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def concept(self, name=None, *, prerequisites=None, difficulty=D.INTERMEDIATE,
                topic="Dynamics", is_active=True):
        return PhysicsConcept.objects.create(
            name=name or f"Concept {self.uid()}", description="d", topic=topic,
            difficulty=difficulty, prerequisites=prerequisites or [], is_active=is_active,
        )

    def lesson(self, *concepts, title=None, problems=None):
        les = Lesson.objects.create(
            title=title or f"Lesson {self.uid()}", topic="Dynamics", grade_level="11",
            duration_minutes=45, learning_objectives=["x"], problems=problems or [],
        )
        for c in concepts:
            les.physics_concepts.add(c)
        return les

    def sim(self, concept, title=None):
        return PhysicsSimulation.objects.create(
            concept=concept, title=title or f"Sim {self.uid()}",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def problems(self, *keys):
        return [
            {"key": k, "type": "numeric", "prompt": f"Q {k}?", "answer": 5} for k in keys
        ]

    def practice(self, student, lesson, key="q1", *, when=None):
        row = PracticeAttempt.objects.create(
            student=student, lesson=lesson, question_key=key,
            question_type=PracticeAttempt.QuestionType.NUMERIC,
            question_prompt="p", answer_text="5", is_correct=True, attempt_number=1,
        )
        if when:
            PracticeAttempt.objects.filter(pk=row.pk).update(created_at=when)
        return row

    def experiment(self, student, sim, *, completed=True, when=None):
        row = ExperimentAttempt.objects.create(
            student=student, simulation=sim,
            prediction="p", observation="o" if completed else "",
            explanation="e" if completed else "",
            completed_at=timezone.now() if completed else None,
        )
        if when:
            ExperimentAttempt.objects.filter(pk=row.pk).update(started_at=when, updated_at=when)
        return row

    def tutor(self, student, lesson, *, turns=1, when=None):
        session = TutorSession.objects.create(student=student, lesson=lesson)
        made = [
            TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.STUDENT, content=f"q{i}"
            )
            for i in range(turns)
        ]
        for i in range(turns):
            TutorMessage.objects.create(
                session=session, role=TutorMessage.Role.TUTOR, content=f"a{i}", mode="explain"
            )
        if when:
            for m in made:
                TutorMessage.objects.filter(pk=m.pk).update(created_at=when)
        return session

    def goal(self, student, teacher, concept, **kw):
        return create_learning_goal(
            student=student, teacher=teacher, concept_id=concept.pk,
            lesson_id=kw["lesson"].pk if kw.get("lesson") else None,
            simulation_id=kw["sim"].pk if kw.get("sim") else None,
            teacher_note=kw.get("note", ""),
        )

    def recommendation(self, student, teacher, *, concept=None, lesson=None,
                       action=None, status=None):
        rec = TeacherIntervention.objects.create(
            student=student, teacher=teacher, concept=concept, lesson=lesson,
            action_type=action or TeacherIntervention.ActionType.RECOMMEND_LESSON,
            status=status or TeacherIntervention.Status.PENDING,
        )
        return rec

    def plan(self, student, **kw):
        kw.setdefault("now", self.now)
        return build_adaptive_activity_plan(student=student, **kw)


# --- FOCUS SELECTION (51.1-7) --------------------------------------


class FocusSelectionTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.c_force = self.concept("Force", difficulty=D.INTRODUCTORY)
        self.c_nsl = self.concept("Newton's Second Law", prerequisites=["Force"])

    def test_active_goal_becomes_focus(self):
        self.goal(self.student, self.teacher, self.c_nsl)
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["concept"], "Newton's Second Law")
        self.assertEqual(data["focus"]["source"], "teacher_goal")
        self.assertEqual(data["teacher_goal"]["concept"], "Newton's Second Law")

    def test_newest_active_goal_wins_with_id_tiebreak(self):
        g1 = self.goal(self.student, self.teacher, self.c_force)
        g2 = self.goal(self.student, self.teacher, self.c_nsl)
        # force identical created_at so the -id tie-break decides
        TeacherLearningGoal.objects.filter(pk__in=[g1.pk, g2.pk]).update(created_at=self.now)
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["concept"], "Newton's Second Law")  # higher id

    def test_no_goal_falls_back_to_recommendation(self):
        self.recommendation(self.student, self.teacher, concept=self.c_force)
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["source"], "pending_recommendation")
        self.assertEqual(data["focus"]["concept"], "Force")

    def test_no_goal_no_recommendation_uses_graph_or_recent(self):
        les = self.lesson(self.c_force, title="Force Lesson")
        self.practice(self.student, les, when=self.recent)  # explores Force -> NSL is a candidate
        data = self.plan(self.student)
        self.assertIn(data["focus"]["source"], {"learning_path", "recent_activity"})

    def test_empty_student_uses_step19_fallback(self):
        data = self.plan(self.student)
        self.assertTrue(data["has_plan"])
        self.assertEqual(data["next_activity"]["type"], "explore")
        self.assertIn("Start with", data["next_activity"]["title"])


# --- ACTIVITY SELECTION FOR A GOAL (51.8-15) --------------------


class GoalActivityTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.c = self.concept("Newton's Third Law")

    def test_goal_with_lesson_not_engaged_chooses_lesson(self):
        les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        self.goal(self.student, self.teacher, self.c, lesson=les)
        act = self.plan(self.student)["next_activity"]
        self.assertEqual(act["type"], "lesson")
        self.assertEqual(act["url"], reverse("students:tutor", args=[les.slug]))

    def test_goal_with_lesson_engaged_chooses_practice(self):
        les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1", "q2"))
        self.goal(self.student, self.teacher, self.c, lesson=les)
        self.practice(self.student, les, "q1", when=self.recent)  # engaged, not all done
        act = self.plan(self.student)["next_activity"]
        self.assertEqual(act["type"], "practice")
        self.assertEqual(act["url"], reverse("students:practice", args=[les.slug]))

    def test_goal_with_simulation_not_completed_chooses_lab(self):
        s = self.sim(self.c, title="N3L Sim")
        self.goal(self.student, self.teacher, self.c, sim=s)
        act = self.plan(self.student)["next_activity"]
        self.assertEqual(act["type"], "lab")
        self.assertEqual(act["url"], reverse("physics_lab:detail", args=[s.slug]))

    def test_goal_with_completed_simulation_moves_on(self):
        s = self.sim(self.c, title="N3L Sim")
        les = self.lesson(self.c, title="N3L Lesson")
        self.goal(self.student, self.teacher, self.c, sim=s)
        self.experiment(self.student, s, completed=True)
        act = self.plan(self.student)["next_activity"]
        self.assertNotEqual(act["type"], "lab")

    def test_concept_only_goal_resolves_deterministically(self):
        les = self.lesson(self.c, title="N3L Lesson")
        self.goal(self.student, self.teacher, self.c)
        act = self.plan(self.student)["next_activity"]
        self.assertEqual(act["type"], "lesson")
        self.assertEqual(act["url"], reverse("students:tutor", args=[les.slug]))
        # stable across reloads
        self.assertEqual(self.plan(self.student), self.plan(self.student))

    def test_concept_only_goal_with_no_activities_falls_back(self):
        self.goal(self.student, self.teacher, self.c)
        act = self.plan(self.student)["next_activity"]
        self.assertEqual(act["url"], reverse("students:lessons"))

    def test_fully_attempted_practice_is_not_reselected(self):
        les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        s = self.sim(self.c)
        self.goal(self.student, self.teacher, self.c, lesson=les)
        self.practice(self.student, les, "q1", when=self.recent)  # engaged AND all done
        act = self.plan(self.student)["next_activity"]
        self.assertNotEqual(act["type"], "practice")
        self.assertEqual(act["type"], "lab")  # next available

    def test_no_mastery_or_readiness_language(self):
        les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        self.goal(self.student, self.teacher, self.c, lesson=les)
        self.practice(self.student, les, "q1", when=self.recent)
        blob = str(self.plan(self.student)).lower()
        for banned in ("mastery", "mastered", "you are ready", "proficient", "weakness", "at risk"):
            self.assertNotIn(banned, blob)


# --- RECOMMENDATION + EXPERIMENT PRIORITY (51.12, 20-23) ------


class PriorityTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.c = self.concept("Force", difficulty=D.INTRODUCTORY)
        self.s = self.sim(self.c)

    def test_incomplete_experiment_takes_priority_over_graph(self):
        self.experiment(self.student, self.s, completed=False, when=self.recent)
        data = self.plan(self.student)
        self.assertEqual(data["next_activity"]["type"], "lab")
        self.assertIn("Finish", data["next_activity"]["title"])

    def test_recommendation_beats_incomplete_experiment(self):
        self.experiment(self.student, self.s, completed=False, when=self.recent)
        self.recommendation(self.student, self.teacher, concept=self.c)
        data = self.plan(self.student)
        self.assertEqual(data["next_activity"]["type"], "recommendation")
        self.assertEqual(data["next_activity"]["url"], reverse("students:recommendations"))

    def test_active_goal_beats_recommendation_and_incomplete_experiment(self):
        les = self.lesson(self.c, title="Force Lesson")
        self.experiment(self.student, self.s, completed=False, when=self.recent)
        self.recommendation(self.student, self.teacher, concept=self.c)
        self.goal(self.student, self.teacher, self.c, lesson=les)
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["source"], "teacher_goal")
        self.assertEqual(data["next_activity"]["type"], "lesson")

    def test_unrelated_experiment_does_not_change_plan(self):
        other = self.sim(self.concept("Momentum", topic="Mechanics"))
        self.experiment(self.student, other, completed=True)
        self.lesson(self.c, title="Force Lesson")
        self.goal(self.student, self.teacher, self.c)
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["concept"], "Force")

    def test_other_students_incomplete_experiment_ignored(self):
        bob = self.make_student("Bob")
        self.experiment(bob, self.s, completed=False, when=self.recent)
        data = self.plan(self.student)
        self.assertNotIn("Finish your Physics Lab", str(data["next_activity"]))

    def test_removing_goal_moves_to_next_priority_without_touching_old_goal(self):
        from apps.teachers.goal_services import close_learning_goal

        les = self.lesson(self.c, title="Force Lesson")
        g = self.goal(self.student, self.teacher, self.c, lesson=les)
        self.experiment(self.student, self.s, completed=False, when=self.recent)
        self.assertEqual(self.plan(self.student)["focus"]["source"], "teacher_goal")

        close_learning_goal(goal_id=g.pk, student=self.student)
        after = self.plan(self.student)
        self.assertEqual(after["next_activity"]["type"], "lab")  # incomplete experiment now
        g.refresh_from_db()
        self.assertEqual(g.status, TeacherLearningGoal.Status.CLOSED)  # untouched by planner


# --- ALTERNATIVES (51.31-33) ----------------------------------


class AlternativeTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.c = self.concept("Newton's Third Law")
        self.les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        self.s = self.sim(self.c, title="N3L Sim")

    def test_at_most_two_alternatives(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        alts = self.plan(self.student)["alternatives"]
        self.assertLessEqual(len(alts), 2)

    def test_alternatives_do_not_duplicate_primary(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        data = self.plan(self.student)
        primary_type = data["next_activity"]["type"]
        self.assertNotIn(primary_type, [a["type"] for a in data["alternatives"]])

    def test_alternatives_are_deterministic(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        self.assertEqual(
            self.plan(self.student)["alternatives"], self.plan(self.student)["alternatives"]
        )


# --- GRAPH FALLBACK (51.27-30) ------------------------------


class GraphFallbackTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.velocity = self.concept("Velocity", difficulty=D.INTRODUCTORY, topic="Kinematics")
        self.accel = self.concept("Acceleration", prerequisites=["Velocity"])

    def test_graph_fallback_picks_connected_unobserved_concept(self):
        vles = self.lesson(self.velocity, title="Velocity Lesson")
        self.lesson(self.accel, title="Acceleration Lesson")
        self.practice(self.student, vles, when=self.recent)  # explores Velocity
        data = self.plan(self.student)
        self.assertEqual(data["focus"]["concept"], "Acceleration")
        self.assertEqual(data["focus"]["source"], "learning_path")
        self.assertEqual(data["next_activity"]["type"], "lesson")

    def test_inactive_concept_is_never_recommended(self):
        self.accel.is_active = False
        self.accel.save(update_fields=["is_active"])
        vles = self.lesson(self.velocity, title="Velocity Lesson")
        self.practice(self.student, vles, when=self.recent)
        data = self.plan(self.student)
        self.assertNotEqual(data.get("focus", {}).get("concept"), "Acceleration")

    def test_cyclic_graph_does_not_hang(self):
        a = self.concept("Cyc A")
        b = self.concept("Cyc B", prerequisites=["Cyc A"])
        a.prerequisites = ["Cyc B"]
        a.save(update_fields=["prerequisites"])
        ales = self.lesson(a, title="Cyc Lesson")
        self.practice(self.student, ales, when=self.recent)
        self.assertTrue(self.plan(self.student)["has_plan"])  # returns, no hang


# --- STUDENT PAGE (51.34-43, 49-58) -------------------------


class PlanPageTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.user = self.make_user()
        self.student = self.make_student("Alex", user=self.user)
        self.c = self.concept("Newton's Third Law")
        self.les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        self.client.force_login(self.user)

    def test_page_loads(self):
        r = self.client.get(PLAN_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Your Next Physics Activity")

    def test_empty_state_is_honest(self):
        r = self.client.get(PLAN_URL)
        self.assertContains(r, "Suggested next activity")
        self.assertNotContains(r, "mastery")
        self.assertNotContains(r, "0%")

    def test_teacher_goal_shown_separately_from_suggestion(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        r = self.client.get(PLAN_URL)
        self.assertContains(r, "Teacher-selected goal")
        self.assertContains(r, "Suggested next activity")
        self.assertContains(r, "not a decision made by your teacher")

    def test_destination_urls_are_named_routes(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        r = self.client.get(PLAN_URL)
        self.assertContains(r, f'href="{reverse("students:tutor", args=[self.les.slug])}"')

    def test_student_id_query_ignored(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        bob = self.make_student("Bob")
        bob_c = self.concept("Bob Only Concept")
        self.goal(bob, self.teacher, bob_c)
        r = self.client.get(PLAN_URL, {"student_id": bob.pk})
        self.assertContains(r, "Newton&#x27;s Third Law")
        self.assertNotContains(r, "Bob Only Concept")

    def test_teacher_note_not_visible(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les, note="PRIVATE-XYZZY")
        r = self.client.get(PLAN_URL)
        self.assertNotContains(r, "PRIVATE-XYZZY")

    def test_misconception_not_visible(self):
        catalog = PhysicsMisconception.objects.create(
            code="FORCE_X", title="Force confusion", description="d", physics_concept=self.c
        )
        StudentMisconception.objects.create(student=self.student, misconception=catalog)
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        r = self.client.get(PLAN_URL)
        self.assertNotContains(r, "FORCE_X")
        self.assertNotContains(r, "Force confusion")
        self.assertNotContains(r, "misconception")

    def test_model_text_is_escaped(self):
        xss_c = self.concept("<script>alert('c')</script>")
        xss_les = self.lesson(xss_c, title="<script>alert('l')</script>")
        self.goal(self.student, self.teacher, xss_c, lesson=xss_les)
        r = self.client.get(PLAN_URL)
        self.assertNotContains(r, "<script>alert('c')</script>")
        self.assertNotContains(r, "<script>alert('l')</script>")
        self.assertContains(r, "&lt;script&gt;")

    def test_get_is_read_only(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        before = (
            PracticeAttempt.objects.count(),
            TeacherIntervention.objects.count(),
            TeacherLearningGoal.objects.count(),
        )
        self.client.get(PLAN_URL)
        self.client.get(PLAN_URL)
        after = (
            PracticeAttempt.objects.count(),
            TeacherIntervention.objects.count(),
            TeacherLearningGoal.objects.count(),
        )
        self.assertEqual(before, after)

    def test_pending_recommendation_not_marked_opened_by_plan(self):
        rec = self.recommendation(self.student, self.teacher, concept=self.c)
        self.client.get(PLAN_URL)
        rec.refresh_from_db()
        self.assertEqual(rec.status, TeacherIntervention.Status.PENDING)

    def test_semantic_headings_and_real_controls(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        body = self.client.get(PLAN_URL).content.decode()
        self.assertIn("<h1>", body)
        self.assertIn("<h2", body)
        self.assertIn('aria-labelledby="plan', body)
        self.assertIn('class="button button-primary"', body)

    def test_guest_fallback_for_anonymous(self):
        self.client.logout()
        self.client.get(PLAN_URL)
        self.client.get(PLAN_URL)
        self.assertEqual(StudentProfile.objects.filter(user__isnull=True).count(), 1)


# --- TEACHER PAGE (51.44-48) --------------------------------


class TeacherPlanTests(PlannerMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student("Alex")
        self.c = self.concept("Newton's Third Law")
        self.les = self.lesson(self.c, title="N3L Lesson", problems=self.problems("q1"))
        self.client.force_login(self.teacher)
        self.url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_teacher_sees_activity_plan_section(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Current activity plan")
        self.assertContains(r, "Suggested next activity")
        self.assertContains(r, "Teacher-selected goal")
        self.assertContains(r, "not a teacher decision")

    def test_student_cannot_access_teacher_plan(self):
        self.client.force_login(self.make_user())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_no_ai_or_provider_internals(self):
        self.goal(self.student, self.teacher, self.c, lesson=self.les)
        body = self.client.get(self.url).content.decode()
        for banned in ("api_key", "OPENAI", "raw model response", "AI prompt", "mastery score"):
            self.assertNotIn(banned, body)


# --- QUERY BUDGET (51.52 / 52) ------------------------------


class PlannerQueryBudgetTests(PlannerMixin, TestCase):
    def test_planner_query_count_is_bounded(self):
        teacher = self.make_user(staff=True)
        student = self.make_student()
        c = self.concept("Newton's Third Law")
        les = self.lesson(c, title="N3L Lesson", problems=self.problems("q1", "q2"))
        self.sim(c)
        self.goal(student, teacher, c, lesson=les)
        self.practice(student, les, "q1", when=self.recent)
        # +1 vs. Step 22's original 16: one bounded read of published
        # assessments per concept (Step 23's assessment_by_slug map). This
        # fixture has no published assessment on the focus concept, so the
        # conditional _assessment_completed check below never fires.
        with self.assertNumQueries(17):
            build_adaptive_activity_plan(student=student, now=self.now)

    def test_planner_query_count_with_a_published_assessment_on_focus_concept(self):
        """A published assessment matching the focus concept adds exactly one
        more query (_assessment_completed) -- memoised, so it is not paid
        twice even though the primary and alternatives resolution both ask."""

        from apps.assessments import services as assessment_services
        from apps.assessments.models import QuestionBankItem

        teacher = self.make_user(staff=True)
        student = self.make_student()
        c = self.concept("Newton's Third Law")
        les = self.lesson(c, title="N3L Lesson", problems=self.problems("q1", "q2"))
        self.sim(c)
        self.goal(student, teacher, c, lesson=les)
        self.practice(student, les, "q1", when=self.recent)

        q = assessment_services.create_question(
            teacher=teacher, question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="N3L assessment question", concept_id=c.pk, expected_value=1,
        )
        a = assessment_services.create_assessment(teacher=teacher, title="N3L Check", concept_id=c.pk)
        assessment_services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        assessment_services.publish_assessment(assessment_id=a.pk, teacher=teacher)

        with self.assertNumQueries(18):
            build_adaptive_activity_plan(student=student, now=self.now)

    def test_history_size_does_not_scale_query_count(self):
        teacher = self.make_user(staff=True)
        student = self.make_student()
        c = self.concept("Newton's Third Law")
        les = self.lesson(c, title="N3L Lesson", problems=self.problems("q1"))
        self.goal(student, teacher, c, lesson=les)

        def count():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as ctx:
                build_adaptive_activity_plan(student=student, now=self.now)
            return len(ctx)

        few = count()
        for i in range(40):
            self.practice(student, les, f"k{i}", when=self.recent)
            self.experiment(student, self.sim(self.concept(f"X{i}")), completed=True)
        many = count()
        self.assertEqual(few, many)
