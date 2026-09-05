"""Orchestrate misconception recovery over the *existing* learning systems.

This module never grades, tutors, or detects misconceptions itself. It only
answers "what should this student do next" and "has that activity actually
happened", by reading/writing a small amount of orchestration state
(``StudentMisconceptionRecovery`` / ``StudentRecoveryActivityCompletion``) and
by delegating real work to what already exists:

* a "physics_lab" activity is completed by the existing Physics Lab endpoints
  writing a completed ``ExperimentAttempt`` (see ``apps.physics.views`` /
  ``apps.students.experiment_services`` -- neither is touched here; this
  module is notified via the post_save signal in ``apps.students.signals``);
* a "tutor_reflection" activity is completed by an ordinary student message
  in the existing Tutor (``apps.students.services.run_tutor_turn``), again
  observed only via signal;
* a "concept_check" activity is answered here, but graded with the same
  pure ``evaluate_choice_answer`` function the practice engine uses -- there
  is no second grading engine.

Misconception re-evaluation is not re-implemented here either: the Physics
Lab explanation step and the Tutor turn both already call
``assess_student_misconceptions`` on their own free-text input, so recovery
evidence naturally feeds the existing detector without this module invoking
it directly. Completing a recovery never changes a ``StudentMisconception``'s
``status`` -- that remains exclusively ``apply_teacher_decision``'s job.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.http import urlencode

from apps.lessons.models import Lesson
from apps.physics.models import MisconceptionRecoveryActivity, MisconceptionRecoveryPath

from .models import (
    LearningEvidence,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentRecoveryActivityCompletion,
    TutorSession,
)
from .practice_services import AnswerValidationError, PracticeError, evaluate_choice_answer
from .recovery_registry import get_activity_kind

_ActivityType = MisconceptionRecoveryActivity.ActivityType
_Result = StudentRecoveryActivityCompletion.Result

# A recovery only makes sense for a misconception the student might still act
# on. A dismissed observation was judged not real; a resolved one is judged
# fixed -- offering recovery for either would contradict the teacher's call.
_ELIGIBLE_STATUSES = (
    StudentMisconception.Status.CANDIDATE,
    StudentMisconception.Status.CONFIRMED_BY_TEACHER,
)


class RecoveryError(ValueError):
    """Base error for the recovery orchestration layer."""


class RecoveryAccessError(RecoveryError):
    """The requested recovery does not belong to the acting student."""


class RecoveryValidationError(RecoveryError):
    """The requested action is not valid for this recovery's current state."""


# --- small shared lookups -------------------------------------------------


def _lesson_for_concept(concept):
    """The most recently updated lesson that teaches this concept, if any.

    Mirrors ``apps.teachers.services._lesson_for_concept`` exactly -- kept as
    a local one-line query rather than importing a private helper across
    apps.
    """

    if concept is None:
        return None
    return Lesson.objects.filter(physics_concepts=concept).order_by("-updated_at").first()


def _current_activity(recovery: StudentMisconceptionRecovery) -> MisconceptionRecoveryActivity | None:
    """The first not-yet-completed active activity, in order, or None if done."""

    done_ids = set(recovery.activity_completions.values_list("activity_id", flat=True))
    for activity in recovery.path.activities.filter(is_active=True).order_by("order"):
        if activity.id not in done_ids:
            return activity
    return None


def _maybe_complete_path(recovery: StudentMisconceptionRecovery) -> None:
    """Mark the recovery complete once every active activity has a completion row.

    Completion means the student worked through the whole sequence -- it is
    never treated as proof the misconception is resolved; only a teacher
    decision (``apply_teacher_decision``) can change that.
    """

    active_ids = set(recovery.path.activities.filter(is_active=True).values_list("id", flat=True))
    if not active_ids:
        return
    done_ids = set(recovery.activity_completions.values_list("activity_id", flat=True))
    if active_ids <= done_ids and recovery.completed_at is None:
        from django.utils import timezone

        recovery.completed_at = timezone.now()
        recovery.save(update_fields=["completed_at"])


def _record_recovery_evidence(
    recovery: StudentMisconceptionRecovery, activity: MisconceptionRecoveryActivity, *, result: str, detail: str = ""
) -> LearningEvidence:
    """One uniform, student-safe LearningEvidence row for any activity type.

    This is *in addition to* whatever evidence the underlying system already
    wrote (an EXPERIMENT_OBSERVED/EXPLANATION_SUBMITTED row for a Physics Lab
    step, a QUESTION_ASKED row for a Tutor turn) -- it is the one place
    recovery progress itself becomes a normal, queryable learning-evidence
    fact, without a second evidence table.
    """

    lesson = _lesson_for_concept(recovery.path.misconception.physics_concept)
    return LearningEvidence.objects.create(
        student_id=recovery.student_id,
        lesson=lesson,
        kind=LearningEvidence.Kind.RECOVERY_ACTIVITY_COMPLETED,
        detail=(detail or activity.label)[:300],
        context={
            "recovery_path": recovery.path_id,
            "misconception": recovery.observation.misconception.code,
            "activity_type": activity.activity_type,
            "activity_order": activity.order,
            "activity_label": activity.label,
            "result": result,
        },
    )


@transaction.atomic
def _complete_activity(
    recovery_id: int, activity_id: int, *, result: str
) -> StudentRecoveryActivityCompletion | None:
    """Race-safe: complete ``activity`` for ``recovery`` iff it is the current step.

    Locks the recovery row first so two near-simultaneous signals (e.g. two
    quick experiment saves) cannot both decide they are completing the same
    step.
    """

    try:
        recovery = (
            StudentMisconceptionRecovery.objects.select_for_update()
            .select_related(
                "path",
                "path__misconception",
                "path__misconception__physics_concept",
                "observation",
                "observation__misconception",
            )
            .get(pk=recovery_id)
        )
    except StudentMisconceptionRecovery.DoesNotExist:
        return None
    if recovery.completed_at is not None:
        return None
    current = _current_activity(recovery)
    if current is None or current.pk != activity_id:
        # Not the student's current step -- ignore. This is what prevents a
        # stray or replayed signal from crediting the wrong step, or from
        # letting a student skip ahead.
        return None

    evidence = _record_recovery_evidence(recovery, current, result=result)
    try:
        completion = StudentRecoveryActivityCompletion.objects.create(
            recovery=recovery, activity=current, evidence=evidence, result=result[:20]
        )
    except IntegrityError:
        return StudentRecoveryActivityCompletion.objects.filter(
            recovery=recovery, activity=current
        ).first()
    _maybe_complete_path(recovery)
    return completion


# --- resolving / starting a recovery ---------------------------------------


@transaction.atomic
def get_or_create_recovery_for_observation(
    observation: StudentMisconception,
) -> StudentMisconceptionRecovery | None:
    """The student's current recovery for one candidate, or None if unavailable.

    Reuses an unfinished recovery if one already exists (no duplicates on a
    refresh or a repeated request); otherwise starts one from the
    misconception's active recovery path, if it has one. A misconception with
    no recovery path yet, or one the teacher has dismissed/resolved, never
    starts a recovery.
    """

    if observation.status not in _ELIGIBLE_STATUSES:
        return None

    existing = (
        StudentMisconceptionRecovery.objects.select_for_update()
        .filter(student_id=observation.student_id, observation=observation, completed_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if existing is not None:
        return existing

    path = (
        MisconceptionRecoveryPath.objects.filter(
            misconception_id=observation.misconception_id, is_active=True
        )
        .order_by("id")
        .first()
    )
    if path is None:
        return None

    try:
        return StudentMisconceptionRecovery.objects.create(
            student_id=observation.student_id, observation=observation, path=path
        )
    except IntegrityError:
        # Lost a race with a concurrent request for the same observation.
        return (
            StudentMisconceptionRecovery.objects.select_for_update()
            .filter(student_id=observation.student_id, observation=observation, completed_at__isnull=True)
            .order_by("-started_at")
            .first()
        )


def _eligible_observations(student):
    return (
        StudentMisconception.objects.filter(student=student, status__in=_ELIGIBLE_STATUSES)
        .select_related("misconception")
        .order_by("-last_observed_at")
    )


def preview_recovery_for_student(student) -> dict | None:
    """Read-only: what recovery should be offered right now, if any.

    Never creates anything -- safe to call from a GET view. Returns either an
    already-started unfinished recovery (with its id, so the caller can link
    straight to it) or the next eligible candidate that *could* start one
    (with its observation id, so the caller can offer a "start" action).
    """

    existing = (
        StudentMisconceptionRecovery.objects.filter(student=student, completed_at__isnull=True)
        .select_related("path")
        .order_by("-started_at")
        .first()
    )
    if existing is not None:
        return {
            "started": True,
            "recovery_id": existing.pk,
            "title": existing.path.title,
            "summary": existing.path.student_summary,
        }

    for observation in _eligible_observations(student):
        path = (
            MisconceptionRecoveryPath.objects.filter(
                misconception_id=observation.misconception_id, is_active=True
            )
            .order_by("id")
            .first()
        )
        if path is not None:
            return {
                "started": False,
                "observation_id": observation.pk,
                "title": path.title,
                "summary": path.student_summary,
            }
    return None


def get_active_recovery_for_student(student) -> StudentMisconceptionRecovery | None:
    """One recovery to work on right now, creating it if none is in progress."""

    existing = (
        StudentMisconceptionRecovery.objects.filter(student=student, completed_at__isnull=True)
        .select_related("path", "observation", "observation__misconception")
        .order_by("-started_at")
        .first()
    )
    if existing is not None:
        return existing
    for observation in _eligible_observations(student):
        recovery = get_or_create_recovery_for_observation(observation)
        if recovery is not None:
            return recovery
    return None


# --- building the student-facing page context -------------------------------


def _tutor_reflection_prefill(activity: MisconceptionRecoveryActivity) -> str:
    lines = [activity.instructions or f"Let's talk through: {activity.label}"]
    lines.append("Can you help me think this through?")
    return "\n".join(lines)


def _activity_launch_url(activity: MisconceptionRecoveryActivity, concept) -> str:
    """``concept`` is the misconception's own concept, passed in by the caller
    (already loaded once for the whole recovery) so this never re-queries
    ``activity.path.misconception`` per activity.
    """

    if activity.activity_type == _ActivityType.PHYSICS_LAB:
        if activity.simulation_id and activity.simulation.is_active:
            return reverse("physics_lab:detail", args=[activity.simulation.slug])
        return ""
    if activity.activity_type == _ActivityType.TUTOR_REFLECTION:
        lesson = _lesson_for_concept(concept)
        if lesson is None:
            return ""
        prefill = _tutor_reflection_prefill(activity)
        return reverse("students:tutor", args=[lesson.slug]) + "?" + urlencode({"prefill": prefill})
    return ""


def build_recovery_context(recovery: StudentMisconceptionRecovery) -> dict:
    """Everything ``students/recovery.html`` needs. Entirely student-safe.

    Never includes the misconception's code, title, description, detector
    name, or confidence -- only the path's own student-facing summary and
    each activity's student-facing label/instructions.
    """

    concept = recovery.path.misconception.physics_concept
    activities = list(
        recovery.path.activities.filter(is_active=True).select_related("simulation").order_by("order")
    )
    completions = {c.activity_id: c for c in recovery.activity_completions.all()}

    steps = []
    current = None
    for activity in activities:
        completion = completions.get(activity.id)
        is_current = current is None and completion is None
        if is_current:
            current = activity
        expected_label = ""
        if (
            activity.check_correct_choice is not None
            and isinstance(activity.check_choices, list)
            and 0 <= activity.check_correct_choice < len(activity.check_choices)
        ):
            expected_label = str(activity.check_choices[activity.check_correct_choice])
        steps.append(
            {
                "activity": activity,
                "completion": completion,
                "is_complete": completion is not None,
                "is_current": is_current,
                "launch_url": _activity_launch_url(activity, concept) if is_current else "",
                "expected_label": expected_label,
                # Presentation metadata from the activity-type registry (e.g. the
                # launch button's call-to-action text) -- never hardcoded per type
                # in the template. None only for a data-entry mistake outside the
                # registered ActivityType choices.
                "kind": get_activity_kind(activity.activity_type),
            }
        )

    return {
        "recovery": recovery,
        "path": recovery.path,
        "steps": steps,
        "current_activity": current,
        "is_complete": recovery.completed_at is not None,
    }


# --- concept-check submission (the one activity type answered here) --------


@transaction.atomic
def record_concept_check_response(
    *, student, recovery: StudentMisconceptionRecovery, activity: MisconceptionRecoveryActivity, submitted_choice
) -> dict:
    """Validate, grade (deterministically) and record one concept-check answer.

    Grading reuses ``evaluate_choice_answer`` -- the same pure function the
    practice engine uses -- so there is no second grading engine. Correctness
    is recorded for the teacher's benefit but does not gate progression: a
    completed recovery means the student worked through it, not that the
    answer was right.
    """

    recovery = (
        StudentMisconceptionRecovery.objects.select_for_update()
        .select_related(
            "path",
            "path__misconception",
            "path__misconception__physics_concept",
            "observation",
            "observation__misconception",
        )
        .get(pk=recovery.pk)
    )
    if recovery.student_id != student.pk:
        raise RecoveryAccessError("This recovery does not belong to this student.")
    if activity.path_id != recovery.path_id or not activity.is_active:
        raise RecoveryValidationError("That step is not part of this recovery.")
    if activity.activity_type != _ActivityType.CONCEPT_CHECK:
        raise RecoveryValidationError("That step is not a concept check.")

    # Checked *before* the "recovery already complete" guard below: completing
    # this exact activity may have been what completed the whole recovery, and
    # a replayed submit of that same final step must still be a safe, idempotent
    # no-op rather than an error.
    existing = StudentRecoveryActivityCompletion.objects.filter(recovery=recovery, activity=activity).first()
    if existing is not None:
        return {"is_correct": existing.result == _Result.CORRECT, "already_completed": True}

    if recovery.completed_at is not None:
        raise RecoveryValidationError("This recovery is already complete.")

    current = _current_activity(recovery)
    if current is None or current.pk != activity.pk:
        raise RecoveryValidationError("Complete the earlier steps first.")

    evaluation = evaluate_choice_answer(
        submitted_choice, activity.check_choices, activity.check_correct_choice
    )
    result = _Result.CORRECT if evaluation.is_correct else _Result.INCORRECT
    evidence = _record_recovery_evidence(
        recovery, activity, result=result, detail=evaluation.submitted_label
    )
    try:
        StudentRecoveryActivityCompletion.objects.create(
            recovery=recovery, activity=activity, evidence=evidence, result=result
        )
    except IntegrityError:
        existing = StudentRecoveryActivityCompletion.objects.filter(
            recovery=recovery, activity=activity
        ).first()
        return {"is_correct": existing.result == _Result.CORRECT, "already_completed": True}

    _maybe_complete_path(recovery)
    return {
        "is_correct": evaluation.is_correct,
        "already_completed": False,
        "expected_label": evaluation.expected_label,
    }


# --- signal-driven completion (called from apps.students.signals) ----------


def sync_recovery_for_experiment(attempt) -> None:
    """A finished Physics Lab experiment may complete a "physics_lab" step.

    Only credits a recovery whose *current* step targets this exact
    simulation, and only when the attempt finished after the recovery began
    -- an old, unrelated completed attempt never silently satisfies a step.
    """

    if attempt.completed_at is None or attempt.simulation_id is None:
        return
    recoveries = StudentMisconceptionRecovery.objects.filter(
        student_id=attempt.student_id, completed_at__isnull=True
    ).select_related("path")
    for recovery in recoveries:
        current = _current_activity(recovery)
        if (
            current is not None
            and current.activity_type == _ActivityType.PHYSICS_LAB
            and current.simulation_id == attempt.simulation_id
            and attempt.completed_at >= recovery.started_at
        ):
            _complete_activity(recovery.pk, current.pk, result=_Result.DONE)


def sync_recovery_for_tutor_message(message) -> None:
    """A student Tutor message may complete a "tutor_reflection" step.

    Only credits a recovery whose current step is a tutor reflection tied to
    the same lesson as the message's session, and only for messages sent
    after the recovery began.
    """

    session = (
        TutorSession.objects.filter(pk=message.session_id)
        .select_related("lesson")
        .values_list("student_id", "lesson_id")
        .first()
    )
    if session is None:
        return
    student_id, lesson_id = session
    recoveries = StudentMisconceptionRecovery.objects.filter(
        student_id=student_id, completed_at__isnull=True
    ).select_related("path", "path__misconception", "path__misconception__physics_concept")
    for recovery in recoveries:
        current = _current_activity(recovery)
        if current is None or current.activity_type != _ActivityType.TUTOR_REFLECTION:
            continue
        lesson = _lesson_for_concept(recovery.path.misconception.physics_concept)
        if lesson is not None and lesson.pk == lesson_id and message.created_at >= recovery.started_at:
            _complete_activity(recovery.pk, current.pk, result=_Result.DONE)


# --- teacher-facing evidence (extends the existing evidence workspace) -----


def build_teacher_recovery_evidence(student) -> list[dict]:
    """Read-only projection for the teacher's existing student-evidence page.

    Teacher pages may use internal codes; this is the one place recovery
    evidence is shown alongside the misconception it targets.
    """

    recoveries = (
        StudentMisconceptionRecovery.objects.filter(student=student)
        .select_related("path", "path__misconception", "observation")
        .prefetch_related(
            "path__activities",
            "activity_completions__activity",
            "activity_completions__evidence",
        )
        .order_by("-started_at")
    )
    rows = []
    for recovery in recoveries:
        completions = {c.activity_id: c for c in recovery.activity_completions.all()}
        steps = [
            # MisconceptionRecoveryActivity.Meta.ordering = ["path", "order", "id"],
            # so the prefetched .all() is already in the right order.
            {"activity": activity, "completion": completions.get(activity.id)}
            for activity in recovery.path.activities.all()
        ]
        rows.append(
            {
                "recovery": recovery,
                "misconception": recovery.path.misconception,
                "steps": steps,
                "is_complete": recovery.completed_at is not None,
            }
        )
    return rows


__all__ = [
    "RecoveryError",
    "RecoveryAccessError",
    "RecoveryValidationError",
    "AnswerValidationError",
    "PracticeError",
    "get_or_create_recovery_for_observation",
    "get_active_recovery_for_student",
    "preview_recovery_for_student",
    "build_recovery_context",
    "record_concept_check_response",
    "sync_recovery_for_experiment",
    "sync_recovery_for_tutor_message",
    "build_teacher_recovery_evidence",
]
