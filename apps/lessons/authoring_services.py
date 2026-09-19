"""Teacher lesson authoring: an orchestration layer over the existing systems.

Nothing here generates content, grades, tutors, detects misconceptions, or
records student learning. It only lets a teacher structure a coherent learning
experience out of what already exists:

* lesson basics / objectives / concepts -> the existing ``Lesson`` fields
* a Physics Lab activity            -> an existing ``physics.PhysicsSimulation``
* a practice activity               -> an existing ``assessments.QuestionBankItem``
                                       graded by the existing pure evaluators
* an assessment activity            -> an existing ``assessments.Assessment``
* a tutor activity                  -> the existing student Tutor
* a recovery activity               -> an existing ``physics.MisconceptionRecoveryPath``

Every meaningful edit records a ``ProvenanceEvent`` through the *existing*
``apps.provenance`` architecture -- no new audit model. Publishing is always an
explicit teacher action and is refused (with teacher-facing reasons) when the
lesson structure is incomplete or references something unusable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from apps.assessments.models import Assessment, QuestionBankItem
from apps.physics.level_catalog import get_level
from apps.physics.models import MisconceptionRecoveryPath, PhysicsConcept, PhysicsSimulation
from apps.physics.simulation_registry import get_simulation_definition
from apps.provenance.models import ProvenanceEvent
from apps.provenance.services import record_event
from apps.students.models import LearningEvidence
from apps.students.practice_services import (
    AnswerValidationError,
    PracticeError,
    evaluate_choice_answer,
    evaluate_numeric_answer,
)

from .models import Lesson, LessonActivity

_ActivityType = LessonActivity.ActivityType

# Explicit allow-list. An activity_type outside this set is rejected server-side.
ACTIVITY_TYPES = frozenset(_ActivityType.values)

# Activity types that carry a reference to an existing object, and which model
# that reference must resolve to. Kept here (not derived by import magic) so a
# forged (type, reference) pairing can never slip through.
_REFERENCE_MODEL = {
    _ActivityType.PHYSICS_LAB: ("simulation", PhysicsSimulation),
    _ActivityType.PRACTICE: ("question", QuestionBankItem),
    _ActivityType.ASSESSMENT: ("assessment", Assessment),
    _ActivityType.RECOVERY: ("recovery_path", MisconceptionRecoveryPath),
}

TITLE_MAX = 200
INSTRUCTIONS_MAX = 4000
TUTOR_FOCUS_MAX = 200
MAX_ACTIVITIES = 40
MAX_OBJECTIVES = 40


class LessonAuthoringError(ValueError):
    """A teacher authoring action was missing or inconsistent."""


class LessonPublishError(LessonAuthoringError):
    """A lesson cannot be published in its current state.

    ``reasons`` is a list of teacher-facing strings.
    """

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons) or "This lesson is not ready to publish.")


# --- small helpers -------------------------------------------------------


def _clean_text(value, *, limit: int) -> str:
    return (value or "").strip()[:limit]


def _norm_objectives(raw_objectives) -> list[str]:
    """Trim, drop empties, preserve order, cap the count."""

    items: list[str] = []
    for entry in raw_objectives or []:
        text = (str(entry) if entry is not None else "").strip()
        if text:
            items.append(text[:500])
        if len(items) >= MAX_OBJECTIVES:
            break
    return items


def _record(lesson: Lesson, *, change: str, teacher, extra: dict | None = None) -> None:
    metadata = {"change": change}
    if extra:
        metadata.update(extra)
    record_event(
        lesson,
        ProvenanceEvent.EventType.LESSON_UPDATED,
        source="teacher",
        actor=teacher,
        metadata=metadata,
    )


# --- lesson basics / objectives / concepts ------------------------------


@transaction.atomic
def update_lesson_basics(
    *,
    lesson: Lesson,
    teacher,
    title: str,
    topic: str,
    grade_level: str,
    duration_minutes,
    description: str = "",
    level: str = "",
) -> Lesson:
    title = _clean_text(title, limit=255)
    topic = _clean_text(topic, limit=255)
    grade_level = _clean_text(grade_level, limit=50)
    description = _clean_text(description, limit=8000)
    level = _clean_text(level, limit=30)
    if not title:
        raise LessonAuthoringError("A lesson title is required.")
    if not topic:
        raise LessonAuthoringError("A lesson topic is required.")
    if not grade_level:
        raise LessonAuthoringError("A grade level is required.")
    try:
        minutes = int(duration_minutes)
    except (TypeError, ValueError):
        raise LessonAuthoringError("Duration must be a whole number of minutes.")
    if minutes < 1 or minutes > 600:
        raise LessonAuthoringError("Duration must be between 1 and 600 minutes.")
    # Unlike grade_level, a physics level is OPTIONAL -- a blank value means
    # "not tagged yet" and is left as-is, not rejected.
    if level and get_level(level) is None:
        raise LessonAuthoringError("Unknown physics level.")

    locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
    locked.title = title
    locked.topic = topic
    locked.grade_level = grade_level
    locked.duration_minutes = minutes
    locked.description = description
    locked.level = level
    locked.save(
        update_fields=[
            "title",
            "topic",
            "grade_level",
            "duration_minutes",
            "description",
            "level",
            "updated_at",
        ]
    )
    _record(locked, change="basics", teacher=teacher)
    return locked


@transaction.atomic
def set_learning_objectives(*, lesson: Lesson, teacher, raw_objectives) -> list[str]:
    objectives = _norm_objectives(raw_objectives)
    locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
    locked.learning_objectives = objectives
    locked.save(update_fields=["learning_objectives", "updated_at"])
    _record(locked, change="objectives", teacher=teacher, extra={"count": len(objectives)})
    return objectives


@transaction.atomic
def set_lesson_concepts(*, lesson: Lesson, teacher, concept_ids) -> list[PhysicsConcept]:
    """Resolve submitted ids against the active Physics concept catalog.

    The browser never invents a concept -- an id that does not resolve to an
    active ``PhysicsConcept`` is a hard error, and duplicates collapse.
    """

    seen: list[int] = []
    for raw in concept_ids or []:
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            raise LessonAuthoringError("A selected Physics concept is not valid.")
        if pk not in seen:
            seen.append(pk)

    concepts = list(PhysicsConcept.objects.filter(is_active=True, pk__in=seen))
    if len(concepts) != len(seen):
        raise LessonAuthoringError(
            "One or more selected Physics concepts could not be found."
        )

    # Preserve the teacher's submitted order.
    by_pk = {c.pk: c for c in concepts}
    ordered = [by_pk[pk] for pk in seen]

    locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
    locked.physics_concepts.set(ordered)
    locked.save(update_fields=["updated_at"])
    _record(
        locked,
        change="concepts",
        teacher=teacher,
        extra={"concepts": [c.name for c in ordered]},
    )
    return ordered


# --- activity reference resolution ------------------------------------


def _resolve_reference(activity_type: str, reference_id):
    """Return (field_name, object) for a typed reference, validated for use.

    ``reference_id`` may be a bare pk or the builder's ``"<type>:<pk>"`` form.
    When the ``"<type>:"`` prefix is present it must match ``activity_type`` --
    this is what stops a teacher (or a forged POST) from pairing, say, an
    assessment pk with a ``physics_lab`` activity when pk spaces overlap.

    Raises ``LessonAuthoringError`` when the reference is missing, unknown, of
    the wrong type, or not currently usable (inactive / unpublished / archived).
    """

    field_name, model = _REFERENCE_MODEL[activity_type]
    raw = "" if reference_id is None else str(reference_id).strip()
    if ":" in raw:
        prefix, _, raw = raw.partition(":")
        if prefix.strip() != activity_type:
            raise LessonAuthoringError("That item does not match the activity type.")
    if raw in ("", "0"):
        raise LessonAuthoringError("This activity type needs a linked item.")
    try:
        obj = model.objects.filter(pk=int(raw)).first()
    except (TypeError, ValueError):
        obj = None
    if obj is None:
        raise LessonAuthoringError("The linked item could not be found.")

    problem = _reference_usability_problem(activity_type, obj)
    if problem:
        raise LessonAuthoringError(problem)
    return field_name, obj


def _question_is_gradeable(question) -> bool:
    """True only when the deterministic evaluators can actually score it.

    A ``QuestionBankItem`` allows null answer definitions, so a malformed one
    (numeric with no ``expected_value``, choice with no key / < 2 options)
    would produce a published activity no student can complete. This mirrors
    what the practice engine's ``_effective_type`` downgrade already guards.
    """

    if question.question_type == QuestionBankItem.QuestionType.MULTIPLE_CHOICE:
        choices = question.choices if isinstance(question.choices, list) else []
        usable = [c for c in choices if str(c).strip()]
        return (
            len(usable) >= 2
            and isinstance(question.correct_choice, int)
            and not isinstance(question.correct_choice, bool)
            and 0 <= question.correct_choice < len(choices)
        )
    return question.expected_value is not None and math.isfinite(question.expected_value)


def _reference_usability_problem(activity_type: str, obj) -> str:
    """"" if ``obj`` is usable for ``activity_type`` now, else a teacher message.

    Pure -- operates on an already-loaded object, so callers that already have
    the reference (e.g. publish validation over prefetched activities) never
    re-query.
    """

    if activity_type == _ActivityType.PHYSICS_LAB:
        if not obj.is_active:
            return "That simulation is not active."
        if get_simulation_definition(obj.simulation_type) is None:
            return "That simulation type is not available yet."
    elif activity_type == _ActivityType.PRACTICE:
        if not obj.is_active:
            return "That question is not active."
        if not _question_is_gradeable(obj):
            return "That question has no usable answer definition and cannot be graded."
    elif activity_type == _ActivityType.ASSESSMENT:
        if obj.status != Assessment.Status.PUBLISHED:
            return "Only a published assessment can be linked."
    elif activity_type == _ActivityType.RECOVERY:
        if not obj.is_active:
            return "That recovery path is not active."
    return ""


def _reference_is_still_usable(activity: LessonActivity) -> bool:
    field_name = activity.reference_field_name
    if field_name is None:
        return True
    obj = getattr(activity, field_name)  # preloaded by lesson_activities()'s select_related
    if obj is None:
        return False
    return not _reference_usability_problem(activity.activity_type, obj)


# --- activity CRUD + reorder -----------------------------------------


def _clean_activity_fields(*, activity_type, title, instructions, tutor_focus):
    key = (activity_type or "").strip().lower()
    if key not in ACTIVITY_TYPES:
        raise LessonAuthoringError("Choose a valid activity type.")
    title = _clean_text(title, limit=TITLE_MAX)
    if not title:
        raise LessonAuthoringError("Give the activity a short title.")
    return (
        key,
        title,
        _clean_text(instructions, limit=INSTRUCTIONS_MAX),
        _clean_text(tutor_focus, limit=TUTOR_FOCUS_MAX),
    )


@transaction.atomic
def create_activity(
    *,
    lesson: Lesson,
    teacher,
    activity_type: str,
    title: str,
    instructions: str = "",
    reference_id=None,
    tutor_focus: str = "",
) -> LessonActivity:
    key, title, instructions, tutor_focus = _clean_activity_fields(
        activity_type=activity_type,
        title=title,
        instructions=instructions,
        tutor_focus=tutor_focus,
    )

    # Lock the lesson row so two quick "Add activity" clicks serialise and get
    # distinct positions rather than colliding on the uniqueness constraint.
    locked_lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
    existing = list(
        LessonActivity.objects.select_for_update()
        .filter(lesson=locked_lesson)
        .order_by("position")
    )
    if len(existing) >= MAX_ACTIVITIES:
        raise LessonAuthoringError(
            f"A lesson can have at most {MAX_ACTIVITIES} activities."
        )
    next_position = (existing[-1].position + 1) if existing else 1

    fields = {
        "lesson": locked_lesson,
        "activity_type": key,
        "title": title,
        "instructions": instructions,
        "tutor_focus": tutor_focus if key == _ActivityType.TUTOR else "",
    }
    if key in _REFERENCE_MODEL:
        field_name, obj = _resolve_reference(key, reference_id)
        fields[field_name] = obj

    # On SQLite ``select_for_update`` is a no-op, so a genuinely concurrent
    # double-submit can still race to the same position. The uniqueness
    # constraint catches it; retry once (inside a savepoint so the outer
    # transaction stays healthy) against a re-read of the max position rather
    # than surfacing an error for a benign second click.
    activity = None
    for attempt in range(2):
        try:
            with transaction.atomic():
                activity = LessonActivity.objects.create(position=next_position, **fields)
            break
        except IntegrityError:
            if attempt == 1:
                raise
            highest = (
                LessonActivity.objects.filter(lesson=locked_lesson)
                .order_by("-position")
                .values_list("position", flat=True)
                .first()
            )
            next_position = (highest or 0) + 1
    locked_lesson.save(update_fields=["updated_at"])
    _record(
        locked_lesson,
        change="activity_created",
        teacher=teacher,
        extra={"activity_type": key, "title": title, "position": next_position},
    )
    return activity


@transaction.atomic
def update_activity(
    *,
    activity: LessonActivity,
    teacher,
    title: str,
    instructions: str = "",
    reference_id=None,
    tutor_focus: str = "",
) -> LessonActivity:
    locked = (
        LessonActivity.objects.select_for_update()
        .select_related("lesson")
        .get(pk=activity.pk)
    )
    # The activity type is fixed once created -- changing it would silently
    # invalidate its reference. A teacher deletes and re-adds instead.
    _key, title, instructions, tutor_focus = _clean_activity_fields(
        activity_type=locked.activity_type,
        title=title,
        instructions=instructions,
        tutor_focus=tutor_focus,
    )
    locked.title = title
    locked.instructions = instructions
    locked.tutor_focus = tutor_focus if locked.activity_type == _ActivityType.TUTOR else ""

    update_fields = ["title", "instructions", "tutor_focus", "updated_at"]
    if locked.activity_type in _REFERENCE_MODEL:
        field_name, obj = _resolve_reference(locked.activity_type, reference_id)
        setattr(locked, field_name, obj)
        update_fields.append(field_name)

    locked.save(update_fields=update_fields)
    locked.lesson.save(update_fields=["updated_at"])
    _record(
        locked.lesson,
        change="activity_updated",
        teacher=teacher,
        extra={"activity_id": str(locked.pk), "title": title},
    )
    return locked


@transaction.atomic
def delete_activity(*, activity: LessonActivity, teacher) -> None:
    locked_lesson = Lesson.objects.select_for_update().get(pk=activity.lesson_id)
    rows = list(
        LessonActivity.objects.select_for_update()
        .filter(lesson=locked_lesson)
        .order_by("position")
    )
    target = next((a for a in rows if a.pk == activity.pk), None)
    if target is None:
        return  # already gone -- repeated delete is a safe no-op

    title = target.title
    target.delete()
    # Compact positions to 1..N with no gaps, shifting temporarily out of the
    # unique range to avoid a mid-update collision.
    remaining = [a for a in rows if a.pk != target.pk]
    for offset, row in enumerate(remaining):
        LessonActivity.objects.filter(pk=row.pk).update(position=1000 + offset)
    for index, row in enumerate(remaining, start=1):
        LessonActivity.objects.filter(pk=row.pk).update(position=index)

    locked_lesson.save(update_fields=["updated_at"])
    _record(
        locked_lesson,
        change="activity_deleted",
        teacher=teacher,
        extra={"title": title},
    )


@transaction.atomic
def move_activity(*, activity: LessonActivity, teacher, direction: str) -> None:
    direction = (direction or "").strip().lower()
    if direction not in {"up", "down"}:
        raise LessonAuthoringError("Choose a direction to move the activity.")

    locked_lesson = Lesson.objects.select_for_update().get(pk=activity.lesson_id)
    rows = list(
        LessonActivity.objects.select_for_update()
        .filter(lesson=locked_lesson)
        .order_by("position")
    )
    index = next((i for i, a in enumerate(rows) if a.pk == activity.pk), None)
    if index is None:
        return
    swap_with = index - 1 if direction == "up" else index + 1
    if swap_with < 0 or swap_with >= len(rows):
        return  # already at the edge -- a safe no-op

    a, b = rows[index], rows[swap_with]
    # Two-step swap so the uniqueness constraint is never violated mid-update.
    LessonActivity.objects.filter(pk=a.pk).update(position=10_000)
    LessonActivity.objects.filter(pk=b.pk).update(position=a.position)
    LessonActivity.objects.filter(pk=a.pk).update(position=b.position)

    locked_lesson.save(update_fields=["updated_at"])
    _record(
        locked_lesson,
        change="activities_reordered",
        teacher=teacher,
        extra={"activity_id": str(a.pk), "direction": direction},
    )


# --- ordered activity access ----------------------------------------


def lesson_activities(lesson: Lesson):
    """The lesson's activities in order, with every reference preselected."""

    return list(
        LessonActivity.objects.filter(lesson=lesson)
        .select_related(
            "simulation",
            "question",
            "assessment",
            "recovery_path",
            "recovery_path__misconception",
        )
        .order_by("position", "id")
    )


# --- publish validation --------------------------------------------


def validate_lesson_for_publish(lesson: Lesson, *, activities=None) -> list[str]:
    """Return a list of teacher-facing reasons the lesson cannot publish yet.

    An empty list means the structure is valid. This never repairs anything.
    """

    reasons: list[str] = []
    if not (lesson.title or "").strip():
        reasons.append("Add a lesson title.")

    objectives = [o for o in (lesson.learning_objectives or []) if str(o).strip()]
    if not objectives:
        reasons.append("Add at least one learning objective.")

    if not lesson.physics_concepts.exists():
        reasons.append("Link at least one Physics concept.")

    activities = lesson_activities(lesson) if activities is None else list(activities)
    has_content = bool(
        (isinstance(lesson.content, dict) and lesson.content)
        or activities
        or (lesson.description or "").strip()
    )
    if not has_content:
        reasons.append(
            "Add usable learning content: an activity, a description, or finalized AI content."
        )

    positions = [a.position for a in activities]
    if positions != list(range(1, len(activities) + 1)):
        reasons.append("The activity order is inconsistent. Re-open the builder and save.")

    for activity in activities:
        field_name = activity.reference_field_name
        if field_name is None:
            continue
        obj = getattr(activity, field_name)
        if obj is None:
            problem = "the linked item is no longer available"
        else:
            problem = _reference_usability_problem(activity.activity_type, obj)
        if problem:
            reasons.append(
                f"Activity {activity.position} (“{activity.title}”): "
                f"{problem[0].lower()}{problem[1:].rstrip('.')}."
            )

    return reasons


@transaction.atomic
def publish_lesson(*, lesson: Lesson, teacher) -> Lesson:
    """Explicit teacher publish. Refuses an invalid structure; never repairs it."""

    locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
    if locked.status == Lesson.Status.PUBLISHED:
        return locked  # idempotent -- a repeated publish click is a safe no-op

    reasons = validate_lesson_for_publish(locked)
    if reasons:
        raise LessonPublishError(reasons)

    locked.status = Lesson.Status.PUBLISHED
    locked.published_at = timezone.now()
    locked.save(update_fields=["status", "published_at", "updated_at"])
    record_event(
        locked,
        ProvenanceEvent.EventType.LESSON_PUBLISHED,
        source="teacher",
        actor=teacher,
        metadata={"status": locked.status},
    )
    return locked


# --- teacher preview + student rendering projections ----------------


@dataclass(frozen=True)
class PreviewActivity:
    position: int
    activity_type: str
    type_label: str
    title: str
    instructions: str
    tutor_focus: str
    reference_label: str  # e.g. "Newton's Second Law Lab" -- display only
    reference_ok: bool


def _type_label(activity_type: str) -> str:
    return dict(_ActivityType.choices).get(activity_type, activity_type)


def _reference_label(activity: LessonActivity) -> str:
    if activity.activity_type == _ActivityType.PHYSICS_LAB and activity.simulation_id:
        return activity.simulation.title
    if activity.activity_type == _ActivityType.PRACTICE and activity.question_id:
        return activity.question.prompt[:120]
    if activity.activity_type == _ActivityType.ASSESSMENT and activity.assessment_id:
        return activity.assessment.title
    if activity.activity_type == _ActivityType.RECOVERY and activity.recovery_path_id:
        return activity.recovery_path.title
    return ""


def build_lesson_preview(lesson: Lesson) -> list[PreviewActivity]:
    """Read-only projection of the ordered activities for the teacher preview.

    Creates nothing and touches no student state.
    """

    preview: list[PreviewActivity] = []
    for activity in lesson_activities(lesson):
        preview.append(
            PreviewActivity(
                position=activity.position,
                activity_type=activity.activity_type,
                type_label=_type_label(activity.activity_type),
                title=activity.title,
                instructions=activity.instructions,
                tutor_focus=activity.tutor_focus,
                reference_label=_reference_label(activity),
                reference_ok=_reference_is_still_usable(activity),
            )
        )
    return preview


@dataclass(frozen=True)
class StudentActivity:
    position: int
    activity_type: str
    type_label: str
    title: str
    instructions: str
    launch_url: str  # into an existing student system; "" if not launchable
    launch_label: str


def _student_launch(activity: LessonActivity, lesson: Lesson) -> tuple[str, str]:
    """(url, label) into an existing student system, or ("", "")."""

    t = activity.activity_type
    if t == _ActivityType.EXPLANATION:
        return "", ""
    if t == _ActivityType.PHYSICS_LAB and activity.simulation_id and activity.simulation.is_active:
        return reverse("physics_lab:detail", args=[activity.simulation.slug]), "Open the Physics Lab"
    if t == _ActivityType.PRACTICE and activity.question_id and activity.question.is_active:
        return reverse("lessons:student_activity_practice", args=[lesson.slug, activity.pk]), "Answer the practice question"
    if t == _ActivityType.ASSESSMENT and activity.assessment_id and activity.assessment.status == Assessment.Status.PUBLISHED:
        return reverse("students:assessment_detail", args=[activity.assessment_id]), "Open the assessment"
    if t == _ActivityType.TUTOR:
        base = reverse("students:tutor", args=[lesson.slug])
        if activity.tutor_focus:
            return base + "?" + urlencode({"prefill": activity.tutor_focus}), "Talk to the Tutor"
        return base, "Talk to the Tutor"
    if t == _ActivityType.RECOVERY:
        # Recovery is student-state-driven: it only runs when the existing
        # detector has an active misconception for this student, so the lesson
        # links to the student's own recovery entry point, never forcing one.
        return reverse("students:progress"), "Check your focus area"
    return "", ""


# --- practice activity: reuse the existing pure evaluators -----------


@dataclass(frozen=True)
class PracticeQuestionView:
    """Student-safe view of a practice question -- carries no answer key."""

    prompt: str
    question_type: str
    unit: str
    choices: tuple[str, ...]


def practice_question_view(question: QuestionBankItem) -> PracticeQuestionView:
    return PracticeQuestionView(
        prompt=question.prompt,
        question_type=question.question_type,
        unit=question.expected_unit or "",
        choices=tuple(str(c) for c in (question.choices or [])),
    )


@transaction.atomic
def record_practice_activity_answer(*, student, lesson: Lesson, activity: LessonActivity, submitted_answer):
    """Grade one practice-activity answer with the existing evaluators.

    No new grading engine and no new evidence table: correctness comes from
    ``apps.students.practice_services`` and the result is a standard
    ``LearningEvidence(kind=PRACTICE_ATTEMPTED)`` row, exactly like the Step 18
    practice engine and the Step 25 recovery concept check.
    """

    question = activity.question
    if activity.activity_type != _ActivityType.PRACTICE or question is None:
        raise LessonAuthoringError("That activity is not a practice question.")
    if not _question_is_gradeable(question):
        # Should be unreachable for a published lesson (link + publish both
        # check this), but a defensive raise keeps a bad admin edit from
        # throwing an uncaught TypeError out of the evaluator.
        raise LessonAuthoringError("This practice question cannot be graded right now.")

    if question.question_type == QuestionBankItem.QuestionType.MULTIPLE_CHOICE:
        evaluation = evaluate_choice_answer(
            submitted_answer, question.choices, question.correct_choice
        )
        is_correct = evaluation.is_correct
        answer_text = evaluation.submitted_label
        expected_display = evaluation.expected_label
    else:  # numeric
        evaluation = evaluate_numeric_answer(
            submitted_answer, question.expected_value, question.tolerance
        )
        is_correct = evaluation.is_correct
        answer_text = str(evaluation.submitted_value)
        expected_display = str(question.expected_value)
        if question.expected_unit:
            expected_display = f"{expected_display} {question.expected_unit}"

    evidence = LearningEvidence.objects.create(
        student=student,
        lesson=lesson,
        kind=LearningEvidence.Kind.PRACTICE_ATTEMPTED,
        detail=answer_text[:300],
        context={
            "practice": True,
            "lesson_activity": str(activity.pk),
            "question_key": question.key,
            "question_type": question.question_type,
            "is_correct": is_correct,
            "concept": question.concept.name if question.concept_id else "",
        },
    )
    return {
        "is_correct": is_correct,
        "expected_display": expected_display,
        "explanation": question.explanation or "",
        "evidence_id": evidence.pk,
    }


def build_student_lesson_activities(lesson: Lesson) -> list[StudentActivity]:
    """Student-safe ordered activity list for a published lesson. Read-only.

    Returns ``[]`` for a lesson that is not published or has no activities, so
    legacy lessons render exactly as before.
    """

    if lesson.status != Lesson.Status.PUBLISHED:
        return []

    out: list[StudentActivity] = []
    for activity in lesson_activities(lesson):
        url, label = _student_launch(activity, lesson)
        out.append(
            StudentActivity(
                position=activity.position,
                activity_type=activity.activity_type,
                type_label=_type_label(activity.activity_type),
                title=activity.title,
                instructions=activity.instructions,
                launch_url=url,
                launch_label=label,
            )
        )
    return out
