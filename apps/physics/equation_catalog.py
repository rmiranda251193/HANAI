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
