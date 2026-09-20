"""Teacher Scenario Studio views. Thin -- validation and persistence live in
``scenario_services.py``. Teacher identity always comes from ``request.user``
(never POST); every mutation is POST + CSRF; GET is always read-only."""

from __future__ import annotations

import logging

from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.teachers.access import teacher_required

from . import scenario_services as services
from .lab_scenarios import allowed_target_kinds, value_fields_for
from .models import PhysicsScenario, PhysicsSimulation
from .scenario_services import TARGET_FIELD_LABELS, TARGET_KIND_LABELS

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR = "That could not be saved. Please try again."


def _simulation_choices():
    return list(
        PhysicsSimulation.objects.filter(
            is_active=True, simulation_type__in=services.TEACHER_SCENARIO_SUPPORTED_TYPES
        )
        .order_by("title")
        .values_list("pk", "title", "simulation_type")
    )


def _target_kind_choices(simulation_type):
    return [(k, TARGET_KIND_LABELS.get(k, k)) for k in sorted(allowed_target_kinds(simulation_type))]


def _target_field_choices(simulation_type):
    labels = TARGET_FIELD_LABELS.get(simulation_type, {})
    return [(f, labels.get(f, f)) for f in sorted(value_fields_for(simulation_type))]


def _scenario_form_context(request, *, scenario=None, error="", draft=None):
    posted = request.POST if request.method == "POST" else None
    simulation_type = ""
    if posted is not None and posted.get("simulation_id"):
        sim = PhysicsSimulation.objects.filter(pk=posted.get("simulation_id")).first()
        simulation_type = sim.simulation_type if sim else ""
    elif scenario is not None:
        simulation_type = scenario.simulation.simulation_type
    elif draft is not None:
        sim = PhysicsSimulation.objects.filter(pk=draft.get("simulation_id")).first()
        simulation_type = sim.simulation_type if sim else ""

    if posted is not None:
        target = {
            "kind": posted.get("target_kind", ""),
            "field": posted.get("target_field", ""),
            "at_time_s": posted.get("at_time_s", ""),
            "target": posted.get("target_value", ""),
            "tolerance": posted.get("tolerance", ""),
            "range_min": posted.get("range_min", ""),
            "range_max": posted.get("range_max", ""),
        }
        values = {
            "title": posted.get("title", ""),
            "simulation_id": posted.get("simulation_id", ""),
            "description": posted.get("description", ""),
            "instructions": posted.get("instructions", ""),
            "prediction_prompt": posted.get("prediction_prompt", ""),
            "reflection_prompt": posted.get("reflection_prompt", ""),
            "initial_state": {
                f: posted.get(f"initial_{f}", "") for f in _input_fields_for(simulation_type)
            },
            "difficulty": posted.get("difficulty", PhysicsScenario.Difficulty.INTRODUCTORY),
            "category": posted.get("category", ""),
            "teacher_request": posted.get("teacher_request", ""),
        }
        values["target"] = target
    elif draft is not None:
        values = {
            "title": draft.get("title", ""),
            "simulation_id": draft.get("simulation_id", ""),
            "description": draft.get("description", ""),
            "instructions": draft.get("instructions", ""),
            "prediction_prompt": "",
            "reflection_prompt": draft.get("reflection_prompt", ""),
            "initial_state": draft.get("initial_state", {}),
            "difficulty": PhysicsScenario.Difficulty.INTRODUCTORY,
            "category": "",
            "teacher_request": "",
        }
        values["target"] = draft.get("target_condition", {})
    elif scenario is not None:
        values = {
            "title": scenario.title,
            "simulation_id": scenario.simulation_id,
            "description": scenario.description,
            "instructions": scenario.instructions,
            "prediction_prompt": scenario.prediction_prompt,
            "reflection_prompt": scenario.reflection_prompt,
            "initial_state": scenario.initial_state,
            "difficulty": scenario.difficulty,
            "category": scenario.category,
            "teacher_request": "",
        }
        values["target"] = scenario.target_condition
    else:
        values = {
            "title": "", "simulation_id": "", "description": "", "instructions": "",
            "prediction_prompt": "", "reflection_prompt": "", "initial_state": {},
            "difficulty": PhysicsScenario.Difficulty.INTRODUCTORY, "category": "",
            "teacher_request": "", "target": {},
        }

    input_fields = _input_fields_for(simulation_type) if simulation_type else []
    initial_state = values.get("initial_state") or {}
    # Django templates cannot look up a dict by a loop variable's key
    # (`{{ dict.field }}` only ever does a LITERAL "field" lookup) -- so the
    # (name, value) pairing is done here, once, instead of adding a custom
    # template filter this codebase doesn't otherwise use anywhere.
    initial_state_rows = [{"name": f, "value": initial_state.get(f, "")} for f in input_fields]
    target_kind_choices = _target_kind_choices(simulation_type)

    return {
        "scenario": scenario,
        "is_used": services.is_used(scenario) if scenario is not None else False,
        "simulation_choices": _simulation_choices(),
        "difficulty_choices": PhysicsScenario.Difficulty.choices,
        "category_choices": PhysicsScenario.Category.choices,
        "target_kind_choices": target_kind_choices,
        "supports_reverses": any(value == "reverses" for value, _ in target_kind_choices),
        "target_field_choices": _target_field_choices(simulation_type) if simulation_type else [],
        "input_fields": input_fields,
        "initial_state_rows": initial_state_rows,
        "values": values,
        "error": error,
        "ai_suggested": draft is not None,
    }


def _input_fields_for(simulation_type):
    from .simulation_registry import get_simulation_definition

    definition = get_simulation_definition(simulation_type) if simulation_type else None
    return list(definition.input_fields) if definition is not None else []


def _initial_state_from_post(request):
    return {
        key[len("initial_"):]: value
        for key, value in request.POST.items()
        if key.startswith("initial_") and value not in (None, "")
    }


def _target_from_post(request):
    return {
        "kind": request.POST.get("target_kind", ""),
        "field": request.POST.get("target_field", ""),
        "at_time_s": request.POST.get("at_time_s", 0),
        "target": request.POST.get("target_value", 0),
        "tolerance": request.POST.get("tolerance", 0),
        "range_min": request.POST.get("range_min", 0),
        "range_max": request.POST.get("range_max", 0),
    }


@teacher_required
def scenario_list(request):
    scenarios = services.list_teacher_scenarios(teacher=request.user)
    return render(request, "teachers/scenario_list.html", {"scenarios": scenarios})


@teacher_required
def scenario_create(request):
    if request.method == "POST":
        if request.POST.get("action") == "choose_simulation":
            # No save, no AI call -- just re-render with the right dynamic
            # fields for the chosen simulation (Section 21: fields come from
            # that simulation's own registered definition, never hardcoded).
            return render(request, "teachers/scenario_form.html", _scenario_form_context(request))

        if request.POST.get("action") == "ai_suggest":
            try:
                draft = services.suggest_scenario_draft(
                    teacher_request=request.POST.get("teacher_request", ""),
                    simulation_id=request.POST.get("simulation_id"),
                )
            except services.ScenarioError as exc:
                return render(
                    request,
                    "teachers/scenario_form.html",
                    _scenario_form_context(request, error=str(exc)),
                )
            except Exception:
                logger.exception("Unexpected AI scenario suggestion failure.")
                return render(
                    request,
                    "teachers/scenario_form.html",
                    _scenario_form_context(request, error=UNEXPECTED_ERROR),
                )
            return render(
                request,
                "teachers/scenario_form.html",
                _scenario_form_context(request, draft=draft),
            )

        try:
            scenario = services.create_scenario(
                teacher=request.user,
                title=request.POST.get("title", ""),
                simulation_id=request.POST.get("simulation_id"),
                description=request.POST.get("description", ""),
                instructions=request.POST.get("instructions", ""),
                prediction_prompt=request.POST.get("prediction_prompt", ""),
                reflection_prompt=request.POST.get("reflection_prompt", ""),
                initial_state=_initial_state_from_post(request),
                target_condition=_target_from_post(request),
                difficulty=request.POST.get("difficulty", PhysicsScenario.Difficulty.INTRODUCTORY),
                category=request.POST.get("category", ""),
            )
        except services.ScenarioError as exc:
            return render(
                request,
                "teachers/scenario_form.html",
                _scenario_form_context(request, error=str(exc)),
            )
        except Exception:
            logger.exception("Unexpected scenario-creation failure.")
            return render(
                request,
                "teachers/scenario_form.html",
                _scenario_form_context(request, error=UNEXPECTED_ERROR),
            )
        return redirect("teachers:scenario_detail", slug=scenario.slug)

    return render(request, "teachers/scenario_form.html", _scenario_form_context(request))


def _owned_scenario_or_403(request, slug):
    scenario = get_object_or_404(PhysicsScenario.objects.select_related("simulation", "created_by"), slug=slug)
    if scenario.created_by_id is not None and scenario.created_by_id != request.user.id:
        raise Http404("That scenario could not be found.")
    return scenario


@teacher_required
def scenario_detail(request, slug):
    scenario = get_object_or_404(PhysicsScenario.objects.select_related("simulation", "created_by"), slug=slug)
    return render(
        request,
        "teachers/scenario_detail.html",
        {
            "scenario": scenario,
            "is_owner": scenario.created_by_id in (None, request.user.id),
            "is_used": services.is_used(scenario),
            "target_kind_label": TARGET_KIND_LABELS.get(
                scenario.target_condition.get("kind", ""), scenario.target_condition.get("kind", "")
            ),
        },
    )


@teacher_required
def scenario_edit(request, slug):
    scenario = _owned_scenario_or_403(request, slug)

    if request.method == "POST":
        fields = {
            "title": request.POST.get("title", ""),
            "description": request.POST.get("description", ""),
            "instructions": request.POST.get("instructions", ""),
            "prediction_prompt": request.POST.get("prediction_prompt", ""),
            "reflection_prompt": request.POST.get("reflection_prompt", ""),
            "difficulty": request.POST.get("difficulty", scenario.difficulty),
            "category": request.POST.get("category", ""),
        }
        if not services.is_used(scenario):
            fields.update(
                simulation_id=request.POST.get("simulation_id"),
                initial_state=_initial_state_from_post(request),
                target_condition=_target_from_post(request),
            )
        try:
            services.update_scenario(scenario_id=scenario.pk, teacher=request.user, **fields)
        except services.ScenarioPermissionError:
            return HttpResponseForbidden("You can only edit your own scenarios.")
        except services.ScenarioError as exc:
            return render(
                request,
                "teachers/scenario_form.html",
                _scenario_form_context(request, scenario=scenario, error=str(exc)),
            )
        except Exception:
            logger.exception("Unexpected scenario-edit failure for scenario %s.", scenario.pk)
            return render(
                request,
                "teachers/scenario_form.html",
                _scenario_form_context(request, scenario=scenario, error=UNEXPECTED_ERROR),
            )
        return redirect("teachers:scenario_detail", slug=scenario.slug)

    return render(request, "teachers/scenario_form.html", _scenario_form_context(request, scenario=scenario))


@require_POST
@teacher_required
def scenario_activate(request, slug):
    scenario = _owned_scenario_or_403(request, slug)
    try:
        services.set_scenario_status(
            scenario_id=scenario.pk, teacher=request.user, status=PhysicsScenario.Status.ACTIVE
        )
    except services.ScenarioPermissionError:
        return HttpResponseForbidden("You can only change your own scenarios.")
    except services.ScenarioError:
        pass
    return redirect("teachers:scenario_detail", slug=scenario.slug)


@require_POST
@teacher_required
def scenario_archive(request, slug):
    scenario = _owned_scenario_or_403(request, slug)
    try:
        services.set_scenario_status(
            scenario_id=scenario.pk, teacher=request.user, status=PhysicsScenario.Status.ARCHIVED
        )
    except services.ScenarioPermissionError:
        return HttpResponseForbidden("You can only change your own scenarios.")
    except services.ScenarioError:
        pass
    return redirect("teachers:scenario_detail", slug=scenario.slug)


@require_POST
@teacher_required
def scenario_delete(request, slug):
    scenario = _owned_scenario_or_403(request, slug)
    try:
        services.delete_scenario(scenario_id=scenario.pk, teacher=request.user)
    except services.ScenarioPermissionError:
        return HttpResponseForbidden("You can only delete your own scenarios.")
    except services.ScenarioError as exc:
        return render(
            request,
            "teachers/scenario_detail.html",
            {
                "scenario": scenario,
                "is_owner": True,
                "is_used": services.is_used(scenario),
                "error": str(exc),
                "target_kind_label": TARGET_KIND_LABELS.get(scenario.target_condition.get("kind", ""), ""),
            },
        )
    return redirect("teachers:scenario_list")
