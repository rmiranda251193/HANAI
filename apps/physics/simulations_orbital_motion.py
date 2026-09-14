"""Deterministic reference model for the Orbital Motion lab.

A small body in a stable circular orbit around a much more massive central
body. Gravity supplies exactly the centripetal force the orbit needs
(G*M*m/r^2 = m*v^2/r), which fixes the orbital speed and period once the
orbital radius and the central body's "gravitational parameter"
mu = G*M are chosen:

    v = sqrt(mu / r)                    (orbital speed, constant)
    T = 2*pi*sqrt(r^3 / mu)             (orbital period -- Kepler's third law)
    omega = 2*pi / T = sqrt(mu / r^3)   (angular speed)
    a_g = mu / r^2 = v^2 / r            (gravitational/centripetal acceleration,
                                          constant in magnitude, always pointing
                                          from the orbiting body toward the
                                          central body -- the same v^2/r shape
                                          as Circular Motion's centripetal
                                          acceleration, since gravity here
                                          plays exactly that role)

    x(t) = r*cos(omega*t), y(t) = r*sin(omega*t)   (same shape as uniform
                                                      circular motion --
                                                      an orbit IS circular
                                                      motion, with gravity
                                                      as the centripetal
                                                      force instead of a
                                                      string or a track)

``mu`` is expressed in scaled, friendly units here (not Earth's real
mu = G*M_earth =~ 3.986e14 m^3/s^2) so the lab's sliders stay in the same
"small, readable numbers" range as every other lab -- this is an idealized
world, not a claim about any specific real planet.

Mirrors ``simulations_circular_motion.py`` closely (an orbit and a string-
swung object share the same x(t)/y(t)/speed shape; only how the angular
speed is derived differs). This module is the single source of truth for
the mathematics, the browser simulation in
``static/js/physics/orbital-motion.js`` mirrors it exactly for live
interaction, and nothing here ever touches an AI provider -- every value is
computed from first principles.
"""

from __future__ import annotations

import math

# UI-facing bounds, in scaled SI-shaped units. Kept in sync with the JS module.
MIN_MU = 50.0
MAX_MU = 2000.0
MIN_RADIUS_M = 1.0
MAX_RADIUS_M = 10.0

MIN_TIME_S = 0.0
MAX_TIME_S = 60.0

DEFAULT_MU = 500.0
DEFAULT_RADIUS_M = 5.0


class SimulationError(ValueError):
    """A simulation input was outside the physically or numerically valid range."""


def _as_float(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SimulationError(f"{label} must be a number.")
    if math.isnan(number) or math.isinf(number):
        raise SimulationError(f"{label} must be a finite number.")
    return number


def clamp_mu(value) -> float:
    """Validate and clamp the gravitational parameter. Non-positive is
    rejected outright -- there is no such thing as negative gravity here."""

    number = _as_float(value, "Gravitational parameter")
    if number <= 0:
        raise SimulationError("Gravitational parameter must be positive.")
    return max(MIN_MU, min(MAX_MU, number))


def clamp_radius(value) -> float:
    """Validate and clamp the orbital radius. Non-positive is rejected
    outright -- there is no orbit at zero or negative radius."""

    number = _as_float(value, "Orbital radius")
    if number <= 0:
        raise SimulationError("Orbital radius must be positive.")
    return max(MIN_RADIUS_M, min(MAX_RADIUS_M, number))


def clamp_time(value) -> float:
    """Validate and clamp simulated time. Negative time is rejected outright."""

    number = _as_float(value, "Time")
    if number < 0:
        raise SimulationError("Time cannot be negative.")
    return max(MIN_TIME_S, min(MAX_TIME_S, number))


def orbital_motion_state(*, mu, radius, time) -> dict:
    """Return the orbiting body's position/velocity/period at ``time``
    seconds into a stable circular orbit.

    Pure: no database writes, no randomness. Inputs are clamped to the
    supported UI range first so the result is always well-defined."""

    m = clamp_mu(mu)
    r = clamp_radius(radius)
    t = clamp_time(time)

    speed = math.sqrt(m / r)
    period = 2.0 * math.pi * math.sqrt((r ** 3) / m)
    omega = 2.0 * math.pi / period
    theta = omega * t
    gravitational_acceleration = m / (r ** 2)

    x = r * math.cos(theta)
    y = r * math.sin(theta)
    vx = -speed * math.sin(theta)
    vy = speed * math.cos(theta)

    return {
        "position_x_m": x,
        "position_y_m": y,
        "velocity_x_m_s": vx,
        "velocity_y_m_s": vy,
        "speed_m_s": speed,
        "period_s": period,
        "gravitational_acceleration_m_s2": gravitational_acceleration,
    }


# --- registry entry ------------------------------------------------------

from .simulation_registry import SimulationDefinition, register  # noqa: E402

register(
    SimulationDefinition(
        simulation_type="orbital_motion",
        template="physics/orbital_motion.html",
        equations=(
            "v = sqrt(mu / r)",
            "T = 2*pi*sqrt(r^3 / mu)  (Kepler's third law)",
            "a_g = mu / r^2",
        ),
        units={
            "mu": "m³/s²",
            "radius_m": "m",
            "time_s": "s",
            "position_x_m": "m",
            "position_y_m": "m",
            "speed_m_s": "m/s",
            "period_s": "s",
            "gravitational_acceleration_m_s2": "m/s²",
        },
        bounds={
            "mu": (MIN_MU, MAX_MU),
            "radius_m": (MIN_RADIUS_M, MAX_RADIUS_M),
            "time_s": (MIN_TIME_S, MAX_TIME_S),
        },
        default_state={
            "mu": DEFAULT_MU,
            "radius_m": DEFAULT_RADIUS_M,
        },
        input_fields=(
            "mu",
            "radius_m",
            "time_s",
        ),
    )
)
