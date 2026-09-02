"""A deterministic, read-only graph over ``PhysicsConcept.prerequisites``.

The graph *describes Physics relationships* -- it is not a curriculum planner and
it never calls an AI provider. Every prerequisite string stored on a concept is
resolved against the real concept set (by name, case-insensitively, or by slug);
anything that does not resolve, points at the concept itself, or repeats is
dropped rather than invented into a node. Ordering everywhere is a stable total
order (difficulty rank, then name, then slug), so the same rows always yield the
same graph, the same edges, and the same traversal results.

One bounded query (:func:`build_physics_concept_graph`); everything else is pure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import PhysicsConcept

MAX_GRAPH_CONCEPTS = 500
MAX_PREREQUISITES_PER_CONCEPT = 50

DIFFICULTY_RANK = {
    PhysicsConcept.Difficulty.FOUNDATIONAL: 0,
    PhysicsConcept.Difficulty.INTRODUCTORY: 1,
    PhysicsConcept.Difficulty.INTERMEDIATE: 2,
    PhysicsConcept.Difficulty.ADVANCED: 3,
}


@dataclass(frozen=True)
class ConceptNode:
    slug: str
    name: str
    topic: str
    difficulty: str
    difficulty_label: str
    is_active: bool


@dataclass(frozen=True)
class ConceptGraph:
    """Resolved, deduplicated, cycle-agnostic view of the prerequisite graph."""

    nodes: dict  # slug -> ConceptNode  (in stable order)
    prerequisites: dict  # slug -> [prerequisite slug, ...] (stable order)
    next_concepts: dict  # slug -> [dependent slug, ...] (stable order)
    unresolved: dict  # slug -> [raw prerequisite string, ...] that did not resolve
    name_index: dict  # lowercased concept name -> slug

    def has(self, slug: str) -> bool:
        return slug in self.nodes

    def slug_for_name(self, name: str) -> str | None:
        return self.name_index.get((name or "").strip().lower())

    def edges(self) -> list[dict]:
        """All prerequisite->dependent edges, in a stable total order."""

        out = []
        for dep_slug, pres in self.prerequisites.items():
            for pre_slug in pres:
                out.append({"from": pre_slug, "to": dep_slug})
        out.sort(key=lambda e: (e["from"], e["to"]))
        return out


def _sort_key(graph_nodes: dict, slug: str):
    node = graph_nodes[slug]
    return (DIFFICULTY_RANK.get(node.difficulty, 99), node.name.lower(), node.slug)


def build_physics_concept_graph(*, include_inactive: bool = False) -> ConceptGraph:
    """Read the concept set once and resolve its prerequisite relationships."""

    rows = list(
        PhysicsConcept.objects.all().order_by("slug")[:MAX_GRAPH_CONCEPTS]
    )

    # Resolution index spans every concept (even inactive ones) so a prerequisite
    # that names an inactive concept is recognised as "known but excluded"
    # rather than mistaken for a typo.
    name_to_slug_all: dict[str, str] = {}
    slug_set_all = {r.slug for r in rows}
    for r in rows:
        name_to_slug_all.setdefault(r.name.strip().lower(), r.slug)

    selected = rows if include_inactive else [r for r in rows if r.is_active]

    nodes: dict[str, ConceptNode] = {}
    for r in sorted(selected, key=lambda r: (DIFFICULTY_RANK.get(r.difficulty, 99), r.name.lower(), r.slug)):
        nodes[r.slug] = ConceptNode(
            slug=r.slug,
            name=r.name,
            topic=r.topic,
            difficulty=r.difficulty,
            difficulty_label=r.get_difficulty_display(),
            is_active=r.is_active,
        )

    prerequisites: dict[str, list[str]] = {slug: [] for slug in nodes}
    unresolved: dict[str, list[str]] = {}

    by_slug = {r.slug: r for r in selected}
    for slug in nodes:
        raw = by_slug[slug].prerequisites
        raw_items = (raw if isinstance(raw, list) else [])[:MAX_PREREQUISITES_PER_CONCEPT]
        seen: set[str] = set()
        resolved: list[str] = []
        bad: list[str] = []
        for item in raw_items:
            if item is None:
                continue
            key = str(item).strip()
            if not key:
                continue
            lowered = key.lower()
            target = name_to_slug_all.get(lowered)
            if target is None and lowered in slug_set_all:
                target = lowered
            if target is None:
                bad.append(key)  # unknown prerequisite reference
                continue
            if target == slug:
                continue  # self-prerequisite -> ignore
            if target not in nodes:
                bad.append(key)  # points at an inactive/excluded concept
                continue
            if target in seen:
                continue  # duplicate -> collapse
            seen.add(target)
            resolved.append(target)
        prerequisites[slug] = sorted(resolved, key=lambda s: _sort_key(nodes, s))
        if bad:
            unresolved[slug] = sorted(set(bad))

    next_concepts: dict[str, list[str]] = {slug: [] for slug in nodes}
    for dep_slug, pres in prerequisites.items():
        for pre_slug in pres:
            next_concepts[pre_slug].append(dep_slug)
    for slug in next_concepts:
        next_concepts[slug] = sorted(
            set(next_concepts[slug]), key=lambda s: _sort_key(nodes, s)
        )

    # Resolve names to slugs the same way prerequisites were resolved (first by
    # slug order), so slug_for_name() and prerequisite resolution never disagree.
    name_index: dict[str, str] = {}
    for r in rows:
        if r.slug in nodes:
            name_index.setdefault(r.name.strip().lower(), r.slug)

    return ConceptGraph(
        nodes=nodes,
        prerequisites=prerequisites,
        next_concepts=next_concepts,
        unresolved=unresolved,
        name_index=name_index,
    )


def get_adjacent_concepts(graph: ConceptGraph, slug: str) -> dict:
    """``{"prerequisites": [ConceptNode...], "next_concepts": [ConceptNode...]}``."""

    if slug not in graph.nodes:
        return {"prerequisites": [], "next_concepts": []}
    return {
        "prerequisites": [graph.nodes[s] for s in graph.prerequisites.get(slug, [])],
        "next_concepts": [graph.nodes[s] for s in graph.next_concepts.get(slug, [])],
    }


def find_shortest_concept_path(
    graph: ConceptGraph, start_slug: str, target_slug: str, *, forward: bool = True
) -> list[str]:
    """BFS from ``start`` to ``target`` following edges in one direction.

    ``forward=True`` walks prerequisite -> dependent; ``forward=False`` walks
    dependent -> prerequisite. Returns the slug list including both ends, or
    ``[]`` when unreachable. A ``visited`` set makes it safe against self-loops
    and cycles; neighbour order is the graph's stable order, so the path is
    deterministic.
    """

    if start_slug not in graph.nodes or target_slug not in graph.nodes:
        return []
    if start_slug == target_slug:
        return [start_slug]

    adjacency = graph.next_concepts if forward else graph.prerequisites
    came_from: dict[str, str | None] = {start_slug: None}
    queue: deque[str] = deque([start_slug])

    while queue:
        current = queue.popleft()
        for neighbour in adjacency.get(current, []):
            if neighbour in came_from:
                continue
            came_from[neighbour] = current
            if neighbour == target_slug:
                path = [neighbour]
                while came_from[path[-1]] is not None:
                    path.append(came_from[path[-1]])
                path.reverse()
                return path
            queue.append(neighbour)
    return []
