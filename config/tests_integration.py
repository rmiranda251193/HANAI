"""Step 30 -- end-to-end MVP integration.

One test drives the whole conceptual pipeline through the real services and
views: a teacher authors and publishes a lesson with AI assistance, a student
learns through the Physics Lab, a misconception recovery produces more evidence,
and that same evidence surfaces in the teacher evidence workspace and in cohort
analytics -- with the provenance trail intact. The other tests are focused
"golden path" checks for each half of the product.

Everything runs offline (``AI_PROVIDER="fake"``); nothing here is a second
integration framework -- it is ordinary Django test code over the existing
systems.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.assessments.models import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    QuestionBankItem,
)
from apps.lessons.models import Lesson
from apps.physics.models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)
from apps.provenance.models import GeneratedLessonDraft, PersistedReviewIssue, ProvenanceEvent
from apps.students.experiment_services import (
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
    complete_experiment,
)
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentProfile,
)
from apps.students.recovery_services import (
    get_or_create_recovery_for_observation,
    record_concept_check_response,
)
from apps.teachers.analytics_services import get_cohort_analytics, resolve_analytics_filters
from apps.teachers.services import build_teacher_student_evidence

User = get_user_model()
Kind = LearningEvidence.Kind
Ev = ProvenanceEvent.EventType


@override_settings(
    AI_PROVIDER="fake",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HanaiMvpPipelineTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("mvp_teacher", password="pw", is_staff=True)
        # The FakeAIProvider's canned v2 draft references these; seeding them
        # keeps the deterministic review to exactly the one AI-authored issue.
        self.concept = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force equals mass times acceleration.",
            topic="Dynamics",
            equations=["F_net = ma"],
            si_units=["newton (N)"],
        )
        self.misconception = PhysicsMisconception.objects.create(
            code="FORCE_VS_ACCELERATION",
            title="A force always means acceleration",
            description="Treating 'a force acts' as 'the object accelerates'.",
            physics_concept=self.concept,
        )
        self.simulation = PhysicsSimulation.objects.create(
            concept=self.concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        self.student = StudentProfile.objects.create(display_name="Mia")

    # --- the full pipeline --------------------------------------

    def test_teacher_authors_publishes_then_student_learning_flows_to_analytics(self):
        client = self.client
        client.force_login(self.teacher)

        # 1. Teacher creates a lesson and links a concept + objective.
        lesson = Lesson.objects.create(
            title="Understanding Newton's Second Law",
            topic="Dynamics",
            grade_level="11",
            duration_minutes=45,
            learning_objectives=["Relate net force, mass, and acceleration."],
            common_misconceptions=["A force always causes motion."],
            created_by=self.teacher,
            status=Lesson.Status.DRAFT,
        )
        lesson.physics_concepts.add(self.concept)

        # 2. Generate an AI draft (fake provider) -- lesson content is untouched.
        self.assertEqual(
            client.post(reverse("lessons:generate", args=[lesson.slug])).status_code, 200
        )
        draft = GeneratedLessonDraft.objects.get(lesson=lesson)
        lesson.refresh_from_db()
        self.assertEqual(lesson.content, {})  # generation never publishes
        self.assertEqual(draft.prompt_version, "lesson-generation-v2")

        # 3. Run and persist the AI review, then decide every finding.
        self.assertEqual(
            client.post(
                reverse("lessons:review", args=[lesson.slug, draft.pk])
            ).status_code,
            200,
        )
        issues = list(PersistedReviewIssue.objects.filter(review__draft=draft))
        self.assertTrue(issues)
        review_id = issues[0].review_id
        for issue in issues:
            client.post(
                reverse(
                    "lessons:review_issue_decision", args=[lesson.slug, draft.pk, issue.pk]
                ),
                {"decision": "accepted"},
            )

        # 4. Finalize -> approved AI content becomes lesson.content (still a draft).
        self.assertEqual(
            client.post(
                reverse("lessons:finalize", args=[lesson.slug, draft.pk, review_id])
            ).status_code,
            200,
        )
        lesson.refresh_from_db()
        self.assertTrue(lesson.content)  # finalized sections copied in
        self.assertNotEqual(lesson.status, Lesson.Status.PUBLISHED)  # publish is separate

        # 5. Explicit teacher publish (Step 26 builder uses Post/Redirect/Get).
        publish_response = client.post(reverse("lessons:publish", args=[lesson.slug]))
        self.assertIn(publish_response.status_code, (200, 302))
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.PUBLISHED)

        # 6. The student can now see the published lesson.
        student_lessons = client_get_as_guest(self, reverse("students:lessons"))
        self.assertContains(student_lessons, lesson.slug)
        self.assertContains(student_lessons, "status-published")

        # 7. Student does a full Physics Lab investigation -> evidence.
        record_experiment_prediction(
            student=self.student,
            simulation=self.simulation,
            prediction="If the net force doubles, the acceleration doubles.",
            lesson=lesson,
        )
        attempt, _ = record_experiment_observation(
            student=self.student,
            simulation=self.simulation,
            observation="Doubling the force from 10 N to 20 N doubled the acceleration.",
            lesson=lesson,
            mass_kg=2.0,
            force_n=20.0,
        )
        record_experiment_explanation(
            student=self.student,
            simulation=self.simulation,
            explanation="a = F_net / m, so more net force at the same mass means more acceleration.",
            lesson=lesson,
            assess=False,
        )
        complete_experiment(attempt)

        lab_kinds = set(
            LearningEvidence.objects.filter(student=self.student).values_list(
                "kind", flat=True
            )
        )
        self.assertEqual(
            {Kind.PREDICTION_SUBMITTED, Kind.EXPERIMENT_OBSERVED, Kind.EXPLANATION_SUBMITTED},
            lab_kinds,
        )
        self.assertEqual(
            ExperimentAttempt.objects.filter(
                student=self.student, completed_at__isnull=False
            ).count(),
            1,
        )

        # 8. A misconception candidate leads to a recovery that produces more
        #    evidence -- and recovery completion is NOT resolution.
        observation = StudentMisconception.objects.create(
            student=self.student,
            misconception=self.misconception,
            status=StudentMisconception.Status.CANDIDATE,
            observation_count=2,
        )
        path = MisconceptionRecoveryPath.objects.create(
            misconception=self.misconception, title="Confront balanced vs unbalanced forces",
            student_summary="Let's separate 'a force acts' from 'it speeds up'.",
        )
        check = MisconceptionRecoveryActivity.objects.create(
            path=path, order=1, activity_type=MisconceptionRecoveryActivity.ActivityType.CONCEPT_CHECK,
            label="Balanced forces", check_prompt="Two equal opposite forces act. Does it accelerate?",
            check_choices=["No -- net force is zero", "Yes -- forces are present"],
            check_correct_choice=0,
        )
        recovery = get_or_create_recovery_for_observation(observation)
        self.assertIsNotNone(recovery)
        result = record_concept_check_response(
            student=self.student, recovery=recovery, activity=check,
            submitted_choice="No -- net force is zero",
        )
        self.assertTrue(result["is_correct"])

        recovery.refresh_from_db()
        observation.refresh_from_db()
        self.assertIsNotNone(recovery.completed_at)  # recovery finished
        self.assertEqual(
            observation.status, StudentMisconception.Status.CANDIDATE
        )  # still only a candidate -- a teacher decision resolves it
        self.assertTrue(
            LearningEvidence.objects.filter(
                student=self.student, kind=Kind.RECOVERY_ACTIVITY_COMPLETED
            ).exists()
        )

        # 9. The teacher evidence workspace reflects everything.
        evidence = build_teacher_student_evidence(student=self.student)
        self.assertTrue(evidence["has_activity"])
        self.assertTrue(evidence["recovery_evidence"])
        self.assertTrue(any(c["observation"].pk == observation.pk for c in evidence["candidates"]))

        # 10. Cohort analytics aggregates the same evidence.
        snapshot = get_cohort_analytics(resolve_analytics_filters({}))
        activity = {r.label: r.value for r in snapshot.activity_summary}
        self.assertGreaterEqual(activity["Predictions submitted"], 1)
        self.assertGreaterEqual(activity["Explanations submitted"], 1)
        self.assertGreaterEqual(activity["Recovery activities completed"], 1)
        self.assertGreaterEqual(snapshot.active_student_count, 1)
        recovery_summary = {r.label: r.value for r in snapshot.recovery_summary}
        self.assertEqual(recovery_summary["Recovery paths started"], 1)
        self.assertEqual(recovery_summary["Recovery paths completed"], 1)
        self.assertEqual(
            recovery_summary["Misconceptions resolved by a teacher decision"], 0
        )

        # 11. Provenance can reconstruct the AI -> review -> decide -> publish chain.
        events = list(
            ProvenanceEvent.objects.filter(lesson=lesson)
            .order_by("created_at")
            .values_list("event_type", flat=True)
        )
        for expected in (
            Ev.AI_DRAFT_GENERATED,
            Ev.AI_REVIEW_COMPLETED,
            Ev.TEACHER_ACCEPTED,
            Ev.LESSON_FINALIZED,
            Ev.LESSON_PUBLISHED,
        ):
            self.assertIn(expected, events, msg=f"missing provenance event {expected}")

    # --- golden: student learning half -------------------------

    def test_golden_student_lesson_to_progress(self):
        lesson = _published_lesson(self, "Forces in Motion")
        record_experiment_prediction(
            student=self.student, simulation=self.simulation,
            prediction="More force, more acceleration.", lesson=lesson,
        )
        from apps.students.progress_services import build_student_learning_progress

        progress = build_student_learning_progress(student=self.student)
        self.assertTrue(progress["has_activity"])

    # --- golden: analytics half -------------------------------

    def test_golden_evidence_reaches_analytics_with_date_filter(self):
        _published_lesson(self, "Kinematics Intro")
        LearningEvidence.objects.create(
            student=self.student, kind=Kind.QUESTION_ASKED, detail="why?"
        )
        recent = get_cohort_analytics(resolve_analytics_filters({"range": "7"}))
        none_window = get_cohort_analytics(
            resolve_analytics_filters({"range": "all", "student": "999999"})
        )
        self.assertGreaterEqual(recent.active_student_count, 1)
        self.assertTrue(any("could not be found" in n for n in none_window.filters.notices))

    # --- golden: the 3D layer is a renderer, not a second pipeline ----

    def test_golden_kinematics_3d_is_the_same_experiment_pipeline(self):
        from apps.physics.models import PhysicsSimulation

        kin_concept = PhysicsConcept.objects.create(
            name="Kinematics", description="Straight-line motion.", topic="Kinematics"
        )
        sim = PhysicsSimulation.objects.create(
            concept=kin_concept, title="Kinematics -- Straight-Line Motion",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        lesson = Lesson.objects.create(
            title="Kinematics lesson", topic="Kinematics", grade_level="11",
            duration_minutes=45, learning_objectives=["Relate x, v, a, t."],
            description="lesson", status=Lesson.Status.PUBLISHED,
        )
        lesson.physics_concepts.add(kin_concept)

        page = self.client.get(reverse("physics_lab:detail", args=[sim.slug])).content.decode()
        self.assertIn('data-renderer="kinematics-3d"', page)
        self.assertIn("js/physics3d/kinematics-3d.js", page)

        before_ev = LearningEvidence.objects.count()
        common = {
            "initial_position_m": "0", "initial_velocity_m_s": "2",
            "acceleration_m_s2": "1", "time_s": "5",
        }
        # Structured prediction (before observation) is stored, not scored.
        self.assertEqual(
            self.client.post(
                reverse("physics_lab:experiment_predict", args=[sim.slug]),
                {
                    "prediction": "velocity rises",
                    "predicted_velocity_m_s": "6",
                    "predicted_position_m": "20",
                    "predicted_direction": "speed_up",
                },
            ).status_code,
            200,
        )
        attempt0 = ExperimentAttempt.objects.get(simulation=sim)
        self.assertEqual(attempt0.parameters["prediction"]["velocity_m_s"], 6.0)

        # Scenario challenge check is server-authoritative and persists nothing.
        ev_before_challenge = LearningEvidence.objects.count()
        chk = self.client.post(
            reverse("physics_lab:experiment_scenario_check", args=[sim.slug, "reach-20-at-4"]),
            {"initial_position_m": "0", "initial_velocity_m_s": "3", "acceleration_m_s2": "1",
             "met": "true"},
        ).json()
        self.assertIs(chk["met"], True)  # v0=3, a=1 -> x(4)=20
        self.assertEqual(LearningEvidence.objects.count(), ev_before_challenge)
        self.assertEqual(ExperimentAttempt.objects.filter(simulation=sim).count(), 1)
        obs = self.client.post(
            reverse("physics_lab:experiment_observe", args=[sim.slug]),
            {"observation": "x about 22.5", **common, "position_m": "99999"},
        ).json()
        self.assertAlmostEqual(obs["position_m"], 22.5, places=2)  # server, not the forged 99999
        self.assertAlmostEqual(obs["velocity_m_s"], 7.0, places=2)
        self.assertEqual(
            self.client.post(
                reverse("physics_lab:experiment_explain", args=[sim.slug]),
                {"explanation": "constant a", **common},
            ).status_code,
            200,
        )

        attempts = ExperimentAttempt.objects.filter(simulation=sim)
        self.assertEqual(attempts.count(), 1)
        self.assertIsNotNone(attempts.get().completed_at)
        self.assertGreater(LearningEvidence.objects.count(), before_ev)
        model_names = {m.__name__ for m in __import__("django.apps", fromlist=["apps"]).apps.get_models()}
        self.assertNotIn("ThreeDExperimentAttempt", model_names)
        self.assertNotIn("ThreeDLearningEvidence", model_names)

    # --- golden: assessment stays server-authoritative -------

    def test_golden_assessment_grading_is_server_side(self):
        q = QuestionBankItem.objects.create(
            key="nsl-accel", question_type="numeric", prompt="F=12 N, m=4 kg. a=?",
            expected_value=3.0, tolerance=0.01, concept=self.concept,
        )
        assessment = Assessment.objects.create(
            title="NSL check", concept=self.concept, status=Assessment.Status.PUBLISHED
        )
        aq = AssessmentQuestion.objects.create(assessment=assessment, question=q, position=0)

        from apps.assessments.services import submit_assessment_answer

        # A forged "is_correct" / "expected" in the payload is impossible: the
        # service only takes the answer text.
        outcome = submit_assessment_answer(
            student=self.student, assessment_id=assessment.pk,
            assessment_question_id=aq.pk, submitted_answer="3.0",
        )
        self.assertTrue(outcome["is_correct"])
        wrong = AssessmentAttempt.objects.get(student=self.student, assessment=assessment)
        answer = AssessmentAnswer.objects.get(attempt=wrong)
        self.assertTrue(answer.is_correct)
        self.assertIsNotNone(answer.evidence)  # evidence row written


def client_get_as_guest(test, url):
    """GET as an anonymous (guest) student -- the teacher client is logged in."""

    test.client.logout()
    response = test.client.get(url)
    test.client.force_login(test.teacher)
    return response


def _published_lesson(test, title):
    lesson = Lesson.objects.create(
        title=title, topic="Dynamics", grade_level="11", duration_minutes=45,
        learning_objectives=["Understand it."], description="A short lesson.",
        status=Lesson.Status.PUBLISHED,
    )
    lesson.physics_concepts.add(test.concept)
    return lesson
