"""The mathematics-prerequisite taxonomy that connects Physics depth to the
mathematics it actually requires (spec: "Physics depth should be connected
to mathematics... mathematics exists here to support Physics").

Code-defined data only, the same pattern as ``level_catalog``: no model, no
migration, no general-purpose mathematics platform. ``MATH_BY_LEVEL`` maps
each ``level_catalog.PhysicsLevel`` key to the math topics a learner would
typically already need *by the time* they reach that Physics level -- it is
a rough, defensible planning aid, not a hard gate that blocks access.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MathTopic:
    key: str
    order: int
    title: str


MATH_TOPICS: tuple[MathTopic, ...] = (
    MathTopic("arithmetic", 0, "Arithmetic"),
    MathTopic("algebra", 10, "Algebra"),
    MathTopic("geometry", 20, "Geometry"),
    MathTopic("trigonometry", 30, "Trigonometry"),
    MathTopic("functions", 40, "Functions"),
    MathTopic("coordinate_geometry", 50, "Coordinate Geometry"),
    MathTopic("vectors", 60, "Vectors"),
    MathTopic("precalculus", 70, "Precalculus"),
    MathTopic("calculus_1", 80, "Calculus I"),
    MathTopic("calculus_2", 90, "Calculus II"),
    MathTopic("multivariable_calculus", 100, "Multivariable Calculus"),
    MathTopic("linear_algebra", 110, "Linear Algebra"),
    MathTopic("differential_equations", 120, "Differential Equations"),
    MathTopic("probability_statistics", 130, "Probability / Statistics"),
    MathTopic("complex_numbers", 140, "Complex Numbers"),
    MathTopic("complex_analysis", 150, "Complex Analysis"),
    MathTopic("fourier_analysis", 160, "Fourier Analysis"),
    MathTopic("tensor_notation", 170, "Tensor / Index Notation"),
    MathTopic("variational_calculus", 180, "Variational Calculus"),
)

_BY_KEY: dict[str, MathTopic] = {m.key: m for m in MATH_TOPICS}

# Cumulative-in-spirit: a level's tuple lists what's typically *newly*
# assumed by that level, on top of everything listed for the levels before
# it. Deliberately conservative -- omits topics rather than over-claiming.
MATH_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "discovery": (),
    "foundation": ("arithmetic",),
    "junior_high": ("algebra", "geometry"),
    "senior_high": ("trigonometry", "functions", "coordinate_geometry", "vectors"),
    "intro_university": ("precalculus", "calculus_1", "calculus_2"),
    "intermediate_university": ("multivariable_calculus", "linear_algebra", "differential_equations"),
    "advanced_undergraduate": ("probability_statistics", "complex_numbers", "fourier_analysis"),
    "graduate_prep": ("complex_analysis", "tensor_notation", "variational_calculus"),
}


def all_math_topics() -> tuple[MathTopic, ...]:
    return tuple(sorted(MATH_TOPICS, key=lambda m: m.order))


def get_math_topic(key) -> MathTopic | None:
    if not isinstance(key, str):
        return None
    return _BY_KEY.get(key.strip().casefold())


def math_prerequisites_for_level(level_key) -> tuple[MathTopic, ...]:
    """Every math topic typically assumed by ``level_key``, cumulative from
    Discovery up to and including that level. Unknown level -> empty tuple,
    never raises."""

    if not isinstance(level_key, str):
        return ()
    from .level_catalog import get_level

    level = get_level(level_key)
    if level is None:
        return ()

    collected_keys: list[str] = []
    for lvl_key, topic_keys in MATH_BY_LEVEL.items():
        candidate = get_level(lvl_key)
        if candidate is not None and candidate.order <= level.order:
            collected_keys.extend(topic_keys)

    topics = []
    for key in dict.fromkeys(collected_keys):  # de-duplicate, keep first seen
        topic = get_math_topic(key)
        if topic is not None:
            topics.append(topic)
    return tuple(sorted(topics, key=lambda m: m.order))
