from urllib.parse import urlencode

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.lessons.models import Lesson
from apps.students.experiment_services import (
    ExperimentValidationError,
    complete_experiment,
    latest_attempt_for,
    record_experiment_explanation,
    record_experiment_observation,
    record_experiment_prediction,
)
from apps.students.models import TutorSession
from apps.students.views import _current_student

from .models import PhysicsSimulation
from .simulation_registry import get_simulation_definition


def physics_lab_index(request):
    """List the interactive simulations a student can open."""

    simulations = (
        PhysicsSimulation.objects.filter(is_active=True)
        .select_related("concept")
    )
    return render(request, "physics/lab.html", {"simulations": simulations})


def _tutor_lesson_for(concept):
    """The most recently updated lesson that teaches this concept, if any."""

    return (
        Lesson.objects.filter(physics_concepts=concept)
        .order_by("-updated_at")
        .first()
    )


_FIELD_LABELS = {
    "mass_kg": "mass",
    "force_n": "net force",
    "acceleration_m_s2": "acceleration",
    "initial_position_m": "initial position",
    "initial_velocity_m_s": "initial velocity",
    "time_s": "time",
    "position_m": "position",
    "velocity_m_s": "velocity",
}


def _default_state_lines(definition):
    """Plain-text setup lines for the initial (no-experiment-yet) tutor prefill."""

    lines = []
    for field, value in definition.default_state.items():
        label = _FIELD_LABELS.get(field, field.replace("_", " "))
        unit = definition.units.get(field, "")
        lines.append(f"{label} = {value:.2f} {unit}".strip())
    return lines


def _initial_tutor_url(lesson, simulation, definition):
    """A no-JS-safe link into the existing tutor, pre-filled with the setup."""

    if lesson is None:
        return ""
    prefill_lines = [
        f"Physics Lab experiment - {simulation.get_simulation_type_display()}"
    ]
    prefill_lines.extend(_default_state_lines(definition))
    prefill_lines.append("What I observed: ")
    prefill = "\n".join(prefill_lines) + "\n"
    return (
        reverse("students:tutor", args=[lesson.slug])
        + "?"
        + urlencode({"prefill": prefill})
    )


def physics_lab_detail(request, slug):
    """Render one simulation. 404 for inactive or not-yet-built types."""

    simulation = get_object_or_404(
        PhysicsSimulation.objects.select_related("concept"),
        slug=slug,
        is_active=True,
    )
    definition = get_simulation_definition(simulation.simulation_type)
    if definition is None:
        raise Http404("This simulation is not available yet.")

    tutor_lesson = _tutor_lesson_for(simulation.concept)

    # Restore the student's in-progress experiment so a refresh keeps their work.
    student = _current_student(request)
    attempt = latest_attempt_for(student, simulation)
    experiment_attempt = attempt if attempt and not attempt.is_complete else None

    bounds = {
        field: {"min": lo, "max": hi} for field, (lo, hi) in definition.bounds.items()
    }
    context = {
        "simulation": simulation,
        "concept": simulation.concept,
        "tutor_lesson": tutor_lesson,
        "tutor_url": _initial_tutor_url(tutor_lesson, simulation, definition),
        "experiment_attempt": experiment_attempt,
        "defaults": definition.default_state,
        "bounds": bounds,
        "equations": definition.equations,
    }
    return render(request, definition.template, context)


# --- Experiment learning-flow endpoints (JSON) --------------------------------
#
# These record meaningful learning moments and reuse the existing student
# services. They never compute physics from the browser and never reach a second
# tutor engine -- the tutor is only linked, via students:tutor.


def _experiment_session(student, lesson):
    """Reuse the student's active TutorSession for this lesson, or make one."""

    if lesson is None:
        return None
    session = (
        TutorSession.objects.filter(
            student=student, lesson=lesson, status=TutorSession.Status.ACTIVE
        )
        .order_by("-started_at")
        .first()
    )
    if session is None:
        session = TutorSession.objects.create(student=student, lesson=lesson)
    return session


def _active_simulation(slug):
    return get_object_or_404(
        PhysicsSimulation.objects.select_related("concept"),
        slug=slug,
        is_active=True,
    )


def _experiment_prefill(attempt):
    """A no-JS-safe tutor prefill built from the attempt's own trusted values.

    Reuses ``ExperimentContext.from_attempt`` (the same type-aware projection
    the tutor prompt itself uses -- see ``apps.students.requests``) instead of
    re-reading ``attempt``/``attempt.parameters`` a second time here.
    """

    from apps.students.requests import ExperimentContext

    ctx = ExperimentContext.from_attempt(attempt)
    parts = [f"Physics Lab experiment - {attempt.simulation.get_simulation_type_display()}"]
    if ctx.simulation_type == "kinematics":
        if ctx.initial_position_m is not None:
            parts.append(f"initial position = {ctx.initial_position_m:.1f} m")
        if ctx.initial_velocity_m_s is not None:
            parts.append(f"initial velocity = {ctx.initial_velocity_m_s:.1f} m/s")
        if ctx.acceleration_m_s2 is not None:
            parts.append(
                f"acceleration = {ctx.acceleration_m_s2:.2f} m/s^2 (computed by the app)"
            )
        if ctx.time_s is not None:
            parts.append(f"observed time = {ctx.time_s:.1f} s")
        if ctx.position_m is not None:
            parts.append(f"position = {ctx.position_m:.2f} m")
        if ctx.velocity_m_s is not None:
            parts.append(f"velocity = {ctx.velocity_m_s:.2f} m/s")
    else:
        if ctx.mass_kg is not None:
            parts.append(f"mass = {ctx.mass_kg:.1f} kg")
        if ctx.force_n is not None:
            parts.append(f"net force = {ctx.force_n:.1f} N")
        if ctx.acceleration_m_s2 is not None:
            parts.append(
                f"acceleration = {ctx.acceleration_m_s2:.2f} m/s^2 "
                "(a = F / m, computed by the app)"
            )
    if ctx.prediction:
        parts.append(f"My prediction: {ctx.prediction}")
    if ctx.observation:
        parts.append(f"What I observed: {ctx.observation}")
    if ctx.explanation:
        parts.append(f"Why I think it happened: {ctx.explanation}")
    parts.append("Can you help me understand this?")
    return "\n".join(parts)


def _observation_message(simulation_type, validated):
    if simulation_type == "kinematics":
        return (
            "Observation saved. Server-computed position: "
            f"{validated.position_m:.2f} m, velocity: {validated.velocity_m_s:.2f} m/s."
        )
    return (
        "Observation saved. Server-computed acceleration: "
        f"{validated.acceleration_m_s2:.2f} m/s² (a = F / m)."
    )


@require_POST
def experiment_predict(request, slug):
    simulation = _active_simulation(slug)
    student = _current_student(request)
    lesson = _tutor_lesson_for(simulation.concept)
    session = _experiment_session(student, lesson)
    try:
        attempt = record_experiment_prediction(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
            prediction=request.POST.get("prediction", ""),
        )
    except ExperimentValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "attempt_id": attempt.pk,
            "message": "Prediction saved. Now run the experiment.",
        }
    )


@require_POST
def experiment_observe(request, slug):
    simulation = _active_simulation(slug)
    definition = get_simulation_definition(simulation.simulation_type)
    student = _current_student(request)
    lesson = _tutor_lesson_for(simulation.concept)
    session = _experiment_session(student, lesson)
    physics_values = {
        field: request.POST.get(field) for field in (definition.input_fields if definition else ())
    }
    try:
        attempt, validated = record_experiment_observation(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
            observation=request.POST.get("observation", ""),
            **physics_values,
        )
    except ExperimentValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    payload = {key: round(value, 4) for key, value in validated.as_dict().items()}
    payload.update(
        ok=True,
        attempt_id=attempt.pk,
        message=_observation_message(simulation.simulation_type, validated),
    )
    return JsonResponse(payload)


@require_POST
def experiment_explain(request, slug):
    simulation = _active_simulation(slug)
    definition = get_simulation_definition(simulation.simulation_type)
    student = _current_student(request)
    lesson = _tutor_lesson_for(simulation.concept)
    session = _experiment_session(student, lesson)
    physics_values = {
        field: request.POST.get(field) for field in (definition.input_fields if definition else ())
    }
    try:
        attempt, _outcomes = record_experiment_explanation(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
            explanation=request.POST.get("explanation", ""),
            **physics_values,
        )
        complete_experiment(attempt)
    except ExperimentValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    tutor_url = ""
    if lesson is not None:
        tutor_url = (
            reverse("students:tutor", args=[lesson.slug])
            + "?"
            + urlencode(
                {"prefill": _experiment_prefill(attempt), "experiment": attempt.pk}
            )
        )
    # Never expose an internal misconception code to the student.
    return JsonResponse(
        {
            "ok": True,
            "attempt_id": attempt.pk,
            "message": (
                "Explanation saved. Your reasoning is the most useful evidence "
                "you can give your teacher and tutor."
            ),
            "tutor_url": tutor_url,
        }
    )
