"""Teacher question bank / assessment builder, and student assessment execution.

Views stay thin -- validation and persistence live in ``services.py``. Teacher
identity always comes from ``request.user`` (never POST); student identity
always comes from the existing session mechanism (``_current_student``,
reused from ``apps.students.views`` -- not duplicated here). Every destination
URL is built with ``reverse()``.
"""

from __future__ import annotations

import logging

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.physics.models import PhysicsConcept
from apps.students.practice_services import AnswerValidationError
from apps.students.views import _current_student
from apps.teachers.access import teacher_required

from . import services
from .models import Assessment, QuestionBankItem

logger = logging.getLogger(__name__)

_QuestionType = QuestionBankItem.QuestionType
_Difficulty = QuestionBankItem.Difficulty

UNEXPECTED_ERROR = "That could not be saved. Please try again."


def _concept_choices():
    return list(PhysicsConcept.objects.filter(is_active=True).order_by("name").values_list("pk", "name"))


def _lesson_choices():
    from apps.lessons.models import Lesson

    return list(Lesson.objects.order_by("title").values_list("pk", "title")[:200])


# --- teacher: question bank ------------------------------------------------


@teacher_required
def question_bank(request):
    questions = services.list_question_bank()
    return render(
        request,
        "teachers/question_bank.html",
        {"questions": questions, "concept_choices": _concept_choices()},
    )


def _question_form_context(request, *, question=None, error=""):
    posted = request.POST if request.method == "POST" else None
    qtype = (
        (posted.get("question_type") if posted else None)
        or (question.question_type if question else "")
        or request.GET.get("type", "")
    )

    if posted is not None:
        values = {
            "prompt": posted.get("prompt", ""),
            "concept_id": posted.get("concept_id", ""),
            "difficulty": posted.get("difficulty", ""),
            "hint": posted.get("hint", ""),
            "explanation": posted.get("explanation", ""),
            "expected_value": posted.get("expected_value", ""),
            "expected_unit": posted.get("expected_unit", ""),
            "tolerance": posted.get("tolerance", ""),
            "choices": posted.getlist("choice") or ["", "", "", ""],
            "correct_choice": posted.get("correct_choice", ""),
        }
    elif question is not None:
        values = {
            "prompt": question.prompt,
            "concept_id": question.concept_id or "",
            "difficulty": question.difficulty,
            "hint": question.hint,
            "explanation": question.explanation,
            "expected_value": question.expected_value if question.expected_value is not None else "",
            "expected_unit": question.expected_unit,
            "tolerance": question.tolerance if question.tolerance is not None else "",
            "choices": question.choices or ["", ""],
            "correct_choice": question.correct_choice if question.correct_choice is not None else "",
        }
    else:
        values = {
            "prompt": "",
            "concept_id": "",
            "difficulty": _Difficulty.MEDIUM,
            "hint": "",
            "explanation": "",
            "expected_value": "",
            "expected_unit": "",
            "tolerance": "",
            "choices": ["", "", "", ""],
            "correct_choice": "",
        }

    return {
        "question": question,
        "is_used": services.is_used(question) if question is not None else False,
        "question_type": qtype,
        "concept_choices": _concept_choices(),
        "difficulty_choices": _Difficulty.choices,
        "values": values,
        "error": error,
    }


@teacher_required
def question_create(request):
    qtype = request.POST.get("question_type") or request.GET.get("type", "")
    if request.method == "POST":
        try:
            services.create_question(
                teacher=request.user,
                question_type=qtype,
                prompt=request.POST.get("prompt", ""),
                concept_id=request.POST.get("concept_id") or None,
                difficulty=request.POST.get("difficulty") or _Difficulty.MEDIUM,
                choices=request.POST.getlist("choice"),
                correct_choice=request.POST.get("correct_choice"),
                expected_value=request.POST.get("expected_value") or None,
                expected_unit=request.POST.get("expected_unit", ""),
                tolerance=request.POST.get("tolerance") or None,
                hint=request.POST.get("hint", ""),
                explanation=request.POST.get("explanation", ""),
            )
        except (services.QuestionError, AnswerValidationError) as exc:
            return render(
                request,
                "teachers/question_form.html",
                _question_form_context(request, error=str(exc)),
            )
        except Exception:
            logger.exception("Unexpected question-creation failure.")
            return render(
                request,
                "teachers/question_form.html",
                _question_form_context(request, error=UNEXPECTED_ERROR),
            )
        return redirect("teachers:question_bank")

    if qtype not in _QuestionType.values:
        return render(request, "teachers/question_type_picker.html", {})
    return render(request, "teachers/question_form.html", _question_form_context(request))


@teacher_required
def question_edit(request, question_id):
    question = get_object_or_404(QuestionBankItem, pk=question_id)

    if request.method == "POST":
        fields = {
            "prompt": request.POST.get("prompt", ""),
            "concept_id": request.POST.get("concept_id") or None,
            "difficulty": request.POST.get("difficulty") or question.difficulty,
            "hint": request.POST.get("hint", ""),
            "explanation": request.POST.get("explanation", ""),
        }
        if not services.is_used(question):
            if question.question_type == _QuestionType.NUMERIC:
                fields.update(
                    expected_value=request.POST.get("expected_value") or None,
                    expected_unit=request.POST.get("expected_unit", ""),
                    tolerance=request.POST.get("tolerance") or None,
                )
            else:
                fields.update(
                    choices=request.POST.getlist("choice"),
                    correct_choice=request.POST.get("correct_choice"),
                )
        try:
            services.update_question(question_id=question.pk, teacher=request.user, **fields)
        except services.QuestionError as exc:
            return render(
                request,
                "teachers/question_form.html",
                _question_form_context(request, question=question, error=str(exc)),
            )
        except Exception:
            logger.exception("Unexpected question-edit failure for question %s.", question.pk)
            return render(
                request,
                "teachers/question_form.html",
                _question_form_context(request, question=question, error=UNEXPECTED_ERROR),
            )
        return redirect("teachers:question_bank")

    return render(request, "teachers/question_form.html", _question_form_context(request, question=question))


@require_POST
@teacher_required
def question_deactivate(request, question_id):
    question = get_object_or_404(QuestionBankItem, pk=question_id)
    services.set_question_active(
        question_id=question.pk, teacher=request.user, is_active=not question.is_active
    )
    return redirect("teachers:question_bank")


# --- teacher: assessment builder -------------------------------------------


@teacher_required
def assessment_list_teacher(request):
    assessments = services.get_teacher_assessment_list()
    return render(request, "teachers/assessment_list.html", {"assessments": assessments})


@teacher_required
def assessment_create(request):
    if request.method == "POST":
        try:
            assessment = services.create_assessment(
                teacher=request.user,
                title=request.POST.get("title", ""),
                description=request.POST.get("description", ""),
                lesson_id=request.POST.get("lesson_id") or None,
                concept_id=request.POST.get("concept_id") or None,
            )
        except services.AssessmentError as exc:
            return render(
                request,
                "teachers/assessment_form.html",
                {
                    "error": str(exc),
                    "concept_choices": _concept_choices(),
                    "lesson_choices": _lesson_choices(),
                },
            )
        return redirect("teachers:assessment_detail_teacher", assessment_id=assessment.pk)

    return render(
        request,
        "teachers/assessment_form.html",
        {"concept_choices": _concept_choices(), "lesson_choices": _lesson_choices()},
    )


def _render_builder(request, assessment_id, **extra):
    try:
        detail = services.get_teacher_assessment_detail(assessment_id=assessment_id)
    except services.AssessmentNotFound:
        raise Http404("That assessment could not be found.")
    detail["available_questions"] = [
        q
        for q in services.list_question_bank(is_active=True)
        if q.pk not in {row.question_id for row in detail["rows"]}
    ]
    detail.update(extra)
    return render(request, "teachers/assessment_builder.html", detail)


@teacher_required
def assessment_detail_teacher(request, assessment_id):
    return _render_builder(request, assessment_id)


@require_POST
@teacher_required
def assessment_add_question(request, assessment_id):
    try:
        services.add_question_to_assessment(
            assessment_id=assessment_id,
            teacher=request.user,
            question_id=request.POST.get("question_id"),
        )
    except services.AssessmentNotFound:
        raise Http404("That assessment could not be found.")
    except services.AssessmentError as exc:
        return _render_builder(request, assessment_id, error=str(exc))
    return redirect("teachers:assessment_detail_teacher", assessment_id=assessment_id)


@require_POST
@teacher_required
def assessment_remove_question(request, assessment_id, question_id):
    try:
        services.remove_question_from_assessment(
            assessment_id=assessment_id, teacher=request.user, question_id=question_id
        )
    except services.AssessmentNotFound:
        raise Http404("That assessment could not be found.")
    except services.AssessmentError as exc:
        return _render_builder(request, assessment_id, error=str(exc))
    return redirect("teachers:assessment_detail_teacher", assessment_id=assessment_id)


@require_POST
@teacher_required
def assessment_publish(request, assessment_id):
    try:
        services.publish_assessment(assessment_id=assessment_id, teacher=request.user)
    except services.AssessmentNotFound:
        raise Http404("That assessment could not be found.")
    except services.AssessmentError as exc:
        return _render_builder(request, assessment_id, error=str(exc))
    return redirect("teachers:assessment_detail_teacher", assessment_id=assessment_id)


@require_POST
@teacher_required
def assessment_archive(request, assessment_id):
    try:
        services.archive_assessment(assessment_id=assessment_id, teacher=request.user)
    except services.AssessmentNotFound:
        raise Http404("That assessment could not be found.")
    except services.AssessmentError as exc:
        return _render_builder(request, assessment_id, error=str(exc))
    return redirect("teachers:assessment_detail_teacher", assessment_id=assessment_id)


# --- student: assessments ---------------------------------------------------


def student_assessment_list(request):
    """Published assessments only. The student is resolved from the session."""

    student = _current_student(request)
    assessments = services.get_student_assessments(student=student)
    return render(
        request, "students/assessment_list.html", {"student": student, "assessments": assessments}
    )


ASSESSMENT_ANSWER_ERROR = "Your answer could not be recorded. Please try again."


def student_assessment_detail(request, assessment_id):
    """One published assessment: answer questions one at a time.

    The POST carries only ``assessment_question_id`` and ``answer`` -- the
    server resolves the student, the assessment, the question, and the
    correct answer. Any other posted field (``is_correct``, ``student_id``,
    ``score`` ...) is ignored.
    """

    student = _current_student(request)
    error = ""

    if request.method == "POST":
        try:
            services.submit_assessment_answer(
                student=student,
                assessment_id=assessment_id,
                assessment_question_id=request.POST.get("assessment_question_id"),
                submitted_answer=request.POST.get("answer", ""),
            )
        except services.AssessmentNotFound:
            raise Http404("That assessment is not available.")
        except (services.AssessmentError, AnswerValidationError) as exc:
            error = str(exc)
        except Exception:
            logger.exception(
                "Unexpected assessment-answer failure for assessment %s.", assessment_id
            )
            error = ASSESSMENT_ANSWER_ERROR
        else:
            # Redirect (PRG) so a successful answer drops ``?q=`` and the page
            # naturally advances to the next unanswered question.
            return redirect("students:assessment_detail", assessment_id=assessment_id)

    try:
        context = services.get_student_assessment_detail(
            student=student, assessment_id=assessment_id, current_id=request.GET.get("q")
        )
    except services.AssessmentNotFound:
        raise Http404("That assessment is not available.")

    context["student"] = student
    context["error"] = error
    return render(request, "students/assessment_detail.html", context)
