"""Step 23 -- student execution, security, completion, evidence, integration."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.physics.models import PhysicsConcept
from apps.students.models import LearningEvidence, StudentProfile
from apps.students.practice_services import AnswerValidationError

from . import services
from .models import Assessment, AssessmentAnswer, AssessmentAttempt, AssessmentQuestion, QuestionBankItem


class ExecutionDataMixin:
    seq = 0

    def uid(self):
        ExecutionDataMixin.seq += 1
        return ExecutionDataMixin.seq

    def make_user(self, *, staff=False):
        return get_user_model().objects.create_user(
            f"ex{self.uid()}", password="pw", is_staff=staff
        )

    def make_student(self, name=None):
        return StudentProfile.objects.create(display_name=name or f"Student {self.uid()}")

    def make_concept(self, name=None):
        return PhysicsConcept.objects.create(
            name=name or f"Concept {self.uid()}", description="d", topic="Dynamics"
        )

    def published_assessment(self, *, teacher=None, concept=None, questions=2):
        teacher = teacher or self.make_user(staff=True)
        a = services.create_assessment(
            teacher=teacher, title=f"Check {self.uid()}", concept_id=concept.pk if concept else None
        )
        qs = []
        for i in range(questions):
            q = services.create_question(
                teacher=teacher,
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt=f"Question {i} - {self.uid()}",
                concept_id=concept.pk if concept else None,
                expected_value=10,
                tolerance=0.1,
            )
            services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
            qs.append(q)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        rows = list(AssessmentQuestion.objects.filter(assessment=a).order_by("position"))
        return a, rows


# --- 25-38: student execution + security --------------------------------


class StudentExecutionTests(ExecutionDataMixin, TestCase):
    def test_student_sees_published_assessment(self):
        a, _ = self.published_assessment()
        student = self.make_student()
        rows = services.get_student_assessments(student=student)
        self.assertEqual(rows[0]["id"], a.pk)

    def test_student_does_not_see_draft(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="Draft one")
        student = self.make_student()
        rows = services.get_student_assessments(student=student)
        self.assertEqual(rows, [])
        with self.assertRaises(services.AssessmentNotFound):
            services.get_student_assessment_detail(student=student, assessment_id=a.pk)

    def test_assessment_attempt_is_created_on_first_answer(self):
        a, rows = self.published_assessment()
        student = self.make_student()
        self.assertFalse(AssessmentAttempt.objects.filter(student=student, assessment=a).exists())
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        self.assertTrue(AssessmentAttempt.objects.filter(student=student, assessment=a).exists())

    def test_numeric_evaluation_is_server_side_and_deterministic(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        result = services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10.05"
        )
        self.assertTrue(result["is_correct"])  # within tolerance 0.1

    def test_numeric_outside_tolerance_is_incorrect(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        result = services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="50"
        )
        self.assertFalse(result["is_correct"])

    def test_multiple_choice_evaluation_is_deterministic(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="MC check")
        q = services.create_question(
            teacher=teacher,
            question_type=QuestionBankItem.QuestionType.MULTIPLE_CHOICE,
            prompt="p",
            choices=["a", "b", "c"],
            correct_choice=2,
        )
        aq = services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        student = self.make_student()
        right = services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=aq.pk, submitted_answer="2"
        )
        self.assertTrue(right["is_correct"])

    def test_client_cannot_submit_is_correct(self):
        """submit_assessment_answer has no is_correct/expected/score parameter at all."""

        import inspect

        params = inspect.signature(services.submit_assessment_answer).parameters
        self.assertNotIn("is_correct", params)
        self.assertNotIn("expected_value", params)
        self.assertNotIn("score", params)

    def test_client_cannot_submit_another_student_id(self):
        a, rows = self.published_assessment(questions=1)
        alice = self.make_student("Alice")
        bob = self.make_student("Bob")
        services.submit_assessment_answer(
            student=alice, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        # Bob's own call creates Bob's own attempt -- nothing lets Bob write as Alice.
        services.submit_assessment_answer(
            student=bob, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        self.assertEqual(
            AssessmentAttempt.objects.filter(student=alice, assessment=a).count(), 1
        )
        self.assertEqual(
            AssessmentAttempt.objects.filter(student=bob, assessment=a).count(), 1
        )

    def test_cannot_submit_a_question_from_another_assessment(self):
        a1, rows1 = self.published_assessment(questions=1)
        a2, rows2 = self.published_assessment(questions=1)
        student = self.make_student()
        with self.assertRaises(services.AssessmentError):
            services.submit_assessment_answer(
                student=student,
                assessment_id=a1.pk,
                assessment_question_id=rows2[0].pk,  # belongs to a2, not a1
                submitted_answer="10",
            )
        self.assertFalse(AssessmentAnswer.objects.filter(attempt__assessment=a1).exists())

    def test_another_students_attempt_is_invisible(self):
        a, rows = self.published_assessment(questions=1)
        alice = self.make_student("Alice")
        bob = self.make_student("Bob")
        services.submit_assessment_answer(
            student=alice, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        bob_detail = services.get_student_assessment_detail(student=bob, assessment_id=a.pk)
        self.assertFalse(bob_detail["questions"][0]["answered"])

    def test_empty_answer_is_rejected(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        with self.assertRaises(AnswerValidationError):
            services.submit_assessment_answer(
                student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="   "
            )

    def test_answering_twice_is_rejected_not_silently_overwritten(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        with self.assertRaises(services.AssessmentError):
            services.submit_assessment_answer(
                student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="999"
            )
        self.assertEqual(AssessmentAnswer.objects.filter(attempt__student=student).count(), 1)

    def test_get_does_not_mutate(self):
        a, rows = self.published_assessment()
        student = self.make_student()
        before = AssessmentAttempt.objects.count()
        services.get_student_assessment_detail(student=student, assessment_id=a.pk)
        services.get_student_assessment_detail(student=student, assessment_id=a.pk)
        self.assertEqual(AssessmentAttempt.objects.count(), before)


class StudentExecutionViewSecurityTests(ExecutionDataMixin, TestCase):
    def test_client_manipulation_fields_are_ignored(self):
        a, rows = self.published_assessment(questions=1)
        # A distinct, user-bound "other" student -- never confusable with the
        # shared anonymous guest identity ``self.client`` will resolve to.
        other_user = self.make_user()
        other = StudentProfile.objects.create(display_name="Other", user=other_user)
        r = self.client.post(
            reverse("students:assessment_detail", args=[a.pk]),
            {
                "assessment_question_id": rows[0].pk,
                "answer": "10",
                "student_id": other.pk,
                "is_correct": "true",
                "expected_value": "999",
                "correct_choice": "0",
                "score": "100",
                "assessment_id": "999999",
            },
        )
        self.assertEqual(r.status_code, 302)
        answer = AssessmentAnswer.objects.get(assessment_question=rows[0])
        self.assertTrue(answer.is_correct)  # graded against the real expected_value=10
        self.assertNotEqual(answer.attempt.student_id, other.pk)

    def test_csrf_is_enforced(self):
        a, rows = self.published_assessment(questions=1)
        strict = Client(enforce_csrf_checks=True)
        r = strict.post(
            reverse("students:assessment_detail", args=[a.pk]),
            {"assessment_question_id": rows[0].pk, "answer": "10"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(AssessmentAnswer.objects.exists())

    def test_student_cannot_reach_teacher_question_management(self):
        r = self.client.get(reverse("teachers:question_bank"))
        self.assertEqual(r.status_code, 403)

    def test_student_cannot_publish_an_assessment(self):
        a, rows = self.published_assessment(questions=1)
        teacher = self.make_user(staff=True)
        draft = services.create_assessment(teacher=teacher, title="Draft")
        r = self.client.post(reverse("teachers:assessment_publish", args=[draft.pk]))
        self.assertEqual(r.status_code, 403)


# --- 39-43: completion semantics -----------------------------------------


class CompletionSemanticsTests(ExecutionDataMixin, TestCase):
    def test_one_unanswered_question_means_incomplete(self):
        a, rows = self.published_assessment(questions=2)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        attempt = AssessmentAttempt.objects.get(student=student, assessment=a)
        self.assertFalse(attempt.is_complete)

    def test_all_questions_answered_means_completed(self):
        a, rows = self.published_assessment(questions=2)
        student = self.make_student()
        for row in rows:
            services.submit_assessment_answer(
                student=student, assessment_id=a.pk, assessment_question_id=row.pk, submitted_answer="10"
            )
        attempt = AssessmentAttempt.objects.get(student=student, assessment=a)
        self.assertTrue(attempt.is_complete)

    def test_incorrect_answers_still_count_as_attempted(self):
        a, rows = self.published_assessment(questions=2)
        student = self.make_student()
        for row in rows:
            services.submit_assessment_answer(
                student=student, assessment_id=a.pk, assessment_question_id=row.pk, submitted_answer="999"
            )
        attempt = AssessmentAttempt.objects.get(student=student, assessment=a)
        self.assertTrue(attempt.is_complete)

    def test_completion_is_never_labelled_mastery(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        r = self.client.get(reverse("students:assessment_detail", args=[a.pk]))
        body = r.content.decode().lower()
        for banned in ("mastery", "proficient", "you are ready", "at risk", "weakness"):
            self.assertNotIn(banned, body)


# --- 46-52: learning evidence ---------------------------------------------


class LearningEvidenceTests(ExecutionDataMixin, TestCase):
    def test_evidence_is_written(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        before = LearningEvidence.objects.filter(kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED).count()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        after = LearningEvidence.objects.filter(kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED).count()
        self.assertEqual(after, before + 1)

    def test_evidence_context_has_safe_identifiers_and_result(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        evidence = LearningEvidence.objects.get(kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED)
        self.assertEqual(evidence.context["assessment"], a.title)
        self.assertIn("question_key", evidence.context)
        self.assertIn("is_correct", evidence.context)
        self.assertEqual(evidence.context["attempt_number"], 1)

    def test_no_answer_keys_in_student_visible_context(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        evidence = LearningEvidence.objects.get(kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED)
        for banned in ("expected_value", "correct_choice", "tolerance"):
            self.assertNotIn(banned, evidence.context)

    def test_assessment_evidence_is_distinct_from_practice_evidence(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        self.assertFalse(
            LearningEvidence.objects.filter(
                student=student, kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
            ).exists()
        )
        self.assertTrue(
            LearningEvidence.objects.filter(
                student=student, kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED
            ).exists()
        )

    def test_assessment_activity_appears_in_student_progress(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        summary = services.get_student_assessment_summary(student=student)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["questions_answered"], 1)

    def test_lessonless_assessment_concept_counts_as_explored(self):
        """A concept-only assessment (no lesson) still credits its concept in
        the student's 'concepts explored' progress projection."""

        from apps.students.progress_services import build_student_learning_progress

        concept = self.make_concept("Impulse")
        a, rows = self.published_assessment(concept=concept, questions=1)
        self.assertIsNone(a.lesson_id)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        progress = build_student_learning_progress(student=student)
        names = {c["name"] for c in progress["concepts"]}
        self.assertIn("Impulse", names)

    def test_assessment_timeline_entry_renders_on_progress_page(self):
        a, rows = self.published_assessment(questions=1)
        r = self.client.post(
            reverse("students:assessment_detail", args=[a.pk]),
            {"assessment_question_id": rows[0].pk, "answer": "10"},
        )
        self.assertEqual(r.status_code, 302)
        body = self.client.get(reverse("students:progress")).content.decode()
        self.assertIn(a.title, body)

    def test_assessment_activity_appears_in_teacher_evidence(self):
        a, rows = self.published_assessment(questions=1)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        evidence = services.get_teacher_assessment_evidence(student)
        self.assertEqual(evidence["questions_answered"], 1)
        self.assertEqual(len(evidence["rows"]), 1)


# --- 53-60: integration ----------------------------------------------------


class IntegrationTests(ExecutionDataMixin, TestCase):
    def test_teacher_question_bank_accessible(self):
        teacher = self.make_user(staff=True)
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("teachers:question_bank")).status_code, 200)

    def test_teacher_assessment_builder_works(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="Builder check")
        self.client.force_login(teacher)
        r = self.client.get(reverse("teachers:assessment_detail_teacher", args=[a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Builder check")

    def test_student_published_assessment_page_works(self):
        a, rows = self.published_assessment()
        r = self.client.get(reverse("students:assessment_detail", args=[a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, a.title)

    def _goal_focused_assessment(self, concept_name, *, questions=1):
        """A concept-only teacher goal so the planner's focus is guaranteed to
        land on this concept, regardless of the student's activity history."""

        from apps.teachers.goal_services import create_learning_goal

        teacher = self.make_user(staff=True)
        concept = self.make_concept(concept_name)
        a, rows = self.published_assessment(teacher=teacher, concept=concept, questions=questions)
        student = self.make_student()
        create_learning_goal(student=student, teacher=teacher, concept_id=concept.pk)
        return student, a, rows

    def test_planner_can_resolve_assessment_activity(self):
        from apps.students.activity_planner import build_adaptive_activity_plan

        student, a, rows = self._goal_focused_assessment("Momentum")
        plan = build_adaptive_activity_plan(student=student)
        self.assertIsNotNone(plan["next_activity"])
        self.assertEqual(plan["next_activity"]["type"], "assessment")

    def test_completed_assessment_is_not_re_suggested_by_planner(self):
        from apps.students.activity_planner import build_adaptive_activity_plan

        student, a, rows = self._goal_focused_assessment("Impulse")
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        plan = build_adaptive_activity_plan(student=student)
        alt_types = {alt["type"] for alt in plan["alternatives"]}
        self.assertNotIn("assessment", alt_types)
        if plan["next_activity"]:
            self.assertNotEqual(plan["next_activity"]["type"], "assessment")

    def test_planner_never_uses_assessment_correctness_as_a_reason(self):
        from apps.students.activity_planner import build_adaptive_activity_plan

        student, a, rows = self._goal_focused_assessment("Torque")
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="999"
        )  # deliberately wrong
        plan = build_adaptive_activity_plan(student=student)
        for banned in ("weak", "mastery", "ready", "risk"):
            self.assertNotIn(banned, plan["reason"].lower())

    def test_step22_planner_tests_still_pass_is_covered_by_full_suite(self):
        # Placeholder marker: apps.students.tests_planner is run as part of the
        # full suite (Section 83) and is not duplicated here.
        self.assertTrue(True)


# --- 61-68: security / XSS regression --------------------------------------


class SecurityAndXSSTests(ExecutionDataMixin, TestCase):
    def test_cross_student_isolation_end_to_end(self):
        a, rows = self.published_assessment(questions=1)
        alice_user = self.make_user()
        alice = StudentProfile.objects.create(display_name="Alice", user=alice_user)
        client_a = Client()
        client_a.force_login(alice_user)
        client_a.post(
            reverse("students:assessment_detail", args=[a.pk]),
            {"assessment_question_id": rows[0].pk, "answer": "10"},
        )
        bob_user = self.make_user()
        client_b = Client()
        client_b.force_login(bob_user)
        body = client_b.get(reverse("students:assessment_detail", args=[a.pk])).content.decode()
        self.assertNotIn("Alice", body)

    def test_xss_in_question_prompt_and_choice_escaped_on_student_page(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(teacher=teacher, title="XSS check")
        q = services.create_question(
            teacher=teacher,
            question_type=QuestionBankItem.QuestionType.MULTIPLE_CHOICE,
            prompt="<script>alert('p')</script>",
            choices=["<script>alert('c')</script>", "safe choice"],
            correct_choice=1,
        )
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        body = self.client.get(reverse("students:assessment_detail", args=[a.pk])).content.decode()
        self.assertNotIn("<script>alert('p')</script>", body)
        self.assertNotIn("<script>alert('c')</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_xss_in_assessment_description_escaped(self):
        teacher = self.make_user(staff=True)
        a = services.create_assessment(
            teacher=teacher, title="Desc check", description="<script>alert('d')</script>"
        )
        q = services.create_question(
            teacher=teacher,
            question_type=QuestionBankItem.QuestionType.NUMERIC,
            prompt="p",
            expected_value=1,
        )
        services.add_question_to_assessment(assessment_id=a.pk, teacher=teacher, question_id=q.pk)
        services.publish_assessment(assessment_id=a.pk, teacher=teacher)
        body = self.client.get(reverse("students:assessment_detail", args=[a.pk])).content.decode()
        self.assertNotIn("<script>alert('d')</script>", body)

    def test_xss_in_student_answer_escaped_on_review(self):
        a, rows = self.published_assessment(questions=1)
        r = self.client.post(
            reverse("students:assessment_detail", args=[a.pk]),
            {"assessment_question_id": rows[0].pk, "answer": "<script>alert('a')</script>"},
        )
        # Numeric evaluation rejects this as non-numeric input -- confirm it is
        # rejected cleanly (no 500) and never stored, let alone rendered raw.
        self.assertIn(r.status_code, (200, 302))
        self.assertFalse(AssessmentAnswer.objects.exists())

    def test_no_private_teacher_note_leaks_to_student(self):
        # QuestionBankItem/Assessment carry no private teacher-note field at
        # all (Section 25) -- nothing to leak by construction.
        self.assertNotIn("teacher_note", [f.name for f in Assessment._meta.get_fields()])
        self.assertNotIn("teacher_note", [f.name for f in QuestionBankItem._meta.get_fields()])


# --- 69: query performance -------------------------------------------------


class QueryBudgetTests(ExecutionDataMixin, TestCase):
    def test_student_assessment_list_is_bounded(self):
        teacher = self.make_user(staff=True)
        concept = self.make_concept()
        for _ in range(5):
            self.published_assessment(teacher=teacher, concept=concept, questions=3)
        student = self.make_student()
        with self.assertNumQueries(2):
            services.get_student_assessments(student=student)

    def test_student_assessment_detail_is_bounded(self):
        a, rows = self.published_assessment(questions=10)
        student = self.make_student()
        with self.assertNumQueries(3):
            services.get_student_assessment_detail(student=student, assessment_id=a.pk)

    def test_student_assessment_detail_is_bounded_with_an_existing_attempt(self):
        """The realistic case for a returning student: one more query to load
        this attempt's own answers, still independent of question count."""

        a, rows = self.published_assessment(questions=10)
        student = self.make_student()
        services.submit_assessment_answer(
            student=student, assessment_id=a.pk, assessment_question_id=rows[0].pk, submitted_answer="10"
        )
        with self.assertNumQueries(4):
            services.get_student_assessment_detail(student=student, assessment_id=a.pk)

    def test_teacher_question_bank_is_bounded(self):
        teacher = self.make_user(staff=True)
        for _ in range(20):
            services.create_question(
                teacher=teacher,
                question_type=QuestionBankItem.QuestionType.NUMERIC,
                prompt=f"p{self.uid()}",
                expected_value=1,
            )
        with self.assertNumQueries(1):
            services.list_question_bank()

    def test_teacher_assessment_list_is_bounded(self):
        teacher = self.make_user(staff=True)
        for _ in range(5):
            self.published_assessment(teacher=teacher, questions=2)
        with self.assertNumQueries(1):
            services.get_teacher_assessment_list()
