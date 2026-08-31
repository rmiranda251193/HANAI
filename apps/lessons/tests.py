from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.ai.exceptions import AIProviderError
from apps.ai.providers import FakeAIProvider
from apps.physics.models import PhysicsConcept
from apps.provenance.models import GeneratedLessonDraft, PersistedReviewIssue, ProvenanceEvent

from .models import Lesson


class LessonPhysicsConceptTests(TestCase):
    def setUp(self):
        self.force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
            equations=["F_net = ma"],
            si_units=["newton (N)"],
            prerequisites=["Acceleration"],
        )
        self.newtons_second_law = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass, and acceleration are related.",
            topic="Dynamics",
        )

    def create_lesson(self, title="Introduction to Newton's Second Law"):
        return Lesson.objects.create(
            title=title,
            topic="Dynamics",
            grade_level="11",
            duration_minutes=60,
            learning_objectives=["Relate net force, mass, and acceleration."],
        )

    def test_lesson_can_be_created_with_draft_status_and_slug(self):
        lesson = self.create_lesson()

        self.assertEqual(lesson.status, Lesson.Status.DRAFT)
        self.assertEqual(lesson.slug, "introduction-to-newtons-second-law")

    def test_lesson_can_reference_multiple_physics_concepts(self):
        lesson = self.create_lesson()

        lesson.physics_concepts.add(self.force, self.newtons_second_law)

        self.assertCountEqual(
            lesson.physics_concepts.values_list("name", flat=True),
            ["Force", "Newton's Second Law"],
        )

    def test_physics_concept_can_belong_to_multiple_lessons(self):
        first_lesson = self.create_lesson()
        second_lesson = self.create_lesson("Using Force and Mass")

        self.force.lessons.add(first_lesson, second_lesson)

        self.assertCountEqual(
            self.force.lessons.values_list("title", flat=True),
            [first_lesson.title, second_lesson.title],
        )

    def test_lesson_does_not_duplicate_physics_concept_reference_fields(self):
        lesson = self.create_lesson()
        lesson.physics_concepts.add(self.force)
        lesson_fields = {field.name for field in Lesson._meta.get_fields()}

        self.assertNotIn("equations", lesson_fields)
        self.assertNotIn("si_units", lesson_fields)
        self.assertNotIn("prerequisites", lesson_fields)
        self.assertEqual(lesson.physics_concepts.get().equations, ["F_net = ma"])


class LessonBuilderViewTests(TestCase):
    def setUp(self):
        self.force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
        )
        self.newtons_second_law = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass, and acceleration are related.",
            topic="Dynamics",
        )

    def valid_lesson_data(self):
        return {
            "title": "Introduction to Newton's Second Law",
            "topic": "Dynamics",
            "grade_level": "11",
            "duration_minutes": "60",
            "physics_concepts": [self.force.pk, self.newtons_second_law.pk],
            "learning_objectives": (
                "Calculate acceleration from net force and mass.\n\n"
                "Explain the relationship between force and mass."
            ),
            "common_misconceptions": "More mass always means more acceleration.\n\n",
        }

    def test_lesson_list_url_works(self):
        response = self.client.get(reverse("lessons:list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/list.html")

    def test_lesson_create_page_works(self):
        response = self.client.get(reverse("lessons:create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/form.html")

    def test_valid_post_creates_draft_with_concepts_and_json_lists(self):
        response = self.client.post(reverse("lessons:create"), self.valid_lesson_data())

        lesson = Lesson.objects.get()
        self.assertRedirects(response, reverse("lessons:detail", args=[lesson.slug]))
        self.assertEqual(lesson.status, Lesson.Status.DRAFT)
        self.assertCountEqual(
            lesson.physics_concepts.values_list("name", flat=True),
            ["Force", "Newton's Second Law"],
        )
        self.assertEqual(
            lesson.learning_objectives,
            [
                "Calculate acceleration from net force and mass.",
                "Explain the relationship between force and mass.",
            ],
        )
        self.assertEqual(
            lesson.common_misconceptions,
            ["More mass always means more acceleration."],
        )

    def test_creating_a_lesson_records_provenance_and_shows_history(self):
        response = self.client.post(reverse("lessons:create"), self.valid_lesson_data())

        lesson = Lesson.objects.get()
        self.assertRedirects(response, reverse("lessons:detail", args=[lesson.slug]))
        event = ProvenanceEvent.objects.get(
            lesson=lesson,
            event_type=ProvenanceEvent.EventType.LESSON_CREATED,
        )
        self.assertEqual(event.source, "teacher")
        self.assertEqual(event.metadata["title"], lesson.title)

        detail = self.client.get(reverse("lessons:detail", args=[lesson.slug]))
        self.assertContains(detail, "Lesson history")
        self.assertContains(detail, "Lesson created")
        self.assertContains(detail, "Teacher")

    def test_lesson_detail_page_works(self):
        lesson = Lesson.objects.create(
            title="Understanding Force",
            topic="Dynamics",
            grade_level="11",
            learning_objectives=["Describe force."],
            common_misconceptions=["Force keeps motion going."],
        )
        lesson.physics_concepts.add(self.force)

        response = self.client.get(reverse("lessons:detail", args=[lesson.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/detail.html")
        self.assertContains(response, "Understanding Force")
        self.assertContains(response, "Force")

    def test_invalid_form_data_does_not_create_a_lesson(self):
        data = self.valid_lesson_data()
        data["title"] = ""

        response = self.client.post(reverse("lessons:create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Lesson.objects.count(), 0)
        self.assertFormError(response.context["form"], "title", "This field is required.")


class LessonGenerationViewTests(TestCase):
    def setUp(self):
        self.force = PhysicsConcept.objects.create(
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
        self.lesson.physics_concepts.add(self.force)

    def generation_url(self):
        return reverse("lessons:generate", args=[self.lesson.slug])

    def test_generate_endpoint_rejects_get(self):
        response = self.client.get(self.generation_url())

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "POST")

    @override_settings(AI_PROVIDER="fake")
    def test_fake_provider_generates_and_displays_a_review_draft(self):
        original_title = self.lesson.title
        original_content = self.lesson.content.copy()
        original_status = self.lesson.status
        original_updated_at = self.lesson.updated_at

        response = self.client.post(self.generation_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/detail.html")
        self.assertContains(response, "AI-generated draft")
        self.assertContains(response, "Introduction to Newton&#x27;s Second Law", html=False)
        self.assertContains(response, "Students relate net force, mass, and acceleration")
        self.assertContains(response, "Calculate acceleration from net force and mass.")
        self.assertContains(response, "Force")
        self.assertContains(response, "Newton&#x27;s Second Law", html=False)
        self.assertContains(response, "Newton&#x27;s second law states", html=False)
        self.assertContains(response, "Cart on a low-friction track")
        self.assertContains(response, "Predict then measure")
        self.assertContains(response, "Two students pull a wagon")
        self.assertContains(response, "This is a draft. Review equations")
        self.assertContains(response, "Saved for review")

        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.title, original_title)
        self.assertEqual(self.lesson.content, original_content)
        self.assertEqual(self.lesson.status, original_status)
        self.assertEqual(self.lesson.updated_at, original_updated_at)

    @override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="")
    def test_missing_openai_key_returns_a_friendly_response(self):
        with patch("apps.lessons.views.logger") as logger:
            response = self.client.post(self.generation_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "AI generation could not be completed. Please check the AI configuration and try again.",
        )
        self.assertNotContains(response, "OPENAI_API_KEY is not configured")
        logger.warning.assert_called_once()

    def test_provider_error_returns_a_friendly_response(self):
        with (
            patch(
                "apps.lessons.views.generate_lesson_draft",
                side_effect=AIProviderError("internal provider detail"),
            ),
            patch("apps.lessons.views.logger") as logger,
        ):
            response = self.client.post(self.generation_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "AI generation could not be completed. Please check the AI configuration and try again.",
        )
        self.assertNotContains(response, "internal provider detail")
        logger.warning.assert_called_once()

    @override_settings(AI_PROVIDER="fake")
    def test_invalid_ai_output_is_handled_safely(self):
        with (
            patch(
                "apps.ai.services.get_ai_provider",
                return_value=FakeAIProvider(response="not valid JSON"),
            ),
            patch("apps.lessons.views.logger") as logger,
        ):
            response = self.client.post(self.generation_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "AI generation could not be completed. Please check the AI configuration and try again.",
        )
        self.assertNotContains(response, "not valid JSON")
        logger.warning.assert_called_once()

    def test_detail_includes_a_csrf_protected_generation_form(self):
        response = self.client.get(
            reverse("lessons:detail", args=[self.lesson.slug])
        )

        self.assertContains(response, self.generation_url())
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Generate with AI")

    @override_settings(AI_PROVIDER="fake")
    def test_generate_endpoint_requires_csrf_protection(self):
        csrf_client = Client(enforce_csrf_checks=True)

        rejected = csrf_client.post(self.generation_url())
        self.assertEqual(rejected.status_code, 403)

        csrf_client.get(reverse("lessons:detail", args=[self.lesson.slug]))
        token = csrf_client.cookies["csrftoken"].value
        accepted = csrf_client.post(self.generation_url(), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(accepted.status_code, 200)

    @override_settings(AI_PROVIDER="fake")
    def test_teacher_can_generate_review_decide_and_finalize_a_draft(self):
        generated = self.client.post(self.generation_url())
        self.assertEqual(generated.status_code, 200)

        draft = GeneratedLessonDraft.objects.get(lesson=self.lesson)
        reviewed = self.client.post(
            reverse("lessons:review", args=[self.lesson.slug, draft.pk])
        )
        self.assertEqual(reviewed.status_code, 200)
        self.assertContains(reviewed, "Teacher decisions required")

        issue = PersistedReviewIssue.objects.get(review__draft=draft)
        decided = self.client.post(
            reverse(
                "lessons:review_issue_decision",
                args=[self.lesson.slug, draft.pk, issue.pk],
            ),
            {"decision": "accepted"},
        )
        self.assertEqual(decided.status_code, 200)

        finalized = self.client.post(
            reverse(
                "lessons:finalize",
                args=[self.lesson.slug, draft.pk, issue.review_id],
            )
        )
        self.assertEqual(finalized.status_code, 200)
        self.assertContains(finalized, "Lesson content was finalized")
        self.assertContains(finalized, "Lesson history")
        self.assertContains(finalized, "AI draft generated")
        self.assertContains(finalized, "AI review completed")
        self.assertContains(finalized, "Teacher accepted")
        self.assertContains(finalized, "Lesson finalized")
        self.assertContains(finalized, "AI-generated draft")
        self.assertContains(finalized, "Teacher decisions required")

        self.lesson.refresh_from_db()
        draft.refresh_from_db()
        self.assertTrue(self.lesson.ai_generated)
        self.assertEqual(self.lesson.status, Lesson.Status.REVIEW)
        self.assertIsNotNone(draft.finalized_at)
        self.assertEqual(
            list(
                ProvenanceEvent.objects.filter(lesson=self.lesson).values_list(
                    "event_type", flat=True
                )
            ),
            [
                ProvenanceEvent.EventType.AI_DRAFT_GENERATED,
                ProvenanceEvent.EventType.AI_REVIEW_COMPLETED,
                ProvenanceEvent.EventType.TEACHER_ACCEPTED,
                ProvenanceEvent.EventType.LESSON_FINALIZED,
            ],
        )
