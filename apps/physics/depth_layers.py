"""The "Depth Toggle" pilot: one real concept (Newton's Second Law) with
genuinely correct explanations at four depths (Understand / Derive / Explore
Deeper / Advanced), proving the level architecture actually works end to end
rather than staying an inert, unused taxonomy.

Code-defined data only, keyed by ``PhysicsConcept.slug`` -- no model, no
migration, no per-concept UI unless a concept has a real entry here. This is
deliberately NOT populated for the other ~90 concepts in the catalog: writing
shallow depth layers for concepts nobody has reviewed would be exactly the
"fake advanced content" this feature is meant to avoid. Add a concept here
only when its four layers have been written and checked like the ones below.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DepthLayer:
    #: Matches level_catalog.py's depth-toggle order, not a PhysicsLevel key
    #: (Explore Deeper" and "Advanced" are teaching *stances*, not learner
    #: levels -- a senior-high student can peek at "Explore Deeper").
    key: str
    label: str
    explanation: str
    equation: str = ""


DEPTH_LAYERS: dict[str, tuple[DepthLayer, ...]] = {
    "newtons-second-law": (
        DepthLayer(
            "understand", "Understand",
            "The net force on an object determines how quickly its velocity "
            "changes. A bigger net force produces a bigger acceleration; a "
            "bigger mass resists acceleration more -- it has more inertia.",
            "F_net = ma",
        ),
        DepthLayer(
            "derive", "Derive",
            "Newton actually stated the law in terms of momentum: net force "
            "is the rate of change of momentum, F_net = dp/dt, with "
            "p = mv. When the mass stays constant, dp/dt = m(dv/dt) = ma, "
            "which recovers the familiar F = ma.",
            "F_net = dp/dt = d(mv)/dt",
        ),
        DepthLayer(
            "explore_deeper", "Explore Deeper",
            "F = ma only holds when mass is constant. A system that gains "
            "or loses mass while moving -- a rocket burning fuel, a raindrop "
            "picking up moisture -- needs the full momentum form, which "
            "picks up an extra term from the changing mass. This is the "
            "starting point for rocket-motion analysis.",
            "F_net = d(mv)/dt = m(dv/dt) + v(dm/dt)",
        ),
        DepthLayer(
            "advanced", "Advanced",
            "In the Lagrangian formulation of mechanics, F = ma is the "
            "special case of the Euler-Lagrange equation for a free "
            "particle. With L = T - V = (1/2)mv^2 - V(x), the equation "
            "reduces to m(dv/dt) = -dV/dx, i.e. Newton's Second Law -- but "
            "the Lagrangian approach generalizes to any coordinates and to "
            "constrained, many-body systems where F = ma alone is unwieldy.",
            "d/dt(dL/dv) - dL/dx = 0, L = (1/2)mv^2 - V(x)",
        ),
    ),
}


def depth_layers_for(slug) -> tuple[DepthLayer, ...]:
    """The depth layers for a concept slug, or an empty tuple if none have
    been written yet. Never raises, never fabricates a layer."""

    if not isinstance(slug, str):
        return ()
    return DEPTH_LAYERS.get(slug.strip().casefold(), ())
