"""Question bank + structured assessment logic.

Three layers, kept separate on purpose:

    QuestionBankItem            -- a reusable, deterministically-gradeable
                                    question. A teacher's instructional
                                    decision; nothing else ever creates one.
    Assessment / AssessmentQuestion
                                 -- an ordered, published set of questions.
    AssessmentAttempt / AssessmentAnswer
                                 -- what one student actually did.

Evaluation reuses the exact Step 18 evaluators
(``apps.students.practice_services.evaluate_numeric_answer`` /
``evaluate_choice_answer``) -- nothing here re-implements grading, and no AI
provider is ever consulted for numeric/multiple-choice correctness.

This module knows nothing about mastery, ability, or risk. An assessment is
"completed" when every one of its questions has an answer; that is a factual
statement about coverage, not a judgement about the student.
"""

from __future__ import annotations

import math
import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.lessons.models import Lesson
from apps.physics.models import PhysicsConcept
from apps.students.models import LearningEvidence
from apps.students.practice_services import (
    AnswerValidationError,
    evaluate_choice_answer,
    evaluate_numeric_answer,
)

from .models import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    QuestionBankItem,
)

# --- limits ----------------------------------------------------------------

PROMPT_MAX_LEN = 2000
HINT_MAX_LEN = 1000
EXPLANATION_MAX_LEN = 2000
UNIT_MAX_LEN = 40
CHOICE_MAX_LEN = 300
TITLE_MAX_LEN = 200
DESCRIPTION_MAX_LEN = 2000
ANSWER_MAX_LEN = 500
KEY_BASE_MAX_LEN = 100

QUESTION_LIST_LIMIT = 500
ASSESSMENT_LIST_LIMIT = 200
TEACHER_ASSESSMENT_EVIDENCE_SCAN = 300
TEACHER_ASSESSMENT_EVIDENCE_SHOWN = 20

_QuestionType = QuestionBankItem.QuestionType
_Difficulty = QuestionBankItem.Difficulty
_AssessmentStatus = Assessment.Status

# Fields that define an answer's trusted meaning. Once a question has a real
# student answer against it, these can no longer change -- see ``is_used``.
_LOCKED_ANSWER_FIELDS = {
    "question_type",
    "choices",
    "correct_choice",
    "expected_value",
    "expected_unit",
    "tolerance",
}


class QuestionError(ValueError):
    """A question-bank submission was missing, malformed, or unsafe to change."""


class AssessmentError(ValueError):
    """An assessment-builder or student-execution request was invalid."""


class AssessmentNotFound(AssessmentError):
    """The assessment does not exist, or is not available in this context."""


# --- small helpers -----------------------------------------------------


def _clip(text, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _clean_prompt(prompt) -> str:
    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not text:
        raise QuestionError("Enter a question prompt.")
    if len(text) > PROMPT_MAX_LEN:
        raise QuestionError("That prompt is too long.")
    return text


def _resolve_concept(raw_id, error_cls=QuestionError):
    if not raw_id:
        return None
    try:
        concept = PhysicsConcept.objects.filter(pk=int(raw_id), is_active=True).first()
    except (TypeError, ValueError):
        concept = None
    if concept is None:
        raise error_cls("That Physics concept could not be found.")
    return concept


def _resolve_lesson(raw_id):
    if not raw_id:
        return None
    try:
        lesson = Lesson.objects.filter(pk=raw_id).first()
    except (ValidationError, ValueError, TypeError):
        lesson = None
    if lesson is None:
        raise AssessmentError("That lesson could not be found.")
    return lesson


def _clean_numeric_fields(expected_value, expected_unit, tolerance):
    try:
        value = float(expected_value)
    except (TypeError, ValueError):
        raise QuestionError("Enter a numeric expected value.")
    if not math.isfinite(value):
        raise QuestionError("The expected value must be a finite number.")

    tol = None
    if tolerance not in (None, ""):
        try:
            tol = float(tolerance)
        except (TypeError, ValueError):
            raise QuestionError("Enter a numeric tolerance.")
        if not math.isfinite(tol):
            raise QuestionError("The tolerance must be a finite number.")
        if tol < 0:
            raise QuestionError("Tolerance cannot be negative.")

    unit = _clip(expected_unit, UNIT_MAX_LEN)
    return value, unit, tol


def _clean_choice_fields(choices, correct_choice):
    if not isinstance(choices, (list, tuple)):
        raise QuestionError("Enter at least two choices.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in choices:
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not text:
            continue
        if len(text) > CHOICE_MAX_LEN:
            raise QuestionError("A choice is too long.")
        key = text.lower()
        if key in seen:
            raise QuestionError("Choices must be different from each other.")
        seen.add(key)
        cleaned.append(text)
    if len(cleaned) < 2:
        raise QuestionError("Enter at least two different choices.")

    if isinstance(correct_choice, bool):
        raise QuestionError("Choose which option is correct.")
    try:
        index = int(correct_choice)
    except (TypeError, ValueError):
        raise QuestionError("Choose which option is correct.")
    if index < 0 or index >= len(cleaned):
        raise QuestionError("The correct choice must be one of the listed options.")
    return cleaned, index


def _generate_key(prompt: str) -> str:
    """A stable, content-derived identifier -- never a positional 'q1'."""

    from django.utils.text import slugify

    base = slugify(prompt)[:KEY_BASE_MAX_LEN] or "question"
    key = base
    suffix = 2
    while QuestionBankItem.objects.filter(key=key).exists():
        key = f"{base}-{suffix}"[:120]
        suffix += 1
    return key


def is_used(question: QuestionBankItem) -> bool:
    """True once a real student answer exists against this question, ever."""

    return AssessmentAnswer.objects.filter(assessment_question__question=question).exists()


# --- question bank: teacher-only writes --------------------------------


@transaction.atomic
def create_question(
    *,
    teacher,
    question_type,
    prompt,
    concept_id=None,
    difficulty=_Difficulty.MEDIUM,
    choices=None,
    correct_choice=None,
    expected_value=None,
    expected_unit="",
    tolerance=None,
    hint="",
    explanation="",
) -> QuestionBankItem:
    """Validate and persist one reusable question. ``teacher`` is server-derived."""

    if question_type not in _QuestionType.values:
        raise QuestionError("Choose a question type.")

    clean_prompt = _clean_prompt(prompt)
    concept = _resolve_concept(concept_id)
    diff = difficulty if difficulty in _Difficulty.values else _Difficulty.MEDIUM

    kwargs = dict(
        key=_generate_key(clean_prompt),
        question_type=question_type,
        prompt=clean_prompt,
        concept=concept,
        difficulty=diff,
        hint=_clip(hint, HINT_MAX_LEN),
        explanation=_clip(explanation, EXPLANATION_MAX_LEN),
        created_by=teacher if getattr(teacher, "is_authenticated", False) else None,
    )

    if question_type == _QuestionType.NUMERIC:
        value, unit, tol = _clean_numeric_fields(expected_value, expected_unit, tolerance)
        kwargs.update(expected_value=value, expected_unit=unit, tolerance=tol)
    else:
        cleaned_choices, index = _clean_choice_fields(choices or [], correct_choice)
        kwargs.update(choices=cleaned_choices, correct_choice=index)

    return QuestionBankItem.objects.create(**kwargs)


@transaction.atomic
def update_question(*, question_id, teacher, **fields) -> QuestionBankItem:
    """Edit a question. The trusted answer definition is locked once used."""

    question = QuestionBankItem.objects.filter(pk=question_id).first()
    if question is None:
        raise QuestionError("That question could not be found.")

    locked = is_used(question)
    if locked and (_LOCKED_ANSWER_FIELDS & set(fields)):
        raise QuestionError(
            "This question has already been answered by a student, so its "
            "trusted answer definition cannot be changed. Create a new "
            "question instead."
        )

    if "prompt" in fields:
        question.prompt = _clean_prompt(fields["prompt"])
    if "concept_id" in fields:
        question.concept = _resolve_concept(fields["concept_id"])
    if "difficulty" in fields and fields["difficulty"] in _Difficulty.values:
        question.difficulty = fields["difficulty"]
    if "hint" in fields:
        question.hint = _clip(fields["hint"], HINT_MAX_LEN)
    if "explanation" in fields:
        question.explanation = _clip(fields["explanation"], EXPLANATION_MAX_LEN)

    if not locked:
        if question.question_type == _QuestionType.NUMERIC:
            if {"expected_value", "expected_unit", "tolerance"} & set(fields):
                value, unit, tol = _clean_numeric_fields(
                    fields.get("expected_value", question.expected_value),
                    fields.get("expected_unit", question.expected_unit),
                    fields.get("tolerance", question.tolerance),
                )
                question.expected_value, question.expected_unit, question.tolerance = (
                    value,
                    unit,
                    tol,
                )
        else:
            if {"choices", "correct_choice"} & set(fields):
                cleaned_choices, index = _clean_choice_fields(
                    fields.get("choices", question.choices),
                    fields.get("correct_choice", question.correct_choice),
                )
                question.choices, question.correct_choice = cleaned_choices, index

    question.save()
    return question


@transaction.atomic
def set_question_active(*, question_id, teacher, is_active: bool) -> QuestionBankItem:
    question = QuestionBankItem.objects.filter(pk=question_id).first()
    if question is None:
        raise QuestionError("That question could not be found.")
    question.is_active = bool(is_active)
    question.save(update_fields=["is_active"])
    return question


def list_question_bank(*, concept_id=None, question_type=None, is_active=None) -> list[QuestionBankItem]:
    qs = QuestionBankItem.objects.select_related("concept", "created_by")
    if concept_id:
        qs = qs.filter(concept_id=concept_id)
    if question_type:
        qs = qs.filter(question_type=question_type)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return list(qs[:QUESTION_LIST_LIMIT])


def get_question(question_id) -> QuestionBankItem | None:
    return QuestionBankItem.objects.select_related("concept").filter(pk=question_id).first()


# --- assessment builder: teacher-only writes ----------------------------


@transaction.atomic
def create_assessment(*, teacher, title, description="", lesson_id=None, concept_id=None) -> Assessment:
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not clean_title:
        raise AssessmentError("Enter a title for this assessment.")
    if len(clean_title) > TITLE_MAX_LEN:
        raise AssessmentError("That title is too long.")

    return Assessment.objects.create(
        title=clean_title,
        description=_clip(description, DESCRIPTION_MAX_LEN),
        lesson=_resolve_lesson(lesson_id),
        concept=_resolve_concept(concept_id, error_cls=AssessmentError),
        created_by=teacher if getattr(teacher, "is_authenticated", False) else None,
    )


def _teacher_assessment(assessment_id) -> Assessment:
    assessment = (
        Assessment.objects.filter(pk=assessment_id).select_related("lesson", "concept").first()
    )
    if assessment is None:
        raise AssessmentNotFound("That assessment could not be found.")
    return assessment


@transaction.atomic
def add_question_to_assessment(*, assessment_id, teacher, question_id) -> AssessmentQuestion:
    assessment = _teacher_assessment(assessment_id)
    if assessment.status != _AssessmentStatus.DRAFT:
        raise AssessmentError("Only a draft assessment can be edited.")

    question = QuestionBankItem.objects.filter(pk=question_id).first()
    if question is None:
        raise AssessmentError("That question could not be found.")
    if not question.is_active:
        raise AssessmentError("That question is not active.")
    if AssessmentQuestion.objects.filter(assessment=assessment, question=question).exists():
        raise AssessmentError("That question is already part of this assessment.")

    highest = AssessmentQuestion.objects.filter(assessment=assessment).aggregate(
        models.Max("position")
    )["position__max"]
    position = 0 if highest is None else highest + 1
    try:
        return AssessmentQuestion.objects.create(
            assessment=assessment, question=question, position=position
        )
    except IntegrityError:
        raise AssessmentError("That question is already part of this assessment.")


@transaction.atomic
def remove_question_from_assessment(*, assessment_id, teacher, question_id) -> None:
    assessment = _teacher_assessment(assessment_id)
    if assessment.status != _AssessmentStatus.DRAFT:
        raise AssessmentError("Only a draft assessment can be edited.")
    deleted, _ = AssessmentQuestion.objects.filter(
        assessment=assessment, question_id=question_id
    ).delete()
    if not deleted:
        raise AssessmentError("That question is not part of this assessment.")


@transaction.atomic
def publish_assessment(*, assessment_id, teacher) -> Assessment:
    assessment = Assessment.objects.select_for_update().filter(pk=assessment_id).first()
    if assessment is None:
        raise AssessmentNotFound("That assessment could not be found.")
    if assessment.status != _AssessmentStatus.DRAFT:
        raise AssessmentError("Only a draft assessment can be published.")

    rows = list(AssessmentQuestion.objects.filter(assessment=assessment).select_related("question"))
    if not rows:
        raise AssessmentError("Add at least one question before publishing.")
    if any(not row.question.is_active for row in rows):
        raise AssessmentError("Every question must be active before publishing.")

    assessment.status = _AssessmentStatus.PUBLISHED
    assessment.published_at = timezone.now()
    assessment.save(update_fields=["status", "published_at"])
    return assessment


@transaction.atomic
def archive_assessment(*, assessment_id, teacher) -> Assessment:
    assessment = Assessment.objects.select_for_update().filter(pk=assessment_id).first()
    if assessment is None:
        raise AssessmentNotFound("That assessment could not be found.")
    if assessment.status == _AssessmentStatus.ARCHIVED:
        raise AssessmentError("That assessment is already archived.")
    assessment.status = _AssessmentStatus.ARCHIVED
    assessment.save(update_fields=["status"])
    return assessment


def get_teacher_assessment_list() -> list[dict]:
    rows = (
        Assessment.objects.select_related("concept")
        .annotate(question_total=models.Count("assessment_questions", distinct=True))
        .order_by("-created_at", "-id")[:ASSESSMENT_LIST_LIMIT]
    )
    return [
        {
            "id": a.pk,
            "title": a.title,
            "concept": a.concept.name if a.concept_id else "",
            "status": a.status,
            "status_label": a.get_status_display(),
            "question_count": a.question_total,
            "created_at": a.created_at,
        }
        for a in rows
    ]


def get_teacher_assessment_detail(*, assessment_id) -> dict:
    assessment = _teacher_assessment(assessment_id)
    rows = list(
        AssessmentQuestion.objects.filter(assessment=assessment)
        .select_related("question", "question__concept")
        .order_by("position", "id")
    )
    return {
        "assessment": assessment,
        "rows": rows,
        "question_count": len(rows),
        "can_publish": assessment.status == _AssessmentStatus.DRAFT and bool(rows),
        "can_archive": assessment.status == _AssessmentStatus.PUBLISHED,
    }


# --- student execution ---------------------------------------------------


def _published_assessment(assessment_id) -> Assessment:
    assessment = (
        Assessment.objects.filter(pk=assessment_id, status=_AssessmentStatus.PUBLISHED)
        .select_related("concept", "lesson")
        .first()
    )
    if assessment is None:
        raise AssessmentNotFound("That assessment is not available.")
    return assessment


def get_student_assessments(*, student) -> list[dict]:
    """Published assessments only, each with this student's own progress."""

    assessments = list(
        Assessment.objects.filter(status=_AssessmentStatus.PUBLISHED)
        .select_related("concept")
        .annotate(question_total=models.Count("assessment_questions", distinct=True))
        .order_by("-published_at", "-id")[:ASSESSMENT_LIST_LIMIT]
    )
    attempts = {
        a.assessment_id: a
        for a in AssessmentAttempt.objects.filter(student=student, assessment__in=assessments)
    }

    rows = []
    for assessment in assessments:
        attempt = attempts.get(assessment.pk)
        if attempt is None:
            status = "not_started"
        elif attempt.is_complete:
            status = "completed"
        else:
            status = "in_progress"
        rows.append(
            {
                "id": assessment.pk,
                "title": assessment.title,
                "description": assessment.description,
                "concept": assessment.concept.name if assessment.concept_id else "",
                "question_count": assessment.question_total,
                "status": status,
            }
        )
    return rows


def get_student_assessment_detail(*, student, assessment_id, current_id=None) -> dict:
    """Student-safe assessment page context. Never carries a trusted answer.

    ``current_id`` optionally names the ``AssessmentQuestion`` to show (a
    student reviewing an earlier, already-answered question); it defaults to
    the first unanswered question, mirroring the practice page's ``?q=``.
    """

    assessment = _published_assessment(assessment_id)
    rows = list(
        AssessmentQuestion.objects.filter(assessment=assessment)
        .select_related("question")
        .order_by("position", "id")
    )
    attempt = AssessmentAttempt.objects.filter(student=student, assessment=assessment).first()
    answered_by_question = {}
    if attempt is not None:
        answered_by_question = {
            a.assessment_question_id: a
            for a in AssessmentAnswer.objects.filter(attempt=attempt)
        }

    try:
        requested_id = int(current_id) if current_id else None
    except (TypeError, ValueError):
        requested_id = None

    questions = []
    next_unanswered = None
    requested_question = None
    for index, row in enumerate(rows):
        answer = answered_by_question.get(row.pk)
        q = row.question
        if answer is None:
            result = None
        elif answer.is_correct is True:
            result = "correct"
        elif answer.is_correct is False:
            result = "incorrect"
        else:
            result = "recorded"
        entry = {
            "assessment_question_id": row.pk,
            "number": index + 1,
            "total": len(rows),
            "type": q.question_type,
            "prompt": q.prompt,
            "unit": q.expected_unit if q.question_type == _QuestionType.NUMERIC else "",
            "choices": (
                tuple(q.choices) if q.question_type == _QuestionType.MULTIPLE_CHOICE else ()
            ),
            "hint": q.hint,
            "answered": answer is not None,
            "result": result,
            "answer_text": answer.answer_text if answer else "",
        }
        questions.append(entry)
        if answer is None and next_unanswered is None:
            next_unanswered = entry
        if requested_id is not None and row.pk == requested_id:
            requested_question = entry

    attempted_count = sum(1 for q in questions if q["answered"])
    completed = attempt is not None and attempt.is_complete

    if requested_question is not None:
        current_question = requested_question
    elif next_unanswered is not None:
        current_question = next_unanswered
    else:
        current_question = questions[-1] if questions else None

    return {
        "assessment": assessment,
        "questions": questions,
        "current_question": current_question,
        "attempted_count": attempted_count,
        "total_count": len(questions),
        "completed": completed,
    }


@transaction.atomic
def submit_assessment_answer(
    *, student, assessment_id, assessment_question_id, submitted_answer
) -> dict:
    """Evaluate one answer against the trusted question definition and persist it.

    ``assessment_question_id`` must name an :class:`AssessmentQuestion` that
    actually belongs to ``assessment_id`` -- a question id from a different
    assessment is rejected. The client's answer text is the ONLY untrusted
    input here: correctness, the expected value/choice, the student and the
    assessment are all resolved server-side, never from the POST body.
    """

    assessment = _published_assessment(assessment_id)
    assessment_question = (
        AssessmentQuestion.objects.filter(pk=assessment_question_id, assessment=assessment)
        .select_related("question")
        .first()
    )
    if assessment_question is None:
        raise AssessmentError("That question is not part of this assessment.")

    attempt, _ = AssessmentAttempt.objects.get_or_create(student=student, assessment=assessment)
    if AssessmentAnswer.objects.filter(
        attempt=attempt, assessment_question=assessment_question
    ).exists():
        raise AssessmentError("You already answered this question.")

    question = assessment_question.question
    answer_text = re.sub(
        r"\s+", " ", str(submitted_answer if submitted_answer is not None else "")
    ).strip()
    if not answer_text:
        raise AnswerValidationError("Enter an answer before submitting.")
    if len(answer_text) > ANSWER_MAX_LEN:
        raise AnswerValidationError("That answer is too long. Keep it short.")

    if question.question_type == _QuestionType.NUMERIC:
        evaluation = evaluate_numeric_answer(answer_text, question.expected_value, question.tolerance)
        is_correct = evaluation.is_correct
    else:
        evaluation = evaluate_choice_answer(answer_text, question.choices, question.correct_choice)
        is_correct = evaluation.is_correct
        answer_text = evaluation.submitted_label

    context = {
        # The assessment's title, not its numeric id -- stable (there is no
        # "edit assessment" path) and already shown to the student elsewhere,
        # so it is safe to echo back on the timeline (Section 25's "safe
        # stable key").
        "assessment": assessment.title,
        "question_key": question.key,
        "question_type": question.question_type,
        "is_correct": is_correct,
        "attempt_number": 1,
    }
    if question.concept_id:
        context["concept"] = question.concept.name

    evidence = LearningEvidence.objects.create(
        student=student,
        lesson=assessment.lesson,
        kind=LearningEvidence.Kind.ASSESSMENT_ATTEMPTED,
        detail=answer_text[:300],
        context=context,
    )
    answer = AssessmentAnswer.objects.create(
        attempt=attempt,
        assessment_question=assessment_question,
        evidence=evidence,
        answer_text=answer_text[:500],
        is_correct=is_correct,
    )

    total_questions = AssessmentQuestion.objects.filter(assessment=assessment).count()
    answered = AssessmentAnswer.objects.filter(attempt=attempt).count()
    if attempt.completed_at is None and answered >= total_questions:
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["completed_at"])

    return {"answer": answer, "is_correct": is_correct, "completed": attempt.completed_at is not None}


# --- planner / evidence integration --------------------------------------


def build_published_assessment_destination_map() -> dict[str, Assessment]:
    """One published assessment per concept slug, newest-published-first.

    Mirrors ``apps.students.concept_path_services.build_concept_destination_maps``:
    one bounded query, deterministic tie-break, used by the adaptive planner so
    a concept never resolves to more than one assessment suggestion.
    """

    assessments = (
        Assessment.objects.filter(status=_AssessmentStatus.PUBLISHED, concept__isnull=False)
        .select_related("concept")
        .order_by("-published_at", "-updated_at", "-id")
    )
    by_slug: dict[str, Assessment] = {}
    for assessment in assessments:
        slug = assessment.concept.slug
        if slug not in by_slug:
            by_slug[slug] = assessment
    return by_slug


def student_completed_assessment(*, student, assessment) -> bool:
    return AssessmentAttempt.objects.filter(
        student=student, assessment=assessment, completed_at__isnull=False
    ).exists()


def get_student_assessment_summary(*, student) -> dict:
    """Factual assessment counts for the student progress page. No score."""

    attempts = list(AssessmentAttempt.objects.filter(student=student).select_related("assessment"))
    completed = [a for a in attempts if a.is_complete]
    questions_answered = AssessmentAnswer.objects.filter(attempt__student=student).count()
    return {
        "completed": len(completed),
        "in_progress": len(attempts) - len(completed),
        "questions_answered": questions_answered,
        "recent": [
            {"title": a.assessment.title, "when": a.completed_at}
            for a in sorted(completed, key=lambda a: a.completed_at, reverse=True)[:5]
        ],
    }


def get_teacher_assessment_evidence(student) -> dict:
    """Compact, factual assessment record for the teacher workspace page.

    Mirrors ``apps.teachers.services._practice_evidence`` exactly in shape and
    tone: counts are labelled attempts/correct/incorrect, never a score.
    """

    answers = list(
        AssessmentAnswer.objects.filter(attempt__student=student)
        .select_related(
            "attempt", "attempt__assessment", "assessment_question", "assessment_question__question"
        )
        .order_by("-attempted_at", "-id")[:TEACHER_ASSESSMENT_EVIDENCE_SCAN]
    )
    rows = []
    for answer in answers[:TEACHER_ASSESSMENT_EVIDENCE_SHOWN]:
        if answer.is_correct is True:
            result = "Correct"
        elif answer.is_correct is False:
            result = "Incorrect"
        else:
            result = "Recorded"
        rows.append(
            {
                "when": answer.attempted_at,
                "assessment": answer.attempt.assessment.title,
                "prompt": answer.assessment_question.question.prompt,
                "answer": answer.answer_text,
                "result": result,
            }
        )

    completed = AssessmentAttempt.objects.filter(
        student=student, completed_at__isnull=False
    ).count()
    scored = [a for a in answers if a.is_correct is not None]
    return {
        "rows": rows,
        "assessments_completed": completed,
        "questions_answered": len(answers),
        "correct_answers": sum(1 for a in scored if a.is_correct),
        "incorrect_answers": sum(1 for a in scored if not a.is_correct),
        "has_more": len(answers) > len(rows),
    }


def get_student_assessment_url(assessment: Assessment) -> str:
    return reverse("students:assessment_detail", args=[assessment.pk])
