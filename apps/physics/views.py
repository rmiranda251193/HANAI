import json
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

from .depth_layers import depth_layers_for
from .domain_catalog import all_domains, domain_for_topic, get_domain
from .equation_catalog import equations_for_concept
from .lab_scenarios import evaluate_scenario, get_scenario, scenarios_for
from .level_catalog import level_range_for_difficulty
from .models import PhysicsConcept, PhysicsSimulation
from .simulation_registry import get_simulation_definition
from .visualization_registry import get_visualization


def physics_lab_index(request):
    """List the interactive simulations a student can open."""

    simulations = (
        PhysicsSimulation.objects.filter(is_active=True)
        .select_related("concept")
    )
    return render(request, "physics/lab.html", {"simulations": simulations})


_DIFFICULTY_ORDER = {"foundational": 0, "introductory": 1, "intermediate": 2, "advanced": 3}


def physics_library(request):
    """A searchable, server-rendered browser of the Physics knowledge catalog.

    Groups every active :class:`PhysicsConcept` by domain (``domain_catalog``)
    then by its ``topic``, and shows each concept's difficulty, description,
    equations (``equation_catalog`` -- display only) and any interactive
    simulations (with the 2D/3D/graph/data views the ``visualization_registry``
    declares). Pure read: nothing here writes, and it never touches an AI
    provider. Filters are plain querystring parameters -- no search engine.
    """

    q = (request.GET.get("q") or "").strip()
    domain_key = (request.GET.get("domain") or "").strip()
    difficulty = (request.GET.get("difficulty") or "").strip().lower()

    concepts = list(
        PhysicsConcept.objects.filter(is_active=True)
        .prefetch_related("simulations")
        .order_by("topic", "name")
    )
    if q:
        needle = q.casefold()
        concepts = [
            c for c in concepts
            if needle in c.name.casefold()
            or needle in (c.topic or "").casefold()
            or needle in (c.description or "").casefold()
        ]
    if difficulty in _DIFFICULTY_ORDER:
        concepts = [c for c in concepts if c.difficulty == difficulty]

    selected_domain = get_domain(domain_key)

    # domain -> [{"topic": str, "concepts": [row, ...]}]
    grouped: dict = {}
    for concept in concepts:
        dom = domain_for_topic(concept.topic)
        if selected_domain is not None and dom.key != selected_domain.key:
            continue
        sims = [
            {
                "simulation": s,
                "views": (get_visualization(s.simulation_type).supported_views
                          if get_visualization(s.simulation_type) else ("2d",)),
            }
            for s in concept.simulations.all()
            if s.is_active
        ]
        row = {
            "concept": concept,
            "difficulty": concept.get_difficulty_display(),
            "equations": equations_for_concept(concept.slug),
            "simulations": sims,
            "level_range": level_range_for_difficulty(concept.difficulty),
            "depth_layers": depth_layers_for(concept.slug),
        }
        grouped.setdefault(dom.key, {}).setdefault(concept.topic or "General", []).append(row)

    domains_view = []
    for dom in all_domains():
        topics = grouped.get(dom.key)
        if not topics:
            continue
        domains_view.append(
            {
                "domain": dom,
                "topics": [
                    {"topic": t, "concepts": rows}
                    for t, rows in sorted(topics.items())
                ],
                "concept_count": sum(len(v) for v in topics.values()),
            }
        )

    real_domains = [d for d in all_domains() if d.key != "other"]
    covered = sum(
        1 for d in real_domains
        if grouped.get(d.key) and any(grouped[d.key].values())
    )
    # Distinct from "has concepts": how many domains additionally have at
    # least one interactive simulation, so the summary line never claims a
    # lab exists where only reference content does.
    labs_covered = sum(
        1 for d in real_domains
        if grouped.get(d.key)
        and any(
            row["simulations"]
            for rows in grouped[d.key].values()
            for row in rows
        )
    )

    return render(
        request,
        "physics/library.html",
        {
            "domains_view": domains_view,
            "all_domains": all_domains(include_other=False),
            "difficulties": [
                ("foundational", "Foundation"), ("introductory", "Introductory"),
                ("intermediate", "Intermediate"), ("advanced", "Advanced"),
            ],
            "q": q,
            "selected_domain": selected_domain,
            "selected_difficulty": difficulty if difficulty in _DIFFICULTY_ORDER else "",
            "match_count": len(concepts),
            "coverage": {
                "covered": covered,
                "total": len(real_domains),
                "labs": labs_covered,
            },
        },
    )


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
    "initial_speed_m_s": "initial speed",
    "launch_angle_deg": "launch angle",
    "initial_height_m": "initial height",
    "position_x_m": "horizontal distance",
    "position_y_m": "height",
    "speed_m_s": "speed",
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

    # Teacher read-only preview: hide the Predict / Observe / Explain / Tutor
    # steps so no learning evidence can be produced from a preview. This is a
    # GET-only presentation flag -- it changes nothing server-side (viewing the
    # lab already records nothing; only the POST endpoints write).
    preview = request.GET.get("preview") == "1"

    # Restore the student's in-progress experiment so a refresh keeps their work.
    student = _current_student(request)
    attempt = latest_attempt_for(student, simulation)
    experiment_attempt = attempt if attempt and not attempt.is_complete else None

    bounds = {
        field: {"min": lo, "max": hi} for field, (lo, hi) in definition.bounds.items()
    }
    _scenario_list = [s.as_client_dict for s in scenarios_for(simulation.simulation_type)]
    visualization = get_visualization(simulation.simulation_type)
    context = {
        "simulation": simulation,
        "concept": simulation.concept,
        "tutor_lesson": tutor_lesson,
        "tutor_url": _initial_tutor_url(tutor_lesson, simulation, definition),
        "experiment_attempt": experiment_attempt,
        "defaults": definition.default_state,
        "bounds": bounds,
        "equations": definition.equations,
        # Presentation-only: which client renderers may draw this simulation.
        "visualization": visualization,
        "scenarios": _scenario_list,
        "scenarios_json": json.dumps({s["scenario_id"]: s for s in _scenario_list}),
        "preview": preview,
        # Bootstrap payload for the optional React island (static/react/lab.js).
        # A progressive enhancement only -- the server-rendered sections above
        # are the real page and work with no JavaScript at all.
        "lab_react_state_json": json.dumps(
            {
                "simulationSlug": simulation.slug,
                "simulationTitle": simulation.title,
                "simulationType": simulation.simulation_type,
                "defaults": definition.default_state,
                "bounds": bounds,
                "equations": definition.equations,
                "preview": preview,
                "tutorUrl": _initial_tutor_url(tutor_lesson, simulation, definition),
                "supportedViews": list(visualization.supported_views) if visualization else ["2d"],
                "scenarios": _scenario_list,
                "experimentAttempt": _serialize_experiment_attempt(experiment_attempt),
                "endpoints": {
                    "predict": reverse("physics_lab:experiment_predict", args=[simulation.slug]),
                    "observe": reverse("physics_lab:experiment_observe", args=[simulation.slug]),
                    "explain": reverse("physics_lab:experiment_explain", args=[simulation.slug]),
                },
            }
        ),
    }
    return render(request, definition.template, context)


def _serialize_experiment_attempt(attempt):
    """Plain-dict projection of an in-progress attempt for the React bootstrap
    payload -- only the fields a student is shown; never an internal status,
    misconception code, or anything the server itself hasn't already decided
    to show on the ordinary server-rendered page."""

    if attempt is None:
        return None
    return {
        "id": attempt.pk,
        "prediction": attempt.prediction,
        "observation": attempt.observation,
        "explanation": attempt.explanation,
        "parameters": attempt.parameters if isinstance(attempt.parameters, dict) else {},
    }


@require_POST
def experiment_scenario_check(request, slug, scenario_id):
    """Server-authoritative check of a scenario challenge. Persists nothing.

    The browser sends only the parameters the student chose. The server clamps
    them and reconstructs the outcome with the deterministic Kinematics model,
    so ``completed=true`` / ``score=100`` in the body can never pass a check.
    The durable learning evidence for a challenge is the explanation the student
    submits through the normal Explain step.
    """

    simulation = _active_simulation(slug)
    scenario = get_scenario(scenario_id)
    if scenario is None or scenario.simulation_type != simulation.simulation_type:
        raise Http404("That challenge is not available.")

    try:
        result = evaluate_scenario(
            scenario,
            initial_position=request.POST.get("initial_position_m", 0),
            initial_velocity=request.POST.get("initial_velocity_m_s", 0),
            acceleration=request.POST.get("acceleration_m_s2", 0),
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "Those parameters are not valid numbers."}, status=400
        )

    return JsonResponse(
        {
            "ok": True,
            "scenario_id": scenario.scenario_id,
            "met": result["met"],
            "checks": result["checks"],
            "message": (
                "Goal reached. Now explain how you did it."
                if result["met"]
                else "Not there yet -- adjust the values and check again."
            ),
        }
    )


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
    elif ctx.simulation_type == "projectile_motion":
        if ctx.initial_speed_m_s is not None:
            parts.append(f"initial speed = {ctx.initial_speed_m_s:.1f} m/s")
        if ctx.launch_angle_deg is not None:
            parts.append(f"launch angle = {ctx.launch_angle_deg:.0f} degrees")
        if ctx.initial_height_m is not None:
            parts.append(f"initial height = {ctx.initial_height_m:.1f} m")
        if ctx.time_s is not None:
            parts.append(f"observed time = {ctx.time_s:.1f} s")
        if ctx.position_x_m is not None:
            parts.append(f"horizontal distance = {ctx.position_x_m:.2f} m")
        if ctx.position_y_m is not None:
            parts.append(f"height at that time = {ctx.position_y_m:.2f} m")
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
    predicted = (attempt.parameters or {}).get("prediction") if isinstance(attempt.parameters, dict) else None
    if isinstance(predicted, dict):
        bits = []
        if "velocity_m_s" in predicted:
            bits.append(f"velocity {predicted['velocity_m_s']:.1f} m/s")
        if "position_m" in predicted:
            bits.append(f"position {predicted['position_m']:.1f} m")
        if bits:
            parts.append("My predicted values: " + ", ".join(bits))
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
            structured={
                "predicted_velocity_m_s": request.POST.get("predicted_velocity_m_s"),
                "predicted_position_m": request.POST.get("predicted_position_m"),
                "predicted_direction": request.POST.get("predicted_direction"),
            },
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
