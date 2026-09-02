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
from apps.students.experiment_services import complete_experiment
from apps.students.models import (
    ExperimentAttempt,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)

from .models import TeacherIntervention
from .services import (
    InterventionError,
    build_teacher_student_evidence,
    create_teacher_intervention,
    dismiss_recommendation,
    list_student_recommendations,
    open_recommendation,
)

User = get_user_model()
REC_URL = reverse("students:recommendations")
Action = TeacherIntervention.ActionType
Status = TeacherIntervention.Status


class RecDataMixin:
    def make_teacher(self, username="teach"):
        return User.objects.create_user(username, password="pw", is_staff=True)

    def make_user(self, username="stud"):
        return User.objects.create_user(username, password="pw")

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name="Acceleration", topic="Kinematics"):
        return PhysicsConcept.objects.create(name=name, description="c", topic=topic)

    def make_lesson(self, *concepts, title="Forces and Motion"):
        lesson = Lesson.objects.create(
            title=title, topic="Dynamics", grade_level="11",
            duration_minutes=45, learning_objectives=["x"],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept, title="Newton's Second Law Lab"):
        return PhysicsSimulation.objects.create(
            concept=concept, title=title,
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def make_rec(self, student, action, *, teacher=None, lesson=None, concept=None,
                 simulation=None, misconception=None, note="", status=Status.PENDING):
        if teacher is None:
            self._rt = getattr(self, "_rt", 0) + 1
            teacher = self.make_teacher(f"recteach{self._rt}")
        rec = TeacherIntervention.objects.create(
            student=student, teacher=teacher,
            action_type=action, lesson=lesson, concept=concept, simulation=simulation,
            misconception=misconception, note=note, status=status,
        )
        return rec

    def complete_attempt(self, student, simulation, **kw):
        attempt = ExperimentAttempt.objects.create(
            student=student, simulation=simulation, **kw
        )
        complete_experiment(attempt)
        attempt.refresh_from_db()
        return attempt

    def as_student(self, username="stud"):
        user = self.make_user(username)
        student = self.make_student(username.title(), user=user)
        self.client.force_login(user)
        return student


# --- STUDENT ACCESS --------------------------------------------------------


class RecommendationAccessTests(RecDataMixin, TestCase):
    def test_recommendation_page_loads(self):
        self.as_student()
        response = self.client.get(REC_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your learning recommendations")

    def test_student_sees_only_their_own_recommendations(self):
        alex = self.as_student("alex")
        bob = self.make_student("Bob")
        lesson_a = self.make_lesson(title="ALEX LESSON")
        lesson_b = self.make_lesson(title="BOB LESSON")
        self.make_rec(alex, Action.RECOMMEND_LESSON, lesson=lesson_a)
        self.make_rec(bob, Action.RECOMMEND_LESSON, lesson=lesson_b)

        response = self.client.get(REC_URL)
        self.assertContains(response, "ALEX LESSON")
        self.assertNotContains(response, "BOB LESSON")

    def test_student_id_query_parameter_is_ignored(self):
        alex = self.as_student("alex")
        bob = self.make_student("Bob")
        self.make_rec(alex, Action.RECOMMEND_LESSON, lesson=self.make_lesson(title="ALEX ONLY"))
        self.make_rec(bob, Action.RECOMMEND_LESSON, lesson=self.make_lesson(title="BOB ONLY"))

        response = self.client.get(REC_URL, {"student_id": bob.pk})
        self.assertContains(response, "ALEX ONLY")
        self.assertNotContains(response, "BOB ONLY")

    def test_anonymous_uses_shared_guest_student(self):
        self.client.get(REC_URL)
        self.client.get(REC_URL)
        self.assertEqual(StudentProfile.objects.filter(user__isnull=True).count(), 1)


# --- VISIBILITY --------------------------------------------------------


class RecommendationVisibilityTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.concept = self.make_concept("Newton's Second Law")
        self.lesson = self.make_lesson(self.concept, title="Forces Lesson")
        self.simulation = self.make_simulation(self.concept)

    def test_recommend_lesson_appears(self):
        self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        response = self.client.get(REC_URL)
        self.assertContains(response, "Forces Lesson")
        self.assertContains(response, "Open Lesson")

    def test_recommend_experiment_appears(self):
        self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.simulation)
        response = self.client.get(REC_URL)
        self.assertContains(response, "Newton&#x27;s Second Law Lab")
        self.assertContains(response, "Open Physics Lab")

    def test_tutor_follow_up_appears(self):
        self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        response = self.client.get(REC_URL)
        self.assertContains(response, "Talk to Tutor")

    def test_teacher_note_never_appears(self):
        TeacherIntervention.objects.create(
            student=self.student, teacher=self.make_teacher("t9"),
            action_type=Action.TEACHER_NOTE, note="PRIVATE-TEACHER-NOTE",
        )
        response = self.client.get(REC_URL)
        self.assertNotContains(response, "PRIVATE-TEACHER-NOTE")
        self.assertContains(response, "No pending recommendations")

    def test_private_note_and_internal_data_not_exposed(self):
        misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION", title="Force and acceleration are the same",
            description="d", physics_concept=self.concept,
        )
        obs = StudentMisconception.objects.create(
            student=self.student, misconception=misconception
        )
        self.make_rec(
            self.student, Action.RECOMMEND_EXPERIMENT,
            simulation=self.simulation, misconception=obs,
            note="<script>alert('private')</script> compare force and acceleration",
        )
        response = self.client.get(REC_URL)
        self.assertNotContains(response, "alert('private')")
        self.assertNotContains(response, "FORCE_VS_ACCELERATION")
        self.assertNotContains(response, "Force and acceleration are the same")
        for token in ("physics-misconception-v1", "rule:", "candidate", "misconception_id", "metadata"):
            self.assertNotContains(response, token)


# --- DESTINATION --------------------------------------------------------


class RecommendationDestinationTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept)
        self.simulation = self.make_simulation(self.concept)

    def test_lesson_recommendation_destination_is_the_student_lesson_route(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        data = list_student_recommendations(student=self.student)
        self.assertEqual(
            data["pending"][0].destination_url,
            reverse("students:tutor", args=[self.lesson.slug]),
        )

    def test_experiment_recommendation_destination_is_the_physics_lab(self):
        self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.simulation)
        data = list_student_recommendations(student=self.student)
        self.assertEqual(
            data["pending"][0].destination_url,
            reverse("physics_lab:detail", args=[self.simulation.slug]),
        )

    def test_tutor_recommendation_destination_is_the_existing_tutor(self):
        self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        data = list_student_recommendations(student=self.student)
        self.assertEqual(
            data["pending"][0].destination_url,
            reverse("students:tutor", args=[self.lesson.slug]),
        )

    def test_open_redirects_to_server_reversed_url_ignoring_client_input(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        response = self.client.post(
            reverse("students:recommendation_open", args=[rec.pk]),
            {"next": "http://evil.example/pwn", "destination_url": "http://evil.example"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("students:tutor", args=[self.lesson.slug]))


# --- STATUS TRANSITIONS --------------------------------------------


class RecommendationStatusTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept)
        self.simulation = self.make_simulation(self.concept)

    def test_new_recommendation_is_pending(self):
        rec = create_teacher_intervention(
            student=self.student, teacher=self.make_teacher("t1"),
            action_type="recommend_lesson", lesson_id=self.lesson.pk,
        )
        self.assertEqual(rec.status, Status.PENDING)

    def test_opening_moves_pending_to_opened(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        response = self.client.post(
            reverse("students:recommendation_open", args=[rec.pk])
        )
        self.assertEqual(response.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)
        self.assertIsNotNone(rec.acted_at)

    def test_student_can_dismiss_with_post(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        response = self.client.post(
            reverse("students:recommendation_dismiss", args=[rec.pk])
        )
        self.assertEqual(response.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.DISMISSED)

    def test_get_cannot_mutate_state(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        self.assertEqual(
            self.client.get(reverse("students:recommendation_open", args=[rec.pk])).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(reverse("students:recommendation_dismiss", args=[rec.pk])).status_code,
            405,
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)

    def test_cannot_dismiss_another_students_recommendation(self):
        other = self.make_student("Bob")
        rec = self.make_rec(other, Action.RECOMMEND_LESSON, lesson=self.lesson)
        response = self.client.post(
            reverse("students:recommendation_dismiss", args=[rec.pk])
        )
        self.assertEqual(response.status_code, 404)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)

    def test_cannot_open_another_students_recommendation(self):
        other = self.make_student("Bob")
        rec = self.make_rec(other, Action.RECOMMEND_EXPERIMENT, simulation=self.simulation)
        response = self.client.post(
            reverse("students:recommendation_open", args=[rec.pk])
        )
        self.assertEqual(response.status_code, 404)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)

    def test_dismissed_recommendation_leaves_the_pending_section(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        self.client.post(reverse("students:recommendation_dismiss", args=[rec.pk]))
        data = list_student_recommendations(student=self.student)
        self.assertEqual(data["pending"], [])
        self.assertEqual(data["history"][0].status, Status.DISMISSED)

    def test_student_cannot_overwrite_status_or_note_via_post(self):
        rec = self.make_rec(
            self.student, Action.RECOMMEND_LESSON, lesson=self.lesson, note="teacher-only"
        )
        self.client.post(
            reverse("students:recommendation_open", args=[rec.pk]),
            {"status": "completed", "note": "hacked", "student": "999"},
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)  # not "completed"
        self.assertEqual(rec.note, "teacher-only")
        self.assertEqual(rec.student, self.student)


# --- EXPERIMENT COMPLETION ------------------------------------------


class ExperimentCompletionTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.concept = self.make_concept()
        self.sim1 = self.make_simulation(self.concept, title="Sim One")
        self.sim2 = self.make_simulation(self.concept, title="Sim Two")

    def test_opening_experiment_recommendation_does_not_mark_it_completed(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)

    def test_completing_the_matching_experiment_completes_the_recommendation(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        self.complete_attempt(self.student, self.sim1, prediction="p", observation="o", explanation="e")
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.COMPLETED)
        self.assertIsNotNone(rec.acted_at)

    def test_unrelated_experiment_does_not_complete_the_recommendation(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        self.complete_attempt(self.student, self.sim2)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)

    def test_only_the_latest_matching_recommendation_completes(self):
        old = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        TeacherIntervention.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=1)
        )
        new = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        self.complete_attempt(self.student, self.sim1)
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(new.status, Status.COMPLETED)
        self.assertEqual(old.status, Status.PENDING)

    def test_another_students_experiment_does_not_complete_this_recommendation(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_EXPERIMENT, simulation=self.sim1)
        other = self.make_student("Bob")
        self.complete_attempt(other, self.sim1)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)


# --- LESSON: HONEST STATUS ONLY --------------------------------


class LessonRecommendationHonestyTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.lesson = self.make_lesson(title="Kinematics 1")

    def test_opening_a_lesson_recommendation_never_claims_completion(self):
        rec = self.make_rec(self.student, Action.RECOMMEND_LESSON, lesson=self.lesson)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)
        response = self.client.get(REC_URL)
        self.assertContains(response, "Opened")
        self.assertNotContains(response, ">Completed<")


# --- TUTOR: EXISTING SESSION ONLY --------------------------------


class TutorRecommendationTests(RecDataMixin, TestCase):
    def setUp(self):
        self.student = self.as_student()
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept, title="Forces Lesson")

    def test_tutor_recommendation_does_not_add_a_conversation_model(self):
        self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        self.client.get(REC_URL)
        self.assertEqual(TutorSession.objects.count(), 0)

    def test_opened_tutor_recommendation_completes_on_a_student_message(self):
        rec = self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="why?"
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.COMPLETED)

    def test_unopened_tutor_recommendation_stays_pending_after_a_message(self):
        rec = self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="hi"
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.PENDING)

    def test_tutor_message_for_a_different_lesson_does_not_complete_it(self):
        rec = self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))
        other_lesson = self.make_lesson(title="Other")
        session = TutorSession.objects.create(student=self.student, lesson=other_lesson)
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="q"
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)

    def test_assistant_message_does_not_complete_a_recommendation(self):
        rec = self.make_rec(self.student, Action.TUTOR_FOLLOW_UP, lesson=self.lesson)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))
        session = TutorSession.objects.create(student=self.student, lesson=self.lesson)
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.TUTOR, content="hello", mode="explain"
        )
        rec.refresh_from_db()
        self.assertEqual(rec.status, Status.OPENED)


# --- TEACHER WORKSPACE VIEW ---------------------------------


class TeacherWorkspaceRecommendationTests(RecDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.make_teacher("mrblue")
        self.concept = self.make_concept()
        self.lesson = self.make_lesson(self.concept, title="Kinematics Intro")
        self.simulation = self.make_simulation(self.concept)
        self.student = self.make_student("Alex")
        self.detail_url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_teacher_sees_recommendation_status_and_target(self):
        self.make_rec(
            self.student, Action.RECOMMEND_EXPERIMENT,
            teacher=self.teacher, simulation=self.simulation, note="PRIVATE-NOTE",
        )
        self.client.force_login(self.teacher)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Pending")
        self.assertContains(response, "Newton&#x27;s Second Law Lab")
        # Private note IS visible to the teacher.
        self.assertContains(response, "PRIVATE-NOTE")

    def test_private_note_is_teacher_only(self):
        self.make_rec(
            self.student, Action.RECOMMEND_LESSON,
            teacher=self.teacher, lesson=self.lesson, note="PRIVATE-NOTE-2",
        )
        student_user = self.make_user("alexuser")
        self.student.user = student_user
        self.student.save(update_fields=["user"])
        self.client.force_login(student_user)
        response = self.client.get(REC_URL)
        self.assertNotContains(response, "PRIVATE-NOTE-2")

    def test_student_action_updates_teacher_facing_status(self):
        rec = self.make_rec(
            self.student, Action.RECOMMEND_LESSON, teacher=self.teacher, lesson=self.lesson
        )
        student_user = self.make_user("alexuser")
        self.student.user = student_user
        self.student.save(update_fields=["user"])
        self.client.force_login(student_user)
        self.client.post(reverse("students:recommendation_open", args=[rec.pk]))

        self.client.force_login(self.teacher)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Opened")
        self.assertContains(response, "Student acted:")


# --- SECURITY: TEACHER-SIDE VALIDATION -----------------------


class RecommendationSecurityTests(RecDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.make_teacher("t")
        self.concept = self.make_concept()
        self.student = self.make_student("Alex")
        self.other = self.make_student("Bob")

    def test_invalid_simulation_id_is_rejected(self):
        with self.assertRaises(InterventionError):
            create_teacher_intervention(
                student=self.student, teacher=self.teacher,
                action_type="recommend_experiment", simulation_id="999999",
            )

    def test_experiment_recommendation_requires_a_target(self):
        with self.assertRaises(InterventionError):
            create_teacher_intervention(
                student=self.student, teacher=self.teacher,
                action_type="recommend_experiment",
            )

    def test_lesson_recommendation_requires_a_target(self):
        with self.assertRaises(InterventionError):
            create_teacher_intervention(
                student=self.student, teacher=self.teacher,
                action_type="recommend_lesson",
            )

    def test_teacher_cannot_link_another_students_misconception(self):
        misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION", title="t", description="d",
            physics_concept=self.concept,
        )
        obs_b = StudentMisconception.objects.create(
            student=self.other, misconception=misconception
        )
        with self.assertRaises(InterventionError):
            create_teacher_intervention(
                student=self.student, teacher=self.teacher,
                action_type="tutor_follow_up", note="n",
                misconception_id=obs_b.pk,
            )


# --- ESCAPING + QUERY BUDGET -------------------------------


class RecommendationRenderingTests(RecDataMixin, TestCase):
    def test_target_title_with_html_is_escaped(self):
        student = self.as_student()
        lesson = self.make_lesson(title="<b>Hax</b> Forces")
        self.make_rec(student, Action.RECOMMEND_LESSON, lesson=lesson)
        response = self.client.get(REC_URL)
        self.assertNotContains(response, "<b>Hax</b>")
        self.assertContains(response, "&lt;b&gt;Hax&lt;/b&gt;")

    def test_list_student_recommendations_query_budget(self):
        student = self.make_student("Alex")
        concept = self.make_concept()
        lesson = self.make_lesson(concept)
        simulation = self.make_simulation(concept)
        for i in range(6):
            self.make_rec(student, Action.RECOMMEND_EXPERIMENT, simulation=simulation)
        self.make_rec(student, Action.RECOMMEND_LESSON, lesson=lesson)

        with self.assertNumQueries(1):
            list_student_recommendations(student=student)
