import logging

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.students.exceptions import MisconceptionDecisionError
from apps.students.misconception_services import apply_teacher_decision
from apps.students.models import StudentMisconception, StudentProfile

from .access import teacher_required
from .services import (
    InterventionError,
    build_teacher_student_evidence,
    create_teacher_intervention,
    list_teacher_students,
)

logger = logging.getLogger(__name__)

INTERVENTION_SAVED = "Intervention recorded."
DECISION_SAVED = "Your decision was recorded."


def _render_detail(request, student: StudentProfile, **extra):
    context = build_teacher_student_evidence(student=student)
    context["student"] = student
    context.update(extra)
    return render(request, "teachers/student_detail.html", context)


@teacher_required
def student_list(request):
    return render(
        request,
        "teachers/student_list.html",
        {"students": list_teacher_students()},
    )


@teacher_required
def student_detail(request, student_id):
    student = get_object_or_404(StudentProfile, pk=student_id)
    return _render_detail(request, student)


@teacher_required
@require_POST
def create_intervention(request, student_id):
    student = get_object_or_404(StudentProfile, pk=student_id)
    try:
        create_teacher_intervention(
            student=student,
            teacher=request.user,
            action_type=request.POST.get("action_type", ""),
            note=request.POST.get("note", ""),
            lesson_id=request.POST.get("lesson_id") or None,
            concept_id=request.POST.get("concept_id") or None,
            misconception_id=request.POST.get("misconception_id") or None,
        )
    except InterventionError as exc:
        return _render_detail(request, student, intervention_error=str(exc))
    except Exception:
        logger.exception("Unexpected intervention failure for student %s.", student.pk)
        return _render_detail(
            request,
            student,
            intervention_error="The intervention could not be saved. Please try again.",
        )
    return _render_detail(request, student, workflow_message=INTERVENTION_SAVED)


@teacher_required
@require_POST
def misconception_decision(request, student_id, observation_id):
    student = get_object_or_404(StudentProfile, pk=student_id)
    # Scoped to this student: another student's candidate is a 404, not an error.
    observation = get_object_or_404(
        StudentMisconception, pk=observation_id, student=student
    )
    try:
        apply_teacher_decision(
            observation,
            request.POST.get("decision", ""),
            teacher=request.user,
            note=request.POST.get("note", ""),
        )
    except MisconceptionDecisionError as exc:
        return _render_detail(request, student, decision_error=str(exc))
    except Exception:
        logger.exception(
            "Unexpected misconception decision failure for student %s.", student.pk
        )
        return _render_detail(
            request,
            student,
            decision_error="Your decision could not be saved. Please try again.",
        )
    return _render_detail(request, student, workflow_message=DECISION_SAVED)
