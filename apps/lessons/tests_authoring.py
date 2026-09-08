"""Step 26 -- Teacher lesson + activity authoring enhancements.

The authoring layer only organises what already exists. These tests assert it
never duplicates the Physics Lab / practice / assessment / tutor / recovery /
evidence / provenance systems, that publishing stays an explicit, validated
teacher action, that a teacher cannot touch another teacher's lesson, that a
teacher preview is presentation-only, and that legacy lessons still work.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.assessments.models import Assessment, AssessmentQuestion, QuestionBankItem
from apps.physics.models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)
from apps.provenance.models import ProvenanceEvent
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
)

from .authoring_services import (
    ACTIVITY_TYPES,
    LessonAuthoringError,
    LessonPublishError,
    build_student_lesson_activities,
    create_activity,
    delete_activity,
    lesson_activities,
    move_activity,
    publish_lesson,
    set_learning_objectives,
    set_lesson_concepts,
    update_activity,
    update_lesson_basics,
    validate_lesson_for_publish,
)
from .models import Lesson, LessonActivity

User = get_user_model()
PW = "pw-authoring-123!"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringTestCase(TestCase):
    """Seed a full fixture and use a fast hasher for the many teacher logins."""

    def setUp(self):
        self.teacher_a = User.objects.create_user(username="teacher_a", password=PW, is_staff=True)
        self.teacher_b = User.objects.create_user(username="teacher_b", password=PW, is_staff=True)
        self.not_a_teacher = User.objects.create_user(username="not_teacher", password=PW)

        self.concept_dyn = PhysicsConcept.objects.create(
            name="Newton's Second Law", description="F = ma.", topic="Dynamics"
        )
        self.concept_kin = PhysicsConcept.objects.create(
            name="Displacement", description="Change in position.", topic="Kinematics"
        )
        self.inactive_concept = PhysicsConcept.objects.create(
            name="Retired Concept", description="x", topic="Other", is_active=False
        )

        self.sim = PhysicsSimulation.objects.create(
            concept=self.concept_dyn,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        self.inactive_sim = PhysicsSimulation.objects.create(
            concept=self.concept_kin,
            title="Retired Sim",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
            is_active=False,
        )

        self.question = QuestionBankItem.objects.create(
            key="nsl-doubling",
            question_type=QuestionBankItem.QuestionType.MULTIPLE_CHOICE,
            prompt="Doubling the mass with the same net force does what to acceleration?",
            choices=["Doubles it", "No change", "Halves it"],
            correct_choice=2,
            concept=self.concept_dyn,
        )
        self.numeric_question = QuestionBankItem.objects.create(
            key="nsl-numeric",
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="A 20 N net force on a 2 kg cart gives what acceleration?",
            expected_value=10.0,
            expected_unit="m/s^2",
            tolerance=0.1,
        )
        self.inactive_question = QuestionBankItem.objects.create(
            key="retired-q",
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="x",
            expected_value=1.0,
            is_active=False,
        )

        self.published_assessment = Assessment.objects.create(
            title="Dynamics Check", status=Assessment.Status.PUBLISHED
        )
        AssessmentQuestion.objects.create(
            assessment=self.published_assessment, question=self.question, position=1
        )
        self.draft_assessment = Assessment.objects.create(
            title="Draft Check", status=Assessment.Status.DRAFT
        )

        misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION",
            title="Force and acceleration confused",
            description="x",
            physics_concept=self.concept_dyn,
        )
        self.recovery_path = MisconceptionRecoveryPath.objects.create(
            misconception=misconception,
            title="Force vs acceleration recovery",
            student_summary="Let's compare force and acceleration.",
        )
        MisconceptionRecoveryActivity.objects.create(
            path=self.recovery_path,
            order=1,
            activity_type=MisconceptionRecoveryActivity.ActivityType.PHYSICS_LAB,
            label="Run the Lab",
            simulation=self.sim,
        )
        self.inactive_recovery_path = MisconceptionRecoveryPath.objects.create(
            misconception=misconception,
            title="Retired recovery",
            student_summary="x",
            is_active=False,
        )

        self.lesson = Lesson.objects.create(
            title="Forces and Motion",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            description="An intro to F = ma.",
            learning_objectives=["Relate net force, mass and acceleration."],
            created_by=self.teacher_a,
        )
        self.lesson.physics_concepts.add(self.concept_dyn)

    # -- helpers --

    def client_for(self, user):
        c = Client()
        c.login(username=user.username, password=PW)
        return c

    def add_lab_activity(self, **kw):
        return create_activity(
            lesson=self.lesson,
            teacher=self.teacher_a,
            activity_type="physics_lab",
            title=kw.get("title", "Run the Lab"),
            instructions=kw.get("instructions", ""),
            reference_id=kw.get("reference_id", self.sim.pk),
        )

    def make_publishable(self):
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a, raw_objectives=["Understand F=ma."]
        )
        self.add_lab_activity()


# --- 1. Model + service: lesson basics / objectives / concepts --------


class LessonBasicsTests(AuthoringTestCase):
    def test_update_basics_persists_and_records_provenance(self):
        update_lesson_basics(
            lesson=self.lesson,
            teacher=self.teacher_a,
            title="Forces, Motion & Newton",
            topic="Dynamics",
            grade_level="12",
            duration_minutes=50,
            description="Updated overview.",
        )
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.title, "Forces, Motion & Newton")
        self.assertEqual(self.lesson.grade_level, "12")
        self.assertEqual(self.lesson.duration_minutes, 50)
        self.assertTrue(
            ProvenanceEvent.objects.filter(
                lesson=self.lesson,
                event_type=ProvenanceEvent.EventType.LESSON_UPDATED,
                metadata__change="basics",
            ).exists()
        )

    def test_update_basics_rejects_empty_title_and_bad_duration(self):
        with self.assertRaises(LessonAuthoringError):
            update_lesson_basics(
                lesson=self.lesson, teacher=self.teacher_a, title="  ",
                topic="Dynamics", grade_level="11", duration_minutes=45,
            )
        with self.assertRaises(LessonAuthoringError):
            update_lesson_basics(
                lesson=self.lesson, teacher=self.teacher_a, title="ok",
                topic="Dynamics", grade_level="11", duration_minutes="not-a-number",
            )

    def test_objectives_are_normalised_order_preserved_empties_dropped(self):
        result = set_learning_objectives(
            lesson=self.lesson,
            teacher=self.teacher_a,
            raw_objectives=["  Second  ", "", "First", "   ", "Third"],
        )
        self.assertEqual(result, ["Second", "First", "Third"])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.learning_objectives, ["Second", "First", "Third"])

    def test_set_concepts_resolves_server_side_and_dedupes(self):
        set_lesson_concepts(
            lesson=self.lesson,
            teacher=self.teacher_a,
            concept_ids=[self.concept_kin.pk, self.concept_dyn.pk, self.concept_kin.pk],
        )
        self.assertCountEqual(
            self.lesson.physics_concepts.values_list("name", flat=True),
            ["Displacement", "Newton's Second Law"],
        )

    def test_set_concepts_rejects_unknown_or_inactive_id(self):
        with self.assertRaises(LessonAuthoringError):
            set_lesson_concepts(
                lesson=self.lesson, teacher=self.teacher_a, concept_ids=[999999]
            )
        with self.assertRaises(LessonAuthoringError):
            set_lesson_concepts(
                lesson=self.lesson, teacher=self.teacher_a,
                concept_ids=[self.inactive_concept.pk],
            )
        with self.assertRaises(LessonAuthoringError):
            set_lesson_concepts(
                lesson=self.lesson, teacher=self.teacher_a, concept_ids=["not-an-int"]
            )


# --- 2. Activities: CRUD + reorder + references ----------------------


class ActivityServiceTests(AuthoringTestCase):
    def test_create_activity_assigns_next_position_and_records_provenance(self):
        a1 = self.add_lab_activity(title="First")
        a2 = create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation",
            title="Second", instructions="Read this.",
        )
        self.assertEqual([a1.position, a2.position], [1, 2])
        self.assertTrue(
            ProvenanceEvent.objects.filter(
                lesson=self.lesson,
                event_type=ProvenanceEvent.EventType.LESSON_UPDATED,
                metadata__change="activity_created",
            ).exists()
        )

    def test_activity_type_allow_list_is_exactly_the_supported_set(self):
        self.assertEqual(
            ACTIVITY_TYPES,
            frozenset(
                {"explanation", "physics_lab", "practice", "tutor", "assessment", "recovery"}
            ),
        )

    def test_unknown_activity_type_is_rejected(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a,
                activity_type="lesson_lab_activity_v2", title="x",
            )

    def test_reference_required_for_typed_activities(self):
        for atype in ("physics_lab", "practice", "assessment", "recovery"):
            with self.assertRaises(LessonAuthoringError):
                create_activity(
                    lesson=self.lesson, teacher=self.teacher_a,
                    activity_type=atype, title="x", reference_id="",
                )

    def test_inactive_simulation_rejected(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="physics_lab",
                title="x", reference_id=self.inactive_sim.pk,
            )

    def test_inactive_question_rejected(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="practice",
                title="x", reference_id=self.inactive_question.pk,
            )

    def test_ungradeable_question_rejected_at_link_publish_and_answer_time(self):
        # An active-but-malformed numeric question (no answer key) -- reachable
        # by an admin edit, not the builder. It must never become a live activity.
        bad = QuestionBankItem.objects.create(
            key="broken-numeric",
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="Unanswerable",
            expected_value=None,
        )
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="practice",
                title="x", reference_id=bad.pk,
            )
        # If one slipped in before the question was broken, publish validation catches it.
        activity = create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="practice",
            title="ok", reference_id=self.question.pk,
        )
        LessonActivity.objects.filter(pk=activity.pk).update(question=bad)
        activity.refresh_from_db()
        reasons = validate_lesson_for_publish(self.lesson)
        self.assertTrue(any("cannot be graded" in r for r in reasons))
        # And the student handler raises a caught error, never a TypeError.
        from .authoring_services import record_practice_activity_answer

        with self.assertRaises(LessonAuthoringError):
            record_practice_activity_answer(
                student=StudentProfile.objects.create(display_name="S"),
                lesson=self.lesson, activity=activity, submitted_answer="5",
            )

    def test_unpublished_assessment_rejected(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="assessment",
                title="x", reference_id=self.draft_assessment.pk,
            )

    def test_inactive_recovery_path_rejected(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="recovery",
                title="x", reference_id=self.inactive_recovery_path.pk,
            )

    def test_typed_prefix_must_match_activity_type(self):
        with self.assertRaises(LessonAuthoringError):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="physics_lab",
                title="x", reference_id=f"assessment:{self.published_assessment.pk}",
            )

    def test_update_activity_changes_title_and_reference(self):
        activity = create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="practice",
            title="Practice", reference_id=self.question.pk,
        )
        update_activity(
            activity=activity, teacher=self.teacher_a, title="Practice v2",
            instructions="Show your working.", reference_id=self.numeric_question.pk,
        )
        activity.refresh_from_db()
        self.assertEqual(activity.title, "Practice v2")
        self.assertEqual(activity.question_id, self.numeric_question.pk)

    def test_delete_activity_compacts_positions(self):
        self.add_lab_activity(title="one")
        a2 = create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation", title="two"
        )
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation", title="three"
        )
        delete_activity(activity=a2, teacher=self.teacher_a)
        rows = lesson_activities(self.lesson)
        self.assertEqual([(r.title, r.position) for r in rows], [("one", 1), ("three", 2)])

    def test_repeated_delete_is_a_safe_no_op(self):
        a1 = self.add_lab_activity()
        delete_activity(activity=a1, teacher=self.teacher_a)
        delete_activity(activity=a1, teacher=self.teacher_a)  # must not raise
        self.assertEqual(LessonActivity.objects.filter(lesson=self.lesson).count(), 0)

    def test_move_activity_swaps_positions_and_is_edge_safe(self):
        create_activity(lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation", title="one")
        a2 = create_activity(lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation", title="two")
        move_activity(activity=a2, teacher=self.teacher_a, direction="up")
        rows = lesson_activities(self.lesson)
        self.assertEqual([r.title for r in rows], ["two", "one"])
        move_activity(activity=rows[0], teacher=self.teacher_a, direction="up")
        self.assertEqual([r.title for r in lesson_activities(self.lesson)], ["two", "one"])

    def test_positions_stay_contiguous_after_many_operations(self):
        for i in range(5):
            create_activity(
                lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation",
                title=f"a{i}",
            )
        rows = lesson_activities(self.lesson)
        delete_activity(activity=rows[1], teacher=self.teacher_a)
        delete_activity(activity=rows[3], teacher=self.teacher_a)
        positions = [r.position for r in lesson_activities(self.lesson)]
        self.assertEqual(positions, [1, 2, 3])


# --- 3. HTTP: builder, permissions, CSRF, GET-safety ----------------


class BuilderHttpTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = self.client_for(self.teacher_a)

    def test_builder_page_renders_for_the_owner(self):
        r = self.client_a.get(reverse("lessons:build", args=[self.lesson.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "lessons/build.html")
        self.assertContains(r, "Learning activities")

    def test_builder_page_has_accessible_structure(self):
        self.add_lab_activity()
        r = self.client_a.get(reverse("lessons:build", args=[self.lesson.slug]))
        content = r.content.decode()
        self.assertEqual(content.count("<h1>"), 1)
        self.assertIn("<h2", content)
        self.assertIn('for="lb-title"', content)          # labelled input
        self.assertIn('aria-labelledby="lb-activities-title"', content)
        self.assertIn(">Move up<", content)               # real button text, not icon-only

    def test_builder_success_banner_is_announced_and_section_specific(self):
        r = self.client_a.get(
            reverse("lessons:build", args=[self.lesson.slug]) + "?ok=objectives"
        )
        self.assertContains(r, 'aria-live="polite"')
        self.assertContains(r, 'role="status"')
        self.assertContains(r, "Learning objectives saved.")

    def test_publish_button_is_really_disabled_when_lesson_is_invalid(self):
        bare = Lesson.objects.create(
            title="Bare", topic="X", grade_level="11", duration_minutes=30,
            created_by=self.teacher_a, learning_objectives=[],
        )
        r = self.client_a.get(reverse("lessons:build", args=[bare.slug]))
        self.assertContains(r, ">Publish lesson</button>")
        # a real disabled attribute, not aria-disabled
        self.assertRegex(r.content.decode(), r'<button[^>]*\bdisabled\b[^>]*>\s*Publish lesson')
        self.assertNotContains(r, 'aria-disabled="true"')

    def test_builder_requires_a_teacher(self):
        self.assertEqual(
            Client().get(reverse("lessons:build", args=[self.lesson.slug])).status_code, 403
        )
        non_teacher = self.client_for(self.not_a_teacher)
        self.assertEqual(
            non_teacher.get(reverse("lessons:build", args=[self.lesson.slug])).status_code,
            403,
        )

    def test_a_different_teacher_cannot_edit_this_lesson(self):
        client_b = self.client_for(self.teacher_b)
        r = client_b.post(
            reverse("lessons:activity_add", args=[self.lesson.slug]),
            {"activity_type": "explanation", "title": "Sneaky"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(LessonActivity.objects.filter(lesson=self.lesson).count(), 0)

    def test_a_different_teacher_cannot_reorder_or_delete_activities(self):
        activity = self.add_lab_activity()
        client_b = self.client_for(self.teacher_b)
        self.assertEqual(
            client_b.post(
                reverse("lessons:activity_delete", args=[self.lesson.slug, activity.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            client_b.post(
                reverse("lessons:activity_move", args=[self.lesson.slug, activity.pk]),
                {"direction": "down"},
            ).status_code,
            403,
        )
        self.assertTrue(LessonActivity.objects.filter(pk=activity.pk).exists())

    def test_legacy_lesson_without_owner_is_editable_by_any_teacher(self):
        legacy = Lesson.objects.create(
            title="Legacy", topic="Dynamics", grade_level="11", duration_minutes=30,
        )
        client_b = self.client_for(self.teacher_b)
        r = client_b.post(
            reverse("lessons:activity_add", args=[legacy.slug]),
            {"activity_type": "explanation", "title": "Intro"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(LessonActivity.objects.filter(lesson=legacy).count(), 1)

    def test_state_changing_endpoints_reject_get(self):
        for name in ("update_basics", "update_objectives", "update_concepts", "activity_add", "publish"):
            r = self.client_a.get(reverse(f"lessons:{name}", args=[self.lesson.slug]))
            self.assertEqual(r.status_code, 405, name)

    def test_csrf_is_enforced_on_authoring_posts(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="teacher_a", password=PW)
        r = csrf_client.post(
            reverse("lessons:activity_add", args=[self.lesson.slug]),
            {"activity_type": "explanation", "title": "x"},
        )
        self.assertEqual(r.status_code, 403)

    def test_add_activity_via_http_uses_typed_reference(self):
        r = self.client_a.post(
            reverse("lessons:activity_add", args=[self.lesson.slug]),
            {
                "activity_type": "physics_lab",
                "title": "Kinematics Lab",
                "reference_id": f"physics_lab:{self.sim.pk}",
            },
        )
        self.assertEqual(r.status_code, 302)
        activity = LessonActivity.objects.get(lesson=self.lesson)
        self.assertEqual(activity.simulation_id, self.sim.pk)

    def test_forged_reference_id_is_rejected_and_rerenders(self):
        r = self.client_a.post(
            reverse("lessons:activity_add", args=[self.lesson.slug]),
            {
                "activity_type": "physics_lab",
                "title": "x",
                "reference_id": f"physics_lab:{self.inactive_sim.pk}",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "not active")
        self.assertEqual(LessonActivity.objects.filter(lesson=self.lesson).count(), 0)

    def test_double_click_add_does_not_break_positions(self):
        payload = {"activity_type": "explanation", "title": "Intro"}
        self.client_a.post(reverse("lessons:activity_add", args=[self.lesson.slug]), payload)
        self.client_a.post(reverse("lessons:activity_add", args=[self.lesson.slug]), payload)
        positions = list(
            LessonActivity.objects.filter(lesson=self.lesson)
            .order_by("position")
            .values_list("position", flat=True)
        )
        self.assertEqual(positions, [1, 2])

    def test_cross_teacher_cannot_target_activity_by_id_from_another_lesson(self):
        other_lesson = Lesson.objects.create(
            title="Other", topic="Kinematics", grade_level="11", duration_minutes=30,
            created_by=self.teacher_a,
        )
        activity = create_activity(
            lesson=other_lesson, teacher=self.teacher_a, activity_type="explanation", title="X"
        )
        r = self.client_a.post(
            reverse("lessons:activity_edit", args=[self.lesson.slug, activity.pk]),
            {"title": "hijack"},
        )
        self.assertEqual(r.status_code, 404)


# --- 4. XSS / safe rendering --------------------------------------


class AuthoringXssTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = self.client_for(self.teacher_a)

    def test_malicious_payloads_are_escaped_in_the_builder(self):
        payload = "<script>alert('x')</script>"
        update_lesson_basics(
            lesson=self.lesson, teacher=self.teacher_a, title=payload, topic="Dynamics",
            grade_level="11", duration_minutes=45,
        )
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a, raw_objectives=[payload]
        )
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation",
            title=payload, instructions=payload,
        )
        r = self.client_a.get(reverse("lessons:build", args=[self.lesson.slug]))
        self.assertNotContains(r, "<script>alert('x')</script>")
        self.assertContains(r, "&lt;script&gt;")

    def test_payloads_are_escaped_in_preview(self):
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="explanation",
            title="<img src=x onerror=alert(1)>", instructions="ok",
        )
        r = self.client_a.get(reverse("lessons:preview", args=[self.lesson.slug]))
        self.assertNotContains(r, "<img src=x onerror=alert(1)>")


# --- 5. Publishing -----------------------------------------------


class PublishTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = self.client_for(self.teacher_a)

    def test_incomplete_lesson_cannot_publish(self):
        bare = Lesson.objects.create(
            title="Bare", topic="X", grade_level="11", duration_minutes=30,
            created_by=self.teacher_a, learning_objectives=[],
        )
        self.assertTrue(validate_lesson_for_publish(bare))
        with self.assertRaises(LessonPublishError):
            publish_lesson(lesson=bare, teacher=self.teacher_a)
        bare.refresh_from_db()
        self.assertEqual(bare.status, Lesson.Status.DRAFT)

    def test_valid_lesson_publishes_explicitly_with_provenance(self):
        self.make_publishable()
        self.assertEqual(validate_lesson_for_publish(self.lesson), [])
        publish_lesson(lesson=self.lesson, teacher=self.teacher_a)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, Lesson.Status.PUBLISHED)
        self.assertIsNotNone(self.lesson.published_at)
        self.assertTrue(
            ProvenanceEvent.objects.filter(
                lesson=self.lesson,
                event_type=ProvenanceEvent.EventType.LESSON_PUBLISHED,
            ).exists()
        )

    def test_publish_is_idempotent(self):
        self.make_publishable()
        publish_lesson(lesson=self.lesson, teacher=self.teacher_a)
        publish_lesson(lesson=self.lesson, teacher=self.teacher_a)
        self.assertEqual(
            ProvenanceEvent.objects.filter(
                lesson=self.lesson,
                event_type=ProvenanceEvent.EventType.LESSON_PUBLISHED,
            ).count(),
            1,
        )

    def test_publish_via_http_returns_teacher_errors_when_invalid(self):
        bare = Lesson.objects.create(
            title="Bare", topic="X", grade_level="11", duration_minutes=30,
            created_by=self.teacher_a, learning_objectives=[],
        )
        r = self.client_a.post(reverse("lessons:publish", args=[bare.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Cannot publish yet")
        bare.refresh_from_db()
        self.assertEqual(bare.status, Lesson.Status.DRAFT)

    def test_publish_blocked_when_a_referenced_item_becomes_unusable(self):
        self.make_publishable()
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="assessment",
            title="Check", reference_id=self.published_assessment.pk,
        )
        self.published_assessment.status = Assessment.Status.ARCHIVED
        self.published_assessment.save(update_fields=["status"])
        reasons = validate_lesson_for_publish(self.lesson)
        self.assertTrue(any("published assessment" in x.lower() for x in reasons))

    def test_ai_finalization_does_not_publish(self):
        self.lesson.content = {"overview": "x"}
        self.lesson.save(update_fields=["content"])
        self.assertNotEqual(self.lesson.status, Lesson.Status.PUBLISHED)


# --- 6. Teacher preview safety ----------------------------------


class PreviewSafetyTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = self.client_for(self.teacher_a)
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a, raw_objectives=["Understand F=ma."]
        )
        self.add_lab_activity()
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="assessment",
            title="Check", reference_id=self.published_assessment.pk,
        )
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="tutor", title="Discuss",
        )

    def test_preview_renders_read_only_and_creates_nothing(self):
        before = (
            ExperimentAttempt.objects.count(),
            LearningEvidence.objects.count(),
            TutorMessage.objects.count(),
            StudentMisconception.objects.count(),
        )
        r = self.client_a.get(reverse("lessons:preview", args=[self.lesson.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Teacher Preview")
        after = (
            ExperimentAttempt.objects.count(),
            LearningEvidence.objects.count(),
            TutorMessage.objects.count(),
            StudentMisconception.objects.count(),
        )
        self.assertEqual(before, after)

    def test_preview_has_no_student_post_forms(self):
        r = self.client_a.get(reverse("lessons:preview", args=[self.lesson.slug]))
        self.assertNotContains(r, 'method="post"')
        self.assertNotContains(r, "csrfmiddlewaretoken")


# --- 7. AI integration + provenance preserved ------------------


class AiIntegrationTests(AuthoringTestCase):
    def test_ai_generation_request_reads_the_authored_fields(self):
        from apps.ai.requests import LessonGenerationRequest

        update_lesson_basics(
            lesson=self.lesson, teacher=self.teacher_a, title="Authored Title",
            topic="Dynamics", grade_level="12", duration_minutes=40,
        )
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a,
            raw_objectives=["Objective one", "Objective two"],
        )
        set_lesson_concepts(
            lesson=self.lesson, teacher=self.teacher_a, concept_ids=[self.concept_dyn.pk]
        )
        self.lesson.refresh_from_db()
        req = LessonGenerationRequest.from_lesson(self.lesson)
        self.assertEqual(req.title, "Authored Title")
        self.assertEqual(req.grade_level, "12")
        self.assertEqual(req.learning_objectives, ("Objective one", "Objective two"))

    def test_teacher_edit_after_ai_finalization_keeps_prior_provenance(self):
        self.lesson.ai_generated = True
        self.lesson.content = {"overview": "AI overview"}
        self.lesson.save(update_fields=["ai_generated", "content"])
        from apps.provenance.services import record_event

        record_event(
            self.lesson, ProvenanceEvent.EventType.LESSON_FINALIZED, source="teacher"
        )
        before = ProvenanceEvent.objects.filter(lesson=self.lesson).count()

        update_lesson_basics(
            lesson=self.lesson, teacher=self.teacher_a, title="Teacher tweak",
            topic="Dynamics", grade_level="11", duration_minutes=45,
        )
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.content, {"overview": "AI overview"})
        self.assertTrue(self.lesson.ai_generated)
        self.assertEqual(
            ProvenanceEvent.objects.filter(lesson=self.lesson).count(), before + 1
        )


# --- 8. Student rendering + backward compatibility -----------


class StudentRenderingTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        StudentProfile.objects.get_or_create(user=None, defaults={"display_name": "Guest"})

    def test_legacy_published_lesson_without_activities_still_works(self):
        legacy = Lesson.objects.create(
            title="Legacy Published", topic="Dynamics", grade_level="11",
            duration_minutes=30, status=Lesson.Status.PUBLISHED,
            learning_objectives=["x"],
        )
        r = Client().get(reverse("students:tutor", args=[legacy.slug]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "In this lesson")

    def test_draft_lesson_never_exposes_activities_to_students(self):
        self.add_lab_activity()
        self.assertEqual(build_student_lesson_activities(self.lesson), [])

    def test_published_activity_lesson_renders_ordered_launch_links(self):
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a, raw_objectives=["Understand."]
        )
        self.add_lab_activity(title="Run the Lab")
        create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="assessment",
            title="Check", reference_id=self.published_assessment.pk,
        )
        publish_lesson(lesson=self.lesson, teacher=self.teacher_a)
        self.lesson.refresh_from_db()

        steps = build_student_lesson_activities(self.lesson)
        self.assertEqual([s.position for s in steps], [1, 2])
        self.assertIn(
            reverse("physics_lab:detail", args=[self.sim.slug]), steps[0].launch_url
        )
        self.assertIn(
            reverse("students:assessment_detail", args=[self.published_assessment.pk]),
            steps[1].launch_url,
        )

        r = Client().get(reverse("students:tutor", args=[self.lesson.slug]))
        self.assertContains(r, "In this lesson")
        self.assertContains(r, "Run the Lab")


# --- 9. Practice activity reuses the existing evaluators -----


class PracticeActivityTests(AuthoringTestCase):
    def setUp(self):
        super().setUp()
        StudentProfile.objects.get_or_create(user=None, defaults={"display_name": "Guest"})
        set_learning_objectives(
            lesson=self.lesson, teacher=self.teacher_a, raw_objectives=["Understand."]
        )
        self.activity = create_activity(
            lesson=self.lesson, teacher=self.teacher_a, activity_type="practice",
            title="Quick check", reference_id=self.question.pk,
        )
        publish_lesson(lesson=self.lesson, teacher=self.teacher_a)
        self.url = reverse(
            "lessons:student_activity_practice", args=[self.lesson.slug, self.activity.pk]
        )

    def test_practice_question_page_hides_the_answer_key(self):
        r = Client().get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.question.prompt)
        self.assertNotContains(r, "correct_choice")

    def test_practice_answer_post_is_csrf_protected(self):
        enforcing = Client(enforce_csrf_checks=True)
        r = enforcing.post(self.url, {"answer": "2"})
        self.assertEqual(r.status_code, 403)

    def test_practice_get_records_no_evidence(self):
        before = LearningEvidence.objects.count()
        Client().get(self.url)
        self.assertEqual(LearningEvidence.objects.count(), before)

    def test_correct_answer_is_server_evaluated_and_records_standard_evidence(self):
        before = LearningEvidence.objects.count()
        r = Client().post(self.url, {"answer": "2"})  # index 2 == "Halves it" (correct)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Correct.")
        self.assertEqual(LearningEvidence.objects.count(), before + 1)
        ev = LearningEvidence.objects.latest("created_at")
        self.assertEqual(ev.kind, LearningEvidence.Kind.PRACTICE_ATTEMPTED)
        self.assertTrue(ev.context["is_correct"])
        self.assertEqual(ev.context["lesson_activity"], str(self.activity.pk))

    def test_client_cannot_forge_correctness(self):
        Client().post(self.url, {"answer": "0", "is_correct": "true", "score": "100"})
        ev = LearningEvidence.objects.latest("created_at")
        self.assertFalse(ev.context["is_correct"])

    def test_practice_activity_on_draft_lesson_is_404(self):
        self.lesson.status = Lesson.Status.DRAFT
        self.lesson.save(update_fields=["status"])
        self.assertEqual(Client().get(self.url).status_code, 404)

    def test_no_new_attempt_or_grading_model_was_created(self):
        Client().post(self.url, {"answer": "2"})
        self.assertEqual(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
            ).count(),
            1,
        )
        from apps.assessments.models import AssessmentAttempt

        self.assertEqual(AssessmentAttempt.objects.count(), 0)
        self.assertEqual(ExperimentAttempt.objects.count(), 0)
