"""Step 23 -- assessment builder: creation, ordering, publishing, visibility."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.physics.models import PhysicsConcept
from apps.students.models import StudentProfile

from . import services
from .models import Assessment, AssessmentQuestion, QuestionBankItem


class AssessmentDataMixin:
    seq = 0

    def uid(self):
        AssessmentDataMixin.seq += 1
        return AssessmentDataMixin.seq

    def make_user(self, *, staff=False):
        return get_user_model().objects.create_user(
            f"ab{self.uid()}", password="pw", is_staff=staff
        )

    def make_student(self):
        return StudentProfile.objects.create(display_name=f"Student {self.uid()}")

    def make_concept(self, name=None):
        return PhysicsConcept.objects.create(
            name=name or f"Concept {self.uid()}", description="d", topic="Dynamics"
        )

    def make_question(self, teacher, *, is_active=True):
        q = services.create_question(
            teacher=teacher,
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt=f"Prompt {self.uid()}",
            expected_value=10,
            tolerance=0.1,
        )
        if not is_active:
            services.set_question_active(question_id=q.pk, teacher=teacher, is_active=False)
        return q


# --- 15-24: assessment builder ----------------------------------------


class AssessmentCreationTests(AssessmentDataMixin, TestCase):
    def test_assessment_can_be_created(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="Newton's Second Law Check")
        self.assertEqual(a.status, Assessment.Status.DRAFT)
        self.assertTrue(a.slug)

    def test_assessment_requires_a_title(self):
        teacher = self.make_user(staff=True)
        with self.assertRaises(services.AssessmentError):
            services.create_assessment(teacher=teacher, title="   ")

    def test_question_ordering_is_deterministic(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q1 = self.make_question(teacher)
        q2 = self.make_question(teacher)
        q3 = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q1.pk)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q2.pk)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q3.pk)
        positions = list(
            AssessmentQuestion.objects.filter(assessment=a).order_by("position").values_list(
                "question_id", flat=True
            )
        )
        self.assertEqual(positions, [q1.pk, q2.pk, q3.pk])

    def test_question_cannot_be_added_twice(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        with self.assertRaises(services.AssessmentError):
            services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)

    def test_removing_a_question_only_works_while_draft(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        with self.assertRaises(services.AssessmentError):
            services.remove_question_from_assessment(
                assessment_id=a.pk, teacher=teacher, question_id=q.pk
            )

    def test_assessment_with_no_questions_cannot_be_published(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        with self.assertRaises(services.AssessmentError):
            services.publish_assessment(assessment_id=a.pk, teacher=teacher)

    def test_assessment_with_inactive_question_cannot_be_published(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.set_question_active(question_id=q.pk, teacher=teacher, is_active=False)
        with self.assertRaises(services.AssessmentError):
            services.publish_assessment(assessment_id=a.pk, teacher=teacher)

    def test_publishing_sets_status_and_timestamp(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        published = services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        self.assertEqual(published.status, Assessment.Status.PUBLISHED)
        self.assertIsNotNone(published.published_at)

    def test_only_a_draft_can_be_published(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        with self.assertRaises(services.AssessmentError):
            services.publish_assessment(assessment_id=a.pk, teacher=teacher)

    def test_concept_target_validates(self):
        teacher = self.make_user(staff=True)
        # An unknown concept id is rejected through the shared resolver, both
        # for a question and for an assessment.
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=teacher,
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
                concept_id=999999,
                expected_value=1,
            )
        with self.assertRaises(services.AssessmentError):
            services.create_assessment(teacher=teacher, title="A", concept_id=999999)


class AssessmentDraftVisibilityTests(AssessmentDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.make_user(staff=True)
        self.student = self.make_student()
        self.question = self.make_question(self.teacher)
        self.assessment = services.create_assessment(teacher=self.teacher, title="A")
        services.add_question_to_assessment(
            assessment_id=self.assessment.pk, teacher=self.teacher, question_id=self.question.pk
        )

    def test_draft_cannot_be_accessed_by_students(self):
        with self.assertRaises(services.AssessmentNotFound):
            services.get_student_assessment_detail(
                student=self.student, assessment_id=self.assessment.pk
            )

    def test_published_assessment_can_be_accessed(self):
        services.publish_assessment(assessment_id=self.assessment.pk, teacher=self.teacher)
        detail = services.get_student_assessment_detail(
            student=self.student, assessment_id=self.assessment.pk
        )
        self.assertEqual(detail["total_count"], 1)

    def test_archived_assessment_is_not_offered_to_students(self):
        services.publish_assessment(assessment_id=self.assessment.pk, teacher=self.teacher)
        services.archive_assessment(assessment_id=self.assessment.pk, teacher=self.teacher)
        with self.assertRaises(services.AssessmentNotFound):
            services.get_student_assessment_detail(
                student=self.student, assessment_id=self.assessment.pk
            )
        rows = services.get_student_assessments(student=self.student)
        self.assertEqual(rows, [])

    def test_draft_is_not_in_the_student_list(self):
        rows = services.get_student_assessments(student=self.student)
        self.assertEqual(rows, [])

    def test_published_appears_in_student_list(self):
        services.publish_assessment(assessment_id=self.assessment.pk, teacher=self.teacher)
        rows = services.get_student_assessments(student=self.student)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "not_started")


class AssessmentBuilderSecurityTests(AssessmentDataMixin, TestCase):
    def test_non_staff_cannot_open_assessment_builder(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        self.client.force_login(self.make_user(staff=False))
        r = self.client.get(reverse("teachers:assessment_detail_teacher", args=[a.pk]))
        self.assertEqual(r.status_code, 403)

    def test_non_staff_cannot_publish(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="A")
        q = self.make_question(teacher)
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        self.client.force_login(self.make_user(staff=False))
        r = self.client.post(reverse("teachers:assessment_publish", args=[a.pk]))
        self.assertEqual(r.status_code, 403)
        a.refresh_from_db()
        self.assertEqual(a.status, Assessment.Status.DRAFT)

    def test_teacher_can_build_and_publish_through_the_views(self):
        teacher = self.make_user(staff=True)
        self.client.force_login(teacher)
        r = self.client.post(reverse("teachers:assessment_create"), {"title": "Force Fundamentals"})
        self.assertEqual(r.status_code, 302)
        a = Assessment.objects.get(title="Force Fundamentals")
        q = self.make_question(teacher)
        self.client.post(
            reverse("teachers:assessment_add_question", args=[a.pk]), {"question_id": q.pk}
        )
        self.assertTrue(AssessmentQuestion.objects.filter(assessment=a, question=q).exists())
        self.client.post(reverse("teachers:assessment_publish", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, Assessment.Status.PUBLISHED)
