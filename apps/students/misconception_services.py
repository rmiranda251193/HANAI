"""Physics misconception engine: rules + optional AI, persisted as candidates.

Confidence policy (transparent, not statistical):

- ``observation_count`` counts *turns* in which this misconception surfaced for
  the student, not raw signals.
- One turn, one detector          -> low
- Two turns, or one turn with two independent detectors (e.g. a rule AND the AI)
                                  -> medium
- Three or more turns             -> high

Confidence never decreases on its own. A teacher confirming, resolving, or
dismissing changes only ``status`` -- never confidence, and it is the only way
``status`` leaves ``candidate``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai.exceptions import AIError
from apps.ai.providers import AIProvider
from apps.ai.requests import ConceptContext
from apps.ai.schemas import parse_model_json
from apps.physics.models import PhysicsConcept, PhysicsMisconception

from .exceptions import InvalidMisconceptionAssessmentError, MisconceptionDecisionError
from .misconception_prompts import (
    MISCONCEPTION_PROMPT_VERSION,
    build_misconception_prompt,
)
from .misconception_providers import get_misconception_provider
from .misconception_rules import RuleSignal, detect_misconceptions
from .misconception_schemas import MisconceptionAssessment, MisconceptionAssessmentBatch
from .models import (
    LearningEvidence,
    MisconceptionEvidence,
    StudentMisconception,
    StudentProfile,
    TutorMessage,
)

logger = logging.getLogger(__name__)

_CONFIDENCE_RANK = {
    StudentMisconception.Confidence.LOW: 0,
    StudentMisconception.Confidence.MEDIUM: 1,
    StudentMisconception.Confidence.HIGH: 2,
}

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{6,})|(api[_-]?key\s*[:=]\s*\S+)|(bearer\s+\S+)",
    re.IGNORECASE,
)

_TEACHER_DECISIONS = {
    "confirm": StudentMisconception.Status.CONFIRMED_BY_TEACHER,
    "dismiss": StudentMisconception.Status.DISMISSED,
    "resolve": StudentMisconception.Status.RESOLVED,
}

EXCERPT_LIMIT = 300


@dataclass(frozen=True)
class MisconceptionOutcome:
    """Result of assessing one misconception for one turn."""

    observation: StudentMisconception
    created: bool
    detectors: tuple[str, ...]
    confidence: str


def scrub_excerpt(text: str, *, limit: int = EXCERPT_LIMIT) -> str:
    """Trim to a short excerpt and strip anything that looks like a secret."""

    cleaned = _SECRET_PATTERN.sub("[redacted]", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def _lesson_concept_names(lesson) -> set[str]:
    if lesson is None:
        return set()
    return {name for name in lesson.physics_concepts.values_list("name", flat=True)}


def _catalog_rows(codes: set[str] | None = None):
    query = PhysicsMisconception.objects.filter(is_active=True).select_related(
        "physics_concept"
    )
    if codes is not None:
        query = query.filter(code__in=codes)
    return list(query)


def _run_ai_assessment(
    *,
    lesson,
    excerpts: tuple[str, ...],
    rule_codes: tuple[str, ...],
    provider: AIProvider | None,
) -> tuple[MisconceptionAssessment, ...]:
    catalog = _catalog_rows()
    if not catalog or not excerpts:
        return ()

    concepts: tuple[ConceptContext, ...] = ()
    if lesson is not None:
        concepts = tuple(
            ConceptContext.from_concept(concept)
            for concept in lesson.physics_concepts.all()
        )

    prompt = build_misconception_prompt(
        lesson_title=getattr(lesson, "title", "") or "Untitled lesson",
        topic=getattr(lesson, "topic", "") or "Physics",
        grade_level=str(getattr(lesson, "grade_level", "") or "unspecified"),
        concepts=concepts,
        catalog=tuple(
            (row.code, row.title, row.description) for row in catalog
        ),
        student_excerpts=excerpts,
        rule_hits=rule_codes,
    )

    provider = provider or get_misconception_provider()
    raw = provider.generate(prompt.user, system_prompt=prompt.system)
    payload = parse_model_json(raw, error_class=InvalidMisconceptionAssessmentError)
    batch = MisconceptionAssessmentBatch.from_dict(payload)
    return batch.assessments


def _recompute_confidence(observation: StudentMisconception) -> str:
    count = observation.observation_count
    distinct_detectors = (
        observation.evidence.exclude(detector="")
        .values_list("detector", flat=True)
        .distinct()
        .count()
    )
    if count >= 3:
        return StudentMisconception.Confidence.HIGH
    if count >= 2 or distinct_detectors >= 2:
        return StudentMisconception.Confidence.MEDIUM
    return StudentMisconception.Confidence.LOW


def _summarize(observation: StudentMisconception, latest_excerpt: str) -> str:
    detectors = sorted(
        set(
            observation.evidence.exclude(detector="").values_list(
                "detector", flat=True
            )
        )
    )
    label = ", ".join(detectors) if detectors else "no detector recorded"
    summary = (
        f"{observation.observation_count} turn(s); signals: {label}. "
        f"Latest: \"{latest_excerpt}\""
    )
    return summary[:500]


@transaction.atomic
def _record_observation(
    *,
    student: StudentProfile,
    catalog: PhysicsMisconception,
    rule_signal: RuleSignal | None,
    ai_assessment: MisconceptionAssessment | None,
    excerpt: str,
    learning_evidence: LearningEvidence | None,
    tutor_message: TutorMessage | None,
) -> MisconceptionOutcome:
    now = timezone.now()
    observation = (
        StudentMisconception.objects.select_for_update()
        .filter(student=student, misconception=catalog)
        .first()
    )
    created = False
    if observation is None:
        try:
            observation = StudentMisconception.objects.create(
                student=student,
                misconception=catalog,
                first_observed_at=now,
                last_observed_at=now,
            )
            created = True
        except IntegrityError:
            # A concurrent turn created it first; fall back to the existing row.
            observation = (
                StudentMisconception.objects.select_for_update().get(
                    student=student, misconception=catalog
                )
            )

    detectors: list[str] = []
    if rule_signal is not None:
        MisconceptionEvidence.objects.create(
            observation=observation,
            learning_evidence=learning_evidence,
            tutor_message=tutor_message,
            source=MisconceptionEvidence.Source.RULE,
            detector=rule_signal.detector,
            excerpt=excerpt,
            reasoning=rule_signal.reasoning[:500],
        )
        detectors.append(rule_signal.detector)
    if ai_assessment is not None:
        MisconceptionEvidence.objects.create(
            observation=observation,
            learning_evidence=learning_evidence,
            tutor_message=tutor_message,
            source=MisconceptionEvidence.Source.AI,
            detector=MISCONCEPTION_PROMPT_VERSION,
            excerpt=excerpt,
            reasoning=ai_assessment.reasoning[:500],
        )
        detectors.append(MISCONCEPTION_PROMPT_VERSION)

    observation.observation_count += 1
    observation.last_observed_at = now

    computed = _recompute_confidence(observation)
    if _CONFIDENCE_RANK[computed] > _CONFIDENCE_RANK[observation.confidence]:
        observation.confidence = computed

    observation.evidence_summary = _summarize(observation, excerpt)
    observation.save(
        update_fields=[
            "observation_count",
            "last_observed_at",
            "confidence",
            "evidence_summary",
            "updated_at",
        ]
    )
    return MisconceptionOutcome(
        observation=observation,
        created=created,
        detectors=tuple(detectors),
        confidence=observation.confidence,
    )


def assess_student_misconceptions(
    *,
    student: StudentProfile,
    lesson=None,
    text: str,
    learning_evidence: LearningEvidence | None = None,
    tutor_message: TutorMessage | None = None,
    use_ai: bool = True,
    provider: AIProvider | None = None,
) -> list[MisconceptionOutcome]:
    """Assess one piece of student text and persist candidate observations.

    Rules run first and always. AI assessment is optional and its failure is
    swallowed with a log line. Nothing here confirms a misconception.
    """

    text = (text or "").strip()
    if not text:
        return []

    concept_names = _lesson_concept_names(lesson) or None
    rule_signals = detect_misconceptions(
        student=student, lesson=lesson, evidence=text, concept_names=concept_names
    )
    rule_codes = tuple(sorted({signal.code for signal in rule_signals}))

    ai_assessments: tuple[MisconceptionAssessment, ...] = ()
    if use_ai:
        try:
            ai_assessments = _run_ai_assessment(
                lesson=lesson,
                excerpts=(text,),
                rule_codes=rule_codes,
                provider=provider,
            )
        except (AIError, InvalidMisconceptionAssessmentError, ValueError) as exc:
            logger.warning(
                "AI misconception assessment skipped (%s).", exc.__class__.__name__
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Unexpected AI misconception assessment failure.")

    by_code: dict[str, dict[str, object]] = {}
    for signal in rule_signals:
        by_code.setdefault(signal.code, {})["rule"] = signal
    for assessment in ai_assessments:
        if not assessment.has_evidence:
            continue
        by_code.setdefault(assessment.candidate_code, {})["ai"] = assessment

    if not by_code:
        return []

    catalog_by_code = {
        row.code: row for row in _catalog_rows(codes=set(by_code))
    }
    excerpt = scrub_excerpt(text)
    outcomes: list[MisconceptionOutcome] = []
    for code, hits in by_code.items():
        catalog = catalog_by_code.get(code)
        if catalog is None:
            # A rule or the AI referenced a code with no active catalog entry.
            # Never invent one; just ignore it.
            continue
        outcomes.append(
            _record_observation(
                student=student,
                catalog=catalog,
                rule_signal=hits.get("rule"),
                ai_assessment=hits.get("ai"),
                excerpt=excerpt,
                learning_evidence=learning_evidence,
                tutor_message=tutor_message,
            )
        )
    return outcomes


def active_candidates_for_lesson(student: StudentProfile, lesson):
    """Return non-dismissed observations tied to this lesson's concepts."""

    concept_ids = list(lesson.physics_concepts.values_list("pk", flat=True))
    query = (
        StudentMisconception.objects.filter(student=student)
        .exclude(status=StudentMisconception.Status.DISMISSED)
        .exclude(status=StudentMisconception.Status.RESOLVED)
        .select_related("misconception", "misconception__physics_concept")
        .order_by("-last_observed_at")
    )
    if concept_ids:
        query = query.filter(misconception__physics_concept_id__in=concept_ids)
    return list(query)


@transaction.atomic
def apply_teacher_decision(
    observation: StudentMisconception,
    decision: str,
    *,
    teacher=None,
    note: str = "",
) -> StudentMisconception:
    """Apply an explicit teacher decision. The only path out of 'candidate'."""

    key = (decision or "").strip().lower()
    if key not in _TEACHER_DECISIONS:
        raise MisconceptionDecisionError(
            "Choose confirm, dismiss, or resolve for this observation."
        )

    locked = (
        StudentMisconception.objects.select_for_update()
        .select_related("misconception")
        .get(pk=observation.pk)
    )
    locked.status = _TEACHER_DECISIONS[key]
    locked.teacher_note = (note or "").strip()[:500]
    locked.decided_at = timezone.now()
    if teacher is not None and getattr(teacher, "is_authenticated", False):
        locked.decided_by = teacher
    locked.save(
        update_fields=["status", "teacher_note", "decided_at", "decided_by", "updated_at"]
    )
    return locked
