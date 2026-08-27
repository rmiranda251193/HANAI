import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept

from .exceptions import (
    AIProviderError,
    InvalidLessonDraftError,
    InvalidLessonReviewError,
    UnsupportedAIProviderError,
)
from .prompts import (
    LESSON_GENERATION_PROMPT_VERSION,
    LESSON_REVIEW_PROMPT_VERSION,
    build_lesson_generation_prompt,
    build_lesson_review_prompt,
)
from .providers import FakeAIProvider, OpenAIProvider, get_ai_provider
from .requests import ConceptContext, LessonGenerationRequest, LessonReviewRequest
from .schemas import (
    LessonDraft,
    LessonReviewResult,
    ReviewIssue,
    example_lesson_draft_dict,
    example_lesson_review_dict,
    parse_model_json,
)
from .services import generate_lesson_draft, review_lesson_draft


def make_concept_context(**overrides) -> ConceptContext:
    data = {
        "name": "Force",
        "description": "An interaction that can change an object's motion.",
        "topic": "Dynamics",
        "difficulty": "introductory",
        "equations": ["F_net = ma"],
        "si_units": ["newton (N)"],
        "prerequisites": ["Acceleration"],
        "common_misconceptions": [
            "A moving object needs a force to keep moving at constant velocity."
        ],
    }
    data.update(overrides)
    return ConceptContext(**data)


def make_request(**overrides) -> LessonGenerationRequest:
    data = {
        "title": "Introduction to Newton's Second Law",
        "topic": "Dynamics",
        "grade_level": "11",
        "duration_minutes": 60,
        "learning_objectives": ["Relate net force, mass, and acceleration."],
        "common_misconceptions": ["More mass always means more acceleration."],
        "concepts": (make_concept_context(),),
    }
    data.update(overrides)
    return LessonGenerationRequest(**data)


def make_review_request(**overrides) -> LessonReviewRequest:
    data = {
        "original_lesson": make_request(),
        "draft": LessonDraft.from_dict(example_lesson_draft_dict()),
    }
    data.update(overrides)
    return LessonReviewRequest(**data)


class AIProviderTests(SimpleTestCase):
    def test_fake_provider_returns_valid_json_without_network(self):
        provider = FakeAIProvider()

        raw = provider.generate("prompt", system_prompt="system")

        self.assertEqual(provider.name, "fake")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]["prompt"], "prompt")
        self.assertEqual(provider.calls[0]["system_prompt"], "system")
        self.assertEqual(json.loads(raw), example_lesson_draft_dict())

    def test_fake_provider_can_return_a_fixed_response(self):
        provider = FakeAIProvider(response='{"title": "fixed"}')

        self.assertEqual(provider.generate("anything"), '{"title": "fixed"}')

    def test_get_ai_provider_returns_fake_by_default(self):
        provider = get_ai_provider()

        self.assertIsInstance(provider, FakeAIProvider)
        self.assertEqual(provider.name, "fake")

    @override_settings(
        AI_PROVIDER="openai",
        OPENAI_API_KEY="test-api-key",
        OPENAI_MODEL="gpt-test-model",
        OPENAI_TIMEOUT=45,
    )
    def test_get_ai_provider_returns_openai_provider(self):
        provider = get_ai_provider()

        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.name, "openai")
        self.assertEqual(provider.model, "gpt-test-model")
        self.assertEqual(provider.timeout, 45)

    @override_settings(AI_PROVIDER="ollama")
    def test_ollama_provider_is_reserved_but_not_implemented(self):
        with self.assertRaisesMessage(
            UnsupportedAIProviderError,
            "The 'ollama' provider is reserved but not implemented yet.",
        ):
            get_ai_provider()

    @override_settings(AI_PROVIDER="unknown-vendor")
    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesMessage(
            UnsupportedAIProviderError,
            "Unknown AI provider 'unknown-vendor'.",
        ):
            get_ai_provider()


class OpenAIProviderTests(SimpleTestCase):
    def test_missing_api_key_only_fails_when_provider_is_invoked(self):
        with override_settings(AI_PROVIDER="openai", OPENAI_API_KEY=""):
            provider = get_ai_provider()

        with self.assertRaisesMessage(AIProviderError, "OPENAI_API_KEY is not configured"):
            provider.generate("prompt")

    @override_settings(
        OPENAI_API_KEY="test-api-key",
        OPENAI_MODEL="gpt-test-model",
        OPENAI_TIMEOUT=42,
    )
    @patch("apps.ai.providers.OpenAI")
    def test_uses_settings_to_configure_sdk_and_returns_response_text(self, openai_class):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" generated lesson "))]
        )
        client = MagicMock()
        client.chat.completions.create.return_value = response
        openai_class.return_value = client

        provider = OpenAIProvider()
        text = provider.generate("user prompt", system_prompt="system prompt")

        self.assertEqual(text, "generated lesson")
        openai_class.assert_called_once_with(
            api_key="test-api-key", timeout=42.0
        )
        client.chat.completions.create.assert_called_once_with(
            model="gpt-test-model",
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
        )

    def test_explicit_configuration_overrides_settings(self):
        client = MagicMock()
        provider = OpenAIProvider(
            api_key="test-api-key", model="gpt-explicit", timeout="15", client=client
        )

        self.assertEqual(provider.model, "gpt-explicit")
        self.assertEqual(provider.timeout, 15.0)

    def test_sdk_errors_are_translated_without_exposing_api_key(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError(
            "Request failed with test-api-key"
        )
        provider = OpenAIProvider(api_key="test-api-key", client=client)

        with self.assertRaises(AIProviderError) as ctx:
            provider.generate("prompt")

        self.assertIn("OpenAI provider request failed", str(ctx.exception))
        self.assertNotIn("test-api-key", str(ctx.exception))
        self.assertIn("[redacted]", str(ctx.exception))

    def test_empty_sdk_response_is_rejected(self):
        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[])
        provider = OpenAIProvider(api_key="test-api-key", client=client)

        with self.assertRaisesMessage(AIProviderError, "empty response"):
            provider.generate("prompt")


class LessonDraftSchemaTests(SimpleTestCase):
    def test_valid_payload_becomes_a_lesson_draft(self):
        draft = LessonDraft.from_dict(example_lesson_draft_dict())

        self.assertEqual(draft.title, "Introduction to Newton's Second Law")
        self.assertEqual(draft.key_concepts, ("Force", "Newton's Second Law"))
        self.assertEqual(draft.worked_examples[0].title, "Cart on a low-friction track")
        self.assertEqual(draft.to_dict()["title"], draft.title)

    def test_missing_required_field_is_rejected(self):
        payload = example_lesson_draft_dict()
        del payload["explanation"]

        with self.assertRaises(InvalidLessonDraftError) as ctx:
            LessonDraft.from_dict(payload)

        self.assertIn("Missing required field 'explanation'.", ctx.exception.reasons)

    def test_empty_title_is_rejected(self):
        payload = example_lesson_draft_dict()
        payload["title"] = "   "

        with self.assertRaises(InvalidLessonDraftError) as ctx:
            LessonDraft.from_dict(payload)

        self.assertIn("Field 'title' cannot be empty.", ctx.exception.reasons)

    def test_wrong_list_type_is_rejected(self):
        payload = example_lesson_draft_dict()
        payload["learning_objectives"] = "not a list"

        with self.assertRaises(InvalidLessonDraftError) as ctx:
            LessonDraft.from_dict(payload)

        self.assertIn(
            "Field 'learning_objectives' must be a list of strings.",
            ctx.exception.reasons,
        )

    def test_worked_example_requires_structured_fields(self):
        payload = example_lesson_draft_dict()
        payload["worked_examples"] = [{"title": "Only a title"}]

        with self.assertRaises(InvalidLessonDraftError) as ctx:
            LessonDraft.from_dict(payload)

        self.assertTrue(
            any("worked_examples[0].problem" in reason for reason in ctx.exception.reasons)
        )

    def test_parse_model_json_accepts_markdown_fences(self):
        payload = example_lesson_draft_dict()
        fenced = "```json\n" + json.dumps(payload) + "\n```"

        self.assertEqual(parse_model_json(fenced), payload)

    def test_parse_model_json_rejects_invalid_json(self):
        with self.assertRaisesMessage(InvalidLessonDraftError, "not valid JSON"):
            parse_model_json("this is not json")


class ReviewIssueSchemaTests(SimpleTestCase):
    def test_valid_review_issue_passes_validation(self):
        payload = example_lesson_review_dict()["issues"][0]

        issue = ReviewIssue.from_dict(payload)

        self.assertEqual(issue.category, "misconception")
        self.assertEqual(issue.severity, "warning")
        self.assertEqual(issue.confidence, "high")

    def test_invalid_review_issue_is_rejected(self):
        payload = example_lesson_review_dict()["issues"][0]
        payload["severity"] = "urgent"

        with self.assertRaises(InvalidLessonReviewError) as ctx:
            ReviewIssue.from_dict(payload)

        self.assertIn(
            "Field 'severity' must be one of: error, info, warning.",
            ctx.exception.reasons,
        )


class LessonReviewResultSchemaTests(SimpleTestCase):
    def test_review_result_accepts_multiple_issues(self):
        payload = example_lesson_review_dict()
        second_issue = payload["issues"][0].copy()
        second_issue.update(
            {
                "category": "clarity",
                "severity": "info",
                "issue": "The explanation could introduce net force before acceleration.",
                "confidence": "medium",
            }
        )
        payload["issues"].append(second_issue)

        result = LessonReviewResult.from_dict(payload)

        self.assertEqual(len(result.issues), 2)
        self.assertEqual(result.issues[1].category, "clarity")
        self.assertEqual(result.to_dict()["issues"][0]["confidence"], "high")

    def test_malformed_review_result_is_rejected(self):
        payload = {"overall_summary": "A useful review."}

        with self.assertRaises(InvalidLessonReviewError) as ctx:
            LessonReviewResult.from_dict(payload)

        self.assertIn("Missing required field 'issues'.", ctx.exception.reasons)


class LessonGenerationRequestTests(SimpleTestCase):
    def test_request_requires_title_topic_grade_objective_and_concept(self):
        with self.assertRaisesMessage(ValueError, "title is required"):
            make_request(title="  ")
        with self.assertRaisesMessage(ValueError, "at least one learning objective is required"):
            make_request(learning_objectives=[])
        with self.assertRaisesMessage(ValueError, "at least one Physics concept is required"):
            make_request(concepts=())
        with self.assertRaisesMessage(ValueError, "duration_minutes must be a positive integer"):
            make_request(duration_minutes=0)


class LessonGenerationRequestFromLessonTests(TestCase):
    def test_from_lesson_copies_teacher_fields_and_concept_knowledge(self):
        force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
            difficulty=PhysicsConcept.Difficulty.INTRODUCTORY,
            equations=["F_net = ma"],
            si_units=["newton (N)"],
            prerequisites=["Acceleration"],
            common_misconceptions=["Forces are stored inside moving objects."],
        )
        lesson = Lesson.objects.create(
            title="Introduction to Newton's Second Law",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass, and acceleration."],
            common_misconceptions=["More mass always means more acceleration."],
        )
        lesson.physics_concepts.add(force)

        request = LessonGenerationRequest.from_lesson(lesson)

        self.assertEqual(request.title, lesson.title)
        self.assertEqual(request.duration_minutes, 45)
        self.assertEqual(request.learning_objectives, ("Relate net force, mass, and acceleration.",))
        self.assertEqual(len(request.concepts), 1)
        self.assertEqual(request.concepts[0].name, "Force")
        self.assertEqual(request.concepts[0].equations, ("F_net = ma",))
        self.assertEqual(request.concepts[0].si_units, ("newton (N)",))


class LessonReviewRequestFromLessonTests(TestCase):
    def test_from_lesson_snapshots_context_and_retains_validated_draft(self):
        force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
            difficulty=PhysicsConcept.Difficulty.INTRODUCTORY,
            equations=["F_net = ma"],
            si_units=["newton (N)"],
            prerequisites=["Acceleration"],
            common_misconceptions=["Forces are stored inside moving objects."],
        )
        lesson = Lesson.objects.create(
            title="Introduction to Newton's Second Law",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass, and acceleration."],
            common_misconceptions=["More mass always means more acceleration."],
        )
        lesson.physics_concepts.add(force)
        draft = LessonDraft.from_dict(example_lesson_draft_dict())

        request = LessonReviewRequest.from_lesson(lesson, draft)

        self.assertEqual(request.title, lesson.title)
        self.assertEqual(request.grade_level, "11")
        self.assertEqual(request.learning_objectives, tuple(lesson.learning_objectives))
        self.assertEqual(
            request.common_misconceptions, tuple(lesson.common_misconceptions)
        )
        self.assertEqual(request.concepts[0].equations, ("F_net = ma",))
        self.assertEqual(
            request.concepts[0].common_misconceptions,
            ("Forces are stored inside moving objects.",),
        )
        self.assertIs(request.draft, draft)


class PromptBuilderTests(SimpleTestCase):
    def test_prompt_includes_request_data_schema_and_teacher_authority(self):
        request = make_request()
        prompt = build_lesson_generation_prompt(request)

        self.assertEqual(prompt.version, LESSON_GENERATION_PROMPT_VERSION)
        self.assertIn("Teachers decide", prompt.system)
        self.assertIn("Return ONLY a JSON object", prompt.system)
        self.assertIn("worked_examples", prompt.system)
        self.assertIn("Do not invent equations", prompt.system)
        self.assertIn(request.title, prompt.user)
        self.assertIn("Grade level: 11", prompt.user)
        self.assertIn("Duration (minutes): 60", prompt.user)
        self.assertIn("Relate net force, mass, and acceleration.", prompt.user)
        self.assertIn("More mass always means more acceleration.", prompt.user)
        self.assertIn("F_net = ma", prompt.user)
        self.assertIn("newton (N)", prompt.user)
        self.assertIn("### Force", prompt.user)


class ReviewPromptBuilderTests(SimpleTestCase):
    def test_review_prompt_includes_draft_and_physics_context(self):
        request = make_review_request()
        prompt = build_lesson_review_prompt(request)

        self.assertEqual(prompt.version, LESSON_REVIEW_PROMPT_VERSION)
        self.assertIn("Return ONLY a JSON object", prompt.system)
        self.assertIn("Do not rewrite it", prompt.system)
        self.assertIn("meaningful issues", prompt.system)
        self.assertIn("equations", prompt.system)
        self.assertIn(request.title, prompt.user)
        self.assertIn("Grade level: 11", prompt.user)
        self.assertIn(request.draft.overview, prompt.user)
        self.assertIn("F_net = ma", prompt.user)
        self.assertIn("newton (N)", prompt.user)
        self.assertIn("More mass always means more acceleration.", prompt.user)
        self.assertIn(
            "A moving object needs a force to keep moving at constant velocity.",
            prompt.user,
        )


class GenerateLessonDraftTests(SimpleTestCase):
    def test_generate_lesson_draft_validates_fake_provider_output(self):
        provider = FakeAIProvider()
        result = generate_lesson_draft(make_request(), provider=provider)

        self.assertEqual(result.provider_name, "fake")
        self.assertEqual(result.prompt_version, LESSON_GENERATION_PROMPT_VERSION)
        self.assertEqual(result.draft.title, "Introduction to Newton's Second Law")
        self.assertEqual(len(provider.calls), 1)
        self.assertIn("Introduction to Newton's Second Law", provider.calls[0]["prompt"])
        self.assertIn("Teachers decide", provider.calls[0]["system_prompt"])

    def test_generate_lesson_draft_rejects_invalid_provider_json(self):
        provider = FakeAIProvider(response="not-json")

        with self.assertRaises(InvalidLessonDraftError):
            generate_lesson_draft(make_request(), provider=provider)

    def test_generate_lesson_draft_rejects_schema_mismatch(self):
        provider = FakeAIProvider(response=json.dumps({"title": "Only a title"}))

        with self.assertRaises(InvalidLessonDraftError) as ctx:
            generate_lesson_draft(make_request(), provider=provider)

        self.assertTrue(any("Missing required field" in reason for reason in ctx.exception.reasons))

    def test_generate_lesson_draft_parses_fenced_json(self):
        payload = example_lesson_draft_dict()
        provider = FakeAIProvider(response="```json\n" + json.dumps(payload) + "\n```")

        result = generate_lesson_draft(make_request(), provider=provider)

        self.assertEqual(result.draft.overview, payload["overview"])


class ReviewLessonDraftTests(SimpleTestCase):
    def test_fake_provider_returns_a_valid_review_result(self):
        provider = FakeAIProvider()

        result = review_lesson_draft(make_review_request(), provider=provider)

        self.assertEqual(result.overall_summary, example_lesson_review_dict()["overall_summary"])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].category, "misconception")
        self.assertEqual(len(provider.calls), 1)
        self.assertIn(LESSON_REVIEW_PROMPT_VERSION, provider.calls[0]["system_prompt"])
        self.assertIn("Introduction to Newton's Second Law", provider.calls[0]["prompt"])

    def test_review_service_rejects_invalid_json_with_review_error(self):
        provider = FakeAIProvider(review_response="not-json")

        with self.assertRaises(InvalidLessonReviewError):
            review_lesson_draft(make_review_request(), provider=provider)

    def test_review_service_rejects_invalid_review_schema(self):
        provider = FakeAIProvider(
            review_response=json.dumps({"overall_summary": "Incomplete review."})
        )

        with self.assertRaises(InvalidLessonReviewError):
            review_lesson_draft(make_review_request(), provider=provider)

    def test_provider_errors_propagate_as_existing_ai_exception(self):
        provider = MagicMock(spec=OpenAIProvider)
        provider.generate.side_effect = AIProviderError("provider unavailable")

        with self.assertRaisesMessage(AIProviderError, "provider unavailable"):
            review_lesson_draft(make_review_request(), provider=provider)

    def test_deterministic_validator_findings_are_combined_with_ai_review(self):
        deterministic_issue = ReviewIssue.from_dict(
            {
                "category": "units",
                "severity": "info",
                "issue": "A unit check is available for teacher review.",
                "explanation": "A future deterministic validator identified this note.",
                "affected_section": "Worked examples",
                "suggested_revision": "Confirm the units before finalizing.",
                "confidence": "high",
            }
        )

        class StubValidator:
            def validate(self, request):
                return (deterministic_issue,)

        result = review_lesson_draft(
            make_review_request(),
            provider=FakeAIProvider(),
            validators=(StubValidator(),),
        )

        self.assertEqual(len(result.issues), 2)
        self.assertEqual(result.issues[0], deterministic_issue)


class AISettingsTests(SimpleTestCase):
    def test_ai_settings_exist_with_safe_defaults(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "AI_PROVIDER"))
        self.assertTrue(hasattr(settings, "OPENAI_API_KEY"))
        self.assertTrue(hasattr(settings, "OLLAMA_BASE_URL"))
        self.assertEqual(settings.AI_PROVIDER, "fake")
        self.assertEqual(settings.OPENAI_API_KEY, "")
