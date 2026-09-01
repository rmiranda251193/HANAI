from urllib.parse import urlencode

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.lessons.models import Lesson

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

    context = {
        "simulation": simulation,
        "concept": simulation.concept,
        "tutor_lesson": tutor_lesson,
        "tutor_url": _initial_tutor_url(
            tutor_lesson, simulation.concept, DEFAULT_MASS_KG, DEFAULT_FORCE_N, acceleration
        ),
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
