"""Connect what a student has actually done to the Physics concept graph.

The concept graph (``apps/physics/concept_graph.py``) describes Physics
relationships. Step 19's ``build_student_learning_patterns`` describes what the
student actually did. This module joins the two: it takes the student's explored
concepts, finds their graph-adjacent concepts, and picks one deterministic,
graph-connected concept to investigate next -- always deferring to an unfinished
experiment or a pending teacher recommendation first.

No mastery, readiness, or ability judgement is ever produced, and nothing is
persisted. Deterministic: the same rows always yield the same path and the same
suggestion.
"""

from __future__ import annotations

from django.urls import reverse

from apps.lessons.models import Lesson
from apps.physics.concept_graph import (
    DIFFICULTY_RANK,
    build_physics_concept_graph,
    find_shortest_concept_path,
)
from apps.physics.models import PhysicsSimulation

from .pattern_services import build_student_learning_patterns

RELATED_LIMIT = 8

# Step 19 next-step codes that describe *unfinished or teacher-directed* work.
# The concept graph must never push past these.
_ACTIVITY_PRIORITY_CODES = {
    "incomplete_experiment",
    "pending_recommendation",
    "practice_after_lab",
    "lab_after_practice",
    "tutor_after_both",
}


def _node_sort_key(node):
    return (DIFFICULTY_RANK.get(node.difficulty, 99), node.name.lower(), node.slug)


def build_concept_destination_maps():
    """``(lesson_by_concept_slug, sim_by_concept_slug)`` -- the best existing
    lesson / active simulation for each Physics concept, published-first, in a
    stable total order. Three bounded queries regardless of how many concepts
    are looked up. Shared with the learning-goal destination resolver."""

    lessons = list(
        Lesson.objects.prefetch_related("physics_concepts").order_by(
            "-published_at", "-updated_at", "-id"  # total order: id breaks ties
        )
    )
    lesson_by_slug: dict[str, Lesson] = {}
    for lesson in lessons:
        for concept in lesson.physics_concepts.all():
            lesson_by_slug.setdefault(concept.slug, lesson)

    sims = list(
        PhysicsSimulation.objects.filter(is_active=True)
        .select_related("concept")
        .order_by("title", "slug")  # slug breaks title ties
    )
    sim_by_slug: dict[str, PhysicsSimulation] = {}
    for sim in sims:
        sim_by_slug.setdefault(sim.concept.slug, sim)

    return lesson_by_slug, sim_by_slug


def _destination_for(slug, lesson_by_slug, sim_by_slug) -> dict:
    """A real, server-resolved activity for a concept. Never built from input."""

    lesson = lesson_by_slug.get(slug)
    if lesson is not None:
        return {
            "kind": "lesson",
            "url": reverse("students:tutor", args=[lesson.slug]),
            "label": "Open the lesson",
        }
    sim = sim_by_slug.get(slug)
    if sim is not None:
        return {
            "kind": "lab",
            "url": reverse("physics_lab:detail", args=[sim.slug]),
            "label": "Open the Physics Lab",
        }
    return {
        "kind": "lessons",
        "url": reverse("students:lessons"),
        "label": "Browse lessons",
    }


def _explored_from_patterns(patterns: dict, graph) -> list[dict]:
    """The student's explored concepts, mapped onto active graph nodes.

    Uses Step 19's conservative attribution unchanged. A concept with activity
    that is not an active graph node (unknown or inactive) is simply left out of
    the graph view -- it still appears on the learning-patterns page.
    """

    explored: list[dict] = []
    for row in patterns.get("concept_activity", []):
        slug = graph.slug_for_name(row.get("concept", ""))
        if slug is None:
            continue
        node = graph.nodes[slug]
        activities = (
            row["practice"]["attempts"]
            + row["experiment"]["attempted"]
            + row["tutor"]["student_messages"]
        )
        explored.append(
            {
                "slug": slug,
                "name": node.name,
                "topic": node.topic,
                "difficulty_label": node.difficulty_label,
                "activities": activities,
            }
        )
    return explored  # already in Step 19's recency order


def build_student_concept_path(
    *,
    student,
    now=None,
    patterns: dict | None = None,
    with_actions: bool = True,
    graph=None,
) -> dict:
    """Everything ``students/path.html`` (and the teacher panel) needs.

    ``graph`` may be supplied by a caller that already built one (e.g. the
    teacher workspace, which also renders learning goals) to avoid a second
    identical concept read.
    """

    if patterns is None:
        patterns = build_student_learning_patterns(student=student, now=now)
    if graph is None:
        graph = build_physics_concept_graph()  # active concepts only

    explored = _explored_from_patterns(patterns, graph)
    explored_slugs = {e["slug"] for e in explored}
    explored_index = {e["slug"]: i for i, e in enumerate(explored)}  # 0 = most recent

    # --- adjacency of explored concepts --------------------------------
    prereq_relations: dict[str, set[str]] = {}
    next_relations: dict[str, set[str]] = {}
    for es in explored_slugs:
        for pre in graph.prerequisites.get(es, []):
            prereq_relations.setdefault(pre, set()).add(es)
        for nxt in graph.next_concepts.get(es, []):
            next_relations.setdefault(nxt, set()).add(es)

    def _names(slugs) -> list[str]:
        return sorted(graph.nodes[s].name for s in slugs)

    related_prerequisites = []
    for slug, of_slugs in prereq_relations.items():
        if slug in explored_slugs:
            continue
        node = graph.nodes[slug]
        related_prerequisites.append(
            {
                "slug": slug,
                "name": node.name,
                "topic": node.topic,
                "difficulty_label": node.difficulty_label,
                "prerequisite_of": _names(of_slugs),
            }
        )
    related_prerequisites.sort(key=lambda e: _node_sort_key(graph.nodes[e["slug"]]))
    related_prerequisites = related_prerequisites[:RELATED_LIMIT]

    next_candidates = []
    for slug, from_slugs in next_relations.items():
        if slug in explored_slugs:
            continue
        node = graph.nodes[slug]
        missing = sorted(
            graph.nodes[p].name
            for p in graph.prerequisites.get(slug, [])
            if p not in explored_slugs
        )
        best_recency = min(explored_index.get(s, 10**9) for s in from_slugs)
        next_candidates.append(
            {
                "slug": slug,
                "name": node.name,
                "topic": node.topic,
                "difficulty_label": node.difficulty_label,
                "follows": _names(from_slugs),
                "missing_prereqs": missing,
                "all_prereqs_explored": not missing,
                "_recency": best_recency,
            }
        )
    next_candidates.sort(
        key=lambda e: (
            0 if e["all_prereqs_explored"] else 1,
            e["_recency"],
            DIFFICULTY_RANK.get(graph.nodes[e["slug"]].difficulty, 99),
            e["name"].lower(),
            e["slug"],
        )
    )
    next_candidates = next_candidates[:RELATED_LIMIT]
    graph_candidate = next_candidates[0] if next_candidates else None

    # --- the longest forward chain that connects two explored concepts ---
    walked_path: list[dict] = []
    if len(explored) >= 2:
        ordered_slugs = [
            e["slug"]
            for e in sorted(explored, key=lambda e: _node_sort_key(graph.nodes[e["slug"]]))
        ]
        best: list[str] = []
        for start in ordered_slugs:
            for end in ordered_slugs:
                if start == end:
                    continue
                candidate_path = find_shortest_concept_path(
                    graph, start, end, forward=True
                )
                if len(candidate_path) > len(best):
                    best = candidate_path
        walked_path = [
            {"slug": s, "name": graph.nodes[s].name, "explored": s in explored_slugs}
            for s in best
        ]

    # --- the one deterministic suggestion --------------------------
    lesson_by_slug: dict = {}
    sim_by_slug: dict = {}
    if with_actions:
        lesson_by_slug, sim_by_slug = build_concept_destination_maps()

    next_investigation = patterns.get("next_investigation")
    suggested = None

    if next_investigation and next_investigation.get("code") in _ACTIVITY_PRIORITY_CODES:
        suggested = {
            "kind": "activity",
            "text": next_investigation["text"],
            "url": next_investigation["url"],
            "url_label": next_investigation["url_label"],
        }
    elif graph_candidate and with_actions and next_investigation is not None:
        # ``next_investigation`` is required here so the activity-priority check
        # above is meaningful; a concept suggestion is only offered once we know
        # no unfinished / teacher-directed step is pending.
        node = graph.nodes[graph_candidate["slug"]]
        predecessor = min(
            next_relations.get(node.slug, {node.slug}),
            key=lambda s: (explored_index.get(s, 10**9), s),
        )
        step_path = find_shortest_concept_path(
            graph, predecessor, node.slug, forward=True
        ) or [node.slug]
        destination = _destination_for(node.slug, lesson_by_slug, sim_by_slug)
        follows = graph_candidate["follows"][0] if graph_candidate["follows"] else ""
        if graph_candidate["all_prereqs_explored"]:
            why = (
                f"This concept connects to the Physics you've already explored"
                + (f" — it follows {follows}." if follows else ".")
            )
        else:
            first_missing = graph_candidate["missing_prereqs"][0]
            why = (
                (f"This concept follows {follows}. " if follows else "")
                + f"Related prerequisite to look at first: {first_missing}."
            )
        suggested = {
            "kind": "concept",
            "concept": node.name,
            "why": why,
            "url": destination["url"],
            "url_label": destination["label"],
            "dest_kind": destination["kind"],
            "missing_prereq": (
                graph_candidate["missing_prereqs"][0]
                if graph_candidate["missing_prereqs"]
                else ""
            ),
            "path": [
                {"slug": s, "name": graph.nodes[s].name, "explored": s in explored_slugs}
                for s in step_path
            ],
        }
    elif next_investigation:
        suggested = {
            "kind": "activity",
            "text": next_investigation["text"],
            "url": next_investigation["url"],
            "url_label": next_investigation["url_label"],
        }

    for candidate in next_candidates:
        candidate.pop("_recency", None)

    return {
        "graph_available": bool(graph.nodes),
        "has_explored": bool(explored),
        "explored": explored,
        "related_prerequisites": related_prerequisites,
        "next_candidates": next_candidates,
        "walked_path": walked_path,
        "suggested": suggested,
    }
