"""Step 25 -- Misconception recovery paths.

Recovery is an orchestration layer over the *existing* Physics Lab, Tutor and
misconception-detection systems -- these tests exercise that it never
duplicates them: it reuses ExperimentAttempt / TutorSession / LearningEvidence
/ MisconceptionEvidence / assess_student_misconceptions / apply_teacher_decision
exactly as they already exist, and adds only the small amount of orchestration
state needed to sequence activities and know when they are done.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)

from .experiment_services import (
    complete_experiment,
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
)
from .models import (
    ExperimentAttempt,
    LearningEvidence,
    MisconceptionEvidence,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentProfile,
    StudentRecoveryActivityCompletion,
    TutorSession,
)
from .providers import FakeTutorProvider
from .recovery_services import (
    RecoveryAccessError,
    RecoveryValidationError,
    build_recovery_context,
    build_teacher_recovery_evidence,
    get_active_recovery_for_student,
    get_or_create_recovery_for_observation,
    preview_recovery_for_student,
    record_concept_check_response,
)
from .services import run_tutor_turn

FORCE_ACCEL = "FORCE_VS_ACCELERATION"
DIST_DISP = "DISTANCE_VS_DISPLACEMENT"
FREE_FALL = "FREE_FALL_MASS_ACCELERATION"

_ActivityType = MisconceptionRecoveryActivity.ActivityType
_Status = StudentMisconception.Status


class RecoveryDataMixin:
    """Seeds all three target misconceptions with an active recovery path."""

    TEST_PASSWORD = "pw12345!"

    def seed(self):
        # --- Force vs acceleration -> Physics Lab (Newton's Second Law) ---
        self.n2l_concept = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass and acceleration are related by F = ma.",
            topic="Dynamics",
        )
        self.force_accel = PhysicsMisconception.objects.create(
            code=FORCE_ACCEL,
            title="Force and acceleration are the same quantity",
            description="A learner may treat force and acceleration as interchangeable.",
            physics_concept=self.n2l_concept,
        )
        self.n2l_sim = PhysicsSimulation.objects.create(
            concept=self.n2l_concept,
            title="Newton's Second Law Lab",
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )
        self.n2l_lesson = Lesson.objects.create(
            title="Forces and Motion", topic="Dynamics", grade_level="11", duration_minutes=45,
        )
        self.n2l_lesson.physics_concepts.add(self.n2l_concept)

        self.force_path = MisconceptionRecoveryPath.objects.create(
            misconception=self.force_accel,
            title="Force vs acceleration",
            student_summary="Let's compare force and acceleration in the Physics Lab.",
        )
        self.force_lab_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.force_path,
            order=1,
            activity_type=_ActivityType.PHYSICS_LAB,
            label="Run the Lab",
            instructions="Think, predict, run, observe, explain.",
            simulation=self.n2l_sim,
        )
        self.force_check_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.force_path,
            order=2,
            activity_type=_ActivityType.CONCEPT_CHECK,
            label="Check your understanding",
            check_prompt="Doubling the mass with the same net force does what to acceleration?",
            check_choices=["It doubles", "It stays the same", "It is cut in half"],
            check_correct_choice=2,
        )

        # --- Distance vs displacement -> Physics Lab (Kinematics) ---
        self.disp_concept = PhysicsConcept.objects.create(
            name="Displacement", description="The change in position.", topic="Kinematics",
        )
        self.dist_disp = PhysicsMisconception.objects.create(
            code=DIST_DISP,
            title="Distance and displacement are always identical",
            description="A learner may believe distance and displacement are always equal.",
            physics_concept=self.disp_concept,
        )
        self.kinematics_sim = PhysicsSimulation.objects.create(
            concept=self.disp_concept,
            title="Kinematics Lab",
            simulation_type=PhysicsSimulation.SimulationType.KINEMATICS,
        )
        self.disp_lesson = Lesson.objects.create(
            title="Motion on a Line", topic="Kinematics", grade_level="11", duration_minutes=45,
        )
        self.disp_lesson.physics_concepts.add(self.disp_concept)

        self.disp_path = MisconceptionRecoveryPath.objects.create(
            misconception=self.dist_disp,
            title="Distance vs displacement",
            student_summary="Let's compare distance and displacement in the Physics Lab.",
        )
        self.disp_lab_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.disp_path,
            order=1,
            activity_type=_ActivityType.PHYSICS_LAB,
            label="Run the Kinematics Lab",
            simulation=self.kinematics_sim,
        )
        self.disp_check_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.disp_path,
            order=2,
            activity_type=_ActivityType.CONCEPT_CHECK,
            label="Check your understanding",
            check_prompt="A student walks 8 m east then 3 m west. Distance and displacement?",
            check_choices=["11 m / 11 m east", "5 m / 5 m east", "11 m / 5 m east"],
            check_correct_choice=2,
        )

        # --- Free fall -> Tutor reflection ---
        self.accel_concept = PhysicsConcept.objects.create(
            name="Acceleration", description="The rate of change of velocity.", topic="Kinematics",
        )
        self.free_fall = PhysicsMisconception.objects.create(
            code=FREE_FALL,
            title="Mass determines free-fall acceleration",
            description="A learner may believe a heavier object falls faster in free fall.",
            physics_concept=self.accel_concept,
        )
        self.free_fall_lesson = Lesson.objects.create(
            title="Free Fall", topic="Kinematics", grade_level="11", duration_minutes=45,
        )
        self.free_fall_lesson.physics_concepts.add(self.accel_concept)

        self.free_fall_path = MisconceptionRecoveryPath.objects.create(
            misconception=self.free_fall,
            title="Free fall and mass",
            student_summary="Let's talk this through with your Tutor.",
        )
        self.free_fall_tutor_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.free_fall_path,
            order=1,
            activity_type=_ActivityType.TUTOR_REFLECTION,
            label="Talk to your Tutor",
            instructions="Compare a 1 kg and a 10 kg ball in free fall.",
        )
        self.free_fall_check_activity = MisconceptionRecoveryActivity.objects.create(
            path=self.free_fall_path,
            order=2,
            activity_type=_ActivityType.CONCEPT_CHECK,
            label="Check your understanding",
            check_prompt="A 1 kg ball and a 10 kg ball fall together in a vacuum. What happens?",
            check_choices=["10 kg lands first", "1 kg lands first", "They land together", "It depends"],
            check_correct_choice=2,
        )

        # ``self.student`` is deliberately the only StudentProfile with
        # user=None -- an unauthenticated Client always resolves to it via
        # _current_student's guest lookup. ``self.other_student`` carries its
        # own real user from the start so the two are never ambiguous, even
        # before any test explicitly logs in as either one.
        self.student = StudentProfile.objects.create(display_name="Alex")
        User = get_user_model()
        other_user = User.objects.create_user(username="sam-recovery-tests", password=self.TEST_PASSWORD)
        self.other_student = StudentProfile.objects.create(display_name="Sam", user=other_user)

    def make_observation(self, student, misconception, *, status=_Status.CANDIDATE):
        return StudentMisconception.objects.create(
            student=student,
            misconception=misconception,
            status=status,
            confidence=StudentMisconception.Confidence.MEDIUM,
            observation_count=1,
        )


# --- 1. Model tests ---------------------------------------------------------


class RecoveryModelTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_path_and_activities_created(self):
        self.assertEqual(self.force_path.misconception, self.force_accel)
        activities = list(self.force_path.activities.order_by("order"))
        self.assertEqual([a.order for a in activities], [1, 2])
        self.assertEqual(activities[0].activity_type, "physics_lab")
        self.assertEqual(activities[1].activity_type, "concept_check")

    def test_current_step_carries_registry_metadata_for_its_launch_button(self):
        """The launch button's text comes from the activity-type registry, not
        a hardcoded per-type branch in the template (apps.students.recovery_registry
        is consulted, not dead code)."""

        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        context = build_recovery_context(recovery)
        self.assertEqual(context["steps"][0]["kind"].cta, "Open the Physics Lab")

        ff_observation = self.make_observation(self.student, self.free_fall)
        ff_recovery = get_or_create_recovery_for_observation(ff_observation)
        ff_context = build_recovery_context(ff_recovery)
        self.assertEqual(ff_context["steps"][0]["kind"].cta, "Talk to your Tutor")

    def test_activity_order_is_unique_per_path(self):
        with self.assertRaises(IntegrityError):
            MisconceptionRecoveryActivity.objects.create(
                path=self.force_path, order=1, activity_type=_ActivityType.CONCEPT_CHECK,
                label="Duplicate order",
            )

    def test_inactive_path_is_not_offered(self):
        self.force_path.is_active = False
        self.force_path.save(update_fields=["is_active"])
        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        self.assertIsNone(recovery)

    def test_inactive_activity_is_excluded_from_progression(self):
        self.force_check_activity.is_active = False
        self.force_check_activity.save(update_fields=["is_active"])
        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        context = build_recovery_context(recovery)
        self.assertEqual(len(context["steps"]), 1)

    def test_active_recovery_uniqueness_constraint(self):
        observation = self.make_observation(self.student, self.force_accel)
        StudentMisconceptionRecovery.objects.create(
            student=self.student, observation=observation, path=self.force_path,
        )
        with self.assertRaises(IntegrityError):
            StudentMisconceptionRecovery.objects.create(
                student=self.student, observation=observation, path=self.force_path,
            )

    def test_a_completed_recovery_allows_a_new_one(self):
        observation = self.make_observation(self.student, self.force_accel)
        first = StudentMisconceptionRecovery.objects.create(
            student=self.student, observation=observation, path=self.force_path,
        )
        first.completed_at = first.started_at
        first.save(update_fields=["completed_at"])
        second = StudentMisconceptionRecovery.objects.create(
            student=self.student, observation=observation, path=self.force_path,
        )
        self.assertNotEqual(first.pk, second.pk)

    def test_activity_completion_uniqueness_constraint(self):
        observation = self.make_observation(self.student, self.force_accel)
        recovery = StudentMisconceptionRecovery.objects.create(
            student=self.student, observation=observation, path=self.force_path,
        )
        StudentRecoveryActivityCompletion.objects.create(
            recovery=recovery, activity=self.force_lab_activity, result="done",
        )
        with self.assertRaises(IntegrityError):
            StudentRecoveryActivityCompletion.objects.create(
                recovery=recovery, activity=self.force_lab_activity, result="done",
            )


# --- 2. Seed command ---------------------------------------------------------


class RecoverySeedCommandTests(TestCase):
    def _seed_concepts_and_misconceptions(self):
        for name, topic in (
            ("Acceleration", "Kinematics"),
            ("Newton's Second Law", "Dynamics"),
            ("Displacement", "Kinematics"),
        ):
            PhysicsConcept.objects.create(name=name, description=name, topic=topic)
        call_command("seed_misconceptions")

    def test_seed_is_idempotent(self):
        self._seed_concepts_and_misconceptions()
        call_command("seed_recovery_paths")
        self.assertEqual(MisconceptionRecoveryPath.objects.count(), 3)
        self.assertEqual(MisconceptionRecoveryActivity.objects.count(), 6)

        call_command("seed_recovery_paths")
        self.assertEqual(MisconceptionRecoveryPath.objects.count(), 3)
        self.assertEqual(MisconceptionRecoveryActivity.objects.count(), 6)

    def test_seed_skips_missing_misconceptions_without_error(self):
        # No misconceptions seeded at all -- the command should skip cleanly.
        call_command("seed_recovery_paths")
        self.assertEqual(MisconceptionRecoveryPath.objects.count(), 0)

    def test_seed_never_invents_a_misconception_row(self):
        self._seed_concepts_and_misconceptions()
        before = set(PhysicsMisconception.objects.values_list("code", flat=True))
        call_command("seed_recovery_paths")
        after = set(PhysicsMisconception.objects.values_list("code", flat=True))
        self.assertEqual(before, after)

    def test_seed_activity_types_are_all_registered(self):
        """Every activity_type this command writes is one recovery_services can
        actually run -- guards against the registry and the seed data drifting
        apart (the registry is consulted, not decorative)."""

        from apps.physics.management.commands.seed_recovery_paths import RECOVERY_PATHS
        from apps.students.recovery_registry import registered_activity_types

        known = registered_activity_types()
        for entry in RECOVERY_PATHS:
            for activity_entry in entry["activities"]:
                self.assertIn(activity_entry["activity_type"], known)

    def test_seed_rejects_an_unregistered_activity_type(self):
        from django.core.management.base import CommandError

        import apps.physics.management.commands.seed_recovery_paths as seed_module

        self._seed_concepts_and_misconceptions()
        original = seed_module.RECOVERY_PATHS
        seed_module.RECOVERY_PATHS = [
            {
                "misconception_code": "FORCE_VS_ACCELERATION",
                "title": "Bad path",
                "student_summary": "x",
                "activities": [
                    {"order": 1, "activity_type": "not_a_real_type", "label": "x"},
                ],
            }
        ]
        try:
            with self.assertRaises(CommandError):
                call_command("seed_recovery_paths")
        finally:
            seed_module.RECOVERY_PATHS = original
        self.assertEqual(MisconceptionRecoveryPath.objects.count(), 0)


# --- 3. Selection service ----------------------------------------------------


class RecoverySelectionServiceTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_no_recovery_for_dismissed_observation(self):
        observation = self.make_observation(self.student, self.force_accel, status=_Status.DISMISSED)
        self.assertIsNone(get_or_create_recovery_for_observation(observation))

    def test_no_recovery_for_resolved_observation(self):
        observation = self.make_observation(self.student, self.force_accel, status=_Status.RESOLVED)
        self.assertIsNone(get_or_create_recovery_for_observation(observation))

    def test_recovery_created_for_candidate(self):
        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        self.assertIsNotNone(recovery)
        self.assertEqual(recovery.path_id, self.force_path.pk)

    def test_recovery_created_for_teacher_confirmed(self):
        observation = self.make_observation(
            self.student, self.force_accel, status=_Status.CONFIRMED_BY_TEACHER
        )
        recovery = get_or_create_recovery_for_observation(observation)
        self.assertIsNotNone(recovery)

    def test_repeated_request_reuses_the_same_unfinished_recovery(self):
        observation = self.make_observation(self.student, self.force_accel)
        first = get_or_create_recovery_for_observation(observation)
        second = get_or_create_recovery_for_observation(observation)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StudentMisconceptionRecovery.objects.count(), 1)

    def test_no_recovery_when_misconception_has_no_path(self):
        pathless_concept = PhysicsConcept.objects.create(
            name="Momentum", description="mv", topic="Dynamics"
        )
        pathless = PhysicsMisconception.objects.create(
            code="MOMENTUM_MISCONCEPTION", title="x", description="x", physics_concept=pathless_concept,
        )
        observation = self.make_observation(self.student, pathless)
        self.assertIsNone(get_or_create_recovery_for_observation(observation))

    def test_preview_does_not_create_anything(self):
        self.make_observation(self.student, self.force_accel)
        preview = preview_recovery_for_student(self.student)
        self.assertIsNotNone(preview)
        self.assertFalse(preview["started"])
        self.assertEqual(StudentMisconceptionRecovery.objects.count(), 0)

    def test_preview_reflects_an_already_started_recovery(self):
        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        preview = preview_recovery_for_student(self.student)
        self.assertTrue(preview["started"])
        self.assertEqual(preview["recovery_id"], recovery.pk)

    def test_get_active_recovery_picks_most_recent_eligible_candidate(self):
        from datetime import timedelta

        from django.utils import timezone

        older = self.make_observation(self.student, self.force_accel)
        older.last_observed_at = timezone.now() - timedelta(minutes=5)
        older.save(update_fields=["last_observed_at"])
        newest = self.make_observation(self.student, self.dist_disp)
        recovery = get_active_recovery_for_student(self.student)
        self.assertEqual(recovery.observation_id, newest.pk)


# --- 4. Authorization / cross-student security ------------------------------


class RecoveryAuthorizationTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)
        self.client = Client()

    def test_owner_can_view_their_recovery(self):
        response = self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.force_path.title)

    def test_get_never_mutates_anything(self):
        before_evidence = LearningEvidence.objects.count()
        before_completions = StudentRecoveryActivityCompletion.objects.count()
        self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertEqual(LearningEvidence.objects.count(), before_evidence)
        self.assertEqual(StudentRecoveryActivityCompletion.objects.count(), before_completions)

    def test_recovery_start_requires_post(self):
        response = self.client.get(reverse("students:recovery_start"))
        self.assertEqual(response.status_code, 405)

    def test_cross_student_get_is_blocked(self):
        """Student A cannot view Student B's recovery by guessing/incrementing an id."""

        other_client = self._client_as(self.other_student)
        response = other_client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cross_student_concept_check_post_is_blocked(self):
        other_client = self._client_as(self.other_student)
        response = other_client.post(
            reverse(
                "students:recovery_check", args=[self.recovery.pk, self.force_check_activity.pk]
            ),
            {"choice": "2"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.force_check_activity
            ).exists()
        )

    def test_recovery_start_with_another_students_observation_id_is_rejected(self):
        other_observation = self.make_observation(self.other_student, self.dist_disp)
        response = self.client.post(
            reverse("students:recovery_start"), {"observation_id": other_observation.pk}
        )
        self.assertRedirects(response, reverse("students:progress"))
        self.assertFalse(
            StudentMisconceptionRecovery.objects.filter(observation=other_observation).exists()
        )

    def _client_as(self, student):
        """A logged-in session that resolves to exactly ``student``.

        The app resolves the acting student from an authenticated user (or the
        shared guest profile). ``student`` already carries its own real user
        (see ``RecoveryDataMixin.seed``), so this just logs in as them.
        """

        if student.user_id is None:
            User = get_user_model()
            user = User.objects.create_user(
                username=f"user-{student.pk}", password=self.TEST_PASSWORD
            )
            student.user = user
            student.save(update_fields=["user"])
        client = Client()
        client.login(username=student.user.get_username(), password=self.TEST_PASSWORD)
        return client


# --- 5. Completion rules -----------------------------------------------------


class RecoveryCompletionTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)
        self.client = Client()

    def test_concept_check_before_lab_step_is_rejected(self):
        with self.assertRaises(RecoveryValidationError):
            record_concept_check_response(
                student=self.student,
                recovery=self.recovery,
                activity=self.force_check_activity,
                submitted_choice="2",
            )
        self.assertFalse(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.force_check_activity
            ).exists()
        )

    def _complete_lab_step(self):
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            prediction="If force doubles, acceleration doubles.",
        )
        attempt, _ = record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="Acceleration went from 5 to 10.", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="Net force increased while mass stayed the same.", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)
        return attempt

    def test_completed_experiment_completes_the_physics_lab_step(self):
        self._complete_lab_step()
        self.assertTrue(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.force_lab_activity
            ).exists()
        )

    def test_full_sequence_completes_the_recovery(self):
        self._complete_lab_step()
        result = record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="2",
        )
        self.assertTrue(result["is_correct"])
        self.recovery.refresh_from_db()
        self.assertIsNotNone(self.recovery.completed_at)

    def test_wrong_concept_check_answer_still_completes_the_step(self):
        self._complete_lab_step()
        result = record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="0",
        )
        self.assertFalse(result["is_correct"])
        self.recovery.refresh_from_db()
        self.assertIsNotNone(self.recovery.completed_at)

    def test_repeated_concept_check_submission_is_idempotent(self):
        self._complete_lab_step()
        record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="0",
        )
        result = record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="2",
        )
        self.assertTrue(result["already_completed"])
        self.assertFalse(result["is_correct"])  # the FIRST answer's verdict is kept
        self.assertEqual(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.force_check_activity
            ).count(),
            1,
        )

    def test_repeated_experiment_completion_does_not_duplicate_recovery_completion(self):
        attempt = self._complete_lab_step()
        # A second, unrelated completed experiment on the same simulation must
        # not create a second completion row for the same activity.
        attempt.completed_at = None
        attempt.save(update_fields=["completed_at"])
        complete_experiment(attempt)
        self.assertEqual(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.force_lab_activity
            ).count(),
            1,
        )

    def test_client_forged_choice_is_ignored_server_recomputes_correctness(self):
        self._complete_lab_step()
        response = self.client.post(
            reverse("students:recovery_check", args=[self.recovery.pk, self.force_check_activity.pk]),
            {"choice": "0", "is_correct": "true", "result": "correct"},
        )
        self.assertEqual(response.status_code, 302)
        completion = StudentRecoveryActivityCompletion.objects.get(
            recovery=self.recovery, activity=self.force_check_activity
        )
        self.assertEqual(completion.result, "incorrect")

    def test_no_completion_before_the_lab_step_via_http(self):
        response = self.client.post(
            reverse("students:recovery_check", args=[self.recovery.pk, self.force_check_activity.pk]),
            {"choice": "2"},
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with an error, not a redirect
        self.assertContains(response, "Complete the earlier steps first")

    def test_get_cannot_submit_a_concept_check(self):
        response = self.client.get(
            reverse("students:recovery_check", args=[self.recovery.pk, self.force_check_activity.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_csrf_is_enforced_on_concept_check(self):
        enforcing_client = Client(enforce_csrf_checks=True)
        self._complete_lab_step()
        response = enforcing_client.post(
            reverse("students:recovery_check", args=[self.recovery.pk, self.force_check_activity.pk]),
            {"choice": "2"},
        )
        self.assertEqual(response.status_code, 403)


# --- 6. Evidence integration --------------------------------------------------


class RecoveryEvidenceTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)

    def test_concept_check_writes_learning_evidence_with_expected_context(self):
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        attempt, _ = record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="Net force increased while mass stayed the same.", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)
        record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="2",
        )
        evidence = next(
            e
            for e in LearningEvidence.objects.filter(
                kind=LearningEvidence.Kind.RECOVERY_ACTIVITY_COMPLETED
            )
            if e.context.get("activity_type") == "concept_check"
        )
        self.assertEqual(evidence.context["recovery_path"], self.force_path.pk)
        self.assertEqual(evidence.context["misconception"], FORCE_ACCEL)
        self.assertEqual(evidence.context["activity_type"], "concept_check")
        self.assertEqual(evidence.context["activity_order"], 2)
        self.assertEqual(evidence.context["result"], "correct")

    def test_no_second_evidence_or_attempt_architecture(self):
        """Completing a recovery never creates a shadow attempt/evidence table."""

        before_attempts = ExperimentAttempt.objects.count()
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        attempt, _ = record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="ok", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)
        # Exactly one ExperimentAttempt exists for this student+simulation --
        # the recovery step reused it, it did not spawn its own.
        self.assertEqual(
            ExperimentAttempt.objects.filter(student=self.student, simulation=self.n2l_sim).count(),
            before_attempts + 1,
        )

    @override_settings(AI_PROVIDER="fake")
    def test_misconception_reasoning_text_still_reaches_the_existing_detector(self):
        """A recovery explanation is still assessed by the *existing* engine."""

        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="Force and acceleration are the same thing, so it just doubled.",
            mass_kg=2, force_n=20,
        )
        self.assertTrue(
            MisconceptionEvidence.objects.filter(observation__student=self.student).exists()
        )


# --- 7. Misconception reevaluation / teacher authority ----------------------


class RecoveryTeacherAuthorityTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)

    def test_completing_recovery_never_changes_status(self):
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="ok", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)
        record_concept_check_response(
            student=self.student, recovery=self.recovery, activity=self.force_check_activity,
            submitted_choice="2",
        )
        self.observation.refresh_from_db()
        self.assertEqual(self.observation.status, _Status.CANDIDATE)

    def test_dismissed_observation_cannot_start_a_new_recovery(self):
        from .misconception_services import apply_teacher_decision

        apply_teacher_decision(self.observation, "dismiss")
        self.observation.refresh_from_db()
        self.assertIsNone(get_or_create_recovery_for_observation(self.observation))


# --- 8. Physics Lab integration ---------------------------------------------


class RecoveryPhysicsLabIntegrationTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.dist_disp)
        self.recovery = get_or_create_recovery_for_observation(self.observation)

    def test_launch_url_points_at_the_existing_generic_physics_lab_endpoint(self):
        context = build_recovery_context(self.recovery)
        current_step = context["steps"][0]
        self.assertEqual(
            current_step["launch_url"], reverse("physics_lab:detail", args=[self.kinematics_sim.slug])
        )

    def test_kinematics_experiment_completes_the_step(self):
        record_experiment_prediction(
            student=self.student, simulation=self.kinematics_sim, lesson=self.disp_lesson,
            prediction="Displacement will be less than distance.",
        )
        attempt, _ = record_experiment_observation(
            student=self.student, simulation=self.kinematics_sim, lesson=self.disp_lesson,
            observation="x", initial_position_m=0, initial_velocity_m_s=2, acceleration_m_s2=1, time_s=5,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.kinematics_sim, lesson=self.disp_lesson,
            explanation="Distance and displacement differ when the path is not a straight line out.",
            initial_position_m=0, initial_velocity_m_s=2, acceleration_m_s2=1, time_s=5,
        )
        complete_experiment(attempt)
        self.assertTrue(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.disp_lab_activity
            ).exists()
        )

    def test_stale_pre_recovery_attempt_does_not_auto_complete(self):
        """An attempt finished *before* the recovery began must not silently satisfy it."""

        # Complete the experiment first, while *no* recovery exists yet for it
        # (the setUp recovery is deleted below) -- the completion signal fires
        # immediately but finds nothing to credit, so it is a pure no-op.
        self.recovery.delete()
        attempt, _ = record_experiment_observation(
            student=self.student, simulation=self.kinematics_sim, lesson=self.disp_lesson,
            observation="x", initial_position_m=0, initial_velocity_m_s=2, acceleration_m_s2=1, time_s=5,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.kinematics_sim, lesson=self.disp_lesson,
            explanation="ok", initial_position_m=0, initial_velocity_m_s=2, acceleration_m_s2=1, time_s=5,
        )
        complete_experiment(attempt)

        # Now start a fresh recovery -- its started_at is necessarily *after*
        # the attempt above already completed.
        self.observation.refresh_from_db()
        new_recovery = get_or_create_recovery_for_observation(self.observation)
        self.assertFalse(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=new_recovery, activity=self.disp_lab_activity
            ).exists()
        )


# --- 9. Tutor integration ----------------------------------------------------


class RecoveryTutorIntegrationTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.free_fall)
        self.recovery = get_or_create_recovery_for_observation(self.observation)

    def test_launch_url_points_at_the_existing_tutor_endpoint(self):
        context = build_recovery_context(self.recovery)
        current_step = context["steps"][0]
        self.assertTrue(
            current_step["launch_url"].startswith(
                reverse("students:tutor", args=[self.free_fall_lesson.slug])
            )
        )

    @override_settings(AI_PROVIDER="fake")
    def test_a_tutor_turn_in_the_matching_lesson_completes_the_step(self):
        session = TutorSession.objects.create(student=self.student, lesson=self.free_fall_lesson)
        run_tutor_turn(
            session,
            student_question="Why do a 1 kg and 10 kg ball fall at the same rate?",
            provider=FakeTutorProvider(),
        )
        self.assertTrue(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.free_fall_tutor_activity
            ).exists()
        )

    @override_settings(AI_PROVIDER="fake")
    def test_tutor_turn_in_an_unrelated_lesson_does_not_complete_the_step(self):
        other_lesson = Lesson.objects.create(
            title="Other lesson", topic="Other", grade_level="11", duration_minutes=30,
        )
        session = TutorSession.objects.create(student=self.student, lesson=other_lesson)
        run_tutor_turn(session, student_question="Unrelated question.", provider=FakeTutorProvider())
        self.assertFalse(
            StudentRecoveryActivityCompletion.objects.filter(
                recovery=self.recovery, activity=self.free_fall_tutor_activity
            ).exists()
        )

    @override_settings(AI_PROVIDER="fake")
    def test_no_second_tutor_engine_is_used(self):
        """Exactly the existing TutorSession/TutorMessage machinery is touched."""

        session = TutorSession.objects.create(student=self.student, lesson=self.free_fall_lesson)
        before_sessions = TutorSession.objects.count()
        run_tutor_turn(session, student_question="Question?", provider=FakeTutorProvider())
        self.assertEqual(TutorSession.objects.count(), before_sessions)


# --- 10. Student UI / accessibility / XSS -----------------------------------


class RecoveryStudentUITests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)
        self.client = Client()

    def test_page_never_leaks_the_internal_misconception_code(self):
        response = self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertNotContains(response, FORCE_ACCEL)
        self.assertNotContains(response, "candidate")  # internal status token

    def test_heading_hierarchy_and_labelled_inputs(self):
        self._complete_lab_step_for_check_step()
        response = self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        content = response.content.decode()
        self.assertIn("<h1>", content)
        self.assertIn("<h2", content)
        self.assertIn('for="recovery-choice-', content)

    def test_dynamic_status_is_announced(self):
        response = self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertContains(response, 'aria-current="step"')

    def test_student_facing_labels_are_escaped(self):
        self.force_lab_activity.label = "<script>alert(1)</script>"
        self.force_lab_activity.save(update_fields=["label"])
        response = self.client.get(reverse("students:recovery_detail", args=[self.recovery.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def _complete_lab_step_for_check_step(self):
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="ok", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)


# --- 11. Teacher evidence integration ---------------------------------------


class RecoveryTeacherEvidenceTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()
        self.observation = self.make_observation(self.student, self.force_accel)
        self.recovery = get_or_create_recovery_for_observation(self.observation)

    def test_build_teacher_recovery_evidence_shape(self):
        rows = build_teacher_recovery_evidence(self.student)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["misconception"].code, FORCE_ACCEL)
        self.assertEqual(len(row["steps"]), 2)
        self.assertFalse(row["is_complete"])

    def test_teacher_student_detail_page_renders_recovery_section(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        teacher = User.objects.create_user(username="teach1", password="pw12345!", is_staff=True)
        client = Client()
        client.login(username="teach1", password="pw12345!")
        response = client.get(reverse("teachers:student_detail", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.force_path.title)
        self.assertContains(response, FORCE_ACCEL)


# --- 12. Progress integration -------------------------------------------------


class RecoveryProgressIntegrationTests(RecoveryDataMixin, TestCase):
    def setUp(self):
        self.seed()

    def test_progress_page_offers_a_start_action_for_an_eligible_candidate(self):
        self.make_observation(self.student, self.force_accel)
        client = Client()
        # The progress view resolves the guest student profile automatically;
        # force this test's student to be that guest profile.
        self.student.user = None
        self.student.save(update_fields=["user"])
        response = client.get(reverse("students:progress"))
        self.assertContains(response, self.force_path.title)

    def test_recovery_evidence_appears_in_the_timeline_without_a_hardcoded_branch(self):
        observation = self.make_observation(self.student, self.force_accel)
        recovery = get_or_create_recovery_for_observation(observation)
        record_experiment_prediction(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson, prediction="x",
        )
        record_experiment_observation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            observation="x", mass_kg=2, force_n=20,
        )
        attempt, _ = record_experiment_explanation(
            student=self.student, simulation=self.n2l_sim, lesson=self.n2l_lesson,
            explanation="ok", mass_kg=2, force_n=20,
        )
        complete_experiment(attempt)
        record_concept_check_response(
            student=self.student, recovery=recovery, activity=self.force_check_activity,
            submitted_choice="2",
        )

        from .progress_services import build_student_learning_progress

        progress = build_student_learning_progress(student=self.student)
        recovery_entries = [
            entry
            for day in progress["recent_activity_days"]
            for entry in day["entries"]
            if entry["recovery"] is not None
        ]
        self.assertTrue(recovery_entries)
        self.assertNotIn(FORCE_ACCEL, recovery_entries[0]["recovery"]["activity_label"])
