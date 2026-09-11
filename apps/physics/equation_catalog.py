"""Display-only Physics equation metadata.

An ``Equation`` here is a **description** of a relationship -- a rendered
expression, its variables, units and the conditions under which it applies. It
is used to *show* equations on the Physics Library / lab pages and to give the
AI a vocabulary of known relationships.

It is NEVER executed. Physics numbers are computed by the explicit deterministic
functions in ``simulations.py`` / ``simulations_kinematics.py`` and validated on
the server. There is no ``eval``/``exec``/``Function`` anywhere near this data,
and no equation string is ever run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Equation:
    key: str
    name: str
    expression: str           # human-readable, for display only
    variables: dict           # symbol -> plain-language meaning
    units: dict                # symbol -> SI unit
    concept_slugs: tuple[str, ...]
    domain_key: str
    conditions: str = ""


_EQUATIONS: tuple[Equation, ...] = (
    Equation(
        key="kinematics-velocity",
        name="Velocity under constant acceleration",
        expression="v = v0 + a t",
        variables={"v": "final velocity", "v0": "initial velocity",
                   "a": "acceleration", "t": "elapsed time"},
        units={"v": "m/s", "v0": "m/s", "a": "m/s^2", "t": "s"},
        concept_slugs=("velocity", "acceleration"),
        domain_key="kinematics",
        conditions="Straight-line motion with constant acceleration.",
    ),
    Equation(
        key="kinematics-position",
        name="Position under constant acceleration",
        expression="x = x0 + v0 t + 1/2 a t^2",
        variables={"x": "position", "x0": "initial position", "v0": "initial velocity",
                   "a": "acceleration", "t": "elapsed time"},
        units={"x": "m", "x0": "m", "v0": "m/s", "a": "m/s^2", "t": "s"},
        concept_slugs=("displacement", "position", "velocity", "acceleration"),
        domain_key="kinematics",
        conditions="Straight-line motion with constant acceleration.",
    ),
    Equation(
        key="kinematics-average-velocity",
        name="Average velocity",
        expression="v_avg = (x2 - x1) / (t2 - t1)",
        variables={"v_avg": "average velocity", "x1": "start position", "x2": "end position",
                   "t1": "start time", "t2": "end time"},
        units={"v_avg": "m/s", "x1": "m", "x2": "m", "t1": "s", "t2": "s"},
        concept_slugs=("velocity", "displacement"),
        domain_key="kinematics",
        conditions="Over any interval; equals instantaneous velocity only for constant velocity.",
    ),
    Equation(
        key="newtons-second-law",
        name="Newton's second law",
        expression="F_net = m a",
        variables={"F_net": "net force", "m": "mass", "a": "acceleration"},
        units={"F_net": "N", "m": "kg", "a": "m/s^2"},
        concept_slugs=("force", "newtons-second-law", "acceleration"),
        domain_key="dynamics",
        conditions="Inertial reference frame; m constant.",
    ),
    Equation(
        key="kinetic-energy",
        name="Kinetic energy",
        expression="KE = 1/2 m v^2",
        variables={"KE": "kinetic energy", "m": "mass", "v": "speed"},
        units={"KE": "J", "m": "kg", "v": "m/s"},
        concept_slugs=("kinetic-energy",),
        domain_key="energy",
    ),
    Equation(
        key="work-done-by-force",
        name="Work done by a constant force",
        expression="W = F d cos(theta)",
        variables={"W": "work", "F": "force magnitude", "d": "displacement magnitude",
                   "theta": "angle between force and displacement"},
        units={"W": "J", "F": "N", "d": "m", "theta": "degrees"},
        concept_slugs=("work-done-by-a-force",),
        domain_key="energy",
    ),
    Equation(
        key="gravitational-potential-energy",
        name="Gravitational potential energy (near a surface)",
        expression="PE = m g h",
        variables={"PE": "potential energy", "m": "mass", "g": "gravitational field strength",
                   "h": "height above the reference level"},
        units={"PE": "J", "m": "kg", "g": "m/s^2", "h": "m"},
        concept_slugs=("gravitational-potential-energy",),
        domain_key="energy",
        conditions="Uniform gravitational field (g approximately constant over h).",
    ),
    Equation(
        key="power",
        name="Power",
        expression="P = W / t",
        variables={"P": "power", "W": "work (or energy transferred)", "t": "elapsed time"},
        units={"P": "W", "W": "J", "t": "s"},
        concept_slugs=("power",),
        domain_key="energy",
    ),
    Equation(
        key="momentum",
        name="Linear momentum",
        expression="p = m v",
        variables={"p": "momentum", "m": "mass", "v": "velocity"},
        units={"p": "kg m/s", "m": "kg", "v": "m/s"},
        concept_slugs=("impulse-and-momentum", "conservation-of-momentum"),
        domain_key="momentum",
    ),
    Equation(
        key="impulse-momentum-theorem",
        name="Impulse-momentum theorem",
        expression="J = F t = delta p",
        variables={"J": "impulse", "F": "net force", "t": "time interval",
                   "delta p": "change in momentum"},
        units={"J": "N s", "F": "N", "t": "s", "delta p": "kg m/s"},
        concept_slugs=("impulse-and-momentum",),
        domain_key="momentum",
    ),
    Equation(
        key="centripetal-force",
        name="Centripetal force",
        expression="F_c = m v^2 / r",
        variables={"F_c": "centripetal force", "m": "mass", "v": "speed",
                   "r": "radius of the circular path"},
        units={"F_c": "N", "m": "kg", "v": "m/s", "r": "m"},
        concept_slugs=("centripetal-force",),
        domain_key="rotation",
        conditions="Uniform circular motion.",
    ),
    Equation(
        key="torque",
        name="Torque",
        expression="tau = r F sin(theta)",
        variables={"tau": "torque", "r": "lever arm length", "F": "applied force",
                   "theta": "angle between r and F"},
        units={"tau": "N m", "r": "m", "F": "N", "theta": "degrees"},
        concept_slugs=("torque",),
        domain_key="rotation",
    ),
    Equation(
        key="newtons-law-of-gravitation",
        name="Newton's law of universal gravitation",
        expression="F = G m1 m2 / r^2",
        variables={"F": "gravitational force", "G": "gravitational constant",
                   "m1": "first mass", "m2": "second mass", "r": "distance between centres"},
        units={"F": "N", "G": "N m^2/kg^2", "m1": "kg", "m2": "kg", "r": "m"},
        concept_slugs=("newtons-law-of-universal-gravitation",),
        domain_key="gravitation",
    ),
    Equation(
        key="buoyant-force",
        name="Archimedes' principle",
        expression="F_b = rho g V",
        variables={"F_b": "buoyant force", "rho": "fluid density", "g": "gravitational field strength",
                   "V": "displaced fluid volume"},
        units={"F_b": "N", "rho": "kg/m^3", "g": "m/s^2", "V": "m^3"},
        concept_slugs=("archimedes-principle-and-buoyancy",),
        domain_key="fluids",
    ),
    Equation(
        key="fluid-pressure",
        name="Pressure",
        expression="P = F / A",
        variables={"P": "pressure", "F": "force applied perpendicular to the surface",
                   "A": "surface area"},
        units={"P": "Pa", "F": "N", "A": "m^2"},
        concept_slugs=("pressure-in-fluids",),
        domain_key="fluids",
    ),
    Equation(
        key="ideal-gas-law",
        name="Ideal gas law",
        expression="P V = n R T",
        variables={"P": "pressure", "V": "volume", "n": "amount of substance",
                   "R": "gas constant", "T": "absolute temperature"},
        units={"P": "Pa", "V": "m^3", "n": "mol", "R": "J/(mol K)", "T": "K"},
        concept_slugs=("the-ideal-gas-law",),
        domain_key="thermodynamics",
        conditions="Ideal-gas approximation.",
    ),
    Equation(
        key="wave-speed",
        name="Wave speed",
        expression="v = f lambda",
        variables={"v": "wave speed", "f": "frequency", "lambda": "wavelength"},
        units={"v": "m/s", "f": "Hz", "lambda": "m"},
        concept_slugs=("wave-properties-wavelength-frequency-and-amplitude",),
        domain_key="waves",
    ),
    Equation(
        key="snells-law",
        name="Snell's law of refraction",
        expression="n1 sin(theta1) = n2 sin(theta2)",
        variables={"n1": "refractive index of the first medium", "n2": "refractive index of the second medium",
                   "theta1": "angle of incidence", "theta2": "angle of refraction"},
        units={"n1": "unitless", "n2": "unitless", "theta1": "degrees", "theta2": "degrees"},
        concept_slugs=("refraction-and-snells-law",),
        domain_key="optics",
    ),
    Equation(
        key="thin-lens-equation",
        name="Thin lens equation",
        expression="1/f = 1/d_o + 1/d_i",
        variables={"f": "focal length", "d_o": "object distance", "d_i": "image distance"},
        units={"f": "m", "d_o": "m", "d_i": "m"},
        concept_slugs=("lenses-and-image-formation",),
        domain_key="optics",
        conditions="Thin-lens, paraxial-ray approximation.",
    ),
    Equation(
        key="coulombs-law",
        name="Coulomb's law",
        expression="F = k q1 q2 / r^2",
        variables={"F": "electrostatic force", "k": "Coulomb's constant",
                   "q1": "first charge", "q2": "second charge", "r": "distance between charges"},
        units={"F": "N", "k": "N m^2/C^2", "q1": "C", "q2": "C", "r": "m"},
        concept_slugs=("electric-charge-and-coulombs-law",),
        domain_key="electrostatics",
    ),
    Equation(
        key="electric-field",
        name="Electric field",
        expression="E = F / q",
        variables={"E": "electric field", "F": "force on a test charge", "q": "test charge"},
        units={"E": "N/C", "F": "N", "q": "C"},
        concept_slugs=("electric-field",),
        domain_key="electrostatics",
    ),
    Equation(
        key="ohms-law",
        name="Ohm's law",
        expression="V = I R",
        variables={"V": "voltage", "I": "current", "R": "resistance"},
        units={"V": "V", "I": "A", "R": "ohm"},
        concept_slugs=("ohms-law-and-resistance",),
        domain_key="circuits",
        conditions="Ohmic (linear) resistors.",
    ),
    Equation(
        key="electric-power",
        name="Electric power",
        expression="P = I V",
        variables={"P": "power", "I": "current", "V": "voltage"},
        units={"P": "W", "I": "A", "V": "V"},
        concept_slugs=("electric-power-in-circuits",),
        domain_key="circuits",
    ),
    Equation(
        key="faradays-law",
        name="Faraday's law of induction",
        expression="EMF = -N (delta Phi / delta t)",
        variables={"EMF": "induced electromotive force", "N": "number of loops",
                   "delta Phi": "change in magnetic flux", "delta t": "time interval"},
        units={"EMF": "V", "N": "unitless", "delta Phi": "Wb", "delta t": "s"},
        concept_slugs=("electromagnetic-induction-and-faradays-law",),
        domain_key="electromagnetism",
    ),
    Equation(
        key="time-dilation",
        name="Time dilation",
        expression="delta t = delta t0 / sqrt(1 - v^2/c^2)",
        variables={"delta t": "time interval measured by a stationary observer",
                   "delta t0": "proper time (measured in the moving frame)",
                   "v": "relative speed", "c": "speed of light"},
        units={"delta t": "s", "delta t0": "s", "v": "m/s", "c": "m/s"},
        concept_slugs=("time-dilation",),
        domain_key="relativity",
        conditions="Special relativity, inertial reference frames.",
    ),
    Equation(
        key="mass-energy-equivalence",
        name="Mass-energy equivalence",
        expression="E = m c^2",
        variables={"E": "rest energy", "m": "mass", "c": "speed of light"},
        units={"E": "J", "m": "kg", "c": "m/s"},
        concept_slugs=("mass-energy-equivalence",),
        domain_key="relativity",
    ),
    Equation(
        key="photoelectric-effect",
        name="Photoelectric effect",
        expression="KE_max = h f - phi",
        variables={"KE_max": "maximum kinetic energy of an emitted electron", "h": "Planck's constant",
                   "f": "frequency of incident light", "phi": "work function of the material"},
        units={"KE_max": "J", "h": "J s", "f": "Hz", "phi": "J"},
        concept_slugs=("the-photoelectric-effect",),
        domain_key="quantum",
        conditions="f above the material's threshold frequency.",
    ),
    Equation(
        key="radioactive-decay",
        name="Radioactive decay and half-life",
        expression="N = N0 (1/2)^(t / T_half)",
        variables={"N": "remaining quantity", "N0": "initial quantity",
                   "t": "elapsed time", "T_half": "half-life"},
        units={"N": "count or mass", "N0": "count or mass", "t": "s", "T_half": "s"},
        concept_slugs=("half-life", "radioactive-decay"),
        domain_key="nuclear",
    ),
)

_BY_KEY = {e.key: e for e in _EQUATIONS}


def all_equations() -> tuple[Equation, ...]:
    return _EQUATIONS


def get_equation(key) -> Equation | None:
    if not isinstance(key, str):
        return None
    return _BY_KEY.get(key)


def equations_for_concept(slug) -> tuple[Equation, ...]:
    if not isinstance(slug, str):
        return ()
    s = slug.strip().casefold()
    return tuple(e for e in _EQUATIONS if s in tuple(x.casefold() for x in e.concept_slugs))
