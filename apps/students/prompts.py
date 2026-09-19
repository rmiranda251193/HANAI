from __future__ import annotations

import json

from apps.ai.prompts import Prompt

from .requests import TutorRequest
from .schemas import TUTOR_RESPONSE_JSON_SCHEMA

TUTOR_PROMPT_VERSION = "physics-tutor-v1"


def _bullets(items: tuple[str, ...], empty_label: str) -> str:
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def build_tutor_prompt(request: TutorRequest) -> Prompt:
    """Build the system and user prompts for one tutoring turn."""

    system = f"""You are the Physics tutor for DodongOS Physics AI.

Core rule: AI assists. Teachers decide. Students learn by thinking.

You are helping one student understand a specific Physics lesson. You are not a
general chatbot and you are not a search engine.

Grounding rules:
- Stay inside the supplied lesson and Physics concepts. Treat the concept
  knowledge (definitions, equations, SI units) as the source of truth.
- Respect the stated grade level in vocabulary and depth.
- Use scientifically correct terminology and SI units where appropriate.
- Do not claim access to information that was not supplied. If something needed
  is missing, say so plainly instead of inventing it.
- Clearly separate what is given in the lesson from any assumption you make.

Tutoring behaviour:
- First work out what the student is actually trying to understand or do.
- Prefer a guiding question or a hint over an immediate final answer when that
  will help the student reason.
- Encourage the student to attempt the next step themselves.
- When the student asks directly for an explanation, explain (mode "explain").
- When you are reacting to a student's attempt, give specific feedback
  (mode "feedback").
- Give a full worked solution (mode "solution") only when guidance has been
  tried or the student clearly needs to see the whole method.
- Correct misconceptions directly but respectfully.
- Keep replies focused and reasonably short.

Possible misconceptions (internal context only):
- You may be told about possible misconceptions to watch for. These are guesses,
  not facts about the student.
- NEVER tell the student they "have" a misconception and never repeat an
  internal label or code.
- Instead choose an intervention: a comparison, a prediction, or a targeted
  question that lets the student test the idea for themselves.

Output contract:
- Return ONLY a JSON object. No markdown, no commentary, no code fences.
- Match this schema exactly:
{json.dumps(TUTOR_RESPONSE_JSON_SCHEMA, indent=2)}
- Valid modes: explain, hint, question, feedback, solution, practice.
- Prompt version: {TUTOR_PROMPT_VERSION}
"""

    objectives = _bullets(
        request.learning_objectives, "None recorded for this lesson."
    )
    misconceptions = _bullets(
        request.common_misconceptions, "None listed by the teacher."
    )
    if request.concepts:
        concept_blocks = "\n\n".join(
            concept.as_prompt_block() for concept in request.concepts
        )
    else:
        concept_blocks = (
            "No Physics concepts were attached to this lesson. Do not invent "
            "concept facts; work only from the lesson topic and objectives."
        )

    if request.recent_messages:
        conversation = "\n".join(
            f"{message.role}: {message.content}"
            for message in request.recent_messages
        )
    else:
        conversation = "(no earlier messages in this session)"

    if request.candidate_misconceptions:
        misconception_lines = []
        for hint in request.candidate_misconceptions:
            parts = [f"- ({hint.confidence} confidence) {hint.concept}: {hint.title}"]
            if hint.description:
                parts.append(f"  what the student may believe: {hint.description}")
            if hint.intervention_guidance:
                parts.append(f"  suggested move: {hint.intervention_guidance}")
            misconception_lines.append("\n".join(parts))
        candidate_block = (
            "Possible misconceptions to gently probe (do NOT name these to the "
            "student):\n" + "\n".join(misconception_lines)
        )
    else:
        candidate_block = (
            "Possible misconceptions to gently probe: none flagged for this student."
        )

    experiment_block = ""
    experiment = request.experiment
    if experiment is not None and experiment.has_content:
        exp_lines = [
            f"Physics Lab experiment the student just ran "
            f"({experiment.simulation or 'simulation'}):"
        ]
        if experiment.simulation_type == "kinematics":
            if (
                experiment.initial_position_m is not None
                and experiment.initial_velocity_m_s is not None
            ):
                setup = (
                    f"- setup: initial position = {experiment.initial_position_m:.2f} m, "
                    f"initial velocity = {experiment.initial_velocity_m_s:.2f} m/s"
                )
                if experiment.acceleration_m_s2 is not None:
                    setup += f", acceleration = {experiment.acceleration_m_s2:.2f} m/s^2"
                exp_lines.append(setup)
            if (
                experiment.time_s is not None
                and experiment.position_m is not None
                and experiment.velocity_m_s is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "v = v0 + at and x = x0 + v0*t + 1/2*a*t^2, computed by the app): "
                    f"position = {experiment.position_m:.2f} m, "
                    f"velocity = {experiment.velocity_m_s:.2f} m/s"
                )
        elif experiment.simulation_type == "projectile_motion":
            if (
                experiment.initial_speed_m_s is not None
                and experiment.launch_angle_deg is not None
            ):
                setup = (
                    f"- setup: initial speed = {experiment.initial_speed_m_s:.2f} m/s, "
                    f"launch angle = {experiment.launch_angle_deg:.0f} degrees"
                )
                if experiment.initial_height_m is not None:
                    setup += f", initial height = {experiment.initial_height_m:.2f} m"
                exp_lines.append(setup)
            if (
                experiment.time_s is not None
                and experiment.position_x_m is not None
                and experiment.position_y_m is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "x = v0*cos(theta)*t and y = y0 + v0*sin(theta)*t - 1/2*g*t^2, "
                    f"computed by the app): horizontal distance = {experiment.position_x_m:.2f} m, "
                    f"height = {experiment.position_y_m:.2f} m"
                )
        elif experiment.simulation_type == "circular_motion":
            if experiment.radius_m is not None and experiment.period_s is not None:
                exp_lines.append(
                    f"- setup: radius = {experiment.radius_m:.2f} m, "
                    f"period = {experiment.period_s:.2f} s"
                )
            if experiment.time_s is not None and experiment.velocity_m_s is not None:
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "v = 2*pi*r/T, computed by the app): speed = "
                    f"{experiment.velocity_m_s:.2f} m/s"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    "- centripetal acceleration (deterministic a_c = v^2 / r, "
                    f"computed by the app): {experiment.acceleration_m_s2:.2f} m/s^2"
                )
        elif experiment.simulation_type == "simple_harmonic_motion":
            if experiment.amplitude_m is not None and experiment.period_s is not None:
                exp_lines.append(
                    f"- setup: amplitude = {experiment.amplitude_m:.2f} m, "
                    f"period = {experiment.period_s:.2f} s"
                )
            if (
                experiment.time_s is not None
                and experiment.position_m is not None
                and experiment.velocity_m_s is not None
            ):
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "x = A*cos(omega*t), computed by the app): "
                    f"position = {experiment.position_m:.2f} m, "
                    f"velocity = {experiment.velocity_m_s:.2f} m/s"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    "- acceleration (deterministic a = -omega^2 * x, "
                    f"computed by the app): {experiment.acceleration_m_s2:.2f} m/s^2"
                )
        elif experiment.simulation_type == "momentum_collision":
            if experiment.mass1_kg is not None and experiment.mass2_kg is not None:
                exp_lines.append(
                    f"- setup: mass 1 = {experiment.mass1_kg:.2f} kg, "
                    f"mass 2 = {experiment.mass2_kg:.2f} kg, cart 1's initial speed = "
                    f"{experiment.initial_velocity_m_s:.2f} m/s (cart 2 starts at rest), "
                    "collision type = "
                    + ("elastic" if (experiment.elastic or 0) >= 0.5 else "perfectly inelastic")
                )
            if (
                experiment.velocity_1_m_s is not None
                and experiment.velocity_2_m_s is not None
            ):
                exp_lines.append(
                    "- after the collision (deterministic, momentum always "
                    f"conserved, computed by the app): velocity 1 = "
                    f"{experiment.velocity_1_m_s:.2f} m/s, velocity 2 = "
                    f"{experiment.velocity_2_m_s:.2f} m/s"
                )
            if experiment.momentum_total_kg_m_s is not None:
                exp_lines.append(
                    f"- total momentum: {experiment.momentum_total_kg_m_s:.2f} kg m/s"
                )
            if experiment.kinetic_energy_total_j is not None:
                exp_lines.append(
                    f"- total kinetic energy: {experiment.kinetic_energy_total_j:.2f} J"
                )
        elif experiment.simulation_type == "energy_incline":
            if experiment.height_m is not None and experiment.angle_deg is not None:
                exp_lines.append(
                    f"- setup: starting height = {experiment.height_m:.2f} m, "
                    f"incline angle = {experiment.angle_deg:.1f} degrees, "
                    f"mass = {experiment.mass_kg:.2f} kg"
                )
            if experiment.time_s is not None and experiment.velocity_m_s is not None:
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    f"computed by the app): speed = {experiment.velocity_m_s:.2f} m/s"
                )
            if (
                experiment.kinetic_energy_j is not None
                and experiment.potential_energy_j is not None
            ):
                exp_lines.append(
                    f"- kinetic energy = {experiment.kinetic_energy_j:.2f} J, "
                    f"potential energy = {experiment.potential_energy_j:.2f} J"
                )
            if experiment.total_energy_j is not None:
                exp_lines.append(
                    "- total mechanical energy (always conserved here, no "
                    f"friction): {experiment.total_energy_j:.2f} J"
                )
        elif experiment.simulation_type == "orbital_motion":
            if experiment.mu is not None and experiment.radius_m is not None:
                exp_lines.append(
                    f"- setup: gravitational parameter (mu) = {experiment.mu:.2f} m^3/s^2, "
                    f"orbital radius = {experiment.radius_m:.2f} m"
                )
            if experiment.period_s is not None:
                exp_lines.append(
                    "- orbital period (deterministic, Kepler's third law "
                    f"T = 2*pi*sqrt(r^3/mu), computed by the app): "
                    f"{experiment.period_s:.2f} s"
                )
            if experiment.time_s is not None and experiment.velocity_m_s is not None:
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "v = sqrt(mu/r), computed by the app): speed = "
                    f"{experiment.velocity_m_s:.2f} m/s"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    "- gravitational acceleration (deterministic a_g = mu / r^2, "
                    f"computed by the app): {experiment.acceleration_m_s2:.2f} m/s^2"
                )
        elif experiment.simulation_type == "series_parallel_circuit":
            if experiment.voltage_v is not None:
                exp_lines.append(
                    f"- setup: source voltage = {experiment.voltage_v:.2f} V, "
                    f"R1 = {experiment.resistance1_ohm:.2f} ohm, R2 = "
                    f"{experiment.resistance2_ohm:.2f} ohm, wired in "
                    + ("series" if experiment.is_series else "parallel")
                )
            if experiment.total_current_a is not None:
                exp_lines.append(
                    "- total current drawn from the source (deterministic, "
                    f"computed by the app): {experiment.total_current_a:.2f} A"
                )
            if experiment.current_1_a is not None and experiment.current_2_a is not None:
                exp_lines.append(
                    f"- current through each resistor: {experiment.current_1_a:.2f} A "
                    f"and {experiment.current_2_a:.2f} A"
                )
            if experiment.voltage_1_v is not None and experiment.voltage_2_v is not None:
                exp_lines.append(
                    f"- voltage across each resistor: {experiment.voltage_1_v:.2f} V "
                    f"and {experiment.voltage_2_v:.2f} V"
                )
            if experiment.total_power_w is not None:
                exp_lines.append(
                    f"- total power delivered by the source: {experiment.total_power_w:.2f} W "
                    "(always equal to the sum of the power dissipated in each resistor)"
                )
        elif experiment.simulation_type == "coulombs_law":
            if experiment.charge1_uc is not None and experiment.charge2_uc is not None:
                exp_lines.append(
                    f"- setup: charge 1 = {experiment.charge1_uc:.2f} uC, "
                    f"charge 2 = {experiment.charge2_uc:.2f} uC, separation = "
                    f"{experiment.coulomb_separation_m:.2f} m"
                )
            if experiment.coulomb_force_n is not None:
                if experiment.coulomb_force_n == 0:
                    interaction = "no force (one of the charges is zero)"
                elif experiment.is_attractive:
                    interaction = "attractive (opposite signs)"
                else:
                    interaction = "repulsive (same sign)"
                exp_lines.append(
                    "- force between them (deterministic, F = k|q1 q2|/r^2, "
                    f"computed by the app): {experiment.coulomb_force_n:.4f} N, {interaction}"
                )
            if experiment.coulomb_potential_energy_j is not None:
                exp_lines.append(
                    "- electric potential energy (deterministic, U = k q1 q2 / r, "
                    f"computed by the app): {experiment.coulomb_potential_energy_j:.6f} J "
                    "(negative means attraction, positive means repulsion)"
                )
        elif experiment.simulation_type == "radioactive_decay":
            if experiment.initial_count is not None and experiment.half_life_s is not None:
                exp_lines.append(
                    f"- setup: initial count = {experiment.initial_count:.0f}, "
                    f"half-life = {experiment.half_life_s:.2f} s"
                )
            if experiment.time_s is not None and experiment.remaining_count is not None:
                exp_lines.append(
                    f"- at t = {experiment.time_s:.2f} s (deterministic, "
                    "N = N0 * (1/2)^(t/T_half), computed by the app): remaining count = "
                    f"{experiment.remaining_count:.1f}"
                )
            if experiment.decayed_count is not None:
                exp_lines.append(
                    f"- decayed so far: {experiment.decayed_count:.1f} "
                    "(remaining + decayed always equals the initial count)"
                )
            if experiment.activity_per_s is not None:
                exp_lines.append(
                    "- activity (deterministic, decays per second, computed by the app): "
                    f"{experiment.activity_per_s:.2f} decays/s"
                )
        elif experiment.simulation_type == "buoyancy":
            if experiment.object_density_kg_m3 is not None and experiment.fluid_density_kg_m3 is not None:
                exp_lines.append(
                    f"- setup: object density = {experiment.object_density_kg_m3:.0f} kg/m^3, "
                    f"fluid density = {experiment.fluid_density_kg_m3:.0f} kg/m^3, "
                    f"volume = {experiment.volume_m3:.4f} m^3"
                )
            if experiment.floats is not None:
                exp_lines.append(
                    "- outcome (deterministic, floats when object density <= fluid density, "
                    "regardless of weight or size, computed by the app): the object "
                    + ("floats" if experiment.floats else "sinks")
                )
            if experiment.buoyant_force_n is not None:
                exp_lines.append(f"- buoyant force: {experiment.buoyant_force_n:.2f} N")
            if experiment.force_n is not None:
                exp_lines.append(
                    f"- net force: {experiment.force_n:.2f} N "
                    "(0 means floating in equilibrium; positive means still sinking)"
                )
        elif experiment.simulation_type == "refraction":
            if experiment.n1 is not None and experiment.n2 is not None:
                exp_lines.append(
                    f"- setup: n1 = {experiment.n1:.2f}, n2 = {experiment.n2:.2f}, "
                    f"angle of incidence = {experiment.angle1_deg:.1f} degrees"
                )
            if experiment.total_internal_reflection is not None:
                if experiment.total_internal_reflection:
                    exp_lines.append(
                        "- outcome (deterministic, n1 sin(theta1) = n2 sin(theta2), computed "
                        "by the app): total internal reflection -- no refracted ray, "
                        "all the light reflects back"
                    )
                else:
                    exp_lines.append(
                        "- outcome (deterministic, n1 sin(theta1) = n2 sin(theta2), computed "
                        f"by the app): refracts at {experiment.angle2_deg:.1f} degrees from the normal"
                    )
            if experiment.has_critical_angle and experiment.critical_angle_deg is not None:
                exp_lines.append(
                    f"- critical angle for this pair of media: {experiment.critical_angle_deg:.1f} "
                    "degrees (past this, total internal reflection always happens)"
                )
        elif experiment.simulation_type == "calorimetry":
            if (
                experiment.mass1_kg is not None and experiment.specific_heat1 is not None
                and experiment.temp1_c is not None
            ):
                exp_lines.append(
                    f"- substance 1: mass = {experiment.mass1_kg:.2f} kg, specific heat = "
                    f"{experiment.specific_heat1:.0f} J/(kg K), starting temperature = "
                    f"{experiment.temp1_c:.1f} C"
                )
            if (
                experiment.mass2_kg is not None and experiment.specific_heat2 is not None
                and experiment.temp2_c is not None
            ):
                exp_lines.append(
                    f"- substance 2: mass = {experiment.mass2_kg:.2f} kg, specific heat = "
                    f"{experiment.specific_heat2:.0f} J/(kg K), starting temperature = "
                    f"{experiment.temp2_c:.1f} C"
                )
            if experiment.equilibrium_temp_c is not None:
                exp_lines.append(
                    "- equilibrium temperature (deterministic, conservation of energy: heat "
                    "lost by the warmer substance equals heat gained by the cooler one, "
                    f"computed by the app): {experiment.equilibrium_temp_c:.1f} C"
                )
            if experiment.heat_transferred_j is not None:
                exp_lines.append(f"- heat transferred: {experiment.heat_transferred_j:.1f} J")
        elif experiment.simulation_type == "ideal_gas_law":
            if experiment.moles is not None and experiment.temperature_k is not None:
                exp_lines.append(
                    f"- setup: amount of gas = {experiment.moles:.2f} mol, "
                    f"temperature = {experiment.temperature_k:.1f} K, "
                    f"volume = {experiment.volume_m3:.4f} m^3"
                )
            if experiment.pressure_pa is not None:
                exp_lines.append(
                    "- pressure (deterministic, P = nRT/V, computed by the app): "
                    f"{experiment.pressure_pa:.1f} Pa"
                )
        elif experiment.simulation_type == "doppler_effect":
            if experiment.source_freq_hz is not None:
                exp_lines.append(
                    f"- setup: source frequency = {experiment.source_freq_hz:.0f} Hz, "
                    f"source velocity = {experiment.source_velocity_m_s:.1f} m/s, "
                    f"observer velocity = {experiment.observer_velocity_m_s:.1f} m/s "
                    "(positive = approaching, negative = receding, for both)"
                )
            if experiment.observed_freq_hz is not None:
                exp_lines.append(
                    "- observed frequency (deterministic, f_observed = f_source * "
                    "(v_sound + v_observer) / (v_sound - v_source), computed by the app): "
                    f"{experiment.observed_freq_hz:.1f} Hz"
                )
        elif experiment.simulation_type == "magnetic_force":
            if experiment.charge_magnitude_c is not None:
                exp_lines.append(
                    f"- setup: charge = {experiment.charge_magnitude_c:.2f} C "
                    + ("(positive)" if experiment.is_positive_charge else "(negative)")
                    + f", mass = {experiment.mass_kg:.2f} kg, speed = "
                    f"{experiment.velocity_m_s:.1f} m/s, magnetic field = "
                    f"{experiment.field_t:.1f} T"
                )
            if experiment.radius_m is not None and experiment.period_s is not None:
                exp_lines.append(
                    "- orbital radius and period (deterministic, r = mv/(|q|B), "
                    "T = 2*pi*m/(|q|B) -- notice T does not depend on speed at all, "
                    f"computed by the app): radius = {experiment.radius_m:.2f} m, "
                    f"period = {experiment.period_s:.2f} s"
                )
            if experiment.force_n is not None:
                exp_lines.append(
                    "- magnetic force (deterministic, F = |q|vB, always perpendicular "
                    f"to velocity so it never changes speed, computed by the app): "
                    f"{experiment.force_n:.2f} N"
                )
        elif experiment.simulation_type == "time_dilation":
            if experiment.velocity_fraction_c is not None:
                exp_lines.append(
                    f"- setup: relative velocity = {experiment.velocity_fraction_c:.2f}c, "
                    f"proper time = {experiment.proper_time_s:.1f} s, proper length = "
                    f"{experiment.proper_length_m:.1f} m"
                )
            if experiment.lorentz_factor is not None:
                exp_lines.append(
                    "- Lorentz factor (deterministic, gamma = 1/sqrt(1 - v^2/c^2), "
                    f"computed by the app): {experiment.lorentz_factor:.3f}"
                )
            if experiment.dilated_time_s is not None and experiment.contracted_length_m is not None:
                exp_lines.append(
                    f"- as measured by a stationary observer: dilated time = "
                    f"{experiment.dilated_time_s:.2f} s (longer than the proper time), "
                    f"contracted length = {experiment.contracted_length_m:.2f} m "
                    "(shorter than the proper length) -- both by the same factor of gamma"
                )
        elif experiment.simulation_type == "photoelectric_effect":
            if experiment.wavelength_nm is not None:
                exp_lines.append(
                    f"- setup: light wavelength = {experiment.wavelength_nm:.0f} nm, "
                    f"work function = {experiment.work_function_ev:.2f} eV, intensity = "
                    f"{experiment.light_intensity:.1f} (arbitrary units)"
                )
            if experiment.photon_energy_ev is not None:
                exp_lines.append(
                    "- photon energy (deterministic, E = hf, computed by the app): "
                    f"{experiment.photon_energy_ev:.2f} eV"
                )
            if experiment.ejects_electrons is not None:
                if experiment.ejects_electrons:
                    exp_lines.append(
                        "- outcome (deterministic, KE_max = hf - phi, computed by the app): "
                        f"electrons ejected with maximum kinetic energy {experiment.ke_max_ev:.2f} eV, "
                        f"at a rate proportional to intensity ({experiment.photoelectron_rate:.1f})"
                    )
                else:
                    exp_lines.append(
                        "- outcome (deterministic, KE_max = hf - phi, computed by the app): "
                        "no electrons ejected at all, no matter how high the intensity is set -- "
                        "the photon energy is below the work function"
                    )
        elif experiment.simulation_type == "electromagnetic_induction":
            if experiment.coil_turns is not None:
                exp_lines.append(
                    f"- setup: {experiment.coil_turns:.0f} turns, area = "
                    f"{experiment.coil_area_m2:.3f} m^2, field went from "
                    f"{experiment.field_initial_t:.2f} T to {experiment.field_final_t:.2f} T "
                    f"over {experiment.time_interval_s:.2f} s"
                )
            if experiment.induced_emf_v is not None:
                direction = "increasing" if experiment.flux_increasing else "decreasing"
                exp_lines.append(
                    "- induced EMF (deterministic, EMF = N|delta Phi|/delta t, computed by "
                    f"the app): {experiment.induced_emf_v:.2f} V, with the flux {direction} "
                    "(by Lenz's law, the induced current opposes that change)"
                )
        elif experiment.simulation_type == "bohr_model":
            if experiment.initial_level is not None:
                exp_lines.append(
                    f"- setup: electron transition from level n={experiment.initial_level} "
                    f"to level n={experiment.final_level} (E_n = -13.6 eV / n^2)"
                )
            if experiment.bohr_photon_energy_ev is not None:
                if not experiment.has_transition:
                    exp_lines.append(
                        "- outcome (deterministic, computed by the app): no transition -- "
                        "the initial and final levels are the same, so no photon is involved"
                    )
                else:
                    verb = "absorbs" if experiment.is_bohr_absorption else "emits"
                    exp_lines.append(
                        f"- outcome (deterministic, computed by the app): the electron {verb} "
                        f"a photon of energy {experiment.bohr_photon_energy_ev:.2f} eV "
                        f"(wavelength {experiment.bohr_wavelength_nm:.1f} nm)"
                    )
        elif experiment.simulation_type == "hubbles_law":
            if experiment.distance_mpc is not None:
                exp_lines.append(
                    f"- setup: a galaxy at distance = {experiment.distance_mpc:.1f} Mpc, "
                    f"Hubble constant H0 = {experiment.hubble_constant_km_s_mpc:.1f} km/s/Mpc"
                )
            if experiment.recession_velocity_km_s is not None:
                exp_lines.append(
                    "- outcome (deterministic, v = H0 d, computed by the app): recession "
                    f"speed = {experiment.recession_velocity_km_s:.1f} km/s, redshift z = "
                    f"{experiment.redshift_z:.5f} (z = v / c)"
                )
        elif experiment.simulation_type == "particle_physics":
            if experiment.rest_energy_mev is not None:
                exp_lines.append(
                    f"- setup: rest energy mc^2 = {experiment.rest_energy_mev:.2f} MeV, "
                    f"momentum pc = {experiment.momentum_mev_c:.2f} MeV"
                )
            if experiment.total_energy_mev is not None:
                exp_lines.append(
                    "- outcome (deterministic, E^2 = (pc)^2 + (mc^2)^2, computed by the "
                    f"app): total energy = {experiment.total_energy_mev:.2f} MeV, kinetic "
                    f"energy = {experiment.kinetic_energy_mev:.2f} MeV, speed = "
                    f"{experiment.velocity_fraction_c:.3f}c"
                )
        else:
            if experiment.mass_kg is not None and experiment.force_n is not None:
                exp_lines.append(
                    f"- setup: mass = {experiment.mass_kg:.2f} kg, "
                    f"net force = {experiment.force_n:.2f} N"
                )
            if experiment.acceleration_m_s2 is not None:
                exp_lines.append(
                    f"- acceleration (deterministic a = F / m, computed by the app): "
                    f"{experiment.acceleration_m_s2:.2f} m/s^2"
                )
        if experiment.prediction:
            exp_lines.append(f"- their prediction beforehand: {experiment.prediction}")
        if experiment.observation:
            exp_lines.append(f"- what they observed: {experiment.observation}")
        if experiment.explanation:
            exp_lines.append(f"- their explanation: {experiment.explanation}")
        exp_lines.append(
            "Compare their prediction with what happened, respond to their "
            "reasoning, and pose a next question (for example, what if the mass "
            "changed instead)."
        )
        experiment_block = "\n".join(exp_lines) + "\n"

    practice_block = ""
    if request.practice_problem:
        practice_block = f"\nPractice problem the student is working on:\n{request.practice_problem}\n"
    if request.student_attempt:
        practice_block += (
            f"\nStudent attempt to review:\n{request.student_attempt}\n"
        )

    current_input = (
        request.student_question
        or request.student_attempt
        or "(the student has not typed anything specific)"
    )

    user = f"""Help the student with this lesson.

Lesson title: {request.lesson_title}
Topic: {request.topic}
Grade level: {request.grade_level}

Learning objectives:
{objectives}

Teacher-listed misconceptions to watch for:
{misconceptions}

Physics concepts (authoritative):
{concept_blocks}

{candidate_block}

{experiment_block}
Recent conversation (oldest first):
{conversation}
{practice_block}
Student's current message:
{current_input}
"""

    return Prompt(system=system.strip(), user=user.strip(), version=TUTOR_PROMPT_VERSION)
