import json

from django.test import TestCase
from django.urls import reverse

from apps.ai.providers import FakeAIProvider
from apps.ai.requests import LessonGenerationRequest, LessonReviewRequest
from apps.ai.services import generate_lesson_draft, review_lesson_draft
from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept

from .models import PersistedReviewIssue, ProvenanceEvent
from .services import (
    finalize_lesson_from_review,
    get_lesson_history,
    persist_generated_lesson_draft,
    persist_lesson_draft_review,
    record_event,
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


class ProvenanceAuditTrailTests(TestCase):
    def setUp(self):
        self.concept = PhysicsConcept.objects.create(
            name="Momentum",
            description="The product of mass and velocity.",
            topic="Mechanics",
            equations=["p = mv"],
            si_units=["kg·m/s"],
        )
        self.lesson = Lesson.objects.create(
            title="Momentum fundamentals",
            topic="Mechanics",
            grade_level="11",
            duration_minutes=60,
            learning_objectives=["Explain momentum and impulse."],
            common_misconceptions=["Momentum only depends on mass."],
            content={"teacher_note": "Start with a simple momentum example."},
        )
        self.lesson.physics_concepts.add(self.concept)

    def create_draft(self):
        return persist_generated_lesson_draft(
            self.lesson,
            generate_lesson_draft(
                LessonGenerationRequest.from_lesson(self.lesson),
                provider=FakeAIProvider(),
            ),
        )

    def create_review(self, draft, *, provider=None):
        return persist_lesson_draft_review(
            draft,
            review_lesson_draft(
                LessonReviewRequest.from_lesson(self.lesson, draft.as_lesson_draft()),
                provider=provider or FakeAIProvider(),
            ),
        )

    def three_issue_review_payload(self):
        return {
            "overall_summary": "Three findings for teacher decisions.",
            "issues": [
                {
                    "category": "units",
                    "severity": "warning",
                    "issue": "Add unit clarification",
                    "explanation": "SI units should be explicit in the explanation.",
                    "affected_section": "Explanation",
                    "suggested_revision": "State that acceleration uses m/s^2.",
                    "confidence": "high",
                },
                {
                    "category": "clarity",
                    "severity": "info",
                    "issue": "Improve explanation of acceleration",
                    "explanation": "The explanation can be simpler for this grade.",
                    "affected_section": "Explanation",
                    "suggested_revision": "Define acceleration as the rate of change of velocity.",
                    "confidence": "medium",
                },
                {
                    "category": "pedagogy",
                    "severity": "info",
                    "issue": "Add advanced derivation",
                    "explanation": "A calculus derivation may be too advanced.",
                    "affected_section": "Teacher notes",
                    "suggested_revision": "Include a calculus-based derivation.",
                    "confidence": "low",
                },
            ],
        }

    def test_lesson_creation_records_provenance_event(self):
        response = self.client.post(
            reverse("lessons:create"),
            {
                "title": "Impulse and momentum",
                "topic": "Mechanics",
                "grade_level": "11",
                "duration_minutes": "50",
                "physics_concepts": [self.concept.pk],
                "learning_objectives": "Explain impulse.\nRelate impulse to momentum change.",
                "common_misconceptions": "Impulse is the same as force.",
            },
        )

        lesson = Lesson.objects.get(title="Impulse and momentum")
        self.assertRedirects(response, reverse("lessons:detail", args=[lesson.slug]))
        event = ProvenanceEvent.objects.get(
            lesson=lesson,
            event_type=ProvenanceEvent.EventType.LESSON_CREATED,
        )
        self.assertEqual(event.source, "teacher")
        self.assertEqual(event.metadata["title"], "Impulse and momentum")
        self.assertEqual(event.metadata["topic"], "Mechanics")
        self.assertEqual(event.metadata["physics_concepts"], ["Momentum"])

    def test_ai_generation_records_provider_model_prompt_metadata(self):
        draft = self.create_draft()

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.AI_DRAFT_GENERATED,
        )
        self.assertEqual(event.source, "fake")
        self.assertEqual(event.metadata["provider"], "fake")
        self.assertEqual(event.metadata["model"], "fake-lesson-draft")
        self.assertEqual(event.metadata["prompt_version"], "lesson-generation-v1")
        self.assertEqual(event.metadata["draft_id"], str(draft.pk))

    def test_ai_review_records_event(self):
        review = self.create_review(self.create_draft())

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.AI_REVIEW_COMPLETED,
        )
        self.assertEqual(event.metadata["review_id"], str(review.pk))
        self.assertGreaterEqual(int(event.metadata["finding_count"]), 1)

    def test_accept_records_teacher_decision(self):
        issue = self.create_review(self.create_draft()).issues.get()

        record_review_issue_decision(
            issue,
            PersistedReviewIssue.Status.ACCEPTED,
            teacher_note="Keep the original wording.",
        )

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.TEACHER_ACCEPTED,
        )
        self.assertEqual(event.metadata["issue_id"], str(issue.pk))
        self.assertEqual(event.metadata["teacher_note"], "Keep the original wording.")

    def test_edit_records_original_suggestion_and_teacher_revision(self):
        issue = self.create_review(self.create_draft()).issues.get()
        original = issue.suggested_revision

        record_review_issue_decision(
            issue,
            PersistedReviewIssue.Status.EDITED,
            teacher_note="Refined wording works better.",
            edited_text="Use a simpler explanation for students.",
        )

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.TEACHER_EDITED,
        )
        self.assertEqual(event.metadata["issue_id"], str(issue.pk))
        self.assertEqual(event.metadata["original_suggestion"], original)
        self.assertEqual(
            event.metadata["teacher_revision"],
            "Use a simpler explanation for students.",
        )

    def test_reject_records_decision_and_note(self):
        issue = self.create_review(self.create_draft()).issues.get()

        record_review_issue_decision(
            issue,
            PersistedReviewIssue.Status.REJECTED,
            teacher_note="Not appropriate for this lesson.",
        )

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.TEACHER_REJECTED,
        )
        self.assertEqual(event.metadata["issue_id"], str(issue.pk))
        self.assertEqual(event.metadata["teacher_note"], "Not appropriate for this lesson.")

    def test_finalization_records_event(self):
        draft = self.create_draft()
        review = self.create_review(draft)
        record_review_issue_decision(
            review.issues.get(),
            PersistedReviewIssue.Status.ACCEPTED,
        )

        finalize_lesson_from_review(review)

        event = ProvenanceEvent.objects.get(
            lesson=self.lesson,
            event_type=ProvenanceEvent.EventType.LESSON_FINALIZED,
        )
        self.assertEqual(event.metadata["draft_id"], str(draft.pk))
        self.assertEqual(event.metadata["review_id"], str(review.pk))
        self.assertEqual(event.metadata["version"], draft.prompt_version)

    def test_provenance_events_are_chronologically_ordered(self):
        record_event(
            self.lesson,
            ProvenanceEvent.EventType.LESSON_CREATED,
            source="teacher",
            metadata={"title": self.lesson.title},
        )
        draft = self.create_draft()
        review = self.create_review(
            draft,
            provider=FakeAIProvider(
                review_response=json.dumps(self.three_issue_review_payload())
            ),
        )
        issues = list(review.issues.all())
        record_review_issue_decision(
            issues[0],
            PersistedReviewIssue.Status.ACCEPTED,
            teacher_note="Add unit clarification",
        )
        record_review_issue_decision(
            issues[1],
            PersistedReviewIssue.Status.EDITED,
            teacher_note="Improve explanation of acceleration",
            edited_text="Define acceleration as the rate of change of velocity.",
        )
        record_review_issue_decision(
            issues[2],
            PersistedReviewIssue.Status.REJECTED,
            teacher_note="Add advanced derivation",
        )
        finalize_lesson_from_review(review)

        ordered_types = list(
            ProvenanceEvent.objects.filter(lesson=self.lesson).values_list(
                "event_type", flat=True
            )
        )
        self.assertEqual(
            ordered_types,
            [
                ProvenanceEvent.EventType.LESSON_CREATED,
                ProvenanceEvent.EventType.AI_DRAFT_GENERATED,
                ProvenanceEvent.EventType.AI_REVIEW_COMPLETED,
                ProvenanceEvent.EventType.TEACHER_ACCEPTED,
                ProvenanceEvent.EventType.TEACHER_EDITED,
                ProvenanceEvent.EventType.TEACHER_REJECTED,
                ProvenanceEvent.EventType.LESSON_FINALIZED,
            ],
        )

    def test_provenance_omits_secret_like_keys(self):
        event = record_event(
            self.lesson,
            ProvenanceEvent.EventType.AI_DRAFT_GENERATED,
            metadata={
                "provider": "openai",
                "api_key": "top-secret",
                "secret": "hidden",
                "nested": {"token": "abc123", "provider": "openai"},
            },
        )

        self.assertNotIn("api_key", event.metadata)
        self.assertNotIn("secret", event.metadata)
        self.assertNotIn("token", event.metadata["nested"])
        self.assertEqual(event.metadata["provider"], "openai")
        self.assertEqual(event.metadata["nested"]["provider"], "openai")

    def test_existing_generation_workflow_remains_intact(self):
        original_content = dict(self.lesson.content)
        original_status = self.lesson.status
        original_title = self.lesson.title

        draft = self.create_draft()

        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.content, original_content)
        self.assertEqual(self.lesson.status, original_status)
        self.assertEqual(self.lesson.title, original_title)
        self.assertFalse(self.lesson.ai_generated)
        self.assertEqual(draft.as_lesson_draft().title, "Introduction to Newton's Second Law")

    def test_existing_review_workflow_remains_intact(self):
        draft = self.create_draft()
        original_draft = draft.draft_data
        review = self.create_review(draft)
        issue = review.issues.get()
        original_suggestion = issue.suggested_revision
        original_issue = issue.issue

        record_review_issue_decision(
            issue,
            PersistedReviewIssue.Status.ACCEPTED,
            teacher_note="Use this.",
        )

        issue.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(issue.suggested_revision, original_suggestion)
        self.assertEqual(issue.issue, original_issue)
        self.assertEqual(draft.draft_data, original_draft)
        self.assertEqual(issue.status, PersistedReviewIssue.Status.ACCEPTED)
        self.assertEqual(issue.decision_record.teacher_note, "Use this.")

    def test_original_ai_draft_and_review_remain_after_finalization(self):
        draft = self.create_draft()
        original_draft = draft.draft_data
        review = self.create_review(draft)
        original_summary = review.overall_summary
        issue = review.issues.get()
        original_suggestion = issue.suggested_revision
        record_review_issue_decision(issue, PersistedReviewIssue.Status.ACCEPTED)

        finalize_lesson_from_review(review)

        draft.refresh_from_db()
        review.refresh_from_db()
        issue.refresh_from_db()
        self.assertEqual(draft.draft_data, original_draft)
        self.assertEqual(review.overall_summary, original_summary)
        self.assertEqual(issue.suggested_revision, original_suggestion)
        self.assertIsNotNone(draft.finalized_at)

    def test_history_is_built_from_persisted_events(self):
        record_event(
            self.lesson,
            ProvenanceEvent.EventType.LESSON_CREATED,
            source="teacher",
            metadata={"title": self.lesson.title},
        )
        self.create_draft()

        entries = get_lesson_history(self.lesson)
        self.assertEqual(entries[0].title, "Lesson created")
        self.assertEqual(entries[0].source_label, "Teacher")
        self.assertEqual(entries[1].title, "AI draft generated")
        self.assertEqual(entries[1].source_label, "Fake")
        self.assertIn("Model: fake-lesson-draft", entries[1].details)
        self.assertIn("Prompt: lesson-generation-v1", entries[1].details)
