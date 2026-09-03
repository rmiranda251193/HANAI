import json
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
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    MisconceptionEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)

from .models import TeacherIntervention
from .services import build_teacher_student_evidence, create_teacher_intervention
from .services import InterventionError

User = get_user_model()
Kind = LearningEvidence.Kind


class WorkspaceDataMixin:
    def make_teacher(self, username="teach"):
        return User.objects.create_user(username, password="pw", is_staff=True)

    def make_student_user(self, username="stud"):
        return User.objects.create_user(username, password="pw")

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name="Acceleration", topic="Kinematics"):
        return PhysicsConcept.objects.create(name=name, description="c", topic=topic)

    def make_misconception(self, concept, *, code="FORCE_VS_ACCELERATION",
                           title="Force and acceleration are the same quantity"):
        return PhysicsMisconception.objects.create(
            code=code, title=title, description="d", physics_concept=concept
        )

    def make_lesson(self, *concepts, title="Forces and Motion"):
        lesson = Lesson.objects.create(
            title=title, topic="Dynamics", grade_level="11",
            duration_minutes=45, learning_objectives=["x"],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept):
        return PhysicsSimulation.objects.create(
            concept=concept, title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def add_evidence(self, student, kind, *, lesson=None, detail="", context=None, when=None):
        ev = LearningEvidence.objects.create(
            student=student, lesson=lesson, kind=kind, detail=detail, context=context or {}
        )
        if when is not None:
            LearningEvidence.objects.filter(pk=ev.pk).update(created_at=when)
            ev.refresh_from_db()
        return ev

    def add_experiment(self, student, simulation, *, lesson=None, completed=False,
                       mass=None, force=None, accel=None,
                       prediction="", observation="", explanation=""):
        return ExperimentAttempt.objects.create(
            student=student, simulation=simulation, lesson=lesson,
            mass_kg=mass, force_n=force, acceleration_m_s2=accel,
            prediction=prediction, observation=observation, explanation=explanation,
            completed_at=timezone.now() if completed else None,
        )

    def add_candidate(self, student, misconception, *, confidence="medium", status="candidate"):
        return StudentMisconception.objects.create(
            student=student, misconception=misconception,
            confidence=confidence, status=status,
        )

    def add_candidate_evidence(self, observation, *, learning_evidence=None,
                               source="rule", detector="rule:force_vs_acceleration",
                               excerpt="force is acceleration"):
        return MisconceptionEvidence.objects.create(
            observation=observation, learning_evidence=learning_evidence,
            source=source, detector=detector, excerpt=excerpt,
        )

    def add_tutor(self, student, lesson, *, student_turns=1, tutor_turns=1):
        session = TutorSession.objects.create(student=student, lesson=lesson)
        for i in range(student_turns):
            TutorMessage.objects.create(session=session, role="student", content=f"q{i}")
        for i in range(tutor_turns):
            TutorMessage.objects.create(session=session, role="tutor", content=f"a{i}", mode="explain")
        return session

    def login_teacher(self):
        teacher = self.make_teacher()
        self.client.force_login(teacher)
        return teacher


# --- AUTHORIZATION -------------------------------------------------------------


class AuthorizationTests(WorkspaceDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.list_url = reverse("teachers:student_list")
        self.detail_url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_teacher_can_open_student_list(self):
        self.login_teacher()
        self.assertEqual(self.client.get(self.list_url).status_code, 200)

    def test_teacher_can_open_student_detail(self):
        self.login_teacher()
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student evidence")

    def test_signed_in_student_cannot_open_student_list(self):
        self.client.force_login(self.make_student_user())
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_signed_in_student_cannot_open_student_detail(self):
        self.client.force_login(self.make_student_user())
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)

    def test_anonymous_access_is_refused(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)

    def test_url_student_is_authoritative_not_a_query_param(self):
        self.login_teacher()
        other = self.make_student("Bob")
        self.add_evidence(self.student, Kind.QUESTION_ASKED, detail="ALEX-ONLY")
        self.add_evidence(other, Kind.QUESTION_ASKED, detail="BOB-ONLY")
        response = self.client.get(self.detail_url, {"student_id": other.pk})
        self.assertContains(response, "ALEX-ONLY")
        self.assertNotContains(response, "BOB-ONLY")


# --- STUDENT EVIDENCE --------------------------------------------------------


class StudentEvidenceViewTests(WorkspaceDataMixin, TestCase):
    def setUp(self):
        self.login_teacher()
        self.concept = self.make_concept("Acceleration")
        self.lesson = self.make_lesson(self.concept)
        self.student = self.make_student()
        self.url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_timeline_shows_real_learning_evidence_with_friendly_labels(self):
        self.add_evidence(self.student, Kind.QUESTION_ASKED, lesson=self.lesson, detail="what is net force")
        response = self.client.get(self.url)
        self.assertContains(response, "what is net force")
        self.assertContains(response, "Asked a Physics question")
        self.assertNotContains(response, "question_asked")

    def test_evidence_is_ordered_newest_first(self):
        now = timezone.now()
        self.add_evidence(self.student, Kind.QUESTION_ASKED, detail="OLDEST", when=now - timedelta(hours=3))
        self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="NEWEST", when=now - timedelta(minutes=2))
        body = self.client.get(self.url).content.decode()
        self.assertLess(body.index("NEWEST"), body.index("OLDEST"))

    def test_student_text_is_escaped(self):
        self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="<script>alert('x')</script>")
        response = self.client.get(self.url)
        self.assertNotContains(response, "<script>alert('x')</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_experiment_context_shows_deterministic_values(self):
        self.add_experiment(
            self.student, self.make_simulation(self.concept),
            lesson=self.lesson, completed=True, mass=2.0, force=20.0, accel=10.0,
            prediction="it doubles",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "10.00")
        self.assertContains(response, "20.0")
        self.assertContains(response, "it doubles")

    def test_tutor_student_message_count_is_correct(self):
        self.add_tutor(self.student, self.lesson, student_turns=3, tutor_turns=5)
        data = build_teacher_student_evidence(student=self.student)
        self.assertEqual(data["tutor_activity"]["messages"], 3)
        response = self.client.get(self.url)
        self.assertContains(response, "student questions and attempts")


# --- CONCEPTS -------------------------------------------------------------


class ConceptsTests(WorkspaceDataMixin, TestCase):
    def setUp(self):
        self.student = self.make_student()
        self.acceleration = self.make_concept("Acceleration")
        self.unused = self.make_concept("Momentum", topic="Mechanics")
        self.lesson = self.make_lesson(self.acceleration)
        self.simulation = self.make_simulation(self.acceleration)

    def test_only_interacted_concepts_appear(self):
        self.add_evidence(self.student, Kind.QUESTION_ASKED, lesson=self.lesson)
        data = build_teacher_student_evidence(student=self.student)
        names = [c["name"] for c in data["concepts"]]
        self.assertIn("Acceleration", names)
        self.assertNotIn("Momentum", names)

    def test_duplicate_concepts_collapse_with_a_count(self):
        for _ in range(3):
            self.add_evidence(self.student, Kind.PREDICTION_SUBMITTED, lesson=self.lesson)
        self.add_experiment(self.student, self.simulation, lesson=self.lesson)
        data = build_teacher_student_evidence(student=self.student)
        rows = [c for c in data["concepts"] if c["name"] == "Acceleration"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 4)


# --- MISCONCEPTION CANDIDATES ------------------------------------------


class MisconceptionCandidateTests(WorkspaceDataMixin, TestCase):
    def setUp(self):
        self.login_teacher()
        self.concept = self.make_concept("Newton's Second Law")
        self.m1 = self.make_misconception(self.concept, code="FORCE_VS_ACCELERATION",
                                          title="Force and acceleration are the same quantity")
        self.student = self.make_student("Alex")
        self.other = self.make_student("Bob")
        self.url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_candidate_appears_for_the_correct_student_only(self):
        m2 = self.make_misconception(self.concept, code="DISTANCE_VS_DISPLACEMENT",
                                     title="Distance and displacement are identical")
        self.add_candidate(self.student, self.m1)
        self.add_candidate(self.other, m2)
        response = self.client.get(self.url)
        self.assertContains(response, "Force and acceleration are the same quantity")
        self.assertNotContains(response, "Distance and displacement are identical")

    def test_supporting_evidence_appears(self):
        obs = self.add_candidate(self.student, self.m1)
        le = self.add_evidence(self.student, Kind.EXPLANATION_SUBMITTED, detail="x")
        self.add_candidate_evidence(obs, learning_evidence=le, excerpt="EVIDENCE-EXCERPT-XYZ")
        response = self.client.get(self.url)
        self.assertContains(response, "EVIDENCE-EXCERPT-XYZ")
        self.assertContains(response, "Explanation submitted")

    def test_internal_misconception_code_is_not_exposed(self):
        obs = self.add_candidate(self.student, self.m1)
        self.add_candidate_evidence(obs, detector="rule:force_vs_acceleration")
        response = self.client.get(self.url)
        self.assertNotContains(response, "FORCE_VS_ACCELERATION")
        self.assertNotContains(response, "rule:force_vs_acceleration")

    def test_teacher_can_confirm_an_eligible_candidate(self):
        teacher = self.make_teacher("mrgreen")
        self.client.force_login(teacher)
        obs = self.add_candidate(self.student, self.m1)
        response = self.client.post(
            reverse("teachers:misconception_decision", args=[self.student.pk, obs.pk]),
            {"decision": "confirm", "note": "seen in class"},
        )
        self.assertEqual(response.status_code, 200)
        obs.refresh_from_db()
        self.assertEqual(obs.status, StudentMisconception.Status.CONFIRMED_BY_TEACHER)
        self.assertEqual(obs.decided_by, teacher)
        self.assertEqual(obs.teacher_note, "seen in class")

    def test_teacher_can_dismiss_a_candidate(self):
        obs = self.add_candidate(self.student, self.m1)
        self.client.post(
            reverse("teachers:misconception_decision", args=[self.student.pk, obs.pk]),
            {"decision": "dismiss"},
        )
        obs.refresh_from_db()
        self.assertEqual(obs.status, StudentMisconception.Status.DISMISSED)

    def test_another_students_candidate_cannot_be_modified(self):
        obs_b = self.add_candidate(self.other, self.m1)
        response = self.client.post(
            reverse("teachers:misconception_decision", args=[self.student.pk, obs_b.pk]),
            {"decision": "confirm"},
        )
        self.assertEqual(response.status_code, 404)
        obs_b.refresh_from_db()
        self.assertEqual(obs_b.status, StudentMisconception.Status.CANDIDATE)

    def test_decision_get_request_does_not_mutate(self):
        obs = self.add_candidate(self.student, self.m1)
        response = self.client.get(
            reverse("teachers:misconception_decision", args=[self.student.pk, obs.pk])
        )
        self.assertEqual(response.status_code, 405)
        obs.refresh_from_db()
        self.assertEqual(obs.status, StudentMisconception.Status.CANDIDATE)


# --- INTERVENTIONS ---------------------------------------------------


class InterventionTests(WorkspaceDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.make_teacher("mrsblue")
        self.client.force_login(self.teacher)
        self.concept = self.make_concept("Acceleration")
        self.lesson = self.make_lesson(self.concept)
        self.student = self.make_student("Alex")
        self.other = self.make_student("Bob")
        self.create_url = reverse("teachers:create_intervention", args=[self.student.pk])

    def test_teacher_can_create_and_persist_an_intervention(self):
        response = self.client.post(
            self.create_url,
            {"action_type": "teacher_note", "note": "Encourage more predictions."},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intervention recorded.")
        self.assertEqual(TeacherIntervention.objects.count(), 1)

    def test_authenticated_teacher_and_url_student_are_stored_not_post_data(self):
        response = self.client.post(
            self.create_url,
            {
                "action_type": "teacher_note",
                "note": "note text",
                "teacher": "999",
                "teacher_id": "999",
                "student": str(self.other.pk),
                "student_id": str(self.other.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        intervention = TeacherIntervention.objects.get()
        self.assertEqual(intervention.teacher, self.teacher)
        self.assertEqual(intervention.student, self.student)

    def test_lesson_and_concept_targets_are_stored(self):
        self.client.post(
            self.create_url,
            {"action_type": "recommend_lesson", "note": "review this",
             "lesson_id": str(self.lesson.pk)},
        )
        self.client.post(
            self.create_url,
            {"action_type": "recommend_experiment", "note": "run again",
             "concept_id": str(self.concept.pk)},
        )
        first, second = list(TeacherIntervention.objects.order_by("created_at"))
        self.assertEqual(first.lesson, self.lesson)
        self.assertEqual(second.concept, self.concept)

    def test_misconception_target_must_belong_to_the_url_student(self):
        misconception = self.make_misconception(self.concept)
        obs_b = self.add_candidate(self.other, misconception)
        response = self.client.post(
            self.create_url,
            {"action_type": "tutor_follow_up", "note": "n",
             "misconception_id": str(obs_b.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not belong to this student")
        self.assertEqual(TeacherIntervention.objects.count(), 0)

    def test_own_students_misconception_can_be_linked(self):
        misconception = self.make_misconception(self.concept)
        obs = self.add_candidate(self.student, misconception)
        self.client.post(
            self.create_url,
            {"action_type": "tutor_follow_up", "note": "n",
             "misconception_id": str(obs.pk)},
        )
        self.assertEqual(TeacherIntervention.objects.get().misconception, obs)

    def test_invalid_action_is_rejected(self):
        response = self.client.post(self.create_url, {"action_type": "banish", "note": "n"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid intervention action")
        self.assertEqual(TeacherIntervention.objects.count(), 0)

    def test_teacher_note_action_requires_text(self):
        response = self.client.post(self.create_url, {"action_type": "teacher_note", "note": "  "})
        self.assertContains(response, "teacher note needs some text")
        self.assertEqual(TeacherIntervention.objects.count(), 0)

    def test_bad_lesson_id_is_rejected(self):
        response = self.client.post(
            self.create_url,
            {"action_type": "recommend_lesson", "note": "n", "lesson_id": "not-a-uuid"},
        )
        self.assertContains(response, "lesson could not be found")
        self.assertEqual(TeacherIntervention.objects.count(), 0)

    def test_intervention_history_is_newest_first(self):
        old = TeacherIntervention.objects.create(
            student=self.student, teacher=self.teacher,
            action_type="teacher_note", note="OLD-NOTE",
        )
        TeacherIntervention.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.client.post(self.create_url, {"action_type": "teacher_note", "note": "NEW-NOTE"})
        body = self.client.get(
            reverse("teachers:student_detail", args=[self.student.pk])
        ).content.decode()
        self.assertLess(body.index("NEW-NOTE"), body.index("OLD-NOTE"))

    def test_student_cannot_create_an_intervention(self):
        self.client.force_login(self.make_student_user())
        response = self.client.post(
            self.create_url, {"action_type": "teacher_note", "note": "x"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TeacherIntervention.objects.count(), 0)

    def test_teacher_note_is_escaped_when_shown(self):
        self.client.post(
            self.create_url,
            {"action_type": "teacher_note", "note": "<script>bad()</script>"},
        )
        response = self.client.get(
            reverse("teachers:student_detail", args=[self.student.pk])
        )
        self.assertNotContains(response, "<script>bad()</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_create_get_request_does_not_mutate(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(TeacherIntervention.objects.count(), 0)


# --- AUDIT METADATA -----------------------------------------------


class InterventionAuditTests(WorkspaceDataMixin, TestCase):
    def test_intervention_metadata_is_a_sanitised_snapshot(self):
        teacher = self.make_teacher("auditteach")
        concept = self.make_concept("Acceleration")
        lesson = self.make_lesson(concept)
        student = self.make_student("Alex")

        intervention = create_teacher_intervention(
            student=student,
            teacher=teacher,
            action_type="recommend_lesson",
            note="review",
            lesson_id=lesson.pk,
            concept_id=concept.pk,
        )
        meta = intervention.metadata
        self.assertEqual(meta["action_type"], "recommend_lesson")
        self.assertEqual(meta["teacher"], "auditteach")
        self.assertEqual(meta["student_id"], student.pk)
        self.assertEqual(meta["lesson_id"], str(lesson.pk))
        self.assertEqual(meta["concept_id"], concept.pk)
        blob = json.dumps(meta).lower()
        for banned in ("api_key", "secret", "token", "password", "authorization"):
            self.assertNotIn(banned, blob)

    def test_cross_student_misconception_link_is_rejected_at_service_layer(self):
        concept = self.make_concept("Acceleration")
        misconception = self.make_misconception(concept)
        student_a = self.make_student("Alex")
        student_b = self.make_student("Bob")
        obs_b = self.add_candidate(student_b, misconception)
        with self.assertRaises(InterventionError):
            create_teacher_intervention(
                student=student_a, teacher=self.make_teacher(),
                action_type="tutor_follow_up", note="n",
                misconception_id=obs_b.pk,
            )


# --- STUDENT LIST -----------------------------------------------


class StudentListTests(WorkspaceDataMixin, TestCase):
    def test_list_shows_real_counts_only(self):
        self.login_teacher()
        concept = self.make_concept("Acceleration")
        lesson = self.make_lesson(concept)
        simulation = self.make_simulation(concept)
        alex = self.make_student("Alex")
        self.make_student("Bob")
        self.add_evidence(alex, Kind.QUESTION_ASKED, lesson=lesson)
        self.add_experiment(alex, simulation, lesson=lesson, completed=True)
        self.add_experiment(alex, simulation, lesson=lesson)

        response = self.client.get(reverse("teachers:student_list"))
        self.assertContains(response, "Alex")
        self.assertContains(response, "Bob")
        self.assertContains(response, "2 experiments")
        self.assertContains(response, "Acceleration")


# --- QUERY BUDGET -----------------------------------------------


class QueryBudgetTests(WorkspaceDataMixin, TestCase):
    def test_build_teacher_student_evidence_query_budget(self):
        from apps.students.models import PracticeAttempt

        concept = self.make_concept("Acceleration")
        lesson = self.make_lesson(concept)
        simulation = self.make_simulation(concept)
        misconception = self.make_misconception(concept)
        student = self.make_student("Alex")
        for i in range(8):
            self.add_evidence(student, Kind.QUESTION_ASKED, lesson=lesson, detail=f"q{i}")
        self.add_experiment(student, simulation, lesson=lesson, completed=True,
                            mass=2.0, force=20.0, accel=10.0)
        # A representative fixture exercises every source table, so no prefetch
        # is silently suppressed by an empty queryset.
        for i in range(3):
            PracticeAttempt.objects.create(
                student=student, lesson=lesson, concept=concept,
                question_key=f"q{i}",
                question_type=PracticeAttempt.QuestionType.NUMERIC,
                question_prompt="p", answer_text="10", is_correct=bool(i % 2),
                attempt_number=1,
            )
        obs = self.add_candidate(student, misconception)
        self.add_candidate_evidence(obs)
        self.add_tutor(student, lesson, student_turns=2, tutor_turns=2)
        TeacherIntervention.objects.create(
            student=student, teacher=self.make_teacher(),
            action_type="teacher_note", note="n",
        )

        # Bounded and intentional: progress projection + candidates (+ prefetch)
        # + practice-attempt evidence + learning-pattern synthesis (practice /
        # experiment / tutor reads, each with one prefetch) + one shared
        # concept-graph read + learning-goals read + activity planner
        # (concept destination maps + goal / recommendation / unfinished-lab
        # reads + a few bounded activity-signal checks) + form choice lists
        # (lesson/concept/simulation) + intervention history. No per-row queries;
        # the number does not grow with student history size.
        with self.assertNumQueries(29):
            build_teacher_student_evidence(student=student)
