"""Step 18 -- deterministic Physics practice evidence engine.

The evaluation tests use no AI provider at all. Only the misconception-routing
tests touch the (fake) provider, and even then a rule is what fires.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsMisconception

from .models import (
    LearningEvidence,
    PracticeAttempt,
    StudentMisconception,
    StudentProfile,
)
from .practice_services import (
    AnswerValidationError,
    PracticeError,
    build_practice_page,
    evaluate_choice_answer,
    evaluate_numeric_answer,
    get_practice_questions,
    record_practice_attempt,
)

MISCONCEPTION_TEXT = (
    "Force and acceleration are the same thing, so doubling the force just "
    "doubled the acceleration."
)
NEUTRAL_TEXT = (
    "Acceleration depends on mass because a heavier cart needs more net force "
    "for the same change in motion."
)


class PracticeDataMixin:
    user_seq = 0

    def make_user(self, *, staff=False):
        PracticeDataMixin.user_seq += 1
        return get_user_model().objects.create_user(
            f"user{PracticeDataMixin.user_seq}", password="pw", is_staff=staff
        )

    def structured_problems(self):
        return [
            {
                "key": "nsl-1",
                "type": "numeric",
                "prompt": "A 20 N net force acts on a 2 kg cart. What is its acceleration?",
                "answer": 10,
                "unit": "m/s^2",
                "tolerance": 0.1,
                "concept": "Newton's Second Law",
                "hint": "Start from a = F / m.",
            },
            {
                "key": "nsl-2",
                "type": "multiple_choice",
                "prompt": "Doubling the net force on a fixed mass will do what to the acceleration?",
                "choices": [
                    "halve the acceleration",
                    "double the acceleration",
                    "leave the acceleration unchanged",
                ],
                "answer": 1,
                "concept": "Newton's Second Law",
            },
            "In your own words, explain why acceleration depends on mass.",
        ]

    def seed(self, problems=None):
        self.concept = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="F = ma.",
            topic="Dynamics",
        )
        self.lesson = Lesson.objects.create(
            title="Forces and Motion",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass and acceleration."],
            problems=self.structured_problems() if problems is None else problems,
        )
        self.lesson.physics_concepts.add(self.concept)
        self.student = StudentProfile.objects.create(display_name="Alex")

    def attempt(self, key, answer, **kw):
        return record_practice_attempt(
            student=kw.pop("student", self.student),
            lesson=kw.pop("lesson", self.lesson),
            question_key=key,
            submitted_answer=answer,
            **kw,
        )


# --- model / persistence (44.1-6) ----------------------------------------


class PracticeModelTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_attempt_is_created_and_linked(self):
        row = self.attempt("nsl-1", "10")
        self.assertIsInstance(row, PracticeAttempt)
        self.assertEqual(row.student, self.student)
        self.assertEqual(row.lesson, self.lesson)
        self.assertIn(row, self.student.practice_attempts.all())

    def test_attempt_records_the_key_type_answer_and_verdict(self):
        row = self.attempt("nsl-1", "10")
        self.assertEqual(row.question_key, "nsl-1")
        self.assertEqual(row.question_type, PracticeAttempt.QuestionType.NUMERIC)
        self.assertEqual(row.answer_text, "10")
        self.assertTrue(row.is_correct)
        self.assertEqual(row.attempt_number, 1)

    def test_retry_creates_a_new_row_and_keeps_history(self):
        first = self.attempt("nsl-1", "7")
        second = self.attempt("nsl-1", "10")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.attempt_number, 1)
        self.assertEqual(second.attempt_number, 2)
        first.refresh_from_db()
        self.assertFalse(first.is_correct)  # earlier attempt is never overwritten
        self.assertEqual(
            list(
                PracticeAttempt.objects.filter(question_key="nsl-1")
                .order_by("attempt_number")
                .values_list("is_correct", flat=True)
            ),
            [False, True],
        )

    def test_attempt_number_is_per_question(self):
        self.attempt("nsl-1", "1")
        row = self.attempt("nsl-2", "0")
        self.assertEqual(row.attempt_number, 1)


# --- numeric evaluation (44.7-14) --------------------------------------


class NumericEvaluationTests(TestCase):
    def test_exact_match_is_correct(self):
        self.assertTrue(evaluate_numeric_answer("10", 10, 0.1).is_correct)

    def test_within_tolerance_is_correct(self):
        self.assertTrue(evaluate_numeric_answer("10.05", 10, 0.1).is_correct)

    def test_outside_tolerance_is_incorrect(self):
        self.assertFalse(evaluate_numeric_answer("7", 10, 0.1).is_correct)

    def test_explicit_tolerance_is_respected(self):
        self.assertTrue(evaluate_numeric_answer("12", 10, 5).is_correct)
        self.assertFalse(evaluate_numeric_answer("12", 10, 1).is_correct)

    def test_default_tolerance_used_when_none_given(self):
        self.assertTrue(evaluate_numeric_answer("10.0", 10, None).is_correct)
        self.assertFalse(evaluate_numeric_answer("10.5", 10, None).is_correct)

    def test_string_equality_is_not_used(self):
        # "10.0" != "10" as strings, but 10.0 == 10 as numbers.
        self.assertTrue(evaluate_numeric_answer("10.0", 10, 0.001).is_correct)
        self.assertTrue(evaluate_numeric_answer("  10 ", 10, 0.001).is_correct)

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(AnswerValidationError):
            evaluate_numeric_answer("ten", 10, 0.1)

    def test_nan_and_infinity_are_rejected(self):
        for bad in ("nan", "inf", "-inf", "Infinity"):
            with self.assertRaises(AnswerValidationError):
                evaluate_numeric_answer(bad, 10, 0.1)

    def test_empty_and_whitespace_are_rejected(self):
        for bad in ("", "   ", "\t"):
            with self.assertRaises(AnswerValidationError):
                evaluate_numeric_answer(bad, 10, 0.1)

    def test_oversized_input_is_rejected(self):
        with self.assertRaises(AnswerValidationError):
            evaluate_numeric_answer("9" * 500, 10, 0.1)


# --- multiple choice (44.15-18) --------------------------------------


class ChoiceEvaluationTests(TestCase):
    CHOICES = ["halve it", "double it", "no change"]

    def test_correct_index_is_correct(self):
        self.assertTrue(evaluate_choice_answer("1", self.CHOICES, 1).is_correct)

    def test_wrong_index_is_incorrect(self):
        self.assertFalse(evaluate_choice_answer("0", self.CHOICES, 1).is_correct)

    def test_correct_answer_may_be_given_as_the_option_text(self):
        result = evaluate_choice_answer("1", self.CHOICES, "double it")
        self.assertTrue(result.is_correct)
        self.assertEqual(result.expected_index, 1)

    def test_submitting_the_option_text_works(self):
        self.assertTrue(evaluate_choice_answer("double it", self.CHOICES, 1).is_correct)

    def test_out_of_range_choice_is_rejected(self):
        with self.assertRaises(AnswerValidationError):
            evaluate_choice_answer("9", self.CHOICES, 1)
        with self.assertRaises(AnswerValidationError):
            evaluate_choice_answer("banana", self.CHOICES, 1)

    def test_malformed_choice_set_is_a_practice_error(self):
        with self.assertRaises(PracticeError):
            evaluate_choice_answer("0", ["only one"], 0)


# --- question resolution (44.19-22) --------------------------------


class QuestionResolutionTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_structured_dicts_are_parsed(self):
        questions = get_practice_questions(self.lesson)
        self.assertEqual([q.key for q in questions], ["nsl-1", "nsl-2", "q3"])
        self.assertEqual(questions[0].type, "numeric")
        self.assertEqual(questions[0].unit, "m/s^2")
        self.assertEqual(questions[1].type, "multiple_choice")
        self.assertEqual(len(questions[1].choices), 3)
        self.assertEqual(questions[2].type, "free_text")
        self.assertEqual(questions[0].number, 1)
        self.assertEqual(questions[0].total, 3)

    def test_plain_string_problems_still_work(self):
        lesson = Lesson.objects.create(
            title="Legacy", topic="Dynamics", grade_level="11",
            problems=["A cart speeds up from 2 m/s to 8 m/s in 3 s. Find a."],
        )
        questions = get_practice_questions(lesson)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].type, "free_text")
        row = record_practice_attempt(
            student=self.student, lesson=lesson,
            question_key=questions[0].key, submitted_answer="a = 2 m/s^2",
        )
        self.assertIsNone(row.is_correct)

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(PracticeError):
            self.attempt("does-not-exist", "10")

    def test_key_from_another_lesson_is_rejected(self):
        other = Lesson.objects.create(
            title="Other", topic="Waves", grade_level="11",
            problems=[{"key": "wave-1", "type": "numeric", "prompt": "f?", "answer": 5}],
        )
        with self.assertRaises(PracticeError):
            record_practice_attempt(
                student=self.student, lesson=self.lesson,
                question_key="wave-1", submitted_answer="5",
            )
        # ...and it is fine against its own lesson.
        row = record_practice_attempt(
            student=self.student, lesson=other,
            question_key="wave-1", submitted_answer="5",
        )
        self.assertTrue(row.is_correct)


# --- learning evidence (44.23-26) --------------------------------


class PracticeEvidenceTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_evidence_row_is_created_and_linked(self):
        row = self.attempt("nsl-1", "10")
        evidence = LearningEvidence.objects.get(
            kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
        )
        self.assertEqual(row.evidence, evidence)
        self.assertEqual(evidence.student, self.student)
        self.assertEqual(evidence.lesson, self.lesson)

    def test_context_carries_structured_practice_detail(self):
        self.attempt("nsl-1", "10")
        ctx = LearningEvidence.objects.get(
            kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
        ).context
        self.assertEqual(ctx["practice"], True)
        self.assertEqual(ctx["question_key"], "nsl-1")
        self.assertEqual(ctx["concept"], "Newton's Second Law")
        self.assertEqual(ctx["is_correct"], True)
        self.assertEqual(ctx["attempt_number"], 1)

    def test_context_has_no_answer_key_or_secret(self):
        self.attempt("nsl-1", "7")
        ctx = LearningEvidence.objects.filter(
            kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
        ).latest("id").context
        for banned in ("answer", "expected", "expected_answer", "tolerance", "expected_display"):
            self.assertNotIn(banned, ctx)

    def test_free_text_evidence_has_no_is_correct(self):
        self.attempt("q3", "because mass resists changes in motion")
        ctx = LearningEvidence.objects.latest("id").context
        self.assertNotIn("is_correct", ctx)


# --- student UI (44.27-34) ------------------------------------


class PracticePageTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.url = reverse("students:practice", args=[self.lesson.slug])

    def test_page_loads_with_heading_and_lesson_name(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Physics Practice")
        self.assertContains(response, "Forces and Motion")
        self.assertContains(response, "Question 1 of 3")

    def test_numeric_question_shows_its_unit(self):
        response = self.client.get(self.url)
        self.assertContains(response, "m/s^2")
        self.assertContains(response, "<h1>", html=False)
        self.assertContains(response, 'aria-live="polite"')

    def test_correct_answer_is_reported(self):
        response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "10"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Correct.")
        self.assertEqual(PracticeAttempt.objects.get().is_correct, True)

    def test_wrong_answer_is_not_falsely_correct_and_allows_retry(self):
        response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "7"})
        self.assertContains(response, "Not quite.")
        self.assertNotContains(response, "Correct.")
        self.assertEqual(PracticeAttempt.objects.get().is_correct, False)
        # The form is still there to try again.
        self.assertContains(response, "Submit Answer")

    def test_first_wrong_answer_does_not_reveal_the_expected_value(self):
        response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "7"})
        self.assertNotContains(response, "Expected answer:")

    def test_third_wrong_answer_reveals_the_expected_value(self):
        for _ in range(3):
            response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "7"})
        self.assertContains(response, "Expected answer:")
        self.assertContains(response, "10 m/s^2")

    def test_question_text_and_answer_are_escaped(self):
        lesson = Lesson.objects.create(
            title="XSS", topic="Dynamics", grade_level="11",
            problems=[{"key": "x1", "type": "free_text", "prompt": "<script>alert(1)</script>"}],
        )
        url = reverse("students:practice", args=[lesson.slug])
        response = self.client.post(url, {"question_key": "x1", "answer": "<b>hi</b>"})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<b>hi</b>")
        self.assertContains(response, "&lt;script&gt;")

    def test_get_does_not_record_an_attempt(self):
        self.client.get(self.url)
        self.assertEqual(PracticeAttempt.objects.count(), 0)

    def test_unknown_lesson_slug_is_404(self):
        response = self.client.get(reverse("students:practice", args=["no-such-lesson"]))
        self.assertEqual(response.status_code, 404)

    def test_completion_summary_is_activity_not_a_grade(self):
        self.client.post(self.url, {"question_key": "nsl-1", "answer": "10"})
        self.client.post(self.url, {"question_key": "nsl-2", "answer": "1"})
        response = self.client.post(self.url, {"question_key": "q3", "answer": "mass resists motion changes"})
        self.assertContains(response, "Practice complete")
        self.assertNotContains(response, "mastery")
        self.assertNotContains(response, "score")

    def test_malformed_key_gives_a_clean_message_not_a_500(self):
        response = self.client.post(self.url, {"question_key": "!!!", "answer": "10"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be found")
        self.assertEqual(PracticeAttempt.objects.count(), 0)

    def test_blank_answer_gives_a_clean_message(self):
        response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter an answer")
        self.assertEqual(PracticeAttempt.objects.count(), 0)


# --- misconception routing (44.35-37) -----------------------


@override_settings(AI_PROVIDER="fake")
class PracticeMisconceptionTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.catalog = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION",
            title="Force and acceleration are the same quantity",
            description="A learner may treat force and acceleration as interchangeable.",
            physics_concept=self.concept,
            intervention_guidance="Work F = ma with numbers.",
        )

    def test_explanatory_wrong_text_reaches_the_existing_engine(self):
        self.attempt("q3", MISCONCEPTION_TEXT)
        observation = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(observation.misconception.code, "FORCE_VS_ACCELERATION")

    def test_bare_wrong_number_creates_no_candidate(self):
        self.attempt("nsl-1", "7")
        self.assertFalse(
            StudentMisconception.objects.filter(student=self.student).exists()
        )

    def test_candidate_stays_a_candidate(self):
        self.attempt("q3", MISCONCEPTION_TEXT)
        observation = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(observation.status, StudentMisconception.Status.CANDIDATE)

    def test_engine_failure_does_not_destroy_the_attempt(self):
        with patch(
            "apps.students.practice_services.assess_student_misconceptions",
            side_effect=RuntimeError("provider down"),
        ):
            row = self.attempt("q3", MISCONCEPTION_TEXT)
        self.assertEqual(PracticeAttempt.objects.count(), 1)
        self.assertEqual(row.evidence.kind, LearningEvidence.Kind.PRACTICE_ATTEMPTED)


# --- teacher evidence (44.38-41) ---------------------------


class TeacherPracticeEvidenceTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.teacher = self.make_user(staff=True)
        self.client.force_login(self.teacher)
        self.detail_url = reverse("teachers:student_detail", args=[self.student.pk])

    def test_detail_page_shows_practice_section(self):
        self.attempt("nsl-1", "7")
        self.attempt("nsl-1", "10")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Practice evidence")
        self.assertContains(response, "acceleration")  # the question prompt
        self.assertContains(response, "Incorrect")
        self.assertContains(response, "Correct")
        self.assertContains(response, "attempt 2 of 2")
        self.assertContains(response, "Newton&#x27;s Second Law")

    def test_counts_are_labelled_as_attempts_not_scores(self):
        self.attempt("nsl-1", "10")
        response = self.client.get(self.detail_url)
        self.assertContains(response, "correct attempt")
        self.assertContains(response, "incorrect attempt")
        self.assertNotContains(response, "mastery")
        self.assertNotContains(response, "performance rating")

    def test_no_internal_security_fields_are_shown(self):
        self.attempt("nsl-1", "7")
        response = self.client.get(self.detail_url)
        self.assertNotContains(response, "student_id")
        self.assertNotContains(response, "lesson_owner")


# --- student progress (44.42-44) --------------------------


class StudentProgressPracticeTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.user = self.make_user()
        self.student.user = self.user
        self.student.save(update_fields=["user"])
        self.client.force_login(self.user)

    def test_progress_shows_practice_activity(self):
        self.attempt("nsl-1", "7")
        response = self.client.get(reverse("students:progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Practice attempts")
        self.assertContains(response, "Incorrect")

    def test_progress_has_no_mastery_or_score_language(self):
        self.attempt("nsl-1", "10")
        response = self.client.get(reverse("students:progress"))
        self.assertNotContains(response, "mastery")
        self.assertNotContains(response, "weak")
        self.assertNotContains(response, "grade")


# --- security (44.45-52) ---------------------------------


class PracticeSecurityTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.url = reverse("students:practice", args=[self.lesson.slug])

    def test_smuggled_authority_fields_are_ignored(self):
        other_student = StudentProfile.objects.create(
            display_name="Other", user=self.make_user()
        )
        other_concept = PhysicsConcept.objects.create(
            name="Momentum", description="p = mv", topic="Mechanics"
        )
        response = self.client.post(
            self.url,
            {
                "question_key": "nsl-1",
                "answer": "7",
                "expected_answer": "7",
                "correct_answer": "7",
                "is_correct": "true",
                "tolerance": "1000",
                "concept": "Momentum",
                "concept_id": str(other_concept.pk),
                "student_id": str(other_student.pk),
                "teacher_id": "1",
                "lesson_owner": "someone",
            },
        )
        self.assertEqual(response.status_code, 200)
        row = PracticeAttempt.objects.get()
        self.assertFalse(row.is_correct)  # server evaluated 7 vs 10 -> wrong
        self.assertEqual(row.student, self.student)  # not the smuggled student
        self.assertEqual(row.concept, self.concept)  # resolved from the lesson

    def test_student_identity_comes_from_the_session_not_the_query(self):
        alice_user = self.make_user()
        alice = StudentProfile.objects.create(display_name="Alice", user=alice_user)
        bob = StudentProfile.objects.create(display_name="Bob", user=self.make_user())
        self.client.force_login(alice_user)

        self.client.post(
            self.url,
            {"question_key": "nsl-1", "answer": "10", "student_id": str(bob.pk)},
        )
        self.assertTrue(PracticeAttempt.objects.filter(student=alice).exists())
        self.assertFalse(PracticeAttempt.objects.filter(student=bob).exists())

    def test_cannot_attempt_a_question_outside_the_displayed_lesson(self):
        other = Lesson.objects.create(
            title="Waves", topic="Waves", grade_level="11",
            problems=[{"key": "w1", "type": "numeric", "prompt": "f?", "answer": 3}],
        )
        response = self.client.post(self.url, {"question_key": "w1", "answer": "3"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be found")
        self.assertFalse(PracticeAttempt.objects.filter(lesson=other).exists())

    def test_oversized_answer_is_handled(self):
        response = self.client.post(
            self.url, {"question_key": "nsl-1", "answer": "9" * 5000}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too long")
        self.assertEqual(PracticeAttempt.objects.count(), 0)

    def test_no_safe_filter_leaks_raw_student_html(self):
        self.client.post(
            self.url, {"question_key": "q3", "answer": "<img src=x onerror=alert(1)>"}
        )
        response = self.client.get(self.url + "?q=q3")
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")


# --- HTTP + regression (44.53-62) ------------------------


class PracticeHttpAndRegressionTests(PracticeDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.url = reverse("students:practice", args=[self.lesson.slug])

    def test_post_creates_attempt_and_evidence_together(self):
        self.client.post(self.url, {"question_key": "nsl-1", "answer": "10"})
        self.assertEqual(PracticeAttempt.objects.count(), 1)
        self.assertEqual(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
            ).count(),
            1,
        )

    def test_practice_is_reachable_from_the_lesson_page(self):
        response = self.client.get(reverse("students:tutor", args=[self.lesson.slug]))
        self.assertContains(response, reverse("students:practice", args=[self.lesson.slug]))
        self.assertContains(response, "Practice this lesson")

    def test_existing_tutor_practice_flow_is_unchanged(self):
        response = self.client.get(reverse("students:tutor", args=[self.lesson.slug]))
        self.assertContains(response, "Try a problem")
        with patch("apps.students.views.run_tutor_turn") as mock_turn:
            posted = self.client.post(
                reverse("students:tutor", args=[self.lesson.slug]),
                {"action": "practice", "problem_index": "0", "attempt": "a = 10 m/s^2"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(mock_turn.call_count, 1)

    def test_no_recommend_practice_action_type_was_added(self):
        from apps.teachers.models import TeacherIntervention

        self.assertNotIn("recommend_practice", TeacherIntervention.ActionType.values)

    def test_discuss_with_tutor_link_after_a_wrong_answer(self):
        response = self.client.post(self.url, {"question_key": "nsl-1", "answer": "7"})
        self.assertContains(response, "Discuss this question with Tutor")
        self.assertContains(response, "prefill=")


# --- performance (44.45 query budget) --------------------


class PracticeQueryBudgetTests(PracticeDataMixin, TestCase):
    def test_build_practice_page_is_bounded(self):
        self.seed()
        for value in ("7", "8", "9", "10"):
            record_practice_attempt(
                student=self.student, lesson=self.lesson,
                question_key="nsl-1", submitted_answer=value,
            )
        # questions come from lesson.problems (already in memory); the page adds
        # one query for this student's attempts on this lesson.
        with self.assertNumQueries(1):
            build_practice_page(lesson=self.lesson, student=self.student)
