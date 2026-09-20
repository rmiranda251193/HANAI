"""The "Depth Toggle": a hand-picked, growing set of real concepts with
genuinely correct explanations at four depths (Understand / Derive / Explore
Deeper / Advanced), proving the level architecture actually works end to end
rather than staying an inert, unused taxonomy.

Code-defined data only, keyed by ``PhysicsConcept.slug`` -- no model, no
migration, no per-concept UI unless a concept has a real entry here. This is
deliberately NOT populated for most of the ~90 concepts in the catalog:
writing shallow depth layers for concepts nobody has reviewed would be
exactly the "fake advanced content" this feature is meant to avoid. Add a
concept here only when its four layers have been written and checked like
the ones below -- each "Advanced" layer in particular is chosen to connect
to a real, already-built Physics Lab simulation wherever a genuine
connection exists, the same way Newton's Second Law's own Advanced layer
(Lagrangian mechanics) was chosen for being real physics, not padding.
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
    "electric-charge-and-coulombs-law": (
        DepthLayer(
            "understand", "Understand",
            "Charge comes in two types, positive and negative. Like "
            "charges push each other apart; opposite charges pull each "
            "other together. The force between two point charges falls "
            "off with the square of the distance between them -- twice "
            "as far apart means a quarter of the force.",
            "F = k q1 q2 / r^2",
        ),
        DepthLayer(
            "derive", "Derive",
            "Coulomb's law can be split into two steps: one charge "
            "creates an electric field that fills the space around it, "
            "and a second charge simply feels a force from whatever field "
            "it sits in. This separation -- field first, force second -- "
            "is what lets the same field idea describe forces from many "
            "charges at once, just by adding up each one's field.",
            "E = k Q / r^2, then F = q E",
        ),
        DepthLayer(
            "explore_deeper", "Explore Deeper",
            "For a single point charge, Gauss's law (relating the total "
            "electric field flowing out through any closed surface to the "
            "charge enclosed) gives back exactly the same 1/r^2 field "
            "Coulomb's law predicts. Gauss's law is not a different rule, "
            "it is the same physics -- but for a symmetric charge "
            "distribution, like a uniformly charged sphere or an infinite "
            "sheet, it finds the field in a couple of lines instead of a "
            "difficult sum over every point charge individually.",
            "closed-surface integral of E dA = Q_enclosed / epsilon_0",
        ),
        DepthLayer(
            "advanced", "Advanced",
            "In quantum electrodynamics, the electromagnetic force between "
            "two charges is understood as an exchange of virtual photons. "
            "It is a general fact of field theory that a force carried by "
            "a MASSLESS particle produces an exact inverse-square law with "
            "unlimited range, while a force carried by a particle WITH "
            "mass produces a force that dies off exponentially beyond a "
            "limited range instead (this is exactly why the strong "
            "nuclear force, carried by massive gluons/mesons, has such a "
            "short range). Coulomb's law's precise 1/r^2 form, reaching "
            "any distance, is therefore a direct consequence of one fact: "
            "the photon has zero rest mass.",
            "V(r) ~ e^(-m_carrier * r) / r  ->  1/r exactly as m_carrier -> 0",
        ),
    ),
    "conservation-of-momentum": (
        DepthLayer(
            "understand", "Understand",
            "Add up every object's momentum (mass times velocity) in a "
            "system. As long as no net force from outside the system acts "
            "on it, that total never changes, even while the objects "
            "inside push and pull on each other and redistribute momentum "
            "among themselves.",
            "p_total = m1 v1 + m2 v2 + ... = constant, when F_external = 0",
        ),
        DepthLayer(
            "derive", "Derive",
            "This follows directly from Newton's third law. Whenever two "
            "objects in the system interact, the force each exerts on the "
            "other is equal and opposite, so those two forces exactly "
            "cancel when you add up how fast the SYSTEM's total momentum "
            "is changing. Only a force from outside the system survives "
            "that cancellation.",
            "d(p1 + p2)/dt = F_1-on-2 + F_2-on-1 + F_external = F_external",
        ),
        DepthLayer(
            "explore_deeper", "Explore Deeper",
            "A system's total momentum is just its total mass times the "
            "velocity of its center of mass. So conservation of momentum "
            "is really the same statement as Newton's first law applied "
            "to the WHOLE system treated as one object: the center of "
            "mass keeps moving at a constant velocity (or stays at rest) "
            "unless an external force acts, no matter how the pieces "
            "inside are colliding, exploding apart, or orbiting each "
            "other.",
            "p_total = M_total * v_center_of_mass",
        ),
        DepthLayer(
            "advanced", "Advanced",
            "This law of conservation of momentum still holds exactly "
            "even for objects moving near the speed of light, but the "
            "quantity that stays conserved is the RELATIVISTIC momentum, "
            "not the everyday p = mv. Relativistic momentum carries an "
            "extra factor of gamma (the same Lorentz factor from time "
            "dilation and length contraction), and it is exactly the "
            "momentum that appears in the relativistic energy-momentum "
            "relation used to find a fast-moving particle's total energy. "
            "At everyday speeds gamma is so close to 1 that relativistic "
            "momentum and the familiar p = mv are indistinguishable, "
            "which is why Newtonian momentum conservation works perfectly "
            "well for collisions between cars, balls, or planets.",
            "p = gamma m v,  gamma = 1 / sqrt(1 - v^2/c^2)",
        ),
    ),
}


def depth_layers_for(slug) -> tuple[DepthLayer, ...]:
    """The depth layers for a concept slug, or an empty tuple if none have
    been written yet. Never raises, never fabricates a layer."""

    if not isinstance(slug, str):
        return ()
    return DEPTH_LAYERS.get(slug.strip().casefold(), ())
