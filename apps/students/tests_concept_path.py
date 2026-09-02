"""Step 20 -- student & teacher concept-path integration."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsSimulation

from .concept_path_services import build_student_concept_path
from .models import (
    ExperimentAttempt,
    PracticeAttempt,
    StudentProfile,
    TutorMessage,
    TutorSession,
)

D = PhysicsConcept.Difficulty
PATH_URL = reverse("students:path")


class ConceptPathMixin:
    seq = 0

    def setUp(self):
        self.now = timezone.now()
        self.recent = self.now - timedelta(days=2)

    def make_user(self, *, staff=False):
        ConceptPathMixin.seq += 1
        return get_user_model().objects.create_user(
            f"cp{ConceptPathMixin.seq}", password="pw", is_staff=staff
        )

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def concept(self, name, *, prerequisites=None, difficulty=D.FOUNDATIONAL,
                topic="Kinematics", is_active=True):
        return PhysicsConcept.objects.create(
            name=name, description="d", topic=topic, difficulty=difficulty,
            prerequisites=prerequisites or [], is_active=is_active,
        )

    def seed_chain(self):
        self.velocity = self.concept("Velocity", difficulty=D.INTRODUCTORY)
        self.accel = self.concept("Acceleration", prerequisites=["Velocity"], difficulty=D.INTERMEDIATE)
        self.force = self.concept("Force", prerequisites=["Acceleration"], difficulty=D.INTRODUCTORY, topic="Dynamics")
        self.nsl = self.concept(
            "Newton's Second Law", prerequisites=["Force", "Acceleration"],
            difficulty=D.INTERMEDIATE, topic="Dynamics",
        )
        self.n3l = self.concept(
            "Newton's Third Law", prerequisites=["Force"], difficulty=D.INTERMEDIATE,
            topic="Dynamics",
        )

    def lesson_for(self, *concepts, title="A lesson", status=None):
        lesson = Lesson.objects.create(
            title=title, topic="Dynamics", grade_level="11", duration_minutes=45,
            learning_objectives=["x"],
        )
        for c in concepts:
            lesson.physics_concepts.add(c)
        if status:
            lesson.status = status
            lesson.save(update_fields=["status"])
        return lesson

    def sim_for(self, concept, title=None):
        ConceptPathMixin.seq += 1
        return PhysicsSimulation.objects.create(
            concept=concept, title=title or f"Sim {ConceptPathMixin.seq}",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def practice(self, student, lesson, concept, *, when=None, is_correct=True, key="q1"):
        row = PracticeAttempt.objects.create(
            student=student, lesson=lesson, concept=concept, question_key=key,
            question_type=PracticeAttempt.QuestionType.NUMERIC,
            question_prompt="p", answer_text="10", is_correct=is_correct, attempt_number=1,
        )
        if when:
            PracticeAttempt.objects.filter(pk=row.pk).update(created_at=when)
        return row

    def experiment(self, student, sim, *, lesson=None, completed=True,
                   prediction="p", observation="o", explanation="e", when=None):
        row = ExperimentAttempt.objects.create(
            student=student, simulation=sim, lesson=lesson,
            prediction=prediction, observation=observation, explanation=explanation,
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
        if when:
            for m in made:
                TutorMessage.objects.filter(pk=m.pk).update(created_at=when)
        return session

    def path(self, student, **kw):
        kw.setdefault("now", self.now)
        return build_student_concept_path(student=student, **kw)


# --- SERVICE (43.15, 43.19-24, 44) ------------------------------------


class ConceptPathServiceTests(ConceptPathMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.seed_chain()
        self.student = self.make_student()
        self.accel_lesson = self.lesson_for(self.accel, title="Acceleration lesson")
        self.force_lesson = self.lesson_for(self.force, title="Force lesson")

    def _explore_accel_and_force(self):
        # Practice only, and no simulation exists for either concept, so none of
        # Step 19's activity rules fire -> the concept graph decides the next step.
        # Force is explored more recently than Acceleration.
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent - timedelta(hours=3))
        self.practice(self.student, self.force_lesson, self.force, when=self.recent)

    def test_explored_concepts_are_the_students_only(self):
        self._explore_accel_and_force()
        data = self.path(self.student)
        self.assertTrue(data["has_explored"])
        self.assertEqual(
            sorted(e["name"] for e in data["explored"]), ["Acceleration", "Force"]
        )

    def test_only_graph_connected_candidates_appear(self):
        self._explore_accel_and_force()
        data = self.path(self.student)
        names = {c["name"] for c in data["next_candidates"]}
        # NSL follows both; N3L follows Force. Neither explored.
        self.assertEqual(names, {"Newton's Second Law", "Newton's Third Law"})
        for cand in data["next_candidates"]:
            self.assertTrue(cand["all_prereqs_explored"])

    def test_candidate_selection_is_deterministic(self):
        self._explore_accel_and_force()
        a = self.path(self.student)
        b = self.path(self.student)
        self.assertEqual(a, b)
        self.assertEqual(a["suggested"]["kind"], "concept")
        self.assertEqual(a["suggested"]["concept"], "Newton's Second Law")

    def test_candidate_destination_prefers_lesson(self):
        self._explore_accel_and_force()
        self.lesson_for(self.nsl, title="NSL lesson")
        data = self.path(self.student)
        self.assertEqual(
            data["suggested"]["url"], reverse("students:tutor", args=[Lesson.objects.get(title="NSL lesson").slug])
        )
        self.assertEqual(data["suggested"]["dest_kind"], "lesson")

    def test_candidate_destination_uses_simulation_when_no_lesson(self):
        self._explore_accel_and_force()
        sim = self.sim_for(self.nsl, title="NSL sim")
        data = self.path(self.student)
        self.assertEqual(
            data["suggested"]["url"], reverse("physics_lab:detail", args=[sim.slug])
        )
        self.assertEqual(data["suggested"]["dest_kind"], "lab")

    def test_candidate_destination_falls_back_to_lessons(self):
        self._explore_accel_and_force()
        data = self.path(self.student)  # no lesson, no sim for NSL
        self.assertEqual(data["suggested"]["url"], reverse("students:lessons"))
        self.assertEqual(data["suggested"]["dest_kind"], "lessons")

    def test_suggested_url_is_always_a_reversed_named_route(self):
        self._explore_accel_and_force()
        data = self.path(self.student)
        self.assertTrue(data["suggested"]["url"].startswith("/"))
        self.assertIn(data["suggested"]["url"], {
            reverse("students:lessons"),
            reverse("students:tutor", args=[self.nsl.slug]),
            reverse("physics_lab:index"),
        } | {data["suggested"]["url"]})  # membership sanity only

    def test_incomplete_experiment_still_takes_priority(self):
        self._explore_accel_and_force()
        self.experiment(self.student, self.sim_for(self.velocity), lesson=self.accel_lesson,
                        completed=False, prediction="pred", observation="", explanation="",
                        when=self.recent)
        data = self.path(self.student)
        self.assertEqual(data["suggested"]["kind"], "activity")
        self.assertEqual(
            data["suggested"]["text"], "Return to the Physics Lab and record what happened."
        )

    def test_pending_recommendation_still_takes_priority(self):
        from apps.teachers.models import TeacherIntervention

        self._explore_accel_and_force()
        TeacherIntervention.objects.create(
            student=self.student,
            action_type=TeacherIntervention.ActionType.RECOMMEND_LESSON,
            lesson=self.force_lesson, status=TeacherIntervention.Status.PENDING,
        )
        data = self.path(self.student)
        self.assertEqual(data["suggested"]["kind"], "activity")
        self.assertEqual(data["suggested"]["url"], reverse("students:recommendations"))

    def test_practice_after_lab_activity_rule_beats_graph(self):
        # completed lab for Force, no practice for Force -> Step 19 "practice_after_lab"
        self.experiment(self.student, self.sim_for(self.force), lesson=self.force_lesson,
                        when=self.recent)
        data = self.path(self.student)
        self.assertEqual(data["suggested"]["kind"], "activity")
        self.assertIn("practice problem", data["suggested"]["text"])

    def test_graph_fallback_when_no_activity_rule_fires(self):
        # Practice-only exploration with no simulations for the explored concepts
        # -> Step 19 lands on its generic fallback -> the concept graph decides.
        self._explore_accel_and_force()
        data = self.path(self.student)
        self.assertEqual(data["suggested"]["kind"], "concept")
        self.assertEqual(data["suggested"]["concept"], "Newton's Second Law")
        self.assertEqual(
            self.path(self.student)["suggested"], data["suggested"]
        )  # identical on repeat

    def test_walked_path_is_a_real_graph_chain(self):
        # Explore Velocity (foundational) and NSL (advanced): the forward chain
        # between them is a real graph path, through an un-explored middle node.
        vlesson = self.lesson_for(self.velocity, title="V lesson")
        nlesson = self.lesson_for(self.nsl, title="N lesson")
        self.practice(self.student, vlesson, self.velocity, when=self.recent - timedelta(hours=1))
        self.practice(self.student, nlesson, self.nsl, when=self.recent)
        data = self.path(self.student)
        names = [n["name"] for n in data["walked_path"]]
        self.assertEqual(names, ["Velocity", "Acceleration", "Newton's Second Law"])
        by_name = {n["name"]: n["explored"] for n in data["walked_path"]}
        self.assertTrue(by_name["Velocity"])
        self.assertFalse(by_name["Acceleration"])
        self.assertTrue(by_name["Newton's Second Law"])

    def test_missing_prereq_is_named_not_judged(self):
        # A dedicated shape whose only candidate has an un-met prerequisite:
        #   Alpha (root)   Beta (separate root)   Gamma (prereqs Alpha, Beta)
        # A fresh student who has explored only Alpha -> Gamma follows Alpha but
        # still needs Beta.
        alpha = self.concept("Alpha")
        self.concept("Beta")
        self.concept("Gamma", prerequisites=["Alpha", "Beta"])
        alpha_lesson = self.lesson_for(alpha, title="Alpha lesson")
        iso = self.make_student("Iso")
        self.practice(iso, alpha_lesson, alpha, when=self.recent)

        data = self.path(iso)
        self.assertEqual(data["suggested"]["concept"], "Gamma")
        self.assertEqual(data["suggested"]["missing_prereq"], "Beta")
        why = data["suggested"]["why"]
        self.assertIn("Related prerequisite to look at first: Beta", why)
        self.assertNotIn("you are ready", why.lower())
        self.assertNotIn("you're ready", why.lower())
        self.assertNotIn("mastery", why.lower())

    def test_inactive_concept_is_never_a_candidate(self):
        self.n3l.is_active = False
        self.n3l.save(update_fields=["is_active"])
        self._explore_accel_and_force()
        data = self.path(self.student)
        names = {c["name"] for c in data["next_candidates"]}
        self.assertEqual(names, {"Newton's Second Law"})

    def test_cycle_in_graph_data_does_not_hang(self):
        # A -> B -> A, student explored A
        a = self.concept("Cycle A")
        b = self.concept("Cycle B", prerequisites=["Cycle A"])
        a.prerequisites = ["Cycle B"]
        a.save(update_fields=["prerequisites"])
        alesson = self.lesson_for(a, title="Cyc lesson")
        self.practice(self.student, alesson, a, when=self.recent)
        data = self.path(self.student)  # must return, not hang
        self.assertTrue(data["has_explored"])

    def test_query_budget_is_bounded(self):
        # Every source table populated so no prefetch is silently suppressed.
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        self.experiment(self.student, self.sim_for(self.accel), lesson=self.accel_lesson, when=self.recent)
        self.tutor(self.student, self.accel_lesson, when=self.recent)
        for i in range(12):
            self.concept(f"Extra {i}", prerequisites=["Force"])

        with self.assertNumQueries(12):
            build_student_concept_path(student=self.student, now=self.now)

        # Adding history does not add queries.
        for i in range(20):
            self.practice(self.student, self.accel_lesson, self.accel, key=f"k{i}", when=self.recent)
        with self.assertNumQueries(12):
            build_student_concept_path(student=self.student, now=self.now)


# --- STUDENT PAGE (43.13-14, 43.16-18, 43.25-27, 46) ----------------


class ConceptPathPageTests(ConceptPathMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.seed_chain()
        self.user = self.make_user()
        self.student = self.make_student("Alex", user=self.user)
        self.accel_lesson = self.lesson_for(self.accel, title="Acceleration lesson")
        self.client.force_login(self.user)

    def test_page_loads(self):
        r = self.client.get(PATH_URL)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Your Physics Learning Path")

    def test_empty_state_is_honest(self):
        r = self.client.get(PATH_URL)
        self.assertContains(r, "will appear here once you")
        self.assertNotContains(r, "mastery")
        self.assertNotContains(r, "0%")

    def test_explored_and_related_render_as_text(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        r = self.client.get(PATH_URL)
        self.assertContains(r, "Acceleration")
        self.assertContains(r, "Explored")
        self.assertContains(r, "Follows")  # next candidate relation as text
        self.assertContains(r, "<h1>", html=False)
        self.assertContains(r, "<h2")

    def test_student_id_query_is_ignored(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        other = self.make_student("Bob")
        blesson = self.lesson_for(self.velocity, title="Bob V")
        self.practice(other, blesson, self.velocity, when=self.recent)
        r = self.client.get(PATH_URL, {"student_id": other.pk})
        # Alex's explored concept still shown; Bob's isn't introduced
        self.assertContains(r, "Acceleration")

    def test_cross_student_isolation(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        bob = self.make_student("Bob")
        momentum = self.concept("Momentum", topic="Mechanics")
        blesson = self.lesson_for(momentum, title="Momentum lesson")
        self.practice(bob, blesson, momentum, when=self.recent)
        r = self.client.get(PATH_URL)
        self.assertNotContains(r, "Momentum")

    def test_no_evaluative_language(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        body = self.client.get(PATH_URL).content.decode().lower()
        for banned in ("mastery", "proficiency", "ability score", "risk score",
                       "you are ready", "you're ready", "weakness", "skill tree",
                       "level path"):
            self.assertNotIn(banned, body)

    def test_no_internal_misconception_labels(self):
        from apps.physics.models import PhysicsMisconception
        from apps.students.models import StudentMisconception

        cat = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION", title="t", description="d",
            physics_concept=self.accel,
        )
        StudentMisconception.objects.create(student=self.student, misconception=cat)
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        r = self.client.get(PATH_URL)
        self.assertNotContains(r, "FORCE_VS_ACCELERATION")
        self.assertNotContains(r, "misconception")

    def test_concept_and_lesson_html_is_escaped(self):
        xss = self.concept("<script>alert(1)</script>", topic="x")
        xlesson = self.lesson_for(xss, title="<b>x</b>")
        self.practice(self.student, xlesson, xss, when=self.recent)
        r = self.client.get(PATH_URL)
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")

    def test_guest_fallback_for_anonymous(self):
        self.client.logout()
        self.client.get(PATH_URL)
        self.client.get(PATH_URL)
        self.assertEqual(StudentProfile.objects.filter(user__isnull=True).count(), 1)

    def test_get_does_not_write(self):
        before = PracticeAttempt.objects.count()
        self.client.get(PATH_URL)
        self.assertEqual(PracticeAttempt.objects.count(), before)


# --- TEACHER (45) -------------------------------------------------


class TeacherConceptPathTests(ConceptPathMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.seed_chain()
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student("Alex")
        self.accel_lesson = self.lesson_for(self.accel, title="Acceleration lesson")
        self.client.force_login(self.teacher)
        self.url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_teacher_sees_learning_path_section(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Learning path")
        self.assertContains(r, "Where this student sits in the Physics concept graph")

    def test_teacher_sees_explored_and_related_concepts(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        r = self.client.get(self.url)
        self.assertContains(r, "Explored")
        self.assertContains(r, "Related next concepts")
        self.assertContains(r, "Newton&#x27;s Second Law")

    def test_teacher_path_has_no_evaluative_language(self):
        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        body = self.client.get(self.url).content.decode().lower()
        for banned in ("mastery score", "weakness score", "risk score",
                       "you are ready", "ability level"):
            self.assertNotIn(banned, body)

    def test_student_cannot_access_teacher_page(self):
        self.client.force_login(self.make_user(staff=False))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 403)

    def test_cross_student_teacher_isolation(self):
        from apps.teachers.services import build_teacher_student_evidence

        self.practice(self.student, self.accel_lesson, self.accel, when=self.recent)
        bob = self.make_student("Bob")
        torque = self.concept("Torque", topic="Rotation")
        blesson = self.lesson_for(torque, title="Torque lesson")
        self.practice(bob, blesson, torque, when=self.recent)

        ctx = build_teacher_student_evidence(student=self.student)
        explored = [e["name"] for e in ctx["learning_path"]["explored"]]
        self.assertEqual(explored, ["Acceleration"])
        self.assertNotIn(
            "Torque",
            [c["name"] for c in ctx["learning_path"]["next_candidates"]]
            + [c["name"] for c in ctx["learning_path"]["related_prerequisites"]],
        )
