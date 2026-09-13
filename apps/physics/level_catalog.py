"""The Physics level taxonomy -- "one Physics universe, multiple levels of
understanding" (the scalable depth spine, alongside ``domain_catalog``'s
scalable breadth spine).

This is **code-defined data only** (the same pattern as ``domain_catalog``
and ``simulation_registry``): an ordered, allow-listed list of learner
levels from absolute-beginner to graduate-preparation. It adds **no
database model and no migration**.

Today, the only thing actually wired to this taxonomy is a *display*
mapping from ``PhysicsConcept.difficulty`` (the 4 tiers that already exist
on the model) onto a level range (see ``level_range_for_difficulty``), plus
one hand-authored pilot of real multi-depth content
(``apps.physics.depth_layers``, Newton's Second Law only). No concept in the
catalog is claimed to have content at every level just because the level
exists here -- see ``templates/physics/library.html``'s honest coverage
line and ``apps.physics.depth_layers`` for what is actually populated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicsLevel:
    key: str
    order: int
    title: str
    #: Rough real-world stage this level corresponds to (not a strict
    #: age/grade promise -- a defensible, human-readable anchor only).
    stage: str
    blurb: str


LEVELS: tuple[PhysicsLevel, ...] = (
    PhysicsLevel(
        "discovery", 0, "Physics Discovery", "Curiosity-driven, no formulas",
        "Noticing that the world follows patterns -- things fall, push back, "
        "get hot, make sound. Pure observation and wonder, no mathematics.",
    ),
    PhysicsLevel(
        "foundation", 1, "Foundation", "Upper elementary / early middle school",
        "Everyday-language cause and effect: pushes and pulls, hot and cold, "
        "faster and slower. Qualitative reasoning before formulas.",
    ),
    PhysicsLevel(
        "junior_high", 2, "Junior High", "Roughly grades 7-8",
        "First real quantities and simple equations (speed = distance / "
        "time). Measurement, units, and basic graphs enter the picture.",
    ),
    PhysicsLevel(
        "senior_high", 3, "Senior High", "Roughly grades 9-12",
        "Algebra-based mechanics, waves, electricity: F = ma, kinematics "
        "equations, circuits. The level HANAI's existing labs are built at.",
    ),
    PhysicsLevel(
        "intro_university", 4, "Introductory University", "First-year university physics",
        "The same topics with calculus available: derivatives and integrals "
        "connect position, velocity and acceleration; vector mechanics.",
    ),
    PhysicsLevel(
        "intermediate_university", 5, "Intermediate University", "Second/third-year physics major",
        "Differential equations, multivariable calculus and linear algebra "
        "applied to mechanics, E&M, and thermodynamics.",
    ),
    PhysicsLevel(
        "advanced_undergraduate", 6, "Advanced Undergraduate", "Senior-year physics major",
        "Formal theoretical structures: Lagrangian and Hamiltonian "
        "mechanics, Maxwell's equations in differential form, statistical "
        "mechanics, an introduction to quantum mechanics.",
    ),
    PhysicsLevel(
        "graduate_prep", 7, "Graduate Preparation", "Preparing for graduate study",
        "Formal derivations, tensor/index notation, variational principles, "
        "and the assumptions and limits of each theory made explicit.",
    ),
)

_BY_KEY: dict[str, PhysicsLevel] = {lvl.key: lvl for lvl in LEVELS}

# A DISPLAY mapping only -- connects the level taxonomy to data that already
# exists (PhysicsConcept.difficulty) instead of requiring every one of the
# existing 88 concepts to be re-tagged before the taxonomy is useful at all.
# It is deliberately a *range*: a concept marked "advanced" today is not
# claimed to reach graduate depth, only that it is *typically first studied*
# somewhere in that range.
_RANGE_BY_DIFFICULTY: dict[str, tuple[str, str]] = {
    "foundational": ("discovery", "foundation"),
    "introductory": ("junior_high", "senior_high"),
    "intermediate": ("senior_high", "intro_university"),
    "advanced": ("advanced_undergraduate", "graduate_prep"),
}


def all_levels() -> tuple[PhysicsLevel, ...]:
    return tuple(sorted(LEVELS, key=lambda lvl: lvl.order))


def get_level(key) -> PhysicsLevel | None:
    if not isinstance(key, str):
        return None
    return _BY_KEY.get(key.strip().casefold())


def level_range_for_difficulty(difficulty) -> tuple[PhysicsLevel, PhysicsLevel] | None:
    """The (low, high) ``PhysicsLevel`` a ``PhysicsConcept.difficulty`` value
    is typically first studied at. ``None`` for an unrecognised value --
    never raises, never invents a range for garbage input."""

    if not isinstance(difficulty, str):
        return None
    keys = _RANGE_BY_DIFFICULTY.get(difficulty.strip().casefold())
    if keys is None:
        return None
    low, high = get_level(keys[0]), get_level(keys[1])
    if low is None or high is None:
        return None
    return (low, high)
