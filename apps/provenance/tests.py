from django.test import TestCase

from apps.ai.providers import FakeAIProvider
from apps.ai.requests import LessonGenerationRequest, LessonReviewRequest
from apps.ai.services import generate_lesson_draft, review_lesson_draft
from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept

from .models import PersistedReviewIssue
from .services import (
    finalize_lesson_from_review,
    persist_generated_lesson_draft,
    persist_lesson_draft_review,
    record_review_issue_decision,
)


class TeacherReviewWorkflowTests(TestCase):
    def setUp(self):
        self.concept = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
            equations=["F_net = ma"],
            si_units=["newton (N)"],
        )
        self.lesson = Lesson.objects.create(
            title="Understanding Force",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Describe how net force affects acceleration."],
            common_misconceptions=["Force keeps an object moving."],
            content={"teacher_note": "Keep this content unchanged."},
            status=Lesson.Status.REVIEW,
        )
        self.lesson.physics_concepts.add(self.concept)

    def create_draft(self):
        result = generate_lesson_draft(
            LessonGenerationRequest.from_lesson(self.lesson),
            provider=FakeAIProvider(),
        )
        return persist_generated_lesson_draft(self.lesson, result)

    def create_review(self, draft):
        result = review_lesson_draft(
            LessonReviewRequest.from_lesson(self.lesson, draft.as_lesson_draft()),
            provider=FakeAIProvider(),
        )
        return persist_lesson_draft_review(draft, result)

    def test_generated_draft_persists_original_content_and_provenance(self):
        draft = self.create_draft()

        self.assertEqual(draft.provider_name, "fake")
        self.assertEqual(draft.model, "fake-lesson-draft")
        self.assertEqual(draft.prompt_version, "lesson-generation-v1")
        self.assertEqual(draft.as_lesson_draft().title, "Introduction to Newton's Second Law")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.content, {"teacher_note": "Keep this content unchanged."})

    def test_review_persists_pending_issue_with_complete_ai_finding(self):
        review = self.create_review(self.create_draft())
        issue = review.issues.get()

        self.assertEqual(issue.status, PersistedReviewIssue.Status.PENDING)
        self.assertEqual(issue.category, "misconception")
        self.assertEqual(issue.severity, "warning")
        self.assertEqual(issue.confidence, "high")
        self.assertTrue(issue.explanation)
        self.assertTrue(issue.affected_section)
        self.assertTrue(issue.suggested_revision)

    def test_accept_decision_preserves_the_ai_recommendation(self):
        issue = self.create_review(self.create_draft()).issues.get()
        original_suggestion = issue.suggested_revision

        record_review_issue_decision(issue, "accepted", teacher_note="Use this.")

        issue.refresh_from_db()
        self.assertEqual(issue.status, PersistedReviewIssue.Status.ACCEPTED)
        self.assertEqual(issue.suggested_revision, original_suggestion)
        self.assertEqual(issue.decision_record.decision, "accepted")
        self.assertEqual(issue.decision_record.teacher_note, "Use this.")

    def test_reject_decision_is_persisted_with_optional_teacher_reason(self):
        issue = self.create_review(self.create_draft()).issues.get()

        record_review_issue_decision(issue, "rejected", teacher_note="Not suitable for this class.")

        issue.refresh_from_db()
        self.assertEqual(issue.status, PersistedReviewIssue.Status.REJECTED)
        self.assertEqual(issue.decision_record.teacher_note, "Not suitable for this class.")

    def test_edit_decision_preserves_original_suggestion_and_teacher_revision(self):
        issue = self.create_review(self.create_draft()).issues.get()
        original_suggestion = issue.suggested_revision

        record_review_issue_decision(
            issue,
            "edited",
            edited_text="Compare balanced and unbalanced forces before the activity.",
        )

        issue.refresh_from_db()
        self.assertEqual(issue.status, PersistedReviewIssue.Status.EDITED)
        self.assertEqual(issue.suggested_revision, original_suggestion)
        self.assertEqual(
            issue.decision_record.edited_text,
            "Compare balanced and unbalanced forces before the activity.",
        )

    def test_finalization_preserves_draft_excludes_rejected_suggestions_and_keeps_status(self):
        draft = self.create_draft()
        review = self.create_review(draft)
        issue = review.issues.get()
        record_review_issue_decision(issue, "rejected", teacher_note="Keep the original activity.")

        finalized_lesson = finalize_lesson_from_review(review)

        finalized_lesson.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(finalized_lesson.status, Lesson.Status.REVIEW)
        self.assertTrue(finalized_lesson.ai_generated)
        self.assertIn("overview", finalized_lesson.content)
        self.assertNotIn("teacher_approved_revisions", finalized_lesson.content)
        self.assertEqual(draft.as_lesson_draft().title, "Introduction to Newton's Second Law")
        self.assertIsNotNone(draft.finalized_at)

    def test_finalization_records_teacher_approved_edited_content(self):
        draft = self.create_draft()
        review = self.create_review(draft)
        issue = review.issues.get()
        revision = "Contrast balanced and unbalanced force cases before prediction."
        record_review_issue_decision(issue, "edited", edited_text=revision)

        finalized_lesson = finalize_lesson_from_review(review)

        approved_revisions = finalized_lesson.content["teacher_approved_revisions"]
        self.assertEqual(approved_revisions[0]["decision"], "edited")
        self.assertEqual(approved_revisions[0]["content"], revision)
        self.assertEqual(approved_revisions[0]["affected_section"], "Activities")
