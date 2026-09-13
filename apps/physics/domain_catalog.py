"""The Physics domain catalog -- the scalable spine of the HANAI Physics universe.

This is **code-defined data only** (the same pattern as ``simulation_registry``
and ``lab_scenarios``): an ordered, allow-listed list of Physics domains, and a
mapping from a ``PhysicsConcept.topic`` string to the domain it belongs to.

It deliberately adds **no database model and no migration**. A domain is a
grouping *above* the existing ``PhysicsConcept.topic`` field; a subtopic, when
one is ever needed, is just a finer ``topic`` string. Concepts, difficulty
levels (Foundation -> Advanced already live on ``PhysicsConcept.difficulty``),
equations, misconceptions, simulations, prerequisites and the concept graph all
stay exactly where they are.

Most domains below have no concepts yet -- that is expected. The Physics Library
page reports coverage honestly rather than fabricating content.

``level_range`` (added alongside ``level_catalog``) states the span of learner
levels this DOMAIN AS A FIELD OF PHYSICS genuinely reaches -- e.g. Gravitation
legitimately runs from a junior-high "things fall down" up through graduate
General Relativity. It is a scope statement about the subject, never a claim
that HANAI has content at every one of those levels yet; see
``level_catalog.py``'s own module docstring and ``apps.physics.depth_layers``
for what is actually populated today.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhysicsDomain:
    key: str
    title: str
    order: int
    blurb: str
    #: ``PhysicsConcept.topic`` strings that roll up into this domain
    topics: tuple[str, ...] = field(default_factory=tuple)
    #: (lowest, highest) ``level_catalog.PhysicsLevel`` key this field of
    #: Physics genuinely spans -- a scope statement, not a content claim.
    level_range: tuple[str, str] = ("junior_high", "senior_high")


# Ordered, curriculum-shaped. Topics are the *expected* topic strings; a concept
# whose topic is not listed anywhere lands in the "other" domain (never lost).
_DOMAINS: tuple[PhysicsDomain, ...] = (
    PhysicsDomain("introduction", "Introduction to Physics", 10,
                  "Measurement, units, estimation and the scientific method.",
                  ("Introduction", "Measurement", "Units"),
                  level_range=("discovery", "senior_high")),
    PhysicsDomain("kinematics", "Kinematics", 20,
                  "Describing motion: position, displacement, velocity and acceleration.",
                  ("Kinematics", "Free Fall", "Projectile Motion"),
                  level_range=("junior_high", "intro_university")),
    PhysicsDomain("dynamics", "Dynamics", 30,
                  "Forces and Newton's laws -- why motion changes.",
                  ("Dynamics", "Forces", "Mechanics", "Friction", "Inclined Plane"),
                  level_range=("junior_high", "advanced_undergraduate")),
    PhysicsDomain("energy", "Work, Energy and Power", 40,
                  "Work, kinetic and potential energy, conservation of energy, power.",
                  ("Energy", "Work", "Power", "Work and Energy"),
                  level_range=("junior_high", "intermediate_university")),
    PhysicsDomain("momentum", "Momentum and Collisions", 50,
                  "Impulse, momentum and its conservation in collisions.",
                  ("Momentum", "Collisions"),
                  level_range=("junior_high", "intermediate_university")),
    PhysicsDomain("rotation", "Circular and Rotational Motion", 60,
                  "Uniform circular motion, torque, angular momentum and rotation.",
                  ("Circular Motion", "Rotation", "Torque", "Rotational Motion"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("gravitation", "Gravitation", 70,
                  "Newtonian gravity, orbits and gravitational fields.",
                  ("Gravitation", "Gravity", "Orbits"),
                  level_range=("junior_high", "graduate_prep")),
    PhysicsDomain("fluids", "Fluid Mechanics", 80,
                  "Pressure, buoyancy, continuity and Bernoulli's principle.",
                  ("Fluids", "Fluid Mechanics", "Pressure", "Buoyancy"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("thermal", "Thermal Physics", 90,
                  "Temperature, heat, thermal expansion and calorimetry.",
                  ("Thermal Physics", "Heat", "Temperature"),
                  level_range=("junior_high", "intro_university")),
    PhysicsDomain("thermodynamics", "Thermodynamics", 100,
                  "The laws of thermodynamics, gas processes and engines.",
                  ("Thermodynamics", "Gas Laws", "Heat Engines"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("waves", "Waves", 110,
                  "Wave motion, superposition, standing waves and resonance.",
                  ("Waves", "Wave Motion", "Oscillations"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("sound", "Sound", 120,
                  "Sound waves, intensity, the Doppler effect and acoustics.",
                  ("Sound", "Acoustics"),
                  level_range=("senior_high", "intermediate_university")),
    PhysicsDomain("optics", "Optics", 130,
                  "Reflection, refraction, lenses, mirrors and wave optics.",
                  ("Optics", "Geometric Optics", "Wave Optics", "Light"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("electrostatics", "Electrostatics", 140,
                  "Charge, Coulomb's law, electric field and electric potential.",
                  ("Electrostatics", "Electric Field", "Electric Potential", "Charge"),
                  level_range=("senior_high", "intermediate_university")),
    PhysicsDomain("circuits", "Electric Circuits", 150,
                  "Current, voltage, resistance, Ohm's law and circuit analysis.",
                  ("Circuits", "Electric Circuits", "Current", "Resistance"),
                  level_range=("senior_high", "intermediate_university")),
    PhysicsDomain("magnetism", "Magnetism", 160,
                  "Magnetic fields, forces on charges and currents.",
                  ("Magnetism", "Magnetic Field"),
                  level_range=("senior_high", "intermediate_university")),
    PhysicsDomain("electromagnetism", "Electromagnetism", 170,
                  "Electromagnetic induction, Faraday's and Lenz's laws, EM waves.",
                  ("Electromagnetism", "Electromagnetic Induction"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("relativity", "Special Relativity", 180,
                  "Time dilation, length contraction and mass-energy equivalence.",
                  ("Relativity", "Special Relativity"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("quantum", "Quantum Physics", 190,
                  "Wave-particle duality, the photoelectric effect and quantisation.",
                  ("Quantum Physics", "Quantum", "Photoelectric Effect"),
                  level_range=("senior_high", "graduate_prep")),
    PhysicsDomain("atomic", "Atomic Physics", 200,
                  "Atomic structure, spectra and energy levels.",
                  ("Atomic Physics", "Atomic Structure"),
                  level_range=("senior_high", "advanced_undergraduate")),
    PhysicsDomain("nuclear", "Nuclear Physics", 210,
                  "Radioactive decay, half-life, fission and fusion.",
                  ("Nuclear Physics", "Nuclear Decay"),
                  level_range=("senior_high", "intermediate_university")),
    PhysicsDomain("particle", "Particle Physics", 220,
                  "Fundamental particles, the Standard Model and interactions.",
                  ("Particle Physics",),
                  level_range=("intro_university", "graduate_prep")),
    PhysicsDomain("astrophysics", "Astrophysics and Space Physics", 230,
                  "Stars, gravitation on cosmic scales, cosmology.",
                  ("Astrophysics", "Space Physics", "Cosmology"),
                  level_range=("junior_high", "advanced_undergraduate")),
    PhysicsDomain("other", "Other", 999,
                  "Concepts not yet mapped to a curriculum domain.", (),
                  level_range=("discovery", "graduate_prep")),
)

_BY_KEY: dict[str, PhysicsDomain] = {d.key: d for d in _DOMAINS}
_TOPIC_TO_DOMAIN: dict[str, PhysicsDomain] = {}
for _d in _DOMAINS:
    for _t in _d.topics:
        _TOPIC_TO_DOMAIN[_t.strip().casefold()] = _d

OTHER = _BY_KEY["other"]


def all_domains(include_other: bool = True) -> tuple[PhysicsDomain, ...]:
    ordered = tuple(sorted(_DOMAINS, key=lambda d: d.order))
    return ordered if include_other else tuple(d for d in ordered if d.key != "other")


def get_domain(key) -> PhysicsDomain | None:
    if not isinstance(key, str):
        return None
    return _BY_KEY.get(key.strip().casefold())


def domain_for_topic(topic) -> PhysicsDomain:
    """The domain a ``PhysicsConcept.topic`` rolls up into. Never raises."""

    if not isinstance(topic, str) or not topic.strip():
        return OTHER
    return _TOPIC_TO_DOMAIN.get(topic.strip().casefold(), OTHER)
