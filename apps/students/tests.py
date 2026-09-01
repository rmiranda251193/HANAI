import json

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.ai.exceptions import AIProviderError
from apps.ai.providers import AIProvider
from apps.ai.requests import ConceptContext
from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept

from .exceptions import EmptyTutorMessageError, InvalidTutorResponseError
from .models import LearningEvidence, StudentProfile, TutorMessage, TutorSession
from .prompts import TUTOR_PROMPT_VERSION, build_tutor_prompt
from .providers import FakeTutorProvider, get_tutor_provider
from .requests import TutorConversationMessage, TutorRequest
from .schemas import TutorResponse, example_tutor_response_dict
from .services import run_tutor_turn, tutor_student
from .views import EMPTY_QUESTION_MESSAGE, TUTOR_ERROR_MESSAGE


def make_concept_context(**overrides) -> ConceptContext:
    data = {
        "name": "Acceleration",
        "description": "The rate of change of velocity with respect to time.",
        "topic": "Kinematics",
        "difficulty": "foundational",
        "equations": ["a = (v - u) / t"],
        "si_units": ["m/s^2"],
        "prerequisites": ["Velocity"],
        "common_misconceptions": ["Acceleration only means speeding up."],
    }
    data.update(overrides)
    return ConceptContext(**data)


def make_tutor_request(**overrides) -> TutorRequest:
    data = {
        "lesson_title": "Motion Basics",
        "topic": "Kinematics",
        "grade_level": "11",
        "learning_objectives": ("Define acceleration and its SI units.",),
        "common_misconceptions": ("Acceleration always means speeding up.",),
        "concepts": (make_concept_context(),),
        "recent_messages": (
            TutorConversationMessage(role="student", content="I am stuck on part b."),
        ),
        "student_question": "What is acceleration?",
    }
    data.update(overrides)
    return TutorRequest(**data)


class TutorDataMixin:
    def make_lesson(self) -> Lesson:
        concept = PhysicsConcept.objects.create(
            name="Acceleration",
            description="The rate of change of velocity with respect to time.",
            topic="Kinematics",
            equations=["a = (v - u) / t"],
            si_units=["m/s^2"],
        )
        lesson = Lesson.objects.create(
            title="Motion Basics",
            topic="Kinematics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Define acceleration and its SI units."],
            common_misconceptions=["Acceleration always means speeding up."],
            problems=["A cart speeds up from 2 m/s to 8 m/s in 3 s. Find its acceleration."],
        )
        lesson.physics_concepts.add(concept)
        return lesson

    def make_session(self, lesson: Lesson | None = None) -> TutorSession:
        lesson = lesson or self.make_lesson()
        student = StudentProfile.objects.create(display_name="Test Learner")
        return TutorSession.objects.create(student=student, lesson=lesson)


class StudentDomainTests(TutorDataMixin, TestCase):
    def test_student_profile_creation(self):
        profile = StudentProfile.objects.create(display_name="Ada")

        self.assertIsNone(profile.user)
        self.assertIsNotNone(profile.created_at)
        self.assertEqual(str(profile), "Ada")

    def test_tutor_session_creation_defaults_to_active_and_allows_many(self):
        lesson = self.make_lesson()
        student = StudentProfile.objects.create(display_name="Ada")

        first = TutorSession.objects.create(student=student, lesson=lesson)
        second = TutorSession.objects.create(student=student, lesson=lesson)

        self.assertEqual(first.status, TutorSession.Status.ACTIVE)
        self.assertEqual(
            TutorSession.objects.filter(student=student, lesson=lesson).count(), 2
        )
        self.assertNotEqual(first.pk, second.pk)

    def test_tutor_message_creation(self):
        session = self.make_session()

        message = TutorMessage.objects.create(
            session=session,
            role=TutorMessage.Role.STUDENT,
            content="What is acceleration?",
        )

        self.assertEqual(message.role, "student")
        self.assertEqual(message.get_role_display(), "Student")
        self.assertEqual(message.data, {})
        self.assertIsNotNone(message.created_at)

    def test_tutor_messages_are_ordered_oldest_to_newest(self):
        session = self.make_session()
        first = TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="First"
        )
        second = TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.TUTOR, content="Second"
        )
        third = TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="Third"
        )

        self.assertEqual(
            list(session.messages.values_list("content", flat=True)),
            ["First", "Second", "Third"],
        )
        self.assertEqual(session.messages.first(), first)
        self.assertEqual(session.messages.last(), third)
        self.assertLessEqual(first.created_at, second.created_at)


class TutorResponseSchemaTests(SimpleTestCase):
    def test_valid_tutor_response_validates(self):
        response = TutorResponse.from_dict(example_tutor_response_dict())

        self.assertEqual(response.mode, "explain")
        self.assertTrue(response.message)
        self.assertFalse(response.needs_student_attempt)
        self.assertEqual(response.to_dict()["mode"], "explain")

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(InvalidTutorResponseError):
            TutorResponse.from_dict({"mode": "chatty", "message": "Here you go."})

    def test_missing_message_is_rejected(self):
        with self.assertRaises(InvalidTutorResponseError):
            TutorResponse.from_dict({"mode": "hint"})

    def test_unexpected_field_is_rejected(self):
        with self.assertRaises(InvalidTutorResponseError):
            TutorResponse.from_dict(
                {"mode": "hint", "message": "Try this.", "answer_key": "42"}
            )

    def test_non_boolean_attempt_flag_is_rejected(self):
        with self.assertRaises(InvalidTutorResponseError):
            TutorResponse.from_dict(
                {"mode": "hint", "message": "Try this.", "needs_student_attempt": "yes"}
            )


class TutorRequestAndPromptTests(TutorDataMixin, TestCase):
    def test_tutor_request_construction_from_session(self):
        session = self.make_session()
        TutorMessage.objects.create(
            session=session, role=TutorMessage.Role.STUDENT, content="Earlier question"
        )

        request = TutorRequest.from_session(session, student_question="Why m/s^2?")

        self.assertEqual(request.topic, "Kinematics")
        self.assertEqual(request.grade_level, "11")
        self.assertEqual(request.lesson_title, "Motion Basics")
        self.assertEqual(len(request.concepts), 1)
        self.assertIsInstance(request.concepts[0], ConceptContext)
        self.assertEqual(request.recent_messages[0].content, "Earlier question")
        self.assertEqual(request.student_question, "Why m/s^2?")

    def test_tutor_request_requires_a_question_or_attempt(self):
        with self.assertRaises(ValueError):
            make_tutor_request(student_question="", student_attempt="")

    def test_prompt_contains_lesson_topic(self):
        prompt = build_tutor_prompt(make_tutor_request(topic="Thermodynamics"))
        self.assertIn("Thermodynamics", prompt.user)

    def test_prompt_contains_physics_concepts(self):
        prompt = build_tutor_prompt(
            make_tutor_request(concepts=(make_concept_context(name="Momentum"),))
        )
        self.assertIn("Momentum", prompt.user)

    def test_prompt_contains_grade_level_and_version(self):
        prompt = build_tutor_prompt(make_tutor_request(grade_level="9"))
        self.assertIn("Grade level: 9", prompt.user)
        self.assertEqual(prompt.version, TUTOR_PROMPT_VERSION)
        self.assertIn(TUTOR_PROMPT_VERSION, prompt.system)

    def test_prompt_contains_recent_conversation(self):
        prompt = build_tutor_prompt(
            make_tutor_request(
                recent_messages=(
                    TutorConversationMessage(
                        role="student", content="I confused speed and acceleration."
                    ),
                )
            )
        )
        self.assertIn("I confused speed and acceleration.", prompt.user)

    def test_prompt_instructs_structured_json_and_guidance(self):
        prompt = build_tutor_prompt(make_tutor_request())
        lowered = prompt.system.lower()
        self.assertIn("json", lowered)
        self.assertIn("si unit", lowered)
        self.assertIn("guiding question", lowered)


class _BoomProvider(AIProvider):
    name = "boom"
    model = "boom"

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        raise AIProviderError("provider is offline")


class TutorServiceTests(TutorDataMixin, TestCase):
    def test_fake_provider_returns_valid_tutoring_result(self):
        result = tutor_student(make_tutor_request(), provider=FakeTutorProvider())

        self.assertIsInstance(result.response, TutorResponse)
        self.assertIn(result.response.mode, {"explain", "hint", "question", "feedback", "solution", "practice"})
        self.assertEqual(result.provider_name, "fake")
        self.assertEqual(result.prompt_version, TUTOR_PROMPT_VERSION)
        self.assertTrue(result.response.concept)

    @override_settings(AI_PROVIDER="fake")
    def test_default_provider_is_the_local_fake(self):
        result = tutor_student(make_tutor_request())
        self.assertEqual(result.provider_name, "fake")
        self.assertIsInstance(get_tutor_provider(), FakeTutorProvider)

    def test_provider_failure_is_raised(self):
        with self.assertRaises(AIProviderError):
            tutor_student(make_tutor_request(), provider=_BoomProvider())

    def test_malformed_ai_output_is_rejected(self):
        with self.assertRaises(InvalidTutorResponseError):
            tutor_student(
                make_tutor_request(),
                provider=FakeTutorProvider(response="not json at all"),
            )

    def test_ai_output_failing_schema_is_rejected(self):
        bad = json.dumps({"mode": "bogus", "message": "x"})
        with self.assertRaises(InvalidTutorResponseError):
            tutor_student(make_tutor_request(), provider=FakeTutorProvider(response=bad))

    def test_run_tutor_turn_persists_both_messages_and_evidence(self):
        session = self.make_session()

        tutor_message, result = run_tutor_turn(
            session, student_question="What is acceleration?"
        )

        roles = list(session.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["student", "tutor"])
        self.assertEqual(tutor_message.content, result.response.message)
        self.assertEqual(tutor_message.mode, result.response.mode)
        evidence = LearningEvidence.objects.get(session=session)
        self.assertEqual(evidence.kind, LearningEvidence.Kind.QUESTION_ASKED)
        self.assertEqual(evidence.tutor_mode, result.response.mode)

    def test_run_tutor_turn_rejects_empty_message(self):
        session = self.make_session()
        with self.assertRaises(EmptyTutorMessageError):
            run_tutor_turn(session, student_question="   ")
        self.assertEqual(session.messages.count(), 0)

    def test_practice_turn_records_practice_evidence(self):
        session = self.make_session()

        run_tutor_turn(
            session,
            practice_problem="A cart accelerates from 2 m/s to 8 m/s in 3 s.",
            student_attempt="a = (8 - 2) / 3 = 2 m/s^2",
        )

        evidence = LearningEvidence.objects.get(session=session)
        self.assertEqual(evidence.kind, LearningEvidence.Kind.PRACTICE_ATTEMPTED)
        self.assertEqual(
            session.messages.filter(role=TutorMessage.Role.STUDENT).first().content,
            "a = (8 - 2) / 3 = 2 m/s^2",
        )


@override_settings(AI_PROVIDER="fake")
class TutorViewTests(TutorDataMixin, TestCase):
    def setUp(self):
        self.lesson = self.make_lesson()
        self.url = reverse("students:tutor", args=[self.lesson.slug])

    def test_tutor_page_loads(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motion Basics")
        self.assertContains(response, "Ask Physics Tutor")
        self.assertContains(response, "Try a problem")

    def test_student_question_post_works(self):
        response = self.client.post(
            self.url, {"action": "ask", "question": "What is acceleration?"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acceleration is the rate at which")

    def test_student_message_is_persisted(self):
        self.client.post(
            self.url, {"action": "ask", "question": "What is acceleration?"}
        )

        student_messages = TutorMessage.objects.filter(role=TutorMessage.Role.STUDENT)
        self.assertEqual(student_messages.count(), 1)
        self.assertEqual(student_messages.first().content, "What is acceleration?")

    def test_tutor_response_is_persisted(self):
        self.client.post(
            self.url, {"action": "ask", "question": "What is acceleration?"}
        )

        tutor_messages = TutorMessage.objects.filter(role=TutorMessage.Role.TUTOR)
        self.assertEqual(tutor_messages.count(), 1)
        self.assertTrue(tutor_messages.first().mode)

    def test_conversation_reappears_after_refresh(self):
        self.client.post(
            self.url, {"action": "ask", "question": "What is acceleration?"}
        )

        refreshed = self.client.get(self.url)
        self.assertContains(refreshed, "What is acceleration?")
        self.assertContains(refreshed, "Acceleration is the rate at which")

    def test_get_does_not_mutate_conversation(self):
        self.client.get(self.url)
        self.client.get(self.url)

        self.assertEqual(TutorMessage.objects.count(), 0)

    def test_guidance_mode_is_used_for_confusion(self):
        response = self.client.post(
            self.url,
            {
                "action": "ask",
                "question": "I don't understand how to solve an acceleration problem.",
            },
        )

        self.assertContains(response, "step by step")
        tutor_message = TutorMessage.objects.filter(role=TutorMessage.Role.TUTOR).first()
        self.assertEqual(tutor_message.mode, "hint")
        self.assertTrue(tutor_message.data.get("next_question"))

    def test_practice_attempt_can_be_submitted(self):
        response = self.client.post(
            self.url,
            {"action": "practice", "problem_index": "0", "attempt": "a = 2 m/s^2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
            ).count(),
            1,
        )

    def test_practice_feedback_is_displayed(self):
        response = self.client.post(
            self.url,
            {"action": "practice", "problem_index": "0", "attempt": "a = 2 m/s^2"},
        )

        self.assertContains(response, "Good start.")
        self.assertContains(response, "feedback")

    def test_empty_question_shows_friendly_error(self):
        response = self.client.post(self.url, {"action": "ask", "question": "   "})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, EMPTY_QUESTION_MESSAGE)
        self.assertEqual(TutorMessage.objects.count(), 0)

    def test_provider_failure_shows_friendly_error(self):
        with override_settings(AI_PROVIDER="fake"):
            from unittest.mock import patch

            with patch(
                "apps.students.views.run_tutor_turn", side_effect=AIProviderError("down")
            ):
                response = self.client.post(
                    self.url, {"action": "ask", "question": "What is acceleration?"}
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TUTOR_ERROR_MESSAGE)
        self.assertNotContains(response, "Traceback")


class StudentEntryViewTests(TutorDataMixin, TestCase):
    def test_student_home_lists_lessons(self):
        self.make_lesson()
        response = self.client.get(reverse("students:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motion Basics")

    def test_student_lessons_page_links_to_tutor(self):
        lesson = self.make_lesson()
        response = self.client.get(reverse("students:lessons"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("students:tutor", args=[lesson.slug]))
