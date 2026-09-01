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
from .simulations import (
    DEFAULT_FORCE_N,
    DEFAULT_MASS_KG,
    MAX_FORCE_N,
    MAX_MASS_KG,
    MIN_FORCE_N,
    MIN_MASS_KG,
    newtons_second_law_acceleration,
)

# Maps a stored simulation_type to the template that renders it.
SIMULATION_TEMPLATES = {
    PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW: "physics/newtons_second_law.html",
}


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


def _initial_tutor_url(lesson, concept, mass, force, acceleration):
    """A no-JS-safe link into the existing tutor, pre-filled with the setup."""

    if lesson is None:
        return ""
    prefill = (
        "Physics Lab experiment - Newton's Second Law\n"
        f"mass = {mass:.1f} kg\n"
        f"net force = {force:.1f} N\n"
        f"acceleration = {acceleration:.2f} m/s^2 (a = F / m, idealized model)\n"
        "What I observed: "
    )
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
    template = SIMULATION_TEMPLATES.get(simulation.simulation_type)
    if template is None:
        raise Http404("This simulation is not available yet.")

    acceleration = newtons_second_law_acceleration(DEFAULT_FORCE_N, DEFAULT_MASS_KG)
    tutor_lesson = _tutor_lesson_for(simulation.concept)

    # Restore the student's in-progress experiment so a refresh keeps their work.
    student = _current_student(request)
    attempt = latest_attempt_for(student, simulation)
    experiment_attempt = attempt if attempt and not attempt.is_complete else None

    context = {
        "simulation": simulation,
        "concept": simulation.concept,
        "tutor_lesson": tutor_lesson,
        "tutor_url": _initial_tutor_url(
            tutor_lesson, simulation.concept, DEFAULT_MASS_KG, DEFAULT_FORCE_N, acceleration
        ),
        "experiment_attempt": experiment_attempt,
        "defaults": {
            "mass": DEFAULT_MASS_KG,
            "force": DEFAULT_FORCE_N,
            "acceleration": acceleration,
        },
        "bounds": {
            "mass_min": MIN_MASS_KG,
            "mass_max": MAX_MASS_KG,
            "force_min": MIN_FORCE_N,
            "force_max": MAX_FORCE_N,
        },
    }
    return render(request, template, context)


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
    parts = [
        f"Physics Lab experiment - {attempt.simulation.get_simulation_type_display()}"
    ]
    if attempt.mass_kg is not None:
        parts.append(f"mass = {attempt.mass_kg:.1f} kg")
    if attempt.force_n is not None:
        parts.append(f"net force = {attempt.force_n:.1f} N")
    if attempt.acceleration_m_s2 is not None:
        parts.append(
            f"acceleration = {attempt.acceleration_m_s2:.2f} m/s^2 "
            "(a = F / m, computed by the app)"
        )
    if attempt.prediction:
        parts.append(f"My prediction: {attempt.prediction}")
    if attempt.observation:
        parts.append(f"What I observed: {attempt.observation}")
    if attempt.explanation:
        parts.append(f"Why I think it happened: {attempt.explanation}")
    parts.append("Can you help me understand this?")
    return "\n".join(parts)


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
    student = _current_student(request)
    lesson = _tutor_lesson_for(simulation.concept)
    session = _experiment_session(student, lesson)
    try:
        attempt, validated = record_experiment_observation(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
            observation=request.POST.get("observation", ""),
            mass_kg=request.POST.get("mass_kg"),
            force_n=request.POST.get("force_n"),
        )
    except ExperimentValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "attempt_id": attempt.pk,
            "mass_kg": round(validated.mass_kg, 4),
            "force_n": round(validated.force_n, 4),
            "acceleration_m_s2": round(validated.acceleration_m_s2, 4),
            "message": (
                "Observation saved. Server-computed acceleration: "
                f"{validated.acceleration_m_s2:.2f} m/s² (a = F / m)."
            ),
        }
    )


@require_POST
def experiment_explain(request, slug):
    simulation = _active_simulation(slug)
    student = _current_student(request)
    lesson = _tutor_lesson_for(simulation.concept)
    session = _experiment_session(student, lesson)
    try:
        attempt, _outcomes = record_experiment_explanation(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
            explanation=request.POST.get("explanation", ""),
            mass_kg=request.POST.get("mass_kg"),
            force_n=request.POST.get("force_n"),
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
