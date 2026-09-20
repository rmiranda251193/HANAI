"""Step 28 -- deterministic cohort analytics for the teacher workspace.

Analytics here are *projections over evidence that already exists*. This module
never writes, never grades, never calls an AI provider, and never becomes a
second source of truth: every number is a bounded aggregate query over the
authoritative records (``LearningEvidence``, ``ExperimentAttempt``,
``AssessmentAttempt`` / ``AssessmentAnswer``, ``PracticeAttempt``,
``StudentMisconception``, the Step 25 recovery models, ``TutorSession`` /
``TutorMessage``, ``LessonActivity``).

Terminology is deliberately factual -- *attempts*, *correct answers*, *evidence*,
*activity*, *misconception candidates*, *recovery activities completed*. There is
no "mastery", "score out of 100", "ability", or "at risk": the project has no
validated model for any of those, so this module does not invent one. Attention
signals are transparent deterministic rules phrased as review prompts, not
diagnoses.

Authorization: the project has no per-teacher student roster (a ``teacher`` is
any ``is_staff`` user and ``student_detail`` already resolves any
``StudentProfile`` by pk). The cohort is therefore every student, exactly like
the existing student list. Filters (student / lesson / concept) are resolved
server-side; an unknown id is reported as a notice and ignored, never created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Case, Count, IntegerField, Max, Q, Sum, When
from django.utils import timezone

from apps.assessments.models import AssessmentAnswer, AssessmentAttempt
from apps.lessons.models import Lesson, LessonActivity
from apps.physics.models import PhysicsConcept
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    PracticeAttempt,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentProfile,
    StudentRecoveryActivityCompletion,
    TutorMessage,
    TutorSession,
)

# --- configuration -------------------------------------------------------

# range key -> whole days back from "now". ``None`` means "all available".
DATE_RANGES: dict[str, int | None] = {"7": 7, "30": 30, "90": 90, "all": None}
DEFAULT_RANGE_KEY = "30"
MAX_RANGE_DAYS = 365

# Hard caps so a pathological database can never turn one page into a slow scan.
STUDENT_CAP = 2000
CONCEPT_CAP = 200
LESSON_CHOICE_CAP = 200
ASSESSMENT_CAP = 200

# "No recent evidence" attention rule: a student with history but nothing newer.
STALE_EVIDENCE_DAYS = 14
# "Repeated incorrect practice" attention rule.
REPEATED_INCORRECT_THRESHOLD = 3
# "Repeated misconception evidence" attention rule.
REPEATED_MISCONCEPTION_OBSERVATIONS = 3
# "Recovery started but not finished" attention rule.
STALLED_RECOVERY_DAYS = 3

_Kind = LearningEvidence.Kind
_MisconceptionStatus = StudentMisconception.Status
_ELIGIBLE_MISCONCEPTION_STATUSES = (
    _MisconceptionStatus.CANDIDATE,
    _MisconceptionStatus.CONFIRMED_BY_TEACHER,
)


# --- filters -----------------------------------------------------------


@dataclass(frozen=True)
class AnalyticsFilters:
    """Resolved, validated cohort filters plus any user-facing notices.

    ``student`` / ``lesson`` / ``concept`` are real objects or ``None``. ``start``
    is timezone-aware or ``None`` ("all available"); ``end`` is always
    timezone-aware. ``notices`` explains any input that was rejected and ignored.
    """

    range_key: str = DEFAULT_RANGE_KEY
    start: datetime | None = None
    end: datetime | None = None
    student: StudentProfile | None = None
    lesson: Lesson | None = None
    concept: PhysicsConcept | None = None
    notices: tuple[str, ...] = ()

    @property
    def range_label(self) -> str:
        if self.range_key == "all":
            return "All available dates"
        if self.range_key == "custom":
            s = self.start.date().isoformat() if self.start else "?"
            e = self.end.date().isoformat() if self.end else "?"
            return f"{s} to {e}"
        return f"Last {DATE_RANGES.get(self.range_key, 30)} days"

    def evidence_window(self, field_name: str) -> Q:
        """A ``Q`` restricting ``field_name`` to [start, end]; empty for 'all'."""

        q = Q(**{f"{field_name}__lte": self.end}) if self.end else Q()
        if self.start is not None:
            q &= Q(**{f"{field_name}__gte": self.start})
        return q


def _parse_date(raw: str) -> datetime | None:
    try:
        parsed = datetime.strptime(raw.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def _resolve_student(raw_id, notices: list[str]) -> StudentProfile | None:
    if not raw_id:
        return None
    try:
        student = StudentProfile.objects.filter(pk=int(raw_id)).first()
    except (TypeError, ValueError):
        student = None
    if student is None:
        notices.append("That student could not be found; showing the whole cohort.")
    return student


def _resolve_lesson(raw_id, notices: list[str]) -> Lesson | None:
    if not raw_id:
        return None
    try:
        lesson = Lesson.objects.filter(pk=raw_id).first()
    except (ValidationError, ValueError, TypeError):
        lesson = None
    if lesson is None:
        notices.append("That lesson could not be found; the lesson filter was ignored.")
    return lesson


def _resolve_concept(raw_id, notices: list[str]) -> PhysicsConcept | None:
    if not raw_id:
        return None
    try:
        concept = PhysicsConcept.objects.filter(pk=int(raw_id)).first()
    except (TypeError, ValueError):
        concept = None
    if concept is None:
        notices.append("That concept could not be found; the concept filter was ignored.")
    return concept


def resolve_analytics_filters(params, *, now=None) -> AnalyticsFilters:
    """Turn raw querystring-style params into a safe :class:`AnalyticsFilters`.

    Never raises for bad input: an invalid date range, an unknown id, or an
    oversized window is recorded in ``notices`` and the safe default is used.
    """

    now = now or timezone.now()
    notices: list[str] = []

    def _get(key):
        try:
            return params.get(key)
        except AttributeError:  # pragma: no cover - defensive
            return None

    range_key = (_get("range") or DEFAULT_RANGE_KEY).strip()
    start_raw = _get("start")
    end_raw = _get("end")

    start: datetime | None = None
    end: datetime = now

    if start_raw or end_raw:
        parsed_start = _parse_date(start_raw or "")
        parsed_end = _parse_date(end_raw or "")
        if parsed_start is None or parsed_end is None:
            notices.append(
                "A custom date was not a valid YYYY-MM-DD value; showing the last "
                f"{DATE_RANGES[DEFAULT_RANGE_KEY]} days instead."
            )
            range_key = DEFAULT_RANGE_KEY
        else:
            # Include the whole end day.
            parsed_end = parsed_end + timedelta(days=1) - timedelta(seconds=1)
            if parsed_start > parsed_end:
                notices.append(
                    "The start date was after the end date; showing the last "
                    f"{DATE_RANGES[DEFAULT_RANGE_KEY]} days instead."
                )
                range_key = DEFAULT_RANGE_KEY
            elif (parsed_end - parsed_start).days > MAX_RANGE_DAYS:
                notices.append(
                    f"A date range cannot be longer than {MAX_RANGE_DAYS} days; "
                    f"showing the {MAX_RANGE_DAYS} days ending on the end date."
                )
                start = parsed_end - timedelta(days=MAX_RANGE_DAYS)
                end = parsed_end
                range_key = "custom"
            else:
                start, end, range_key = parsed_start, parsed_end, "custom"

    if range_key not in DATE_RANGES and range_key != "custom":
        notices.append("Unknown date range; showing the last 30 days.")
        range_key = DEFAULT_RANGE_KEY

    if range_key in DATE_RANGES:
        days = DATE_RANGES[range_key]
        start = None if days is None else now - timedelta(days=days)
        end = now

    student = _resolve_student(_get("student"), notices)
    lesson = _resolve_lesson(_get("lesson"), notices)
    concept = _resolve_concept(_get("concept"), notices)

    return AnalyticsFilters(
        range_key=range_key,
        start=start,
        end=end,
        student=student,
        lesson=lesson,
        concept=concept,
        notices=tuple(notices),
    )


# --- snapshot dataclasses --------------------------------------------


@dataclass(frozen=True)
class CountRow:
    label: str
    value: int
    note: str = ""


@dataclass(frozen=True)
class ConceptRow:
    concept: str
    topic: str
    students_engaged: int
    lesson_linked_evidence: int
    practice_attempts: int
    practice_correct: int
    assessment_answers: int
    assessment_correct: int
    misconception_candidates: int
    recovery_activities_completed: int


@dataclass(frozen=True)
class MisconceptionRow:
    code: str
    title: str
    concept: str
    students_affected: int
    candidates: int
    confirmed: int
    resolved: int
    dismissed: int
    recoveries_started: int
    recoveries_completed: int
    recent_observations: int


@dataclass(frozen=True)
class AssessmentRow:
    title: str
    concept: str
    attempts: int
    completed: int
    completion_label: str
    avg_correct_label: str


@dataclass(frozen=True)
class SimulationRow:
    simulation_type: str
    started: int
    completed: int
    completion_label: str


@dataclass(frozen=True)
class ScenarioRow:
    scenario: str
    attempts: int
    target_achieved: int
    achievement_label: str


@dataclass(frozen=True)
class AttentionRow:
    student_id: int
    student: str
    band: str  # "Needs attention" | "Review suggested" | "No recent evidence"
    signals: tuple[str, ...]


@dataclass(frozen=True)
class AnalyticsSnapshot:
    filters: AnalyticsFilters
    student_count: int
    active_student_count: int
    activity_summary: tuple[CountRow, ...]
    concept_summary: tuple[ConceptRow, ...]
    misconception_summary: tuple[MisconceptionRow, ...]
    recovery_summary: tuple[CountRow, ...]
    assessment_summary: tuple[AssessmentRow, ...]
    practice_summary: tuple[CountRow, ...]
    physics_lab_summary: tuple[CountRow, ...]
    simulation_usage: tuple[SimulationRow, ...]
    scenario_summary: tuple[ScenarioRow, ...]
    tutor_summary: tuple[CountRow, ...]
    activity_type_summary: tuple[CountRow, ...]
    attention_signals: tuple[AttentionRow, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


# --- small helpers ---------------------------------------------------


def _rate_label(part: int, whole: int, *, unit: str = "") -> str:
    """A factual 'a of b' label with an optional plain percentage in words.

    Never called a score or mastery -- it is literally 'how many of how many'.
    """

    if whole <= 0:
        return "no data yet"
    pct = round(100 * part / whole)
    suffix = f" {unit}" if unit else ""
    return f"{part} of {whole}{suffix} ({pct}%)"


def _sum_case(condition: Q) -> Sum:
    return Sum(Case(When(condition, then=1), default=0, output_field=IntegerField()))


# --- the one orchestrator ------------------------------------------


def get_cohort_analytics(filters: AnalyticsFilters) -> AnalyticsSnapshot:
    """Build the whole dashboard snapshot with a bounded set of grouped queries.

    No query runs per student, per concept, or per misconception: each section
    is one (occasionally two) aggregate query grouped in the database. The
    number of queries does not grow with cohort size or history length.
    """

    students = list(
        StudentProfile.objects.all().order_by("display_name")[:STUDENT_CAP]
        if filters.student is None
        else StudentProfile.objects.filter(pk=filters.student.pk)
    )
    student_ids = [s.pk for s in students]
    names = {s.pk: s.display_name for s in students}
    student_count = len(students)

    ev_window = filters.evidence_window
    lesson_q = Q(lesson_id=filters.lesson.pk) if filters.lesson else Q()
    concept_pk = filters.concept.pk if filters.concept else None

    # --- activity summary + active students (LearningEvidence) --------
    evidence_qs = LearningEvidence.objects.filter(
        Q(student_id__in=student_ids) & ev_window("created_at") & lesson_q
    )
    if concept_pk is not None:
        evidence_qs = evidence_qs.filter(lesson__physics_concepts=concept_pk)
    by_kind = {
        row["kind"]: row["n"]
        for row in evidence_qs.values("kind").annotate(n=Count("id"))
    }
    active_student_count = (
        evidence_qs.values("student_id").distinct().count() if student_ids else 0
    )

    def _k(kind) -> int:
        return by_kind.get(kind, 0)

    activity_summary = (
        CountRow("Questions asked", _k(_Kind.QUESTION_ASKED)),
        CountRow("Practice attempted", _k(_Kind.PRACTICE_ATTEMPTED)),
        CountRow("Predictions submitted", _k(_Kind.PREDICTION_SUBMITTED)),
        CountRow("Observations submitted", _k(_Kind.EXPERIMENT_OBSERVED)),
        CountRow("Explanations submitted", _k(_Kind.EXPLANATION_SUBMITTED)),
        CountRow("Assessment answers", _k(_Kind.ASSESSMENT_ATTEMPTED)),
        CountRow("Recovery activities completed", _k(_Kind.RECOVERY_ACTIVITY_COMPLETED)),
    )

    # --- practice (cohort aggregate + per concept) -------------------
    practice_base = PracticeAttempt.objects.filter(
        Q(student_id__in=student_ids) & ev_window("created_at") & lesson_q
    )
    if concept_pk is not None:
        practice_base = practice_base.filter(concept_id=concept_pk)
    practice_totals = practice_base.aggregate(
        attempts=Count("id"),
        correct=_sum_case(Q(is_correct=True)),
        incorrect=_sum_case(Q(is_correct=False)),
    )
    p_attempts = practice_totals["attempts"] or 0
    p_correct = practice_totals["correct"] or 0
    p_incorrect = practice_totals["incorrect"] or 0
    practice_summary = (
        CountRow("Attempts", p_attempts),
        CountRow("Correct", p_correct),
        CountRow("Incorrect", p_incorrect),
        CountRow(
            "Correct-answer rate",
            0,
            note=_rate_label(p_correct, p_correct + p_incorrect, unit="graded attempts"),
        ),
    )

    practice_by_concept = {
        row["concept_id"]: row
        for row in practice_base.filter(concept_id__isnull=False)
        .values("concept_id")
        .annotate(
            attempts=Count("id"),
            correct=_sum_case(Q(is_correct=True)),
            students=Count("student_id", distinct=True),
        )
    }

    # --- assessments (per assessment + per concept) -----------------
    attempt_base = AssessmentAttempt.objects.filter(
        Q(student_id__in=student_ids) & ev_window("started_at")
    )
    if filters.lesson:
        attempt_base = attempt_base.filter(assessment__lesson_id=filters.lesson.pk)
    if concept_pk is not None:
        attempt_base = attempt_base.filter(assessment__concept_id=concept_pk)
    assessment_rows_raw = list(
        attempt_base.values(
            "assessment_id", "assessment__title", "assessment__concept__name"
        ).annotate(
            attempts=Count("id"),
            completed=_sum_case(Q(completed_at__isnull=False)),
        )[:ASSESSMENT_CAP]
    )
    assessment_ids = [r["assessment_id"] for r in assessment_rows_raw]
    # Correct-answer counts, completed attempts only, grouped by assessment.
    completed_answer_stats = {
        row["attempt__assessment_id"]: row
        for row in AssessmentAnswer.objects.filter(
            attempt__student_id__in=student_ids,
            attempt__completed_at__isnull=False,
            attempt__assessment_id__in=assessment_ids,
        )
        .values("attempt__assessment_id")
        .annotate(correct=_sum_case(Q(is_correct=True)), answered=Count("id"))
    }
    assessment_summary = tuple(
        AssessmentRow(
            title=r["assessment__title"],
            concept=r["assessment__concept__name"] or "",
            attempts=r["attempts"],
            completed=r["completed"] or 0,
            completion_label=_rate_label(r["completed"] or 0, r["attempts"]),
            avg_correct_label=_assessment_avg_label(
                completed_answer_stats.get(r["assessment_id"]), r["completed"] or 0
            ),
        )
        for r in sorted(assessment_rows_raw, key=lambda r: -r["attempts"])
    )

    _concept_key = "assessment_question__question__concept_id"
    assessment_by_concept = {
        row[_concept_key]: row
        for row in AssessmentAnswer.objects.filter(
            Q(attempt__student_id__in=student_ids)
            & ev_window("attempted_at")
            & Q(assessment_question__question__concept__isnull=False)
            & (
                Q(assessment_question__question__concept_id=concept_pk)
                if concept_pk is not None
                else Q()
            )
        )
        .values(_concept_key)
        .annotate(
            answered=Count("id"),
            correct=_sum_case(Q(is_correct=True)),
            students=Count("attempt__student_id", distinct=True),
        )
    }

    # --- misconceptions --------------------------------------------
    misc_window = ev_window("last_observed_at")
    misc_rows = list(
        StudentMisconception.objects.filter(Q(student_id__in=student_ids))
        .filter(
            Q(misconception__physics_concept_id=concept_pk)
            if concept_pk is not None
            else Q()
        )
        .values(
            "misconception_id",
            "misconception__code",
            "misconception__title",
            "misconception__physics_concept__name",
        )
        .annotate(
            students_affected=Count("student_id", distinct=True),
            candidates=_sum_case(Q(status=_MisconceptionStatus.CANDIDATE)),
            confirmed=_sum_case(Q(status=_MisconceptionStatus.CONFIRMED_BY_TEACHER)),
            resolved=_sum_case(Q(status=_MisconceptionStatus.RESOLVED)),
            dismissed=_sum_case(Q(status=_MisconceptionStatus.DISMISSED)),
            recent_observations=_sum_case(misc_window),
        )
    )
    recovery_by_misconception = {
        row["path__misconception_id"]: row
        for row in StudentMisconceptionRecovery.objects.filter(
            student_id__in=student_ids
        )
        .values("path__misconception_id")
        .annotate(
            started=Count("id"),
            completed=_sum_case(Q(completed_at__isnull=False)),
        )
    }
    misconception_summary = tuple(
        MisconceptionRow(
            code=r["misconception__code"],
            title=r["misconception__title"],
            concept=r["misconception__physics_concept__name"] or "",
            students_affected=r["students_affected"],
            candidates=r["candidates"] or 0,
            confirmed=r["confirmed"] or 0,
            resolved=r["resolved"] or 0,
            dismissed=r["dismissed"] or 0,
            recoveries_started=(
                recovery_by_misconception.get(r["misconception_id"], {}).get("started", 0)
            ),
            recoveries_completed=(
                recovery_by_misconception.get(r["misconception_id"], {}).get("completed", 0)
                or 0
            ),
            recent_observations=r["recent_observations"] or 0,
        )
        for r in sorted(misc_rows, key=lambda r: (-r["students_affected"], r["misconception__code"]))
    )

    # --- recovery (Step 25) --------------------------------------
    recovery_agg = StudentMisconceptionRecovery.objects.filter(
        Q(student_id__in=student_ids) & ev_window("started_at")
    ).aggregate(
        started=Count("id"),
        completed=_sum_case(Q(completed_at__isnull=False)),
    )
    r_started = recovery_agg["started"] or 0
    r_completed = recovery_agg["completed"] or 0
    activities_completed = StudentRecoveryActivityCompletion.objects.filter(
        Q(recovery__student_id__in=student_ids) & ev_window("completed_at")
    ).count()
    misconceptions_with_completed_recovery = (
        StudentMisconceptionRecovery.objects.filter(
            student_id__in=student_ids, completed_at__isnull=False
        )
        .values("observation__misconception_id")
        .distinct()
        .count()
    )
    misconceptions_resolved_by_teacher = StudentMisconception.objects.filter(
        student_id__in=student_ids, status=_MisconceptionStatus.RESOLVED
    ).count()
    recovery_summary = (
        CountRow("Recovery paths started", r_started),
        CountRow("Recovery activities completed", activities_completed),
        CountRow("Recovery paths completed", r_completed),
        CountRow("Completion rate", 0, note=_rate_label(r_completed, r_started, unit="paths")),
        CountRow(
            "Misconceptions with a completed recovery",
            misconceptions_with_completed_recovery,
            note="Completing a recovery is not the same as the misconception being resolved.",
        ),
        CountRow(
            "Misconceptions resolved by a teacher decision",
            misconceptions_resolved_by_teacher,
            note="Only a teacher decision resolves a misconception.",
        ),
    )

    # --- physics lab -------------------------------------------
    lab_base = ExperimentAttempt.objects.filter(
        Q(student_id__in=student_ids) & ev_window("started_at") & lesson_q
    )
    if concept_pk is not None:
        lab_base = lab_base.filter(simulation__concept_id=concept_pk)
    lab_agg = lab_base.aggregate(
        started=Count("id"),
        completed=_sum_case(Q(completed_at__isnull=False)),
        predictions=_sum_case(~Q(prediction="")),
        observations=_sum_case(~Q(observation="")),
        explanations=_sum_case(~Q(explanation="")),
    )
    l_started = lab_agg["started"] or 0
    l_completed = lab_agg["completed"] or 0
    physics_lab_summary = (
        CountRow("Experiments started", l_started),
        CountRow("Experiments completed", l_completed),
        CountRow("Predictions submitted", lab_agg["predictions"] or 0),
        CountRow("Observations submitted", lab_agg["observations"] or 0),
        CountRow("Explanations submitted", lab_agg["explanations"] or 0),
        CountRow(
            "Completion rate",
            0,
            note=_rate_label(l_completed, l_started, unit="experiments"),
        ),
    )
    simulation_usage = tuple(
        SimulationRow(
            simulation_type=row["simulation__simulation_type"],
            started=row["started"],
            completed=row["completed"] or 0,
            completion_label=_rate_label(row["completed"] or 0, row["started"]),
        )
        for row in sorted(
            lab_base.values("simulation__simulation_type").annotate(
                started=Count("id"),
                completed=_sum_case(Q(completed_at__isnull=False)),
            ),
            key=lambda r: -r["started"],
        )
    )

    # --- teacher-authored scenario challenges (Scenario Studio) -----
    # These checks record a compact LearningEvidence row (kind
    # EXPERIMENT_OBSERVED, a "scenario" key in context) rather than an
    # ExperimentAttempt, so they are counted here rather than folded into
    # physics_lab_summary above. Not lesson/concept filtered: a scenario
    # check is not itself tagged with the lesson it may have been launched
    # from -- see the "notes" disclosure below.
    scenario_rows_raw = list(
        LearningEvidence.objects.filter(
            Q(student_id__in=student_ids) & ev_window("created_at"),
            kind=_Kind.EXPERIMENT_OBSERVED,
            context__has_key="scenario",
        )
        .values("context__scenario", "context__scenario_title")
        .annotate(
            attempts=Count("id"),
            target_achieved=_sum_case(Q(context__result=True)),
        )
    )
    scenario_summary = tuple(
        ScenarioRow(
            scenario=r["context__scenario_title"] or r["context__scenario"],
            attempts=r["attempts"],
            target_achieved=r["target_achieved"] or 0,
            achievement_label=_rate_label(r["target_achieved"] or 0, r["attempts"], unit="attempts"),
        )
        for r in sorted(scenario_rows_raw, key=lambda r: -r["attempts"])
    )

    # --- tutor (aggregate only, never conversation content) -------
    tutor_sessions = (
        TutorSession.objects.filter(
            Q(student_id__in=student_ids) & ev_window("started_at") & lesson_q
        ).count()
    )
    tutor_messages = TutorMessage.objects.filter(
        Q(session__student_id__in=student_ids)
        & Q(role=TutorMessage.Role.STUDENT)
        & ev_window("created_at")
        & (Q(session__lesson_id=filters.lesson.pk) if filters.lesson else Q())
    ).count()
    tutor_summary = (
        CountRow("Tutor sessions", tutor_sessions),
        CountRow("Student messages", tutor_messages),
        CountRow("Questions asked (evidence)", _k(_Kind.QUESTION_ASKED)),
    )

    # --- lesson activity composition (Step 26) ------------------
    activity_type_qs = LessonActivity.objects.all()
    if filters.lesson:
        activity_type_qs = activity_type_qs.filter(lesson_id=filters.lesson.pk)
    if concept_pk is not None:
        activity_type_qs = activity_type_qs.filter(lesson__physics_concepts=concept_pk)
    activity_type_counts = {
        row["activity_type"]: row["n"]
        for row in activity_type_qs.values("activity_type").annotate(n=Count("id"))
    }
    activity_type_summary = tuple(
        CountRow(label, activity_type_counts.get(value, 0))
        for value, label in LessonActivity.ActivityType.choices
    )

    # --- concept summary (join the per-concept maps above) --------
    concept_qs = PhysicsConcept.objects.filter(is_active=True)
    if concept_pk is not None:
        concept_qs = concept_qs.filter(pk=concept_pk)
    concepts = list(concept_qs.order_by("topic", "name")[:CONCEPT_CAP])

    # Built from a fresh queryset (not chained off ``evidence_qs``) so a concept
    # filter does not add a second M2M join and inflate the per-concept count on
    # multi-concept lessons.
    evidence_concept_qs = LearningEvidence.objects.filter(
        Q(student_id__in=student_ids)
        & ev_window("created_at")
        & lesson_q
        & Q(lesson__physics_concepts__isnull=False)
    )
    if concept_pk is not None:
        evidence_concept_qs = evidence_concept_qs.filter(lesson__physics_concepts=concept_pk)
    evidence_by_concept = {
        row["lesson__physics_concepts"]: row["n"]
        for row in evidence_concept_qs.values("lesson__physics_concepts").annotate(
            n=Count("id")
        )
    }
    misc_candidates_by_concept = {
        row["misconception__physics_concept_id"]: row["n"]
        for row in StudentMisconception.objects.filter(
            student_id__in=student_ids, status__in=_ELIGIBLE_MISCONCEPTION_STATUSES
        )
        .values("misconception__physics_concept_id")
        .annotate(n=Count("id"))
    }
    recovery_activity_by_concept = {
        row["recovery__path__misconception__physics_concept_id"]: row["n"]
        for row in StudentRecoveryActivityCompletion.objects.filter(
            Q(recovery__student_id__in=student_ids) & ev_window("completed_at")
        )
        .values("recovery__path__misconception__physics_concept_id")
        .annotate(n=Count("id"))
    }

    concept_summary_rows = []
    for concept in concepts:
        p = practice_by_concept.get(concept.pk, {})
        a = assessment_by_concept.get(concept.pk, {})
        engaged = max(p.get("students", 0), a.get("students", 0))
        row = ConceptRow(
            concept=concept.name,
            topic=concept.topic,
            students_engaged=engaged,
            lesson_linked_evidence=evidence_by_concept.get(concept.pk, 0),
            practice_attempts=p.get("attempts", 0),
            practice_correct=p.get("correct", 0) or 0,
            assessment_answers=a.get("answered", 0),
            assessment_correct=a.get("correct", 0) or 0,
            misconception_candidates=misc_candidates_by_concept.get(concept.pk, 0),
            recovery_activities_completed=recovery_activity_by_concept.get(concept.pk, 0),
        )
        if (
            row.lesson_linked_evidence
            or row.practice_attempts
            or row.assessment_answers
            or row.misconception_candidates
            or row.recovery_activities_completed
        ):
            concept_summary_rows.append(row)

    # --- attention signals (deterministic rules, review prompts) ---
    attention_signals = _attention_signals(
        student_ids=student_ids,
        names=names,
        filters=filters,
    )

    notes = (
        "Every number is activity and evidence that already happened -- not a "
        "score, a grade, or a prediction.",
        "Per-activity launch/completion is not tracked at the lesson-activity "
        "level; activity composition is shown instead.",
        "Scenario challenge attempts are not filtered by lesson or concept: a "
        "check is not itself tagged with the lesson it may have been "
        "launched from.",
    )

    return AnalyticsSnapshot(
        filters=filters,
        student_count=student_count,
        active_student_count=active_student_count,
        activity_summary=activity_summary,
        concept_summary=tuple(concept_summary_rows),
        misconception_summary=misconception_summary,
        recovery_summary=recovery_summary,
        assessment_summary=assessment_summary,
        practice_summary=practice_summary,
        physics_lab_summary=physics_lab_summary,
        simulation_usage=simulation_usage,
        scenario_summary=scenario_summary,
        tutor_summary=tutor_summary,
        activity_type_summary=activity_type_summary,
        attention_signals=attention_signals,
        notes=notes,
    )


def _assessment_avg_label(stats: dict | None, completed_attempts: int) -> str:
    if not stats or completed_attempts <= 0:
        return "no completed attempts yet"
    correct = stats.get("correct", 0) or 0
    answered = stats.get("answered", 0) or 0
    avg_correct = correct / completed_attempts
    avg_answered = answered / completed_attempts
    pct = round(100 * correct / answered) if answered else 0
    return (
        f"{avg_correct:.1f} correct of {avg_answered:.1f} answered per completed "
        f"attempt ({pct}% of answered, {completed_attempts} completed)"
    )


def _attention_signals(*, student_ids, names, filters) -> tuple[AttentionRow, ...]:
    """A few transparent deterministic rules. Every phrase is a review prompt."""

    if not student_ids:
        return ()

    ev_window = filters.evidence_window
    per_student: dict[int, dict] = {}

    def _bucket(sid: int) -> dict:
        return per_student.setdefault(sid, {"signals": [], "bands": set()})

    # Rule 1 -- repeated incorrect practice on one concept.
    practice_rule = (
        PracticeAttempt.objects.filter(
            Q(student_id__in=student_ids) & ev_window("created_at") & Q(concept__isnull=False)
        )
        .values("student_id", "concept__name")
        .annotate(
            incorrect=_sum_case(Q(is_correct=False)),
            correct=_sum_case(Q(is_correct=True)),
        )
    )
    for row in practice_rule:
        if (row["incorrect"] or 0) >= REPEATED_INCORRECT_THRESHOLD and (
            row["incorrect"] or 0
        ) > (row["correct"] or 0):
            b = _bucket(row["student_id"])
            b["signals"].append(
                f"Repeated incorrect practice on {row['concept__name']} "
                f"({row['incorrect']} incorrect)."
            )
            b["bands"].add("Needs attention")

    # Rule 2 -- a misconception candidate observed several times.
    misc_rule = (
        StudentMisconception.objects.filter(
            student_id__in=student_ids, status__in=_ELIGIBLE_MISCONCEPTION_STATUSES
        )
        .values("student_id", "misconception__title")
        .annotate(observations=Max("observation_count"))
    )
    for row in misc_rule:
        if (row["observations"] or 0) >= REPEATED_MISCONCEPTION_OBSERVATIONS:
            b = _bucket(row["student_id"])
            b["signals"].append(
                f"Repeated evidence for a misconception "
                f"({row['observations']} observations)."
            )
            b["bands"].add("Review suggested")

    # Rule 3 -- a recovery started a while ago and not finished.
    now = filters.end or timezone.now()
    stalled = (
        StudentMisconceptionRecovery.objects.filter(
            student_id__in=student_ids,
            completed_at__isnull=True,
            started_at__lte=now - timedelta(days=STALLED_RECOVERY_DAYS),
        )
        .values("student_id")
        .annotate(n=Count("id"))
    )
    for row in stalled:
        b = _bucket(row["student_id"])
        b["signals"].append("A recovery path was started but not completed.")
        b["bands"].add("Review suggested")

    # Rule 4 -- history exists but nothing recent.
    last_evidence = (
        LearningEvidence.objects.filter(student_id__in=student_ids)
        .values("student_id")
        .annotate(last=Max("created_at"))
    )
    stale_cutoff = now - timedelta(days=STALE_EVIDENCE_DAYS)
    for row in last_evidence:
        if row["last"] and row["last"] < stale_cutoff:
            b = _bucket(row["student_id"])
            b["signals"].append(
                f"No learning evidence in the last {STALE_EVIDENCE_DAYS} days."
            )
            b["bands"].add("No recent evidence")

    def _band(bands: set[str]) -> str:
        for candidate in ("Needs attention", "Review suggested", "No recent evidence"):
            if candidate in bands:
                return candidate
        return "Review suggested"

    rows = [
        AttentionRow(
            student_id=sid,
            student=names.get(sid, f"Student {sid}"),
            band=_band(data["bands"]),
            signals=tuple(data["signals"]),
        )
        for sid, data in per_student.items()
        if data["signals"]
    ]
    band_rank = {"Needs attention": 0, "Review suggested": 1, "No recent evidence": 2}
    rows.sort(key=lambda r: (band_rank.get(r.band, 3), r.student.lower()))
    return tuple(rows)


# --- choice lists for the filter form ------------------------------


def analytics_filter_choices():
    """(students, lessons, concepts) option lists for the dashboard filter form."""

    students = list(
        StudentProfile.objects.order_by("display_name").values_list("pk", "display_name")[
            :STUDENT_CAP
        ]
    )
    lessons = list(
        Lesson.objects.order_by("title").values_list("pk", "title")[:LESSON_CHOICE_CAP]
    )
    concepts = list(
        PhysicsConcept.objects.filter(is_active=True)
        .order_by("topic", "name")
        .values_list("pk", "name")[:CONCEPT_CAP]
    )
    return students, lessons, concepts


# --- CSV export ---------------------------------------------------


def cohort_csv_rows(snapshot: AnalyticsSnapshot):
    """Yield spreadsheet rows (lists of str) for the cohort overview + concepts.

    Only data the dashboard already shows. No raw tutor text, no teacher notes,
    no hidden identifiers. Cells are neutralised against spreadsheet formula
    injection by the view.
    """

    f = snapshot.filters
    yield ["DodongOS Physics AI -- cohort analytics"]
    yield ["Date range", f.range_label]
    if f.student:
        yield ["Student filter", f.student.display_name]
    if f.lesson:
        yield ["Lesson filter", f.lesson.title]
    if f.concept:
        yield ["Concept filter", f.concept.name]
    yield ["Students in view", str(snapshot.student_count)]
    yield ["Active students (evidence in range)", str(snapshot.active_student_count)]
    yield []

    yield ["Cohort activity", "Count"]
    for row in snapshot.activity_summary:
        yield [row.label, str(row.value)]
    yield []

    yield [
        "Concept",
        "Topic",
        "Students engaged",
        "Lesson-linked evidence",
        "Practice attempts",
        "Practice correct",
        "Assessment answers",
        "Assessment correct",
        "Misconception candidates",
        "Recovery activities completed",
    ]
    for c in snapshot.concept_summary:
        yield [
            c.concept,
            c.topic,
            str(c.students_engaged),
            str(c.lesson_linked_evidence),
            str(c.practice_attempts),
            str(c.practice_correct),
            str(c.assessment_answers),
            str(c.assessment_correct),
            str(c.misconception_candidates),
            str(c.recovery_activities_completed),
        ]
