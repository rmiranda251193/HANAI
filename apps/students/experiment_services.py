"""Turn Physics Lab interaction into explicit, meaningful learning evidence.

A simulation action is not automatically learning evidence. Nothing here is
recorded for a slider move. Evidence is written only at the four learning
moments: prediction, observation, explanation, and the tutor turn that follows.

Every physical value is recomputed on the server with the deterministic model
(a = F / m). The browser's acceleration is never trusted.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.physics.simulations import (
    MAX_FORCE_N,
    MAX_MASS_KG,
    clamp_force,
    clamp_mass,
    newtons_second_law_acceleration,
)
from apps.physics.simulations_kinematics import (
    MAX_ACCELERATION_MS2,
    MAX_INITIAL_POSITION_M,
    MAX_INITIAL_VELOCITY_MS,
    MAX_TIME_S,
    clamp_acceleration,
    clamp_initial_position,
    clamp_initial_velocity,
    clamp_time,
    kinematics_state,
)
from apps.physics.simulations_projectile import (
    MAX_INITIAL_HEIGHT_M,
    MAX_INITIAL_SPEED_MS,
    MAX_LAUNCH_ANGLE_DEG,
)
from apps.physics.simulations_projectile import MAX_TIME_S as PROJECTILE_MAX_TIME_S
from apps.physics.simulations_projectile import (
    clamp_initial_height,
    clamp_initial_speed,
    clamp_launch_angle,
)
from apps.physics.simulations_projectile import clamp_time as clamp_projectile_time
from apps.physics.simulations_projectile import projectile_state
from apps.physics.simulations_circular_motion import (
    MAX_PERIOD_S,
    MAX_RADIUS_M,
)
from apps.physics.simulations_circular_motion import MAX_TIME_S as CIRCULAR_MAX_TIME_S
from apps.physics.simulations_circular_motion import clamp_period, clamp_radius
from apps.physics.simulations_circular_motion import clamp_time as clamp_circular_time
from apps.physics.simulations_circular_motion import circular_motion_state
from apps.physics.simulations_shm import (
    MAX_AMPLITUDE_M,
    MAX_PERIOD_S as SHM_MAX_PERIOD_S,
)
from apps.physics.simulations_shm import MAX_TIME_S as SHM_MAX_TIME_S
from apps.physics.simulations_shm import clamp_amplitude
from apps.physics.simulations_shm import clamp_period as clamp_shm_period
from apps.physics.simulations_shm import clamp_time as clamp_shm_time
from apps.physics.simulations_shm import shm_state
from apps.physics.simulations_collision import (
    MAX_INITIAL_VELOCITY_MS as COLLISION_MAX_VELOCITY_MS,
    MAX_MASS_KG as COLLISION_MAX_MASS_KG,
)
from apps.physics.simulations_collision import MAX_TIME_S as COLLISION_MAX_TIME_S
from apps.physics.simulations_collision import clamp_elastic, clamp_mass as clamp_collision_mass
from apps.physics.simulations_collision import clamp_initial_velocity as clamp_collision_velocity
from apps.physics.simulations_collision import clamp_time as clamp_collision_time
from apps.physics.simulations_collision import collision_state
from apps.physics.simulations_energy_incline import (
    MAX_ANGLE_DEG as ENERGY_MAX_ANGLE_DEG,
    MAX_HEIGHT_M as ENERGY_MAX_HEIGHT_M,
    MAX_MASS_KG as ENERGY_MAX_MASS_KG,
)
from apps.physics.simulations_energy_incline import MAX_TIME_S as ENERGY_MAX_TIME_S
from apps.physics.simulations_energy_incline import clamp_angle as clamp_energy_angle
from apps.physics.simulations_energy_incline import clamp_height as clamp_energy_height
from apps.physics.simulations_energy_incline import clamp_mass as clamp_energy_mass
from apps.physics.simulations_energy_incline import clamp_time as clamp_energy_time
from apps.physics.simulations_energy_incline import energy_incline_state
from apps.physics.simulations_orbital_motion import (
    MAX_MU as ORBITAL_MAX_MU,
    MAX_RADIUS_M as ORBITAL_MAX_RADIUS_M,
)
from apps.physics.simulations_orbital_motion import MAX_TIME_S as ORBITAL_MAX_TIME_S
from apps.physics.simulations_orbital_motion import clamp_mu, clamp_radius as clamp_orbital_radius
from apps.physics.simulations_orbital_motion import clamp_time as clamp_orbital_time
from apps.physics.simulations_orbital_motion import orbital_motion_state
from apps.physics.simulations_circuits import (
    MAX_RESISTANCE_OHM as CIRCUIT_MAX_RESISTANCE_OHM,
    MAX_VOLTAGE_V as CIRCUIT_MAX_VOLTAGE_V,
)
from apps.physics.simulations_circuits import circuit_state
from apps.physics.simulations_circuits import clamp_resistance, clamp_series, clamp_voltage
from apps.physics.simulations_coulombs_law import MAX_SEPARATION_M as COULOMB_MAX_SEPARATION_M
from apps.physics.simulations_coulombs_law import coulombs_law_state
from apps.physics.simulations_coulombs_law import clamp_charge, clamp_separation
from apps.physics.simulations_radioactive_decay import (
    MAX_HALF_LIFE_S as DECAY_MAX_HALF_LIFE_S,
    MAX_INITIAL_COUNT as DECAY_MAX_INITIAL_COUNT,
)
from apps.physics.simulations_radioactive_decay import MAX_TIME_S as DECAY_MAX_TIME_S
from apps.physics.simulations_radioactive_decay import clamp_half_life, clamp_initial_count
from apps.physics.simulations_radioactive_decay import clamp_time as clamp_decay_time
from apps.physics.simulations_radioactive_decay import radioactive_decay_state
from apps.physics.simulations_buoyancy import MAX_DENSITY_KG_M3 as BUOYANCY_MAX_DENSITY_KG_M3
from apps.physics.simulations_buoyancy import MAX_VOLUME_M3 as BUOYANCY_MAX_VOLUME_M3
from apps.physics.simulations_buoyancy import buoyancy_state
from apps.physics.simulations_buoyancy import clamp_density, clamp_volume
from apps.physics.simulations_refraction import MAX_ANGLE_DEG as REFRACTION_MAX_ANGLE_DEG
from apps.physics.simulations_refraction import MAX_INDEX as REFRACTION_MAX_INDEX
from apps.physics.simulations_refraction import clamp_angle as clamp_refraction_angle
from apps.physics.simulations_refraction import clamp_index, refraction_state
from apps.physics.simulations_calorimetry import (
    MAX_MASS_KG as CALORIMETRY_MAX_MASS_KG,
    MAX_SPECIFIC_HEAT as CALORIMETRY_MAX_SPECIFIC_HEAT,
)
from apps.physics.simulations_calorimetry import calorimetry_state
from apps.physics.simulations_calorimetry import clamp_mass as clamp_calorimetry_mass
from apps.physics.simulations_calorimetry import clamp_specific_heat, clamp_temp

from .misconception_services import assess_student_misconceptions
from .models import ExperimentAttempt, LearningEvidence

logger = logging.getLogger(__name__)

# Anything past these is a nonsense submission, not a slider value -> reject.
MASS_HARD_MAX_KG = MAX_MASS_KG * 5
FORCE_HARD_MAX_N = MAX_FORCE_N * 5
FORCE_HARD_MIN_N = -1.0

POSITION_HARD_MAX_M = MAX_INITIAL_POSITION_M * 5
VELOCITY_HARD_MAX_MS = MAX_INITIAL_VELOCITY_MS * 5
ACCELERATION_HARD_MAX_MS2 = MAX_ACCELERATION_MS2 * 5
TIME_HARD_MAX_S = MAX_TIME_S * 5

SPEED_HARD_MAX_MS = MAX_INITIAL_SPEED_MS * 5
ANGLE_HARD_MAX_DEG = 360.0
HEIGHT_HARD_MAX_M = MAX_INITIAL_HEIGHT_M * 5
PROJECTILE_TIME_HARD_MAX_S = PROJECTILE_MAX_TIME_S * 5

RADIUS_HARD_MAX_M = MAX_RADIUS_M * 5
PERIOD_HARD_MAX_S = MAX_PERIOD_S * 5
CIRCULAR_TIME_HARD_MAX_S = CIRCULAR_MAX_TIME_S * 5

AMPLITUDE_HARD_MAX_M = MAX_AMPLITUDE_M * 5
SHM_PERIOD_HARD_MAX_S = SHM_MAX_PERIOD_S * 5
SHM_TIME_HARD_MAX_S = SHM_MAX_TIME_S * 5

COLLISION_MASS_HARD_MAX_KG = COLLISION_MAX_MASS_KG * 5
COLLISION_VELOCITY_HARD_MAX_MS = COLLISION_MAX_VELOCITY_MS * 5
COLLISION_TIME_HARD_MAX_S = COLLISION_MAX_TIME_S * 5

ENERGY_HEIGHT_HARD_MAX_M = ENERGY_MAX_HEIGHT_M * 5
ENERGY_ANGLE_HARD_MAX_DEG = 90.0
ENERGY_MASS_HARD_MAX_KG = ENERGY_MAX_MASS_KG * 5
ENERGY_TIME_HARD_MAX_S = ENERGY_MAX_TIME_S * 5

ORBITAL_MU_HARD_MAX = ORBITAL_MAX_MU * 5
ORBITAL_RADIUS_HARD_MAX_M = ORBITAL_MAX_RADIUS_M * 5
ORBITAL_TIME_HARD_MAX_S = ORBITAL_MAX_TIME_S * 5

CIRCUIT_VOLTAGE_HARD_MAX_V = CIRCUIT_MAX_VOLTAGE_V * 5
CIRCUIT_RESISTANCE_HARD_MAX_OHM = CIRCUIT_MAX_RESISTANCE_OHM * 5

COULOMB_CHARGE_HARD_MAX_UC = 40.0  # 5x the UI bound magnitude (+-8 uC)
COULOMB_SEPARATION_HARD_MAX_M = COULOMB_MAX_SEPARATION_M * 5

DECAY_INITIAL_COUNT_HARD_MAX = DECAY_MAX_INITIAL_COUNT * 5
DECAY_HALF_LIFE_HARD_MAX_S = DECAY_MAX_HALF_LIFE_S * 5
DECAY_TIME_HARD_MAX_S = DECAY_MAX_TIME_S * 5

BUOYANCY_DENSITY_HARD_MAX_KG_M3 = BUOYANCY_MAX_DENSITY_KG_M3 * 5
BUOYANCY_VOLUME_HARD_MAX_M3 = BUOYANCY_MAX_VOLUME_M3 * 5

REFRACTION_INDEX_HARD_MAX = REFRACTION_MAX_INDEX * 5
REFRACTION_ANGLE_HARD_MAX_DEG = 90.0  # angles clamp at 89 deg; 90+ is meaningless here

CALORIMETRY_MASS_HARD_MAX_KG = CALORIMETRY_MAX_MASS_KG * 5
CALORIMETRY_SPECIFIC_HEAT_HARD_MAX = CALORIMETRY_MAX_SPECIFIC_HEAT * 5
CALORIMETRY_TEMP_HARD_MAX_C = 1000.0  # generous vs the -20..300 UI range

TEXT_LIMIT = 2000


class ExperimentValidationError(ValueError):
    """A submitted experiment value or text was missing or invalid."""


@dataclass(frozen=True)
class ValidatedNewtonsSecondLaw:
    """Server-recomputed, deterministic experiment values (SI units)."""

    mass_kg: float
    force_n: float
    acceleration_m_s2: float

    def as_dict(self) -> dict:
        return {
            "mass_kg": self.mass_kg,
            "force_n": self.force_n,
            "acceleration_m_s2": self.acceleration_m_s2,
        }


def validate_newtons_second_law(mass_kg, force_n) -> ValidatedNewtonsSecondLaw:
    """Recompute a = F / m on the server. Reject nonsense; clamp to lab bounds."""

    try:
        mass_raw = float(mass_kg)
        force_raw = float(force_n)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Mass and net force must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (mass_raw, force_raw)):
        raise ExperimentValidationError("Mass and net force must be finite numbers.")
    if mass_raw <= 0:
        raise ExperimentValidationError("Mass must be greater than zero (kg).")
    if (
        mass_raw > MASS_HARD_MAX_KG
        or force_raw > FORCE_HARD_MAX_N
        or force_raw < FORCE_HARD_MIN_N
    ):
        raise ExperimentValidationError(
            "Those values are outside the simulation's range."
        )

    mass = clamp_mass(mass_raw)
    force = clamp_force(force_raw)
    acceleration = newtons_second_law_acceleration(force, mass)
    return ValidatedNewtonsSecondLaw(
        mass_kg=mass, force_n=force, acceleration_m_s2=acceleration
    )


@dataclass(frozen=True)
class ValidatedKinematics:
    """Server-recomputed, deterministic Kinematics values (SI units)."""

    initial_position_m: float
    initial_velocity_m_s: float
    acceleration_m_s2: float
    time_s: float
    position_m: float
    velocity_m_s: float

    def as_dict(self) -> dict:
        return {
            "initial_position_m": self.initial_position_m,
            "initial_velocity_m_s": self.initial_velocity_m_s,
            "acceleration_m_s2": self.acceleration_m_s2,
            "time_s": self.time_s,
            "position_m": self.position_m,
            "velocity_m_s": self.velocity_m_s,
        }


def validate_kinematics(
    initial_position_m, initial_velocity_m_s, acceleration_m_s2, time_s
) -> ValidatedKinematics:
    """Recompute position/velocity on the server. Reject nonsense; clamp to lab bounds."""

    try:
        x0_raw = float(initial_position_m)
        v0_raw = float(initial_velocity_m_s)
        a_raw = float(acceleration_m_s2)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError(
            "Initial position, initial velocity, acceleration and time must be numbers."
        )

    if any(math.isnan(v) or math.isinf(v) for v in (x0_raw, v0_raw, a_raw, t_raw)):
        raise ExperimentValidationError(
            "Initial position, initial velocity, acceleration and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if (
        abs(x0_raw) > POSITION_HARD_MAX_M
        or abs(v0_raw) > VELOCITY_HARD_MAX_MS
        or abs(a_raw) > ACCELERATION_HARD_MAX_MS2
        or t_raw > TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError(
            "Those values are outside the simulation's range."
        )

    state = kinematics_state(
        initial_position=x0_raw, initial_velocity=v0_raw, acceleration=a_raw, time=t_raw
    )
    return ValidatedKinematics(
        initial_position_m=clamp_initial_position(x0_raw),
        initial_velocity_m_s=clamp_initial_velocity(v0_raw),
        acceleration_m_s2=state["acceleration_m_s2"],
        time_s=clamp_time(t_raw),
        position_m=state["position_m"],
        velocity_m_s=state["velocity_m_s"],
    )


@dataclass(frozen=True)
class ValidatedProjectileMotion:
    """Server-recomputed, deterministic Projectile Motion values (SI units)."""

    initial_speed_m_s: float
    launch_angle_deg: float
    initial_height_m: float
    time_s: float
    position_x_m: float
    position_y_m: float
    speed_m_s: float

    def as_dict(self) -> dict:
        return {
            "initial_speed_m_s": self.initial_speed_m_s,
            "launch_angle_deg": self.launch_angle_deg,
            "initial_height_m": self.initial_height_m,
            "time_s": self.time_s,
            "position_x_m": self.position_x_m,
            "position_y_m": self.position_y_m,
            "speed_m_s": self.speed_m_s,
        }


def validate_projectile_motion(
    initial_speed_m_s, launch_angle_deg, initial_height_m, time_s
) -> ValidatedProjectileMotion:
    """Recompute x/y position on the server. Reject nonsense; clamp to lab bounds."""

    try:
        v0_raw = float(initial_speed_m_s)
        angle_raw = float(launch_angle_deg)
        h0_raw = float(initial_height_m)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError(
            "Initial speed, launch angle, initial height and time must be numbers."
        )

    if any(math.isnan(v) or math.isinf(v) for v in (v0_raw, angle_raw, h0_raw, t_raw)):
        raise ExperimentValidationError(
            "Initial speed, launch angle, initial height and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if (
        v0_raw < 0
        or v0_raw > SPEED_HARD_MAX_MS
        or abs(angle_raw) > ANGLE_HARD_MAX_DEG
        or h0_raw < 0
        or h0_raw > HEIGHT_HARD_MAX_M
        or t_raw > PROJECTILE_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError(
            "Those values are outside the simulation's range."
        )

    state = projectile_state(
        initial_speed=v0_raw, launch_angle=angle_raw, initial_height=h0_raw, time=t_raw
    )
    return ValidatedProjectileMotion(
        initial_speed_m_s=clamp_initial_speed(v0_raw),
        launch_angle_deg=clamp_launch_angle(angle_raw),
        initial_height_m=clamp_initial_height(h0_raw),
        time_s=clamp_projectile_time(t_raw),
        position_x_m=state["position_x_m"],
        position_y_m=state["position_y_m"],
        speed_m_s=state["speed_m_s"],
    )


@dataclass(frozen=True)
class ValidatedCircularMotion:
    """Server-recomputed, deterministic Circular Motion values (SI units)."""

    radius_m: float
    period_s: float
    time_s: float
    position_x_m: float
    position_y_m: float
    speed_m_s: float
    centripetal_acceleration_m_s2: float

    def as_dict(self) -> dict:
        return {
            "radius_m": self.radius_m,
            "period_s": self.period_s,
            "time_s": self.time_s,
            "position_x_m": self.position_x_m,
            "position_y_m": self.position_y_m,
            "speed_m_s": self.speed_m_s,
            "centripetal_acceleration_m_s2": self.centripetal_acceleration_m_s2,
        }


def validate_circular_motion(radius_m, period_s, time_s) -> ValidatedCircularMotion:
    """Recompute position/speed/centripetal acceleration on the server.
    Reject nonsense; clamp to lab bounds."""

    try:
        r_raw = float(radius_m)
        period_raw = float(period_s)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Radius, period and time must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (r_raw, period_raw, t_raw)):
        raise ExperimentValidationError("Radius, period and time must be finite numbers.")
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if period_raw <= 0:
        raise ExperimentValidationError("Period must be positive.")
    if (
        r_raw <= 0
        or r_raw > RADIUS_HARD_MAX_M
        or period_raw > PERIOD_HARD_MAX_S
        or t_raw > CIRCULAR_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = circular_motion_state(radius=r_raw, period=period_raw, time=t_raw)
    return ValidatedCircularMotion(
        radius_m=clamp_radius(r_raw),
        period_s=clamp_period(period_raw),
        time_s=clamp_circular_time(t_raw),
        position_x_m=state["position_x_m"],
        position_y_m=state["position_y_m"],
        speed_m_s=state["speed_m_s"],
        centripetal_acceleration_m_s2=state["centripetal_acceleration_m_s2"],
    )


@dataclass(frozen=True)
class ValidatedSHM:
    """Server-recomputed, deterministic Simple Harmonic Motion values (SI units)."""

    amplitude_m: float
    period_s: float
    time_s: float
    position_m: float
    velocity_m_s: float
    acceleration_m_s2: float

    def as_dict(self) -> dict:
        return {
            "amplitude_m": self.amplitude_m,
            "period_s": self.period_s,
            "time_s": self.time_s,
            "position_m": self.position_m,
            "velocity_m_s": self.velocity_m_s,
            "acceleration_m_s2": self.acceleration_m_s2,
        }


def validate_shm(amplitude_m, period_s, time_s) -> ValidatedSHM:
    """Recompute displacement/velocity/acceleration on the server. Reject
    nonsense; clamp to lab bounds."""

    try:
        a_raw = float(amplitude_m)
        period_raw = float(period_s)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Amplitude, period and time must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (a_raw, period_raw, t_raw)):
        raise ExperimentValidationError("Amplitude, period and time must be finite numbers.")
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if period_raw <= 0:
        raise ExperimentValidationError("Period must be positive.")
    if (
        a_raw <= 0
        or a_raw > AMPLITUDE_HARD_MAX_M
        or period_raw > SHM_PERIOD_HARD_MAX_S
        or t_raw > SHM_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = shm_state(amplitude=a_raw, period=period_raw, time=t_raw)
    return ValidatedSHM(
        amplitude_m=clamp_amplitude(a_raw),
        period_s=clamp_shm_period(period_raw),
        time_s=clamp_shm_time(t_raw),
        position_m=state["position_m"],
        velocity_m_s=state["velocity_m_s"],
        acceleration_m_s2=state["acceleration_m_s2"],
    )


@dataclass(frozen=True)
class ValidatedCollision:
    """Server-recomputed, deterministic Momentum/Collision values (SI units)."""

    mass1_kg: float
    mass2_kg: float
    initial_velocity_m_s: float
    elastic: float
    time_s: float
    position_1_m: float
    position_2_m: float
    velocity_1_m_s: float
    velocity_2_m_s: float
    has_collided: bool
    collision_time_s: float
    momentum_total_kg_m_s: float
    kinetic_energy_total_j: float

    def as_dict(self) -> dict:
        return {
            "mass1_kg": self.mass1_kg,
            "mass2_kg": self.mass2_kg,
            "initial_velocity_m_s": self.initial_velocity_m_s,
            "elastic": self.elastic,
            "time_s": self.time_s,
            "position_1_m": self.position_1_m,
            "position_2_m": self.position_2_m,
            "velocity_1_m_s": self.velocity_1_m_s,
            "velocity_2_m_s": self.velocity_2_m_s,
            "has_collided": self.has_collided,
            "collision_time_s": self.collision_time_s,
            "momentum_total_kg_m_s": self.momentum_total_kg_m_s,
            "kinetic_energy_total_j": self.kinetic_energy_total_j,
        }


def validate_collision(mass1_kg, mass2_kg, initial_velocity_m_s, elastic, time_s) -> ValidatedCollision:
    """Recompute both carts' positions/velocities on the server. Reject
    nonsense; clamp to lab bounds."""

    try:
        m1_raw = float(mass1_kg)
        m2_raw = float(mass2_kg)
        v1_raw = float(initial_velocity_m_s)
        elastic_raw = float(elastic)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError(
            "Mass 1, mass 2, initial velocity, collision type and time must be numbers."
        )

    if any(math.isnan(v) or math.isinf(v) for v in (m1_raw, m2_raw, v1_raw, elastic_raw, t_raw)):
        raise ExperimentValidationError(
            "Mass 1, mass 2, initial velocity, collision type and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if v1_raw <= 0:
        raise ExperimentValidationError("Initial velocity must be positive.")
    if (
        m1_raw <= 0
        or m1_raw > COLLISION_MASS_HARD_MAX_KG
        or m2_raw <= 0
        or m2_raw > COLLISION_MASS_HARD_MAX_KG
        or v1_raw > COLLISION_VELOCITY_HARD_MAX_MS
        or t_raw > COLLISION_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = collision_state(
        mass1=m1_raw, mass2=m2_raw, initial_velocity=v1_raw, elastic=elastic_raw, time=t_raw
    )
    return ValidatedCollision(
        mass1_kg=clamp_collision_mass(m1_raw),
        mass2_kg=clamp_collision_mass(m2_raw),
        initial_velocity_m_s=clamp_collision_velocity(v1_raw),
        elastic=clamp_elastic(elastic_raw),
        time_s=clamp_collision_time(t_raw),
        position_1_m=state["position_1_m"],
        position_2_m=state["position_2_m"],
        velocity_1_m_s=state["velocity_1_m_s"],
        velocity_2_m_s=state["velocity_2_m_s"],
        has_collided=state["has_collided"],
        collision_time_s=state["collision_time_s"],
        momentum_total_kg_m_s=state["momentum_total_kg_m_s"],
        kinetic_energy_total_j=state["kinetic_energy_total_j"],
    )


@dataclass(frozen=True)
class ValidatedEnergyIncline:
    """Server-recomputed, deterministic Energy-on-an-Incline values (SI units)."""

    height_m: float
    angle_deg: float
    mass_kg: float
    time_s: float
    distance_m: float
    height_dropped_m: float
    speed_m_s: float
    kinetic_energy_j: float
    potential_energy_j: float
    total_energy_j: float

    def as_dict(self) -> dict:
        return {
            "height_m": self.height_m,
            "angle_deg": self.angle_deg,
            "mass_kg": self.mass_kg,
            "time_s": self.time_s,
            "distance_m": self.distance_m,
            "height_dropped_m": self.height_dropped_m,
            "speed_m_s": self.speed_m_s,
            "kinetic_energy_j": self.kinetic_energy_j,
            "potential_energy_j": self.potential_energy_j,
            "total_energy_j": self.total_energy_j,
        }


def validate_energy_incline(height_m, angle_deg, mass_kg, time_s) -> ValidatedEnergyIncline:
    """Recompute distance/speed/energy on the server. Reject nonsense;
    clamp to lab bounds."""

    try:
        h_raw = float(height_m)
        angle_raw = float(angle_deg)
        m_raw = float(mass_kg)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Height, angle, mass and time must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (h_raw, angle_raw, m_raw, t_raw)):
        raise ExperimentValidationError("Height, angle, mass and time must be finite numbers.")
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if angle_raw <= 0 or angle_raw >= ENERGY_ANGLE_HARD_MAX_DEG:
        raise ExperimentValidationError("Angle must be strictly between 0 and 90 degrees.")
    if (
        h_raw <= 0
        or h_raw > ENERGY_HEIGHT_HARD_MAX_M
        or m_raw <= 0
        or m_raw > ENERGY_MASS_HARD_MAX_KG
        or t_raw > ENERGY_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = energy_incline_state(height=h_raw, angle=angle_raw, mass=m_raw, time=t_raw)
    return ValidatedEnergyIncline(
        height_m=clamp_energy_height(h_raw),
        angle_deg=clamp_energy_angle(angle_raw),
        mass_kg=clamp_energy_mass(m_raw),
        time_s=clamp_energy_time(t_raw),
        distance_m=state["distance_m"],
        height_dropped_m=state["height_dropped_m"],
        speed_m_s=state["speed_m_s"],
        kinetic_energy_j=state["kinetic_energy_j"],
        potential_energy_j=state["potential_energy_j"],
        total_energy_j=state["total_energy_j"],
    )


@dataclass(frozen=True)
class ValidatedOrbitalMotion:
    """Server-recomputed, deterministic Orbital Motion values (SI-shaped units)."""

    mu: float
    radius_m: float
    time_s: float
    position_x_m: float
    position_y_m: float
    speed_m_s: float
    period_s: float
    gravitational_acceleration_m_s2: float

    def as_dict(self) -> dict:
        return {
            "mu": self.mu,
            "radius_m": self.radius_m,
            "time_s": self.time_s,
            "position_x_m": self.position_x_m,
            "position_y_m": self.position_y_m,
            "speed_m_s": self.speed_m_s,
            "period_s": self.period_s,
            "gravitational_acceleration_m_s2": self.gravitational_acceleration_m_s2,
        }


def validate_orbital_motion(mu, radius_m, time_s) -> ValidatedOrbitalMotion:
    """Recompute the orbit's position/speed/period on the server. Reject
    nonsense; clamp to lab bounds."""

    try:
        mu_raw = float(mu)
        r_raw = float(radius_m)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Gravitational parameter, radius and time must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (mu_raw, r_raw, t_raw)):
        raise ExperimentValidationError(
            "Gravitational parameter, radius and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if mu_raw <= 0:
        raise ExperimentValidationError("Gravitational parameter must be positive.")
    if r_raw <= 0:
        raise ExperimentValidationError("Orbital radius must be positive.")
    if (
        mu_raw > ORBITAL_MU_HARD_MAX
        or r_raw > ORBITAL_RADIUS_HARD_MAX_M
        or t_raw > ORBITAL_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = orbital_motion_state(mu=mu_raw, radius=r_raw, time=t_raw)
    return ValidatedOrbitalMotion(
        mu=clamp_mu(mu_raw),
        radius_m=clamp_orbital_radius(r_raw),
        time_s=clamp_orbital_time(t_raw),
        position_x_m=state["position_x_m"],
        position_y_m=state["position_y_m"],
        speed_m_s=state["speed_m_s"],
        period_s=state["period_s"],
        gravitational_acceleration_m_s2=state["gravitational_acceleration_m_s2"],
    )


@dataclass(frozen=True)
class ValidatedCircuit:
    """Server-recomputed, deterministic Series/Parallel Circuit values (SI units)."""

    voltage_v: float
    resistance1_ohm: float
    resistance2_ohm: float
    series: float
    total_resistance_ohm: float
    total_current_a: float
    current_1_a: float
    current_2_a: float
    voltage_1_v: float
    voltage_2_v: float
    power_1_w: float
    power_2_w: float
    total_power_w: float
    series_total_resistance_ohm: float
    parallel_total_resistance_ohm: float

    def as_dict(self) -> dict:
        return {
            "voltage_v": self.voltage_v,
            "resistance1_ohm": self.resistance1_ohm,
            "resistance2_ohm": self.resistance2_ohm,
            "series": self.series,
            "total_resistance_ohm": self.total_resistance_ohm,
            "total_current_a": self.total_current_a,
            "current_1_a": self.current_1_a,
            "current_2_a": self.current_2_a,
            "voltage_1_v": self.voltage_1_v,
            "voltage_2_v": self.voltage_2_v,
            "power_1_w": self.power_1_w,
            "power_2_w": self.power_2_w,
            "total_power_w": self.total_power_w,
            "series_total_resistance_ohm": self.series_total_resistance_ohm,
            "parallel_total_resistance_ohm": self.parallel_total_resistance_ohm,
        }


def validate_circuit(voltage_v, resistance1_ohm, resistance2_ohm, series) -> ValidatedCircuit:
    """Recompute the circuit's currents/voltages/power on the server. Reject
    nonsense; clamp to lab bounds. There is no time input here -- see the
    module docstring in ``simulations_circuits.py`` for why."""

    try:
        v_raw = float(voltage_v)
        r1_raw = float(resistance1_ohm)
        r2_raw = float(resistance2_ohm)
        series_raw = float(series)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Voltage, resistance and circuit type must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (v_raw, r1_raw, r2_raw, series_raw)):
        raise ExperimentValidationError(
            "Voltage, resistance and circuit type must be finite numbers."
        )
    if v_raw <= 0:
        raise ExperimentValidationError("Voltage must be positive.")
    if r1_raw <= 0 or r2_raw <= 0:
        raise ExperimentValidationError("Resistance must be positive.")
    if (
        v_raw > CIRCUIT_VOLTAGE_HARD_MAX_V
        or r1_raw > CIRCUIT_RESISTANCE_HARD_MAX_OHM
        or r2_raw > CIRCUIT_RESISTANCE_HARD_MAX_OHM
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = circuit_state(voltage=v_raw, resistance1=r1_raw, resistance2=r2_raw, series=series_raw)
    return ValidatedCircuit(
        voltage_v=clamp_voltage(v_raw),
        resistance1_ohm=clamp_resistance(r1_raw),
        resistance2_ohm=clamp_resistance(r2_raw),
        series=clamp_series(series_raw),
        total_resistance_ohm=state["total_resistance_ohm"],
        total_current_a=state["total_current_a"],
        current_1_a=state["current_1_a"],
        current_2_a=state["current_2_a"],
        voltage_1_v=state["voltage_1_v"],
        voltage_2_v=state["voltage_2_v"],
        power_1_w=state["power_1_w"],
        power_2_w=state["power_2_w"],
        total_power_w=state["total_power_w"],
        series_total_resistance_ohm=state["series_total_resistance_ohm"],
        parallel_total_resistance_ohm=state["parallel_total_resistance_ohm"],
    )


@dataclass(frozen=True)
class ValidatedCoulomb:
    """Server-recomputed, deterministic Coulomb's Law values (SI-shaped units)."""

    charge1_uc: float
    charge2_uc: float
    separation_m: float
    force_n: float
    is_attractive: bool
    potential_energy_j: float
    field_1_at_2_n_per_c: float
    field_2_at_1_n_per_c: float

    def as_dict(self) -> dict:
        return {
            "charge1_uc": self.charge1_uc,
            "charge2_uc": self.charge2_uc,
            "separation_m": self.separation_m,
            "force_n": self.force_n,
            "is_attractive": self.is_attractive,
            "potential_energy_j": self.potential_energy_j,
            "field_1_at_2_n_per_c": self.field_1_at_2_n_per_c,
            "field_2_at_1_n_per_c": self.field_2_at_1_n_per_c,
        }


def validate_coulombs_law(charge1_uc, charge2_uc, separation_m) -> ValidatedCoulomb:
    """Recompute the force/energy/field between two point charges on the
    server. Reject nonsense; clamp to lab bounds. Unlike every other
    ``validate_*`` function here, the charge inputs are NOT rejected for
    being zero or negative -- see the module docstring in
    ``simulations_coulombs_law.py`` for why that's physically correct."""

    try:
        q1_raw = float(charge1_uc)
        q2_raw = float(charge2_uc)
        r_raw = float(separation_m)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Charge and separation must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (q1_raw, q2_raw, r_raw)):
        raise ExperimentValidationError("Charge and separation must be finite numbers.")
    if r_raw <= 0:
        raise ExperimentValidationError("Separation must be positive.")
    if (
        abs(q1_raw) > COULOMB_CHARGE_HARD_MAX_UC
        or abs(q2_raw) > COULOMB_CHARGE_HARD_MAX_UC
        or r_raw > COULOMB_SEPARATION_HARD_MAX_M
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = coulombs_law_state(charge1=q1_raw, charge2=q2_raw, separation=r_raw)
    return ValidatedCoulomb(
        charge1_uc=clamp_charge(q1_raw),
        charge2_uc=clamp_charge(q2_raw),
        separation_m=clamp_separation(r_raw),
        force_n=state["force_n"],
        is_attractive=state["is_attractive"],
        potential_energy_j=state["potential_energy_j"],
        field_1_at_2_n_per_c=state["field_1_at_2_n_per_c"],
        field_2_at_1_n_per_c=state["field_2_at_1_n_per_c"],
    )


@dataclass(frozen=True)
class ValidatedDecay:
    """Server-recomputed, deterministic Radioactive Decay values."""

    initial_count: float
    half_life_s: float
    time_s: float
    remaining_count: float
    decayed_count: float
    remaining_fraction: float
    activity_per_s: float

    def as_dict(self) -> dict:
        return {
            "initial_count": self.initial_count,
            "half_life_s": self.half_life_s,
            "time_s": self.time_s,
            "remaining_count": self.remaining_count,
            "decayed_count": self.decayed_count,
            "remaining_fraction": self.remaining_fraction,
            "activity_per_s": self.activity_per_s,
        }


def validate_radioactive_decay(initial_count, half_life_s, time_s) -> ValidatedDecay:
    """Recompute the remaining/decayed count and activity on the server.
    Reject nonsense; clamp to lab bounds."""

    try:
        n0_raw = float(initial_count)
        half_life_raw = float(half_life_s)
        t_raw = float(time_s)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Initial count, half-life and time must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (n0_raw, half_life_raw, t_raw)):
        raise ExperimentValidationError(
            "Initial count, half-life and time must be finite numbers."
        )
    if t_raw < 0:
        raise ExperimentValidationError("Time cannot be negative.")
    if n0_raw <= 0:
        raise ExperimentValidationError("Initial count must be positive.")
    if half_life_raw <= 0:
        raise ExperimentValidationError("Half-life must be positive.")
    if (
        n0_raw > DECAY_INITIAL_COUNT_HARD_MAX
        or half_life_raw > DECAY_HALF_LIFE_HARD_MAX_S
        or t_raw > DECAY_TIME_HARD_MAX_S
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = radioactive_decay_state(initial_count=n0_raw, half_life=half_life_raw, time=t_raw)
    return ValidatedDecay(
        initial_count=clamp_initial_count(n0_raw),
        half_life_s=clamp_half_life(half_life_raw),
        time_s=clamp_decay_time(t_raw),
        remaining_count=state["remaining_count"],
        decayed_count=state["decayed_count"],
        remaining_fraction=state["remaining_fraction"],
        activity_per_s=state["activity_per_s"],
    )


@dataclass(frozen=True)
class ValidatedBuoyancy:
    """Server-recomputed, deterministic Buoyancy values (SI units)."""

    object_density_kg_m3: float
    fluid_density_kg_m3: float
    volume_m3: float
    weight_n: float
    buoyant_force_n: float
    submerged_fraction: float
    floats: bool
    net_force_n: float

    def as_dict(self) -> dict:
        return {
            "object_density_kg_m3": self.object_density_kg_m3,
            "fluid_density_kg_m3": self.fluid_density_kg_m3,
            "volume_m3": self.volume_m3,
            "weight_n": self.weight_n,
            "buoyant_force_n": self.buoyant_force_n,
            "submerged_fraction": self.submerged_fraction,
            "floats": self.floats,
            "net_force_n": self.net_force_n,
        }


def validate_buoyancy(object_density_kg_m3, fluid_density_kg_m3, volume_m3) -> ValidatedBuoyancy:
    """Recompute the weight/buoyant force/submerged fraction on the server.
    Reject nonsense; clamp to lab bounds. There is no time input here --
    see the module docstring in ``simulations_buoyancy.py`` for why."""

    try:
        rho_object_raw = float(object_density_kg_m3)
        rho_fluid_raw = float(fluid_density_kg_m3)
        v_raw = float(volume_m3)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Density and volume must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (rho_object_raw, rho_fluid_raw, v_raw)):
        raise ExperimentValidationError("Density and volume must be finite numbers.")
    if rho_object_raw <= 0 or rho_fluid_raw <= 0:
        raise ExperimentValidationError("Density must be positive.")
    if v_raw <= 0:
        raise ExperimentValidationError("Volume must be positive.")
    if (
        rho_object_raw > BUOYANCY_DENSITY_HARD_MAX_KG_M3
        or rho_fluid_raw > BUOYANCY_DENSITY_HARD_MAX_KG_M3
        or v_raw > BUOYANCY_VOLUME_HARD_MAX_M3
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = buoyancy_state(object_density=rho_object_raw, fluid_density=rho_fluid_raw, volume=v_raw)
    return ValidatedBuoyancy(
        object_density_kg_m3=clamp_density(rho_object_raw),
        fluid_density_kg_m3=clamp_density(rho_fluid_raw),
        volume_m3=clamp_volume(v_raw),
        weight_n=state["weight_n"],
        buoyant_force_n=state["buoyant_force_n"],
        submerged_fraction=state["submerged_fraction"],
        floats=state["floats"],
        net_force_n=state["net_force_n"],
    )


@dataclass(frozen=True)
class ValidatedRefraction:
    """Server-recomputed, deterministic Refraction (Snell's Law) values."""

    n1: float
    n2: float
    angle1_deg: float
    has_critical_angle: bool
    critical_angle_deg: float
    total_internal_reflection: bool
    angle2_deg: float

    def as_dict(self) -> dict:
        return {
            "n1": self.n1,
            "n2": self.n2,
            "angle1_deg": self.angle1_deg,
            "has_critical_angle": self.has_critical_angle,
            "critical_angle_deg": self.critical_angle_deg,
            "total_internal_reflection": self.total_internal_reflection,
            "angle2_deg": self.angle2_deg,
        }


def validate_refraction(n1, n2, angle1_deg) -> ValidatedRefraction:
    """Recompute the refracted/TIR angle on the server. Reject nonsense;
    clamp to lab bounds. There is no time input here -- see the module
    docstring in ``simulations_refraction.py`` for why."""

    try:
        n1_raw = float(n1)
        n2_raw = float(n2)
        angle_raw = float(angle1_deg)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Refractive index and angle must be numbers.")

    if any(math.isnan(v) or math.isinf(v) for v in (n1_raw, n2_raw, angle_raw)):
        raise ExperimentValidationError("Refractive index and angle must be finite numbers.")
    if n1_raw < 1.0 or n2_raw < 1.0:
        raise ExperimentValidationError("Refractive index must be at least 1.0.")
    if angle_raw < 0:
        raise ExperimentValidationError("Angle of incidence cannot be negative.")
    if (
        n1_raw > REFRACTION_INDEX_HARD_MAX
        or n2_raw > REFRACTION_INDEX_HARD_MAX
        or angle_raw > REFRACTION_ANGLE_HARD_MAX_DEG
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = refraction_state(n1=n1_raw, n2=n2_raw, angle1_deg=angle_raw)
    return ValidatedRefraction(
        n1=clamp_index(n1_raw),
        n2=clamp_index(n2_raw),
        angle1_deg=clamp_refraction_angle(angle_raw),
        has_critical_angle=state["has_critical_angle"],
        critical_angle_deg=state["critical_angle_deg"],
        total_internal_reflection=state["total_internal_reflection"],
        angle2_deg=state["angle2_deg"],
    )


@dataclass(frozen=True)
class ValidatedCalorimetry:
    """Server-recomputed, deterministic Calorimetry values (SI-shaped units)."""

    mass1_kg: float
    specific_heat1: float
    temp1_c: float
    mass2_kg: float
    specific_heat2: float
    temp2_c: float
    heat_capacity1_j_per_k: float
    heat_capacity2_j_per_k: float
    equilibrium_temp_c: float
    heat_transferred_j: float

    def as_dict(self) -> dict:
        return {
            "mass1_kg": self.mass1_kg,
            "specific_heat1": self.specific_heat1,
            "temp1_c": self.temp1_c,
            "mass2_kg": self.mass2_kg,
            "specific_heat2": self.specific_heat2,
            "temp2_c": self.temp2_c,
            "heat_capacity1_j_per_k": self.heat_capacity1_j_per_k,
            "heat_capacity2_j_per_k": self.heat_capacity2_j_per_k,
            "equilibrium_temp_c": self.equilibrium_temp_c,
            "heat_transferred_j": self.heat_transferred_j,
        }


def validate_calorimetry(
    mass1_kg, specific_heat1, temp1_c, mass2_kg, specific_heat2, temp2_c
) -> ValidatedCalorimetry:
    """Recompute the equilibrium temperature/heat transferred on the
    server. Reject nonsense; clamp to lab bounds. There is no time input
    here -- see the module docstring in ``simulations_calorimetry.py`` for
    why."""

    try:
        m1_raw = float(mass1_kg)
        c1_raw = float(specific_heat1)
        t1_raw = float(temp1_c)
        m2_raw = float(mass2_kg)
        c2_raw = float(specific_heat2)
        t2_raw = float(temp2_c)
    except (TypeError, ValueError):
        raise ExperimentValidationError("Mass, specific heat and temperature must be numbers.")

    if any(
        math.isnan(v) or math.isinf(v)
        for v in (m1_raw, c1_raw, t1_raw, m2_raw, c2_raw, t2_raw)
    ):
        raise ExperimentValidationError(
            "Mass, specific heat and temperature must be finite numbers."
        )
    if m1_raw <= 0 or m2_raw <= 0:
        raise ExperimentValidationError("Mass must be positive.")
    if c1_raw <= 0 or c2_raw <= 0:
        raise ExperimentValidationError("Specific heat must be positive.")
    if (
        m1_raw > CALORIMETRY_MASS_HARD_MAX_KG
        or m2_raw > CALORIMETRY_MASS_HARD_MAX_KG
        or c1_raw > CALORIMETRY_SPECIFIC_HEAT_HARD_MAX
        or c2_raw > CALORIMETRY_SPECIFIC_HEAT_HARD_MAX
        or abs(t1_raw) > CALORIMETRY_TEMP_HARD_MAX_C
        or abs(t2_raw) > CALORIMETRY_TEMP_HARD_MAX_C
    ):
        raise ExperimentValidationError("Those values are outside the simulation's range.")

    state = calorimetry_state(
        mass1=m1_raw, specific_heat1=c1_raw, temp1=t1_raw,
        mass2=m2_raw, specific_heat2=c2_raw, temp2=t2_raw,
    )
    return ValidatedCalorimetry(
        mass1_kg=clamp_calorimetry_mass(m1_raw),
        specific_heat1=clamp_specific_heat(c1_raw),
        temp1_c=clamp_temp(t1_raw),
        mass2_kg=clamp_calorimetry_mass(m2_raw),
        specific_heat2=clamp_specific_heat(c2_raw),
        temp2_c=clamp_temp(t2_raw),
        heat_capacity1_j_per_k=state["heat_capacity1_j_per_k"],
        heat_capacity2_j_per_k=state["heat_capacity2_j_per_k"],
        equilibrium_temp_c=state["equilibrium_temp_c"],
        heat_transferred_j=state["heat_transferred_j"],
    )


# --- per-simulation-type dispatch ---------------------------------------
#
# The generic record_experiment_observation/explanation functions below never
# hardcode a simulation's field names. Each simulation type registers three
# small functions here: how to validate raw submitted values, how to write
# the trusted result onto the dedicated ExperimentAttempt fields, and how to
# write it into ExperimentAttempt.parameters (JSON). Adding a third
# simulation type means adding one more entry to each dict, not touching the
# functions that use them.


def _validate_newtons_second_law(values: dict) -> ValidatedNewtonsSecondLaw:
    return validate_newtons_second_law(values.get("mass_kg"), values.get("force_n"))


def _validate_kinematics(values: dict) -> ValidatedKinematics:
    return validate_kinematics(
        values.get("initial_position_m"),
        values.get("initial_velocity_m_s"),
        values.get("acceleration_m_s2"),
        values.get("time_s"),
    )


def _validate_projectile_motion(values: dict) -> ValidatedProjectileMotion:
    return validate_projectile_motion(
        values.get("initial_speed_m_s"),
        values.get("launch_angle_deg"),
        values.get("initial_height_m"),
        values.get("time_s"),
    )


def _validate_circular_motion(values: dict) -> ValidatedCircularMotion:
    return validate_circular_motion(
        values.get("radius_m"),
        values.get("period_s"),
        values.get("time_s"),
    )


def _validate_shm(values: dict) -> ValidatedSHM:
    return validate_shm(
        values.get("amplitude_m"),
        values.get("period_s"),
        values.get("time_s"),
    )


def _validate_collision(values: dict) -> ValidatedCollision:
    return validate_collision(
        values.get("mass1_kg"),
        values.get("mass2_kg"),
        values.get("initial_velocity_m_s"),
        values.get("elastic"),
        values.get("time_s"),
    )


def _validate_energy_incline(values: dict) -> ValidatedEnergyIncline:
    return validate_energy_incline(
        values.get("height_m"),
        values.get("angle_deg"),
        values.get("mass_kg"),
        values.get("time_s"),
    )


def _validate_orbital_motion(values: dict) -> ValidatedOrbitalMotion:
    return validate_orbital_motion(
        values.get("mu"),
        values.get("radius_m"),
        values.get("time_s"),
    )


def _validate_circuit(values: dict) -> ValidatedCircuit:
    return validate_circuit(
        values.get("voltage_v"),
        values.get("resistance1_ohm"),
        values.get("resistance2_ohm"),
        values.get("series"),
    )


def _validate_coulombs_law(values: dict) -> ValidatedCoulomb:
    return validate_coulombs_law(
        values.get("charge1_uc"),
        values.get("charge2_uc"),
        values.get("separation_m"),
    )


def _validate_radioactive_decay(values: dict) -> ValidatedDecay:
    return validate_radioactive_decay(
        values.get("initial_count"),
        values.get("half_life_s"),
        values.get("time_s"),
    )


def _validate_buoyancy(values: dict) -> ValidatedBuoyancy:
    return validate_buoyancy(
        values.get("object_density_kg_m3"),
        values.get("fluid_density_kg_m3"),
        values.get("volume_m3"),
    )


def _validate_refraction(values: dict) -> ValidatedRefraction:
    return validate_refraction(
        values.get("n1"),
        values.get("n2"),
        values.get("angle1_deg"),
    )


def _validate_calorimetry(values: dict) -> ValidatedCalorimetry:
    return validate_calorimetry(
        values.get("mass1_kg"),
        values.get("specific_heat1"),
        values.get("temp1_c"),
        values.get("mass2_kg"),
        values.get("specific_heat2"),
        values.get("temp2_c"),
    )


_VALIDATORS = {
    "newtons_second_law": _validate_newtons_second_law,
    "kinematics": _validate_kinematics,
    "projectile_motion": _validate_projectile_motion,
    "circular_motion": _validate_circular_motion,
    "simple_harmonic_motion": _validate_shm,
    "momentum_collision": _validate_collision,
    "energy_incline": _validate_energy_incline,
    "orbital_motion": _validate_orbital_motion,
    "series_parallel_circuit": _validate_circuit,
    "coulombs_law": _validate_coulombs_law,
    "radioactive_decay": _validate_radioactive_decay,
    "buoyancy": _validate_buoyancy,
    "refraction": _validate_refraction,
    "calorimetry": _validate_calorimetry,
}

# Which submitted fields must ALL be present before Explain recomputes the
# trusted values (mirrors the original "mass_kg is not None and force_n is
# not None" guard).
_EXPLAIN_REQUIRED_FIELDS = {
    "newtons_second_law": ("mass_kg", "force_n"),
    "kinematics": ("initial_position_m", "initial_velocity_m_s", "acceleration_m_s2", "time_s"),
    "projectile_motion": ("initial_speed_m_s", "launch_angle_deg", "initial_height_m", "time_s"),
    "circular_motion": ("radius_m", "period_s", "time_s"),
    "simple_harmonic_motion": ("amplitude_m", "period_s", "time_s"),
    "momentum_collision": ("mass1_kg", "mass2_kg", "initial_velocity_m_s", "elastic", "time_s"),
    "energy_incline": ("height_m", "angle_deg", "mass_kg", "time_s"),
    "orbital_motion": ("mu", "radius_m", "time_s"),
    "series_parallel_circuit": ("voltage_v", "resistance1_ohm", "resistance2_ohm", "series"),
    "coulombs_law": ("charge1_uc", "charge2_uc", "separation_m"),
    "radioactive_decay": ("initial_count", "half_life_s", "time_s"),
    "buoyancy": ("object_density_kg_m3", "fluid_density_kg_m3", "volume_m3"),
    "refraction": ("n1", "n2", "angle1_deg"),
    "calorimetry": (
        "mass1_kg", "specific_heat1", "temp1_c",
        "mass2_kg", "specific_heat2", "temp2_c",
    ),
}


def _apply_fields_newtons_second_law(attempt, validated: ValidatedNewtonsSecondLaw) -> None:
    attempt.mass_kg = validated.mass_kg
    attempt.force_n = validated.force_n
    attempt.acceleration_m_s2 = validated.acceleration_m_s2


def _apply_fields_kinematics(attempt, validated: ValidatedKinematics) -> None:
    attempt.acceleration_m_s2 = validated.acceleration_m_s2


def _apply_fields_projectile_motion(attempt, validated: ValidatedProjectileMotion) -> None:
    # No ExperimentAttempt column fits (there is no single "acceleration"
    # result here -- gravity is a fixed constant, not a computed outcome).
    # Everything lives in attempt.parameters, exactly like the rest of
    # Kinematics' non-acceleration values already do.
    pass


def _apply_fields_circular_motion(attempt, validated: ValidatedCircularMotion) -> None:
    # Centripetal acceleration IS a genuinely computed outcome here (unlike
    # projectile motion's fixed gravity), so it fits the shared column.
    attempt.acceleration_m_s2 = validated.centripetal_acceleration_m_s2


def _apply_fields_shm(attempt, validated: ValidatedSHM) -> None:
    attempt.acceleration_m_s2 = validated.acceleration_m_s2


def _apply_fields_collision(attempt, validated: ValidatedCollision) -> None:
    # Two masses and two velocities don't fit the single shared mass_kg/
    # force_n/acceleration_m_s2 columns -- everything lives in
    # attempt.parameters, exactly like Projectile Motion's non-fitting values.
    pass


def _apply_fields_energy_incline(attempt, validated: ValidatedEnergyIncline) -> None:
    # A single mass fits the shared column (same role as Newton's Second
    # Law's own mass_kg); there is no single "acceleration" result here
    # (it's g*sin(theta) on the ramp, then zero on flat ground), so that
    # column is left alone, like Projectile Motion's fixed gravity.
    attempt.mass_kg = validated.mass_kg


def _apply_fields_orbital_motion(attempt, validated: ValidatedOrbitalMotion) -> None:
    # Gravitational acceleration IS a genuinely computed outcome here (the
    # same v^2/r shape as Circular Motion's centripetal acceleration, with
    # gravity supplying the centripetal force), so it fits the shared column
    # exactly like Circular Motion's does. mu/radius/period don't fit any
    # other column and live in attempt.parameters instead.
    attempt.acceleration_m_s2 = validated.gravitational_acceleration_m_s2


def _apply_fields_circuit(attempt, validated: ValidatedCircuit) -> None:
    # No ExperimentAttempt column fits a circuit's voltage/resistance/
    # current -- there is no mass, force or acceleration here at all.
    # Everything lives in attempt.parameters, like Collision's non-fitting
    # per-cart values.
    pass


def _apply_fields_coulombs_law(attempt, validated: ValidatedCoulomb) -> None:
    # force_n could in principle fit attempt.force_n, but that column means
    # "net force on this attempt's object" everywhere else it's used (Newton's
    # Second Law), and there is no single "object" here -- it's the mutual
    # force between two charges, with a sign-derived attract/repel meaning
    # that force_n's bare magnitude would lose. Keeping it in
    # attempt.parameters only avoids that false-equivalence risk.
    pass


def _apply_fields_radioactive_decay(attempt, validated: ValidatedDecay) -> None:
    # No ExperimentAttempt column fits a sample count or a decay rate --
    # everything lives in attempt.parameters, like Coulomb's Law's and
    # Collision's non-fitting values.
    pass


def _apply_fields_buoyancy(attempt, validated: ValidatedBuoyancy) -> None:
    # net_force_n IS a genuinely computed single-object net force (0 when
    # floating in equilibrium, positive -- downward -- when sinking), the
    # same "net force on this one object" meaning force_n has for Newton's
    # Second Law, so it fits the shared column -- unlike Coulomb's Law's
    # force, which is a MUTUAL force between two separate charges with no
    # single "object" to attach it to.
    attempt.force_n = validated.net_force_n


def _apply_fields_refraction(attempt, validated: ValidatedRefraction) -> None:
    # No ExperimentAttempt column fits an angle -- everything lives in
    # attempt.parameters, like Coulomb's Law's and Collision's non-fitting
    # values.
    pass


def _apply_fields_calorimetry(attempt, validated: ValidatedCalorimetry) -> None:
    # No ExperimentAttempt column fits two substances' masses/heat
    # capacities -- everything lives in attempt.parameters, like
    # Collision's non-fitting two-object values.
    pass


_FIELD_APPLIERS = {
    "newtons_second_law": _apply_fields_newtons_second_law,
    "kinematics": _apply_fields_kinematics,
    "projectile_motion": _apply_fields_projectile_motion,
    "circular_motion": _apply_fields_circular_motion,
    "simple_harmonic_motion": _apply_fields_shm,
    "momentum_collision": _apply_fields_collision,
    "energy_incline": _apply_fields_energy_incline,
    "orbital_motion": _apply_fields_orbital_motion,
    "series_parallel_circuit": _apply_fields_circuit,
    "coulombs_law": _apply_fields_coulombs_law,
    "radioactive_decay": _apply_fields_radioactive_decay,
    "buoyancy": _apply_fields_buoyancy,
    "refraction": _apply_fields_refraction,
    "calorimetry": _apply_fields_calorimetry,
}


def _apply_parameters_newtons_second_law(attempt, simulation, validated: ValidatedNewtonsSecondLaw) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation": simulation.simulation_type,
        "observed": validated.as_dict(),
    }


def _apply_parameters_kinematics(attempt, simulation, validated: ValidatedKinematics) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "initial_position_m": validated.initial_position_m,
        "initial_velocity_m_s": validated.initial_velocity_m_s,
        "acceleration_m_s2": validated.acceleration_m_s2,
        "observed_time_s": validated.time_s,
        "observed_position_m": validated.position_m,
        "observed_velocity_m_s": validated.velocity_m_s,
    }


def _apply_parameters_projectile_motion(attempt, simulation, validated: ValidatedProjectileMotion) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "initial_speed_m_s": validated.initial_speed_m_s,
        "launch_angle_deg": validated.launch_angle_deg,
        "initial_height_m": validated.initial_height_m,
        "observed_time_s": validated.time_s,
        "observed_position_x_m": validated.position_x_m,
        "observed_position_y_m": validated.position_y_m,
        "observed_speed_m_s": validated.speed_m_s,
    }


def _apply_parameters_circular_motion(attempt, simulation, validated: ValidatedCircularMotion) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "radius_m": validated.radius_m,
        "period_s": validated.period_s,
        "observed_time_s": validated.time_s,
        "observed_position_x_m": validated.position_x_m,
        "observed_position_y_m": validated.position_y_m,
        "observed_speed_m_s": validated.speed_m_s,
        "observed_centripetal_acceleration_m_s2": validated.centripetal_acceleration_m_s2,
    }


def _apply_parameters_shm(attempt, simulation, validated: ValidatedSHM) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "amplitude_m": validated.amplitude_m,
        "period_s": validated.period_s,
        "observed_time_s": validated.time_s,
        "observed_position_m": validated.position_m,
        "observed_velocity_m_s": validated.velocity_m_s,
    }


def _apply_parameters_collision(attempt, simulation, validated: ValidatedCollision) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "mass1_kg": validated.mass1_kg,
        "mass2_kg": validated.mass2_kg,
        "initial_velocity_m_s": validated.initial_velocity_m_s,
        "elastic": validated.elastic,
        "observed_time_s": validated.time_s,
        "observed_position_1_m": validated.position_1_m,
        "observed_position_2_m": validated.position_2_m,
        "observed_velocity_1_m_s": validated.velocity_1_m_s,
        "observed_velocity_2_m_s": validated.velocity_2_m_s,
        "observed_has_collided": validated.has_collided,
        "observed_momentum_total_kg_m_s": validated.momentum_total_kg_m_s,
        "observed_kinetic_energy_total_j": validated.kinetic_energy_total_j,
    }


def _apply_parameters_energy_incline(attempt, simulation, validated: ValidatedEnergyIncline) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "height_m": validated.height_m,
        "angle_deg": validated.angle_deg,
        "observed_time_s": validated.time_s,
        "observed_distance_m": validated.distance_m,
        "observed_height_dropped_m": validated.height_dropped_m,
        "observed_speed_m_s": validated.speed_m_s,
        "observed_kinetic_energy_j": validated.kinetic_energy_j,
        "observed_potential_energy_j": validated.potential_energy_j,
        "observed_total_energy_j": validated.total_energy_j,
    }


def _apply_parameters_orbital_motion(attempt, simulation, validated: ValidatedOrbitalMotion) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "mu": validated.mu,
        "radius_m": validated.radius_m,
        "observed_time_s": validated.time_s,
        "observed_position_x_m": validated.position_x_m,
        "observed_position_y_m": validated.position_y_m,
        "observed_speed_m_s": validated.speed_m_s,
        "observed_period_s": validated.period_s,
        "observed_gravitational_acceleration_m_s2": validated.gravitational_acceleration_m_s2,
    }


def _apply_parameters_circuit(attempt, simulation, validated: ValidatedCircuit) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "voltage_v": validated.voltage_v,
        "resistance1_ohm": validated.resistance1_ohm,
        "resistance2_ohm": validated.resistance2_ohm,
        "series": validated.series,
        "observed_total_resistance_ohm": validated.total_resistance_ohm,
        "observed_total_current_a": validated.total_current_a,
        "observed_current_1_a": validated.current_1_a,
        "observed_current_2_a": validated.current_2_a,
        "observed_voltage_1_v": validated.voltage_1_v,
        "observed_voltage_2_v": validated.voltage_2_v,
        "observed_power_1_w": validated.power_1_w,
        "observed_power_2_w": validated.power_2_w,
        "observed_total_power_w": validated.total_power_w,
    }


def _apply_parameters_coulombs_law(attempt, simulation, validated: ValidatedCoulomb) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "charge1_uc": validated.charge1_uc,
        "charge2_uc": validated.charge2_uc,
        "separation_m": validated.separation_m,
        "observed_force_n": validated.force_n,
        "observed_is_attractive": validated.is_attractive,
        "observed_potential_energy_j": validated.potential_energy_j,
        "observed_field_1_at_2_n_per_c": validated.field_1_at_2_n_per_c,
        "observed_field_2_at_1_n_per_c": validated.field_2_at_1_n_per_c,
    }


def _apply_parameters_radioactive_decay(attempt, simulation, validated: ValidatedDecay) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "initial_count": validated.initial_count,
        "half_life_s": validated.half_life_s,
        "observed_time_s": validated.time_s,
        "observed_remaining_count": validated.remaining_count,
        "observed_decayed_count": validated.decayed_count,
        "observed_remaining_fraction": validated.remaining_fraction,
        "observed_activity_per_s": validated.activity_per_s,
    }


def _apply_parameters_buoyancy(attempt, simulation, validated: ValidatedBuoyancy) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "object_density_kg_m3": validated.object_density_kg_m3,
        "fluid_density_kg_m3": validated.fluid_density_kg_m3,
        "volume_m3": validated.volume_m3,
        "observed_weight_n": validated.weight_n,
        "observed_buoyant_force_n": validated.buoyant_force_n,
        "observed_submerged_fraction": validated.submerged_fraction,
        "observed_floats": validated.floats,
        "observed_net_force_n": validated.net_force_n,
    }


def _apply_parameters_refraction(attempt, simulation, validated: ValidatedRefraction) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "n1": validated.n1,
        "n2": validated.n2,
        "angle1_deg": validated.angle1_deg,
        "observed_has_critical_angle": validated.has_critical_angle,
        "observed_critical_angle_deg": validated.critical_angle_deg,
        "observed_total_internal_reflection": validated.total_internal_reflection,
        "observed_angle2_deg": validated.angle2_deg,
    }


def _apply_parameters_calorimetry(attempt, simulation, validated: ValidatedCalorimetry) -> None:
    attempt.parameters = {
        **(attempt.parameters or {}),
        "simulation_type": simulation.simulation_type,
        "mass1_kg": validated.mass1_kg,
        "specific_heat1": validated.specific_heat1,
        "temp1_c": validated.temp1_c,
        "mass2_kg": validated.mass2_kg,
        "specific_heat2": validated.specific_heat2,
        "temp2_c": validated.temp2_c,
        "observed_heat_capacity1_j_per_k": validated.heat_capacity1_j_per_k,
        "observed_heat_capacity2_j_per_k": validated.heat_capacity2_j_per_k,
        "observed_equilibrium_temp_c": validated.equilibrium_temp_c,
        "observed_heat_transferred_j": validated.heat_transferred_j,
    }


_PARAMETER_APPLIERS = {
    "newtons_second_law": _apply_parameters_newtons_second_law,
    "kinematics": _apply_parameters_kinematics,
    "projectile_motion": _apply_parameters_projectile_motion,
    "circular_motion": _apply_parameters_circular_motion,
    "simple_harmonic_motion": _apply_parameters_shm,
    "momentum_collision": _apply_parameters_collision,
    "energy_incline": _apply_parameters_energy_incline,
    "orbital_motion": _apply_parameters_orbital_motion,
    "series_parallel_circuit": _apply_parameters_circuit,
    "coulombs_law": _apply_parameters_coulombs_law,
    "radioactive_decay": _apply_parameters_radioactive_decay,
    "buoyancy": _apply_parameters_buoyancy,
    "refraction": _apply_parameters_refraction,
    "calorimetry": _apply_parameters_calorimetry,
}


def _clean_text(value: str, *, field_label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ExperimentValidationError(f"Write your {field_label} before submitting.")
    return text[:TEXT_LIMIT]


def _active_attempt(student, simulation, *, session=None, lesson=None) -> ExperimentAttempt:
    """The student's current, not-yet-completed attempt for this simulation."""

    attempt = (
        ExperimentAttempt.objects.filter(
            student=student, simulation=simulation, completed_at__isnull=True
        )
        .order_by("-started_at")
        .first()
    )
    if attempt is None:
        attempt = ExperimentAttempt.objects.create(
            student=student,
            simulation=simulation,
            session=session,
            lesson=lesson,
        )
    else:
        dirty = []
        if session is not None and attempt.session_id is None:
            attempt.session = session
            dirty.append("session")
        if lesson is not None and attempt.lesson_id is None:
            attempt.lesson = lesson
            dirty.append("lesson")
        if dirty:
            attempt.save(update_fields=dirty + ["updated_at"])
    return attempt


def _record_evidence(attempt, kind, detail, *, context=None) -> LearningEvidence:
    return LearningEvidence.objects.create(
        student=attempt.student,
        lesson=attempt.lesson,
        session=attempt.session,
        kind=kind,
        detail=(detail or "")[:300],
        context=context or {},
    )


def _base_context(attempt, simulation) -> dict:
    context = {"simulation": simulation.simulation_type}
    if attempt.mass_kg is not None:
        context["mass_kg"] = attempt.mass_kg
    if attempt.force_n is not None:
        context["force_n"] = attempt.force_n
    if attempt.acceleration_m_s2 is not None:
        context["acceleration_m_s2"] = attempt.acceleration_m_s2
    if simulation.simulation_type == "kinematics":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("initial_position_m", "initial_velocity_m_s"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_position_m" in params:
            context["position_m"] = params["observed_position_m"]
        if "observed_velocity_m_s" in params:
            context["velocity_m_s"] = params["observed_velocity_m_s"]
    elif simulation.simulation_type == "projectile_motion":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("initial_speed_m_s", "launch_angle_deg", "initial_height_m"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_position_x_m" in params:
            context["position_x_m"] = params["observed_position_x_m"]
        if "observed_position_y_m" in params:
            context["position_y_m"] = params["observed_position_y_m"]
        if "observed_speed_m_s" in params:
            context["speed_m_s"] = params["observed_speed_m_s"]
    elif simulation.simulation_type == "circular_motion":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("radius_m", "period_s"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_position_x_m" in params:
            context["position_x_m"] = params["observed_position_x_m"]
        if "observed_position_y_m" in params:
            context["position_y_m"] = params["observed_position_y_m"]
        if "observed_speed_m_s" in params:
            context["speed_m_s"] = params["observed_speed_m_s"]
    elif simulation.simulation_type == "simple_harmonic_motion":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        if "amplitude_m" in params:
            context["amplitude_m"] = params["amplitude_m"]
        if "period_s" in params:
            context["period_s"] = params["period_s"]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_position_m" in params:
            context["position_m"] = params["observed_position_m"]
        if "observed_velocity_m_s" in params:
            context["velocity_m_s"] = params["observed_velocity_m_s"]
    elif simulation.simulation_type == "momentum_collision":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("mass1_kg", "mass2_kg", "initial_velocity_m_s", "elastic"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        for key in (
            "observed_position_1_m", "observed_position_2_m",
            "observed_velocity_1_m_s", "observed_velocity_2_m_s",
            "observed_has_collided", "observed_momentum_total_kg_m_s",
            "observed_kinetic_energy_total_j",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "energy_incline":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("height_m", "angle_deg"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        for key in (
            "observed_distance_m", "observed_height_dropped_m",
            "observed_speed_m_s", "observed_kinetic_energy_j",
            "observed_potential_energy_j", "observed_total_energy_j",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "orbital_motion":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("mu", "radius_m"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        if "observed_period_s" in params:
            context["period_s"] = params["observed_period_s"]
        if "observed_position_x_m" in params:
            context["position_x_m"] = params["observed_position_x_m"]
        if "observed_position_y_m" in params:
            context["position_y_m"] = params["observed_position_y_m"]
        if "observed_speed_m_s" in params:
            context["speed_m_s"] = params["observed_speed_m_s"]
    elif simulation.simulation_type == "series_parallel_circuit":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("voltage_v", "resistance1_ohm", "resistance2_ohm", "series"):
            if key in params:
                context[key] = params[key]
        for key in (
            "observed_total_resistance_ohm", "observed_total_current_a",
            "observed_current_1_a", "observed_current_2_a",
            "observed_voltage_1_v", "observed_voltage_2_v",
            "observed_total_power_w",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "coulombs_law":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("charge1_uc", "charge2_uc", "separation_m"):
            if key in params:
                context[key] = params[key]
        for key in (
            "observed_force_n", "observed_is_attractive", "observed_potential_energy_j",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "radioactive_decay":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("initial_count", "half_life_s"):
            if key in params:
                context[key] = params[key]
        if "observed_time_s" in params:
            context["time_s"] = params["observed_time_s"]
        for key in (
            "observed_remaining_count", "observed_decayed_count",
            "observed_remaining_fraction", "observed_activity_per_s",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "buoyancy":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("object_density_kg_m3", "fluid_density_kg_m3", "volume_m3"):
            if key in params:
                context[key] = params[key]
        for key in (
            "observed_weight_n", "observed_buoyant_force_n",
            "observed_submerged_fraction", "observed_floats",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "refraction":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in ("n1", "n2", "angle1_deg"):
            if key in params:
                context[key] = params[key]
        for key in (
            "observed_has_critical_angle", "observed_critical_angle_deg",
            "observed_total_internal_reflection", "observed_angle2_deg",
        ):
            if key in params:
                context[key] = params[key]
    elif simulation.simulation_type == "calorimetry":
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        for key in (
            "mass1_kg", "specific_heat1", "temp1_c",
            "mass2_kg", "specific_heat2", "temp2_c",
        ):
            if key in params:
                context[key] = params[key]
        for key in ("observed_equilibrium_temp_c", "observed_heat_transferred_j"):
            if key in params:
                context[key] = params[key]
    return context


_DIRECTION_CHOICES = frozenset(
    {"speed_up", "slow_down", "constant", "reverse"}
)


def _clean_predicted_number(value, low, high):
    """A finite prediction figure clamped to the model's range, or ``None``.

    A blank/garbage/absent value is fine -- structured prediction is optional.
    A forged huge number is clamped, never trusted.
    """

    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(low, min(high, number))


@transaction.atomic
def record_experiment_prediction(
    *, student, simulation, prediction, session=None, lesson=None, structured=None
) -> ExperimentAttempt:
    """Learning moment 1: the student commits to a prediction. Not judged now.

    ``structured`` (optional) may carry ``predicted_velocity_m_s`` /
    ``predicted_position_m`` / ``predicted_direction``. It is stored under
    ``attempt.parameters['prediction']`` so the Observe step can show a
    prediction-vs-observed comparison -- it is never scored and never gates
    anything.
    """

    text = _clean_text(prediction, field_label="prediction")
    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    attempt.prediction = text

    update_fields = ["prediction", "updated_at"]
    structured = structured or {}
    predicted = {}
    v = _clean_predicted_number(
        structured.get("predicted_velocity_m_s"),
        -MAX_INITIAL_VELOCITY_MS - MAX_ACCELERATION_MS2 * MAX_TIME_S,
        MAX_INITIAL_VELOCITY_MS + MAX_ACCELERATION_MS2 * MAX_TIME_S,
    )
    x = _clean_predicted_number(
        structured.get("predicted_position_m"), -10000.0, 10000.0
    )
    direction = str(structured.get("predicted_direction") or "").strip().lower()
    if v is not None:
        predicted["velocity_m_s"] = round(v, 4)
    if x is not None:
        predicted["position_m"] = round(x, 4)
    if direction in _DIRECTION_CHOICES:
        predicted["direction"] = direction
    if predicted:
        params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
        params = dict(params)
        params["prediction"] = predicted
        attempt.parameters = params
        update_fields.append("parameters")

    attempt.save(update_fields=update_fields)
    _record_evidence(
        attempt,
        LearningEvidence.Kind.PREDICTION_SUBMITTED,
        text,
        context={
            "simulation": simulation.simulation_type,
            "phase": "prediction",
            **({"predicted": predicted} if predicted else {}),
        },
    )
    return attempt


@transaction.atomic
def record_experiment_observation(
    *, student, simulation, observation, session=None, lesson=None, **physics_values
) -> tuple[ExperimentAttempt, object]:
    """Learning moment 2: the student reports what happened. Values recomputed.

    ``**physics_values`` carries whatever raw fields this simulation type
    needs (``mass_kg``/``force_n`` for Newton's Second Law,
    ``initial_position_m``/``initial_velocity_m_s``/``acceleration_m_s2``/
    ``time_s`` for Kinematics) -- never trusted as-is, always re-validated
    against the deterministic model for ``simulation.simulation_type``.
    """

    text = _clean_text(observation, field_label="observation")
    validator = _VALIDATORS.get(simulation.simulation_type)
    if validator is None:
        raise ExperimentValidationError("This simulation type does not support experiments yet.")
    validated = validator(physics_values)

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    attempt.observation = text
    _FIELD_APPLIERS[simulation.simulation_type](attempt, validated)
    _PARAMETER_APPLIERS[simulation.simulation_type](attempt, simulation, validated)
    attempt.save(
        update_fields=[
            "observation",
            "mass_kg",
            "force_n",
            "acceleration_m_s2",
            "parameters",
            "updated_at",
        ]
    )
    _record_evidence(
        attempt,
        LearningEvidence.Kind.EXPERIMENT_OBSERVED,
        text,
        context={**_base_context(attempt, simulation), "phase": "observation"},
    )
    return attempt, validated


@transaction.atomic
def record_experiment_explanation(
    *,
    student,
    simulation,
    explanation,
    session=None,
    lesson=None,
    provider=None,
    assess: bool = True,
    **physics_values,
) -> tuple[ExperimentAttempt, list]:
    """Learning moment 3: the student explains their reasoning.

    This is the richest evidence. The explanation is also passed through the
    existing misconception engine; any candidate stays a *candidate* -- only a
    teacher can confirm it.
    """

    text = _clean_text(explanation, field_label="explanation")

    attempt = _active_attempt(student, simulation, session=session, lesson=lesson)
    required = _EXPLAIN_REQUIRED_FIELDS.get(simulation.simulation_type, ())
    if required and all(physics_values.get(f) is not None for f in required):
        validator = _VALIDATORS.get(simulation.simulation_type)
        validated = validator(physics_values)
        _FIELD_APPLIERS[simulation.simulation_type](attempt, validated)
        # Keep ``parameters`` in step with the dedicated fields above -- for
        # Kinematics, position/velocity/time live ONLY in parameters, so a
        # fresh explain-time setup must refresh them too, or the evidence
        # context built from ``attempt.parameters`` would pair a fresh
        # acceleration with a stale position/velocity/time snapshot.
        _PARAMETER_APPLIERS[simulation.simulation_type](attempt, simulation, validated)
    attempt.explanation = text
    attempt.save(
        update_fields=[
            "explanation",
            "mass_kg",
            "force_n",
            "acceleration_m_s2",
            "parameters",
            "updated_at",
        ]
    )
    evidence = _record_evidence(
        attempt,
        LearningEvidence.Kind.EXPLANATION_SUBMITTED,
        text,
        context={**_base_context(attempt, simulation), "phase": "explanation"},
    )

    outcomes: list = []
    if assess:
        try:
            outcomes = assess_student_misconceptions(
                student=student,
                lesson=attempt.lesson,
                text=text,
                learning_evidence=evidence,
                tutor_message=None,
                provider=provider,
            )
        except Exception:  # pragma: no cover - defensive; must not block the flow
            logger.exception(
                "Misconception assessment failed for experiment attempt %s.",
                attempt.pk,
            )
    return attempt, outcomes


@transaction.atomic
def complete_experiment(attempt: ExperimentAttempt) -> ExperimentAttempt:
    """Mark the attempt finished so the next prediction starts a fresh run."""

    if attempt.completed_at is None:
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["completed_at", "updated_at"])
    return attempt


def latest_attempt_for(student, simulation) -> ExperimentAttempt | None:
    """The student's most recent attempt (complete or not) for this simulation."""

    return (
        ExperimentAttempt.objects.filter(student=student, simulation=simulation)
        .order_by("-started_at")
        .first()
    )
