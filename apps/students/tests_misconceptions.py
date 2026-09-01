import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.ai.exceptions import AIProviderError
from apps.ai.providers import AIProvider
from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept, PhysicsMisconception

from .exceptions import InvalidMisconceptionAssessmentError, MisconceptionDecisionError
from .misconception_prompts import (
    MISCONCEPTION_PROMPT_VERSION,
    build_misconception_prompt,
)
from .misconception_providers import FakeMisconceptionProvider, get_misconception_provider
from .misconception_rules import detect_misconceptions
from .misconception_schemas import (
    MisconceptionAssessment,
    MisconceptionAssessmentBatch,
    example_misconception_assessment_dict,
)
from .misconception_services import (
    active_candidates_for_lesson,
    apply_teacher_decision,
    assess_student_misconceptions,
    scrub_excerpt,
)
from .models import (
    LearningEvidence,
    MisconceptionEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
    TutorSession,
)
from .prompts import build_tutor_prompt
from .providers import FakeTutorProvider
from .requests import CandidateHint, TutorRequest
from .services import run_tutor_turn

FREE_FALL = "FREE_FALL_MASS_ACCELERATION"
FORCE_ACCEL = "FORCE_VS_ACCELERATION"
DIST_DISP = "DISTANCE_VS_DISPLACEMENT"


class _BoomAIProvider(AIProvider):
    name = "boom"
    model = "boom"

    def generate(self, prompt: str, *, system_prompt: str = "") -> str:
        raise AIProviderError("assessment provider offline")


class MisconceptionDataMixin:
    CONCEPTS = {
        "Acceleration": "The rate of change of velocity with respect to time.",
        "Newton's Second Law": "An object's acceleration is set by the net force and its mass.",
        "Displacement": "The change in position, including direction.",
    }
    CATALOG = {
        FREE_FALL: ("Acceleration", "Mass determines free-fall acceleration",
                    "A learner may believe a heavier object falls faster in free fall."),
        FORCE_ACCEL: ("Newton's Second Law", "Force and acceleration are the same quantity",
                      "A learner may treat force and acceleration as interchangeable."),
        DIST_DISP: ("Displacement", "Distance and displacement are always identical",
                    "A learner may believe distance and displacement are always equal."),
    }

    def seed_catalog(self):
        self.concepts = {}
        for name, description in self.CONCEPTS.items():
            self.concepts[name] = PhysicsConcept.objects.create(
                name=name, description=description, topic="Kinematics"
            )
        self.catalog = {}
        for code, (concept_name, title, description) in self.CATALOG.items():
            self.catalog[code] = PhysicsMisconception.objects.create(
                code=code,
                title=title,
                description=description,
                physics_concept=self.concepts[concept_name],
                intervention_guidance=f"Use a controlled comparison for {concept_name}.",
            )

    def make_lesson(self, *, concepts=None):
        lesson = Lesson.objects.create(
            title="Free Fall",
            topic="Kinematics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Explain free fall."],
            problems=["Two balls of different mass are dropped in a vacuum. Compare them."],
        )
        for name in (concepts or list(self.CONCEPTS)):
            lesson.physics_concepts.add(self.concepts[name])
        return lesson

    def make_student(self, name="Example Student"):
        return StudentProfile.objects.create(display_name=name)

    def make_session(self, lesson=None, student=None):
        lesson = lesson or self.make_lesson()
        student = student or self.make_student()
        return TutorSession.objects.create(student=student, lesson=lesson)


# --- DOMAIN --------------------------------------------------------------------


class MisconceptionDomainTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()

    def test_physics_misconception_creation(self):
        entry = self.catalog[FREE_FALL]
        self.assertEqual(entry.code, FREE_FALL)
        self.assertTrue(entry.is_active)
        self.assertIn(FREE_FALL, str(entry))

    def test_misconception_linked_to_physics_concept(self):
        entry = self.catalog[FREE_FALL]
        self.assertEqual(entry.physics_concept.name, "Acceleration")
        self.assertIn(entry, self.concepts["Acceleration"].misconceptions.all())

    def test_student_misconception_creation_defaults(self):
        student = self.make_student()
        obs = StudentMisconception.objects.create(
            student=student, misconception=self.catalog[FREE_FALL]
        )
        self.assertEqual(obs.confidence, StudentMisconception.Confidence.LOW)
        self.assertEqual(obs.status, StudentMisconception.Status.CANDIDATE)
        self.assertEqual(obs.observation_count, 0)
        self.assertFalse(obs.is_teacher_decided)

    def test_confidence_and_status_validation(self):
        student = self.make_student()
        obs = StudentMisconception(
            student=student, misconception=self.catalog[FREE_FALL]
        )
        obs.confidence = "certain"
        with self.assertRaises(ValidationError):
            obs.full_clean()
        obs.confidence = StudentMisconception.Confidence.MEDIUM
        obs.status = "guessed"
        with self.assertRaises(ValidationError):
            obs.full_clean()

    def test_duplicate_student_misconception_is_prevented(self):
        student = self.make_student()
        StudentMisconception.objects.create(
            student=student, misconception=self.catalog[FREE_FALL]
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentMisconception.objects.create(
                    student=student, misconception=self.catalog[FREE_FALL]
                )


# --- EVIDENCE ----------------------------------------------------------------


class MisconceptionEvidenceTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()
        self.session = self.make_session()
        self.observation = StudentMisconception.objects.create(
            student=self.session.student, misconception=self.catalog[FREE_FALL]
        )

    def test_evidence_links_to_learning_evidence(self):
        learning = LearningEvidence.objects.create(
            student=self.session.student,
            lesson=self.session.lesson,
            session=self.session,
            kind=LearningEvidence.Kind.QUESTION_ASKED,
            detail="Heavier objects fall faster.",
        )
        evidence = MisconceptionEvidence.objects.create(
            observation=self.observation,
            learning_evidence=learning,
            source=MisconceptionEvidence.Source.RULE,
            detector="rule:free_fall_mass_acceleration",
            excerpt="Heavier objects fall faster.",
        )
        self.assertEqual(evidence.learning_evidence, learning)
        self.assertIn(evidence, learning.misconception_evidence.all())
        self.assertIn(evidence, self.observation.evidence.all())

    def test_evidence_excerpt_is_persisted(self):
        MisconceptionEvidence.objects.create(
            observation=self.observation,
            source=MisconceptionEvidence.Source.AI,
            detector=MISCONCEPTION_PROMPT_VERSION,
            excerpt="A heavier ball reaches the ground first.",
            reasoning="Links mass to fall speed.",
        )
        stored = self.observation.evidence.get()
        self.assertEqual(stored.excerpt, "A heavier ball reaches the ground first.")
        self.assertEqual(stored.reasoning, "Links mass to fall speed.")

    def test_scrub_excerpt_removes_secrets_and_truncates(self):
        out = scrub_excerpt("token sk-ABC123DEF456 and api_key=HUNTER2 fine")
        self.assertNotIn("sk-ABC123DEF456", out)
        self.assertNotIn("HUNTER2", out)
        self.assertIn("[redacted]", out)

        long_out = scrub_excerpt("x " * 400)
        self.assertLessEqual(len(long_out), 300)


# --- RULE DETECTION --------------------------------------------------------


class RuleDetectionTests(SimpleTestCase):
    def test_free_fall_rule_detects_candidate(self):
        signals = detect_misconceptions(
            evidence="I think heavier objects fall faster than lighter ones."
        )
        self.assertEqual([s.code for s in signals], [FREE_FALL])

    def test_force_vs_acceleration_rule_detects_candidate(self):
        signals = detect_misconceptions(
            evidence="Force is the same thing as acceleration, right?"
        )
        self.assertIn(FORCE_ACCEL, [s.code for s in signals])

    def test_distance_vs_displacement_rule_detects_candidate(self):
        signals = detect_misconceptions(
            evidence="Distance and displacement are always the same."
        )
        self.assertIn(DIST_DISP, [s.code for s in signals])

    def test_unrelated_evidence_creates_no_candidate(self):
        signals = detect_misconceptions(
            evidence="Velocity is the rate of change of displacement."
        )
        self.assertEqual(signals, ())

    def test_correct_free_fall_statement_is_not_flagged(self):
        signals = detect_misconceptions(
            evidence="In a vacuum all objects fall at the same rate regardless of mass."
        )
        self.assertEqual(signals, ())

    def test_concept_scope_filters_rules(self):
        signals = detect_misconceptions(
            evidence="Heavier objects fall faster.",
            concept_names={"Displacement"},
        )
        self.assertEqual(signals, ())


class RuleConfidenceTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()
        self.lesson = self.make_lesson()
        self.student = self.make_student()

    def test_single_weak_signal_yields_low_confidence(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="heavier things fall faster",
            use_ai=False,
        )
        self.assertEqual(len(outcomes), 1)
        obs = outcomes[0].observation
        self.assertEqual(obs.confidence, StudentMisconception.Confidence.LOW)
        self.assertEqual(obs.observation_count, 1)

    def test_repeated_evidence_increases_confidence(self):
        for _ in range(2):
            assess_student_misconceptions(
                student=self.student,
                lesson=self.lesson,
                text="heavier objects fall faster",
                use_ai=False,
            )
        obs = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(obs.observation_count, 2)
        self.assertEqual(obs.confidence, StudentMisconception.Confidence.MEDIUM)

        assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="heavier objects fall faster",
            use_ai=False,
        )
        obs.refresh_from_db()
        self.assertEqual(obs.observation_count, 3)
        self.assertEqual(obs.confidence, StudentMisconception.Confidence.HIGH)

    def test_two_independent_detectors_yield_medium(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="heavier objects fall faster",
            use_ai=True,
        )
        obs = outcomes[0].observation
        self.assertEqual(obs.observation_count, 1)
        self.assertGreaterEqual(obs.evidence.count(), 2)
        self.assertEqual(obs.confidence, StudentMisconception.Confidence.MEDIUM)


# --- AI --------------------------------------------------------------------


class MisconceptionAssessmentSchemaTests(SimpleTestCase):
    def test_valid_ai_assessment_validates(self):
        batch = MisconceptionAssessmentBatch.from_dict(
            example_misconception_assessment_dict()
        )
        self.assertEqual(len(batch.assessments), 1)
        assessment = batch.assessments[0]
        self.assertEqual(assessment.candidate_code, FREE_FALL)
        self.assertEqual(assessment.evidence_strength, "moderate")
        self.assertTrue(assessment.has_evidence)

    def test_missing_assessments_key_is_rejected(self):
        with self.assertRaises(InvalidMisconceptionAssessmentError):
            MisconceptionAssessmentBatch.from_dict({})

    def test_non_list_assessments_is_rejected(self):
        with self.assertRaises(InvalidMisconceptionAssessmentError):
            MisconceptionAssessmentBatch.from_dict({"assessments": "nope"})

    def test_invalid_evidence_strength_is_rejected(self):
        with self.assertRaises(InvalidMisconceptionAssessmentError):
            MisconceptionAssessmentBatch.from_dict(
                {
                    "assessments": [
                        {
                            "candidate_code": "X",
                            "evidence_strength": "enormous",
                            "confidence": "low",
                            "reasoning": "r",
                        }
                    ]
                }
            )

    def test_unexpected_field_is_rejected(self):
        with self.assertRaises(InvalidMisconceptionAssessmentError):
            MisconceptionAssessment.from_dict(
                {
                    "candidate_code": "X",
                    "evidence_strength": "weak",
                    "confidence": "low",
                    "reasoning": "r",
                    "answer_key": "42",
                }
            )


class FakeMisconceptionProviderTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()

    def _prompt_for(self, *excerpts):
        return build_misconception_prompt(
            lesson_title="Free Fall",
            topic="Kinematics",
            grade_level="11",
            catalog=tuple(
                (row.code, row.title, row.description)
                for row in PhysicsMisconception.objects.all()
            ),
            student_excerpts=excerpts,
        )

    def test_fake_provider_flags_free_fall_without_network(self):
        prompt = self._prompt_for("Heavier objects fall faster than light ones.")
        raw = FakeMisconceptionProvider().generate(
            prompt.user, system_prompt=prompt.system
        )
        batch = MisconceptionAssessmentBatch.from_dict(json.loads(raw))
        self.assertIn(FREE_FALL, [a.candidate_code for a in batch.assessments])

    def test_fake_provider_returns_empty_for_correct_answer(self):
        prompt = self._prompt_for("Acceleration in free fall does not depend on mass.")
        raw = FakeMisconceptionProvider().generate(
            prompt.user, system_prompt=prompt.system
        )
        batch = MisconceptionAssessmentBatch.from_dict(json.loads(raw))
        self.assertEqual(batch.assessments, ())

    def test_fixed_response_is_used_when_supplied(self):
        provider = FakeMisconceptionProvider(response='{"assessments": []}')
        self.assertEqual(provider.generate("anything"), '{"assessments": []}')

    @override_settings(AI_PROVIDER="fake")
    def test_get_misconception_provider_returns_fake(self):
        self.assertIsInstance(get_misconception_provider(), FakeMisconceptionProvider)


class MisconceptionServiceTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()
        self.lesson = self.make_lesson()
        self.student = self.make_student()

    def test_rule_based_assessment_works_without_ai(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="Heavier objects fall faster.",
            use_ai=False,
        )
        self.assertEqual(len(outcomes), 1)
        obs = outcomes[0].observation
        sources = list(obs.evidence.values_list("source", flat=True))
        self.assertEqual(sources, [MisconceptionEvidence.Source.RULE])

    def test_ai_provider_failure_is_handled(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="Heavier objects fall faster.",
            use_ai=True,
            provider=_BoomAIProvider(),
        )
        self.assertEqual(len(outcomes), 1)
        obs = outcomes[0].observation
        self.assertEqual(
            list(obs.evidence.values_list("source", flat=True)),
            [MisconceptionEvidence.Source.RULE],
        )

    def test_malformed_ai_output_is_ignored_safely(self):
        provider = FakeMisconceptionProvider(response="not json at all")
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="Heavier objects fall faster.",
            use_ai=True,
            provider=provider,
        )
        # Rule signal still recorded; bad AI output did not crash the pass.
        self.assertEqual(len(outcomes), 1)

    def test_combined_assessment_records_rule_and_ai_evidence(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="Heavier objects fall faster.",
            use_ai=True,
        )
        obs = outcomes[0].observation
        sources = set(obs.evidence.values_list("source", flat=True))
        self.assertEqual(
            sources,
            {MisconceptionEvidence.Source.RULE, MisconceptionEvidence.Source.AI},
        )

    def test_existing_observation_updates_rather_than_duplicates(self):
        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="Heavier objects fall faster.", use_ai=True,
        )
        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="A heavier ball hits the ground first.", use_ai=True,
        )
        self.assertEqual(
            StudentMisconception.objects.filter(student=self.student).count(), 1
        )
        obs = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(obs.observation_count, 2)
        self.assertGreaterEqual(obs.evidence.count(), 3)

    def test_assessment_never_auto_confirms(self):
        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="Heavier objects fall faster.", use_ai=True,
        )
        obs = StudentMisconception.objects.get(student=self.student)
        self.assertEqual(obs.status, StudentMisconception.Status.CANDIDATE)

    def test_teacher_decision_keeps_status_after_more_evidence(self):
        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="Heavier objects fall faster.", use_ai=False,
        )
        obs = StudentMisconception.objects.get(student=self.student)
        apply_teacher_decision(obs, "confirm")
        obs.refresh_from_db()
        self.assertEqual(obs.status, StudentMisconception.Status.CONFIRMED_BY_TEACHER)

        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="Heavier objects fall faster.", use_ai=False,
        )
        obs.refresh_from_db()
        self.assertEqual(obs.status, StudentMisconception.Status.CONFIRMED_BY_TEACHER)
        self.assertEqual(obs.observation_count, 2)

    def test_apply_teacher_decision_rejects_unknown_choice(self):
        assess_student_misconceptions(
            student=self.student, lesson=self.lesson,
            text="Heavier objects fall faster.", use_ai=False,
        )
        obs = StudentMisconception.objects.get(student=self.student)
        with self.assertRaises(MisconceptionDecisionError):
            apply_teacher_decision(obs, "maybe")

    def test_correct_answer_creates_no_observation(self):
        outcomes = assess_student_misconceptions(
            student=self.student,
            lesson=self.lesson,
            text="In a vacuum, all objects fall at the same rate regardless of mass.",
            use_ai=True,
        )
        self.assertEqual(outcomes, [])
        self.assertEqual(StudentMisconception.objects.count(), 0)


# --- TUTOR INTEGRATION ---------------------------------------------------


class TutorMisconceptionIntegrationTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()
        self.lesson = self.make_lesson()
        self.session = self.make_session(lesson=self.lesson)

    def test_candidate_influences_tutor_prompt_context(self):
        hint = CandidateHint(
            concept="Acceleration",
            title="Mass determines free-fall acceleration",
            description="A learner may believe heavier objects fall faster.",
            intervention_guidance="Compare two masses dropped in a vacuum.",
        )
        request = TutorRequest(
            lesson_title="Free Fall",
            topic="Kinematics",
            grade_level="11",
            candidate_misconceptions=(hint,),
            student_question="Why do things fall?",
        )
        prompt = build_tutor_prompt(request)
        self.assertIn("Compare two masses dropped in a vacuum.", prompt.user)
        self.assertIn("do NOT name these to the student", prompt.user)

    def test_active_candidate_reaches_run_tutor_turn_context(self):
        StudentMisconception.objects.create(
            student=self.session.student,
            misconception=self.catalog[FREE_FALL],
            observation_count=1,
        )
        provider = FakeTutorProvider()
        run_tutor_turn(
            self.session,
            student_question="Do heavier things fall faster?",
            provider=provider,
        )
        sent_prompt = provider.calls[0]["prompt"]
        self.assertIn("heavier object falls faster", sent_prompt.lower())

    def test_student_facing_reply_hides_internal_labels(self):
        StudentMisconception.objects.create(
            student=self.session.student,
            misconception=self.catalog[FREE_FALL],
            observation_count=1,
        )
        tutor_message, _ = run_tutor_turn(
            self.session,
            student_question="Heavier objects fall faster, right?",
            provider=FakeTutorProvider(),
        )
        self.assertNotIn(FREE_FALL, tutor_message.content)
        self.assertNotIn("misconception", tutor_message.content.lower())

    def test_tutor_turn_records_misconception_candidate(self):
        run_tutor_turn(
            self.session,
            student_question="I think heavier objects fall faster than light ones.",
            provider=FakeTutorProvider(),
        )
        obs = StudentMisconception.objects.get(student=self.session.student)
        self.assertEqual(obs.misconception.code, FREE_FALL)
        self.assertGreaterEqual(obs.observation_count, 1)
        self.assertTrue(obs.evidence.exists())
        self.assertEqual(obs.status, StudentMisconception.Status.CANDIDATE)

    def test_practice_attempt_still_works_and_is_assessed(self):
        run_tutor_turn(
            self.session,
            practice_problem="Compare two dropped masses.",
            student_attempt="The heavier ball will fall faster and land first.",
            provider=FakeTutorProvider(),
        )
        self.assertTrue(
            LearningEvidence.objects.filter(
                session=self.session, kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED
            ).exists()
        )
        self.assertTrue(
            StudentMisconception.objects.filter(student=self.session.student).exists()
        )

    def test_learning_evidence_still_works(self):
        run_tutor_turn(
            self.session,
            student_question="What is acceleration?",
            provider=FakeTutorProvider(),
        )
        self.assertEqual(
            LearningEvidence.objects.filter(
                session=self.session, kind=LearningEvidence.Kind.QUESTION_ASKED
            ).count(),
            1,
        )

    def test_existing_tutor_conversation_still_works(self):
        run_tutor_turn(self.session, student_question="What is acceleration?",
                       provider=FakeTutorProvider())
        run_tutor_turn(self.session, student_question="How is it measured?",
                       provider=FakeTutorProvider())
        roles = list(self.session.messages.values_list("role", flat=True))
        self.assertEqual(roles, ["student", "tutor", "student", "tutor"])

    def test_normal_question_creates_no_misconception(self):
        run_tutor_turn(
            self.session,
            student_question="Acceleration is measured in metres per second squared.",
            provider=FakeTutorProvider(),
        )
        self.assertFalse(
            StudentMisconception.objects.filter(student=self.session.student).exists()
        )

    def test_active_candidates_for_lesson_scopes_by_concept(self):
        other_lesson = self.make_lesson(concepts=["Displacement"])
        StudentMisconception.objects.create(
            student=self.session.student,
            misconception=self.catalog[FREE_FALL],  # Acceleration concept
            observation_count=1,
        )
        self.assertEqual(
            len(active_candidates_for_lesson(self.session.student, self.lesson)), 1
        )
        self.assertEqual(
            len(active_candidates_for_lesson(self.session.student, other_lesson)), 0
        )


# --- TEACHER VISIBILITY ------------------------------------------------


@override_settings(AI_PROVIDER="fake")
class TeacherInsightViewTests(MisconceptionDataMixin, TestCase):
    def setUp(self):
        self.seed_catalog()
        self.lesson = self.make_lesson()
        self.session = self.make_session(lesson=self.lesson)
        self.observation = StudentMisconception.objects.create(
            student=self.session.student,
            misconception=self.catalog[FREE_FALL],
            confidence=StudentMisconception.Confidence.MEDIUM,
            observation_count=2,
            evidence_summary="2 turn(s).",
        )
        MisconceptionEvidence.objects.create(
            observation=self.observation,
            source=MisconceptionEvidence.Source.RULE,
            detector="rule:free_fall_mass_acceleration",
            excerpt="Heavier objects fall faster.",
        )
        self.insights_url = reverse("students:insights", args=[self.lesson.slug])

    def test_insights_page_loads_with_possible_language(self):
        response = self.client.get(self.insights_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Possible misconceptions")
        self.assertContains(response, "Example Student")
        self.assertContains(response, "Medium confidence")
        self.assertNotContains(response, "%")

    def test_insights_does_not_leak_to_student_tutor_page(self):
        tutor_response = self.client.get(
            reverse("students:tutor", args=[self.lesson.slug])
        )
        self.assertNotContains(tutor_response, FREE_FALL)
        self.assertNotContains(tutor_response, "Possible misconception")

    def test_teacher_can_confirm_candidate(self):
        url = reverse(
            "students:misconception_decision",
            args=[self.lesson.slug, self.observation.id],
        )
        response = self.client.post(url, {"decision": "confirm", "note": "Seen in class."})
        self.assertEqual(response.status_code, 200)
        self.observation.refresh_from_db()
        self.assertEqual(
            self.observation.status,
            StudentMisconception.Status.CONFIRMED_BY_TEACHER,
        )
        self.assertIsNotNone(self.observation.decided_at)
        self.assertEqual(self.observation.teacher_note, "Seen in class.")

    def test_teacher_can_dismiss_candidate(self):
        url = reverse(
            "students:misconception_decision",
            args=[self.lesson.slug, self.observation.id],
        )
        self.client.post(url, {"decision": "dismiss"})
        self.observation.refresh_from_db()
        self.assertEqual(
            self.observation.status, StudentMisconception.Status.DISMISSED
        )

    def test_invalid_decision_is_rejected(self):
        url = reverse(
            "students:misconception_decision",
            args=[self.lesson.slug, self.observation.id],
        )
        response = self.client.post(url, {"decision": "banish"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose confirm, dismiss, or resolve")
        self.observation.refresh_from_db()
        self.assertEqual(
            self.observation.status, StudentMisconception.Status.CANDIDATE
        )

    def test_lesson_detail_links_to_insights(self):
        response = self.client.get(
            reverse("lessons:detail", args=[self.lesson.slug])
        )
        self.assertContains(response, self.insights_url)
