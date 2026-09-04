"""Step 23 -- question bank: creation, validation, immutability, security."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.physics.models import PhysicsConcept

from . import services
from .models import Assessment, AssessmentQuestion, QuestionBankItem


class QuestionDataMixin:
    seq = 0

    def uid(self):
        QuestionDataMixin.seq += 1
        return QuestionDataMixin.seq

    def make_user(self, *, staff=False):
        return get_user_model().objects.create_user(
            f"qb{self.uid()}", password="pw", is_staff=staff
        )

    def make_concept(self, name=None):
        return PhysicsConcept.objects.create(
            name=name or f"Concept {self.uid()}", description="d", topic="Dynamics"
        )

    def numeric_question(self, *, teacher=None, concept=None, expected_value=10, tolerance=0.1, prompt=None):
        return services.create_question(
            teacher=teacher or self.make_user(staff=True),
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt=prompt or f"A 20 N force acts on a 2 kg cart {self.uid()}. Acceleration?",
            concept_id=concept.pk if concept else None,
            expected_value=expected_value,
            expected_unit="m/s^2",
            tolerance=tolerance,
        )

    def mc_question(self, *, teacher=None, concept=None, choices=None, correct_choice=1, prompt=None):
        return services.create_question(
            teacher=teacher or self.make_user(staff=True),
            question_type=QuestionBankItem.QuestionType.MULTIPLE_CHOICE,
            prompt=prompt or f"Doubling force does what to acceleration? {self.uid()}",
            concept_id=concept.pk if concept else None,
            choices=choices or ["halves it", "doubles it", "no change"],
            correct_choice=correct_choice,
        )


# --- 1-14: question bank ---------------------------------------------------


class QuestionCreationTests(QuestionDataMixin, TestCase):
    def test_numeric_question_can_be_created(self):
        q = self.numeric_question()
        self.assertEqual(q.question_type, QuestionBankItem.QuestionType.NUMERIC)
        self.assertEqual(q.expected_value, 10)

    def test_multiple_choice_question_can_be_created(self):
        q = self.mc_question()
        self.assertEqual(q.question_type, QuestionBankItem.QuestionType.MULTIPLE_CHOICE)
        self.assertEqual(q.correct_choice, 1)

    def test_key_is_stable_and_unique(self):
        q1 = self.numeric_question(prompt="Same prompt text")
        q2 = self.numeric_question(prompt="Same prompt text")
        self.assertNotEqual(q1.key, q2.key)
        self.assertTrue(QuestionBankItem.objects.filter(key=q1.key).exists())
        self.assertTrue(QuestionBankItem.objects.filter(key=q2.key).exists())

    def test_key_is_not_a_positional_index(self):
        q = self.numeric_question(prompt="A totally distinct prompt")
        self.assertNotIn(q.key, {"q1", "q2", "q3"})

    def test_question_concept_links_to_real_concept(self):
        concept = self.make_concept("Force")
        q = self.numeric_question(concept=concept)
        self.assertEqual(q.concept_id, concept.pk)
        self.assertIsInstance(q.concept, PhysicsConcept)

    def test_concept_is_optional(self):
        q = self.numeric_question(concept=None)
        self.assertIsNone(q.concept_id)


class QuestionValidationTests(QuestionDataMixin, TestCase):
    def test_invalid_numeric_expected_value_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
                expected_value="not-a-number",
            )

    def test_nan_expected_value_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
                expected_value=float("nan"),
            )

    def test_infinite_expected_value_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
                expected_value=float("inf"),
            )

    def test_negative_tolerance_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
                expected_value=10,
                tolerance=-1,
            )

    def test_zero_tolerance_is_accepted(self):
        q = services.create_question(
            teacher=self.make_user(staff=True),
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="p",
            expected_value=10,
            tolerance=0,
        )
        self.assertEqual(q.tolerance, 0)

    def test_missing_expected_value_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt="p",
            )

    def test_multiple_choice_requires_at_least_two_choices(self):
        with self.assertRaises(services.QuestionError):
            self.mc_question(choices=["only one"], correct_choice=0)

    def test_correct_choice_must_exist_among_choices(self):
        with self.assertRaises(services.QuestionError):
            self.mc_question(choices=["a", "b"], correct_choice=5)

    def test_duplicate_choices_are_rejected(self):
        with self.assertRaises(services.QuestionError):
            self.mc_question(choices=["same", "same"], correct_choice=0)

    def test_blank_choices_are_dropped_not_counted(self):
        with self.assertRaises(services.QuestionError):
            self.mc_question(choices=["only-one", "  ", ""], correct_choice=0)

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            self.numeric_question(prompt="   ")

    def test_unknown_question_type_is_rejected(self):
        with self.assertRaises(services.QuestionError):
            services.create_question(
                teacher=self.make_user(staff=True),
                question_type="essay",
                prompt="p",
                expected_value=1,
            )


class QuestionImmutabilityTests(QuestionDataMixin, TestCase):
    def _use(self, question, teacher):
        """Simulate a real student answer against ``question`` via a minimal
        published assessment, so ``services.is_used`` becomes True."""

        from apps.students.models import StudentProfile

        assessment = services.create_assessment(teacher=teacher, title=f"A{self.uid()}")
        aq = services.add_question_to_assessment(
            assessment_id=assessment.pk, teacher=teacher, question_id=question.pk
        )
        services.publish_assessment(assessment_id=assessment.pk, teacher=teacher)
        student = StudentProfile.objects.create(display_name="Alex")
        services.submit_assessment_answer(
            student=student,
            assessment_id=assessment.pk,
            assessment_question_id=aq.pk,
            submitted_answer="10" if question.question_type == "numeric" else "1",
        )
        return student

    def test_unused_question_answer_definition_is_editable(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher, expected_value=10)
        self.assertFalse(services.is_used(q))
        updated = services.update_question(question_id=q.pk, teacher=teacher, expected_value=99)
        self.assertEqual(updated.expected_value, 99)

    def test_used_question_answer_definition_is_locked(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher, expected_value=10)
        self._use(q, teacher)
        self.assertTrue(services.is_used(q))
        with self.assertRaises(services.QuestionError):
            services.update_question(question_id=q.pk, teacher=teacher, expected_value=999)
        q.refresh_from_db()
        self.assertEqual(q.expected_value, 10)

    def test_used_question_prompt_hint_explanation_remain_editable(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher, expected_value=10)
        self._use(q, teacher)
        updated = services.update_question(
            question_id=q.pk, teacher=teacher, prompt="A clearer prompt.", hint="A hint."
        )
        self.assertEqual(updated.prompt, "A clearer prompt.")
        self.assertEqual(updated.hint, "A hint.")

    def test_used_mc_question_choices_are_locked(self):
        teacher = self.make_user(staff=True)
        q = self.mc_question(teacher=teacher)
        self._use(q, teacher)
        with self.assertRaises(services.QuestionError):
            services.update_question(
                question_id=q.pk, teacher=teacher, choices=["x", "y"], correct_choice=0
            )

    def test_historical_answer_stays_interpretable_after_lock_attempt(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher, expected_value=10, tolerance=0.1)
        student = self._use(q, teacher)
        try:
            services.update_question(question_id=q.pk, teacher=teacher, expected_value=999)
        except services.QuestionError:
            pass
        from .models import AssessmentAnswer

        answer = AssessmentAnswer.objects.get(attempt__student=student)
        self.assertTrue(answer.is_correct)  # still correct against the original value=10


class QuestionActiveTests(QuestionDataMixin, TestCase):
    def test_deactivated_question_cannot_be_added_to_a_new_assessment(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher)
        services.set_question_active(question_id=q.pk, teacher=teacher, is_active=False)
        assessment = services.create_assessment(teacher=teacher, title="A")
        with self.assertRaises(services.AssessmentError):
            services.add_question_to_assessment(
                assessment_id=assessment.pk, teacher=teacher, question_id=q.pk
            )

    def test_deactivating_does_not_delete_the_question(self):
        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher)
        services.set_question_active(question_id=q.pk, teacher=teacher, is_active=False)
        self.assertTrue(QuestionBankItem.objects.filter(pk=q.pk).exists())


class QuestionSecurityTests(QuestionDataMixin, TestCase):
    def test_teacher_can_open_question_bank(self):
        teacher = self.make_user(staff=True)
        self.client.force_login(teacher)
        r = self.client.get(reverse("teachers:question_bank"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Question Bank")

    def test_anonymous_cannot_open_question_bank(self):
        r = self.client.get(reverse("teachers:question_bank"))
        self.assertEqual(r.status_code, 403)

    def test_student_cannot_open_question_bank(self):
        self.client.force_login(self.make_user(staff=False))
        r = self.client.get(reverse("teachers:question_bank"))
        self.assertEqual(r.status_code, 403)

    def test_student_cannot_create_a_question(self):
        self.client.force_login(self.make_user(staff=False))
        r = self.client.post(
            reverse("teachers:question_create") + "?type=numeric",
            {"prompt": "p", "expected_value": "1"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(QuestionBankItem.objects.filter(prompt="p").exists())

    def test_teacher_identity_is_server_derived_not_from_post(self):
        teacher = self.make_user(staff=True)
        other = self.make_user(staff=True)
        self.client.force_login(teacher)
        self.client.post(
            reverse("teachers:question_create") + "?type=numeric",
            {
                "prompt": "identity check",
                "expected_value": "1",
                "created_by": other.pk,  # smuggled -- must be ignored
            },
        )
        q = QuestionBankItem.objects.get(prompt="identity check")
        self.assertEqual(q.created_by_id, teacher.pk)

    def test_xss_in_prompt_is_escaped_on_question_bank_page(self):
        teacher = self.make_user(staff=True)
        self.numeric_question(teacher=teacher, prompt="<script>alert('x')</script>")
        self.client.force_login(teacher)
        body = self.client.get(reverse("teachers:question_bank")).content.decode()
        self.assertNotIn("<script>alert('x')</script>", body)
        self.assertIn("&lt;script&gt;", body)


class AdminImmutabilityTests(QuestionDataMixin, TestCase):
    """/admin/ must not be a back door around the answer-definition lock."""

    def test_used_question_answer_fields_are_readonly_in_admin(self):
        from apps.assessments.admin import QuestionBankItemAdmin
        from apps.assessments.models import QuestionBankItem as Model
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher, expected_value=10)
        from apps.students.models import StudentProfile

        a = services.create_assessment(teacher=teacher, title="Admin lock check")
        aq = services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        student = StudentProfile.objects.create(display_name="Alex")
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=aq.pk, submitted_answer="10"
        )

        model_admin = QuestionBankItemAdmin(Model, site)
        request = RequestFactory().get("/admin/")
        request.user = teacher
        readonly = model_admin.get_readonly_fields(request, obj=q)
        for locked in ("expected_value", "expected_unit", "tolerance", "question_type"):
            self.assertIn(locked, readonly)

    def test_unused_question_answer_fields_stay_editable_in_admin(self):
        from apps.assessments.admin import QuestionBankItemAdmin
        from apps.assessments.models import QuestionBankItem as Model
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        teacher = self.make_user(staff=True)
        q = self.numeric_question(teacher=teacher)
        model_admin = QuestionBankItemAdmin(Model, site)
        request = RequestFactory().get("/admin/")
        request.user = teacher
        readonly = model_admin.get_readonly_fields(request, obj=q)
        self.assertNotIn("expected_value", readonly)

    def test_assessment_status_is_readonly_in_admin(self):
        from apps.assessments.admin import AssessmentAdmin
        from apps.assessments.models import Assessment as Model

        self.assertIn("status", AssessmentAdmin.readonly_fields)
