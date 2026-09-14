from __future__ import annotations

from dataclasses import dataclass

from apps.ai.requests import ConceptContext

RECENT_MESSAGE_LIMIT = 6


@dataclass(frozen=True)
class TutorConversationMessage:
    """One prior turn supplied to the tutor for context."""

    role: str
    content: str

    def __post_init__(self):
        object.__setattr__(self, "role", str(self.role).strip().lower())
        object.__setattr__(self, "content", str(self.content).strip())


@dataclass(frozen=True)
class CandidateHint:
    """A possible misconception the tutor may gently probe.

    This is context for the tutor only. It must never be shown to the student
    as a label or verdict.
    """

    concept: str
    title: str
    description: str
    intervention_guidance: str = ""
    confidence: str = "low"

    def __post_init__(self):
        object.__setattr__(self, "concept", str(self.concept).strip())
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(
            self, "intervention_guidance", str(self.intervention_guidance).strip()
        )
        object.__setattr__(self, "confidence", str(self.confidence).strip().lower())


@dataclass(frozen=True)
class ExperimentContext:
    """A completed (or in-progress) Physics Lab experiment, as tutor context.

    The numeric fields are the server-recomputed deterministic values, so the
    tutor reasons about the same values the app computed, not a browser
    number. ``mass_kg``/``force_n`` are Newton's Second Law-specific;
    ``initial_position_m``/``initial_velocity_m_s``/``position_m``/
    ``velocity_m_s`` are Kinematics-specific; ``initial_speed_m_s``/
    ``launch_angle_deg``/``initial_height_m``/``position_x_m``/
    ``position_y_m`` are Projectile Motion-specific; ``radius_m``/
    ``period_s`` are Circular Motion-specific (which also reuses
    ``position_x_m``/``position_y_m``/``velocity_m_s`` for its own position
    and speed); ``amplitude_m`` is Simple Harmonic Motion-specific (which
    reuses ``period_s``/``position_m``/``velocity_m_s``/
    ``acceleration_m_s2``); ``mass1_kg``/``mass2_kg``/``elastic``/
    ``position_1_m``/``position_2_m``/``velocity_1_m_s``/``velocity_2_m_s``/
    ``has_collided``/``momentum_total_kg_m_s``/``kinetic_energy_total_j``
    are Momentum/Collision-specific (which reuses ``initial_velocity_m_s``
    for cart 1's starting speed); ``height_m``/``angle_deg``/``distance_m``/
    ``height_dropped_m``/``kinetic_energy_j``/``potential_energy_j``/
    ``total_energy_j`` are Energy-on-an-Incline-specific (which reuses
    ``mass_kg`` and ``velocity_m_s`` for its own mass and speed). ``mu`` is
    Orbital-Motion-specific (which reuses ``radius_m``/``period_s``/
    ``position_x_m``/``position_y_m``/``velocity_m_s`` from Circular Motion
    for its own radius, period, position and speed). ``time_s`` and
    ``acceleration_m_s2`` are shared where they apply (``acceleration_m_s2``
    is Circular Motion's centripetal acceleration, Simple Harmonic Motion's
    restoring acceleration, or Orbital Motion's gravitational/centripetal
    acceleration). ``voltage_v``/``resistance1_ohm``/``resistance2_ohm``/
    ``is_series``/``total_resistance_ohm``/``total_current_a``/
    ``current_1_a``/``current_2_a``/``voltage_1_v``/``voltage_2_v``/
    ``total_power_w`` are Series/Parallel-Circuit-specific -- there is no
    motion here at all, so this simulation shares no fields with any other.
    ``charge1_uc``/``charge2_uc``/``coulomb_separation_m``/
    ``coulomb_force_n``/``is_attractive``/``coulomb_potential_energy_j`` are
    Coulomb's-Law-specific -- deliberately NOT sharing Orbital Motion's
    ``radius_m``/``force_n``, since that would wrongly imply the same
    physical meaning: gravity is always attractive, Coulomb's force can
    attract or repel. ``initial_count``/``half_life_s``/``remaining_count``/
    ``decayed_count``/``remaining_fraction``/``activity_per_s`` are
    Radioactive-Decay-specific (reusing shared ``time_s``) -- the first
    simulation whose quantity never returns to an earlier value, unlike
    every periodic/orbiting/oscillating one above. ``object_density_kg_m3``/
    ``fluid_density_kg_m3``/``volume_m3``/``buoyant_force_n``/
    ``submerged_fraction``/``floats`` are Buoyancy-specific (which reuses
    ``force_n`` for its net force -- 0 while floating in equilibrium,
    positive/downward while sinking -- since that IS a genuine single-object
    net force, the same meaning ``force_n`` has for Newton's Second Law,
    unlike Coulomb's Law's mutual two-charge force). ``n1``/``n2``/
    ``angle1_deg``/``angle2_deg``/``has_critical_angle``/
    ``critical_angle_deg``/``total_internal_reflection`` are Refraction-
    specific (deliberately NOT reusing Energy-on-an-Incline's ``angle_deg``,
    a different physical angle entirely). ``specific_heat1``/
    ``specific_heat2``/``temp1_c``/``temp2_c``/``equilibrium_temp_c``/
    ``heat_transferred_j`` are Calorimetry-specific (which reuses
    ``mass1_kg``/``mass2_kg`` from Momentum/Collision -- the same plain
    "mass of object 1/2" meaning in both). ``moles``/``temperature_k``/
    ``pressure_pa`` are Ideal-Gas-Law-specific (which reuses
    ``volume_m3`` from Buoyancy -- the same plain "volume" meaning in
    both). ``source_freq_hz``/``source_velocity_m_s``/
    ``observer_velocity_m_s``/``observed_freq_hz`` are Doppler-Effect-
    specific. ``charge_magnitude_c``/``is_positive_charge``/``field_t`` are
    Magnetic-Force-specific (which reuses ``mass_kg`` from Newton's Second
    Law, ``force_n`` from Buoyancy, ``radius_m``/``period_s``/
    ``position_x_m``/``position_y_m`` from Circular Motion, and
    ``velocity_m_s`` for the particle's -- always constant -- speed; the
    magnetic force changes direction but never speed, which is the whole
    point of this lab). ``velocity_fraction_c``/``proper_time_s``/
    ``proper_length_m``/``lorentz_factor``/``dilated_time_s``/
    ``contracted_length_m`` are Time-Dilation-specific.
    ``wavelength_nm``/``work_function_ev``/``light_intensity``/
    ``photon_energy_ev``/``ejects_electrons``/``ke_max_ev``/
    ``photoelectron_rate`` are Photoelectric-Effect-specific. A given
    experiment only ever populates the fields for its own simulation type
    -- the rest stay ``None``.
    """

    simulation: str = ""
    simulation_type: str = ""
    mass_kg: float | None = None
    force_n: float | None = None
    acceleration_m_s2: float | None = None
    initial_position_m: float | None = None
    initial_velocity_m_s: float | None = None
    time_s: float | None = None
    position_m: float | None = None
    velocity_m_s: float | None = None
    initial_speed_m_s: float | None = None
    launch_angle_deg: float | None = None
    initial_height_m: float | None = None
    position_x_m: float | None = None
    position_y_m: float | None = None
    radius_m: float | None = None
    period_s: float | None = None
    amplitude_m: float | None = None
    mass1_kg: float | None = None
    mass2_kg: float | None = None
    elastic: float | None = None
    position_1_m: float | None = None
    position_2_m: float | None = None
    velocity_1_m_s: float | None = None
    velocity_2_m_s: float | None = None
    has_collided: bool | None = None
    momentum_total_kg_m_s: float | None = None
    kinetic_energy_total_j: float | None = None
    height_m: float | None = None
    angle_deg: float | None = None
    distance_m: float | None = None
    height_dropped_m: float | None = None
    kinetic_energy_j: float | None = None
    potential_energy_j: float | None = None
    total_energy_j: float | None = None
    mu: float | None = None
    voltage_v: float | None = None
    resistance1_ohm: float | None = None
    resistance2_ohm: float | None = None
    is_series: bool | None = None
    total_resistance_ohm: float | None = None
    total_current_a: float | None = None
    current_1_a: float | None = None
    current_2_a: float | None = None
    voltage_1_v: float | None = None
    voltage_2_v: float | None = None
    total_power_w: float | None = None
    charge1_uc: float | None = None
    charge2_uc: float | None = None
    coulomb_separation_m: float | None = None
    coulomb_force_n: float | None = None
    is_attractive: bool | None = None
    coulomb_potential_energy_j: float | None = None
    initial_count: float | None = None
    half_life_s: float | None = None
    remaining_count: float | None = None
    decayed_count: float | None = None
    remaining_fraction: float | None = None
    activity_per_s: float | None = None
    object_density_kg_m3: float | None = None
    fluid_density_kg_m3: float | None = None
    volume_m3: float | None = None
    buoyant_force_n: float | None = None
    submerged_fraction: float | None = None
    floats: bool | None = None
    n1: float | None = None
    n2: float | None = None
    angle1_deg: float | None = None
    angle2_deg: float | None = None
    has_critical_angle: bool | None = None
    critical_angle_deg: float | None = None
    total_internal_reflection: bool | None = None
    specific_heat1: float | None = None
    specific_heat2: float | None = None
    temp1_c: float | None = None
    temp2_c: float | None = None
    equilibrium_temp_c: float | None = None
    heat_transferred_j: float | None = None
    moles: float | None = None
    temperature_k: float | None = None
    pressure_pa: float | None = None
    source_freq_hz: float | None = None
    source_velocity_m_s: float | None = None
    observer_velocity_m_s: float | None = None
    observed_freq_hz: float | None = None
    charge_magnitude_c: float | None = None
    is_positive_charge: bool | None = None
    field_t: float | None = None
    velocity_fraction_c: float | None = None
    proper_time_s: float | None = None
    proper_length_m: float | None = None
    lorentz_factor: float | None = None
    dilated_time_s: float | None = None
    contracted_length_m: float | None = None
    wavelength_nm: float | None = None
    work_function_ev: float | None = None
    light_intensity: float | None = None
    photon_energy_ev: float | None = None
    ejects_electrons: bool | None = None
    ke_max_ev: float | None = None
    photoelectron_rate: float | None = None
    prediction: str = ""
    observation: str = ""
    explanation: str = ""

    def __post_init__(self):
        object.__setattr__(self, "simulation", str(self.simulation or "").strip())
        object.__setattr__(self, "simulation_type", str(self.simulation_type or "").strip())
        for name in ("prediction", "observation", "explanation"):
            object.__setattr__(self, name, str(getattr(self, name) or "").strip())

    @property
    def has_content(self) -> bool:
        return any(
            [
                self.prediction,
                self.observation,
                self.explanation,
                self.mass_kg is not None,
                self.force_n is not None,
                self.acceleration_m_s2 is not None,
                self.initial_position_m is not None,
                self.initial_velocity_m_s is not None,
                self.position_m is not None,
                self.velocity_m_s is not None,
                self.initial_speed_m_s is not None,
                self.launch_angle_deg is not None,
                self.position_x_m is not None,
                self.position_y_m is not None,
                self.radius_m is not None,
                self.period_s is not None,
                self.amplitude_m is not None,
                self.mass1_kg is not None,
                self.mass2_kg is not None,
                self.position_1_m is not None,
                self.position_2_m is not None,
                self.height_m is not None,
                self.distance_m is not None,
                self.mu is not None,
                self.voltage_v is not None,
                self.total_current_a is not None,
                self.charge1_uc is not None,
                self.initial_count is not None,
                self.object_density_kg_m3 is not None,
                self.n1 is not None,
                self.equilibrium_temp_c is not None,
                self.moles is not None,
                self.source_freq_hz is not None,
                self.charge_magnitude_c is not None,
                self.lorentz_factor is not None,
                self.wavelength_nm is not None,
            ]
        )

    @classmethod
    def from_attempt(cls, attempt) -> "ExperimentContext":
        simulation = getattr(attempt, "simulation", None)
        if simulation is not None and hasattr(simulation, "get_simulation_type_display"):
            label = simulation.get_simulation_type_display()
        else:
            label = str(simulation) if simulation is not None else ""
        simulation_type = getattr(simulation, "simulation_type", "") or ""

        kwargs = dict(
            simulation=label,
            simulation_type=simulation_type,
            acceleration_m_s2=attempt.acceleration_m_s2,
            prediction=attempt.prediction,
            observation=attempt.observation,
            explanation=attempt.explanation,
        )
        if simulation_type == "kinematics":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                initial_position_m=params.get("initial_position_m"),
                initial_velocity_m_s=params.get("initial_velocity_m_s"),
                time_s=params.get("observed_time_s"),
                position_m=params.get("observed_position_m"),
                velocity_m_s=params.get("observed_velocity_m_s"),
            )
        elif simulation_type == "projectile_motion":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                initial_speed_m_s=params.get("initial_speed_m_s"),
                launch_angle_deg=params.get("launch_angle_deg"),
                initial_height_m=params.get("initial_height_m"),
                time_s=params.get("observed_time_s"),
                position_x_m=params.get("observed_position_x_m"),
                position_y_m=params.get("observed_position_y_m"),
            )
        elif simulation_type == "circular_motion":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                radius_m=params.get("radius_m"),
                period_s=params.get("period_s"),
                time_s=params.get("observed_time_s"),
                position_x_m=params.get("observed_position_x_m"),
                position_y_m=params.get("observed_position_y_m"),
                velocity_m_s=params.get("observed_speed_m_s"),
            )
        elif simulation_type == "simple_harmonic_motion":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                amplitude_m=params.get("amplitude_m"),
                period_s=params.get("period_s"),
                time_s=params.get("observed_time_s"),
                position_m=params.get("observed_position_m"),
                velocity_m_s=params.get("observed_velocity_m_s"),
            )
        elif simulation_type == "momentum_collision":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                mass1_kg=params.get("mass1_kg"),
                mass2_kg=params.get("mass2_kg"),
                initial_velocity_m_s=params.get("initial_velocity_m_s"),
                elastic=params.get("elastic"),
                time_s=params.get("observed_time_s"),
                position_1_m=params.get("observed_position_1_m"),
                position_2_m=params.get("observed_position_2_m"),
                velocity_1_m_s=params.get("observed_velocity_1_m_s"),
                velocity_2_m_s=params.get("observed_velocity_2_m_s"),
                has_collided=params.get("observed_has_collided"),
                momentum_total_kg_m_s=params.get("observed_momentum_total_kg_m_s"),
                kinetic_energy_total_j=params.get("observed_kinetic_energy_total_j"),
            )
        elif simulation_type == "energy_incline":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                mass_kg=attempt.mass_kg,
                height_m=params.get("height_m"),
                angle_deg=params.get("angle_deg"),
                time_s=params.get("observed_time_s"),
                distance_m=params.get("observed_distance_m"),
                height_dropped_m=params.get("observed_height_dropped_m"),
                velocity_m_s=params.get("observed_speed_m_s"),
                kinetic_energy_j=params.get("observed_kinetic_energy_j"),
                potential_energy_j=params.get("observed_potential_energy_j"),
                total_energy_j=params.get("observed_total_energy_j"),
            )
        elif simulation_type == "orbital_motion":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                mu=params.get("mu"),
                radius_m=params.get("radius_m"),
                period_s=params.get("observed_period_s"),
                time_s=params.get("observed_time_s"),
                position_x_m=params.get("observed_position_x_m"),
                position_y_m=params.get("observed_position_y_m"),
                velocity_m_s=params.get("observed_speed_m_s"),
            )
        elif simulation_type == "series_parallel_circuit":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            series_flag = params.get("series")
            kwargs.update(
                voltage_v=params.get("voltage_v"),
                resistance1_ohm=params.get("resistance1_ohm"),
                resistance2_ohm=params.get("resistance2_ohm"),
                is_series=(series_flag >= 0.5) if series_flag is not None else None,
                total_resistance_ohm=params.get("observed_total_resistance_ohm"),
                total_current_a=params.get("observed_total_current_a"),
                current_1_a=params.get("observed_current_1_a"),
                current_2_a=params.get("observed_current_2_a"),
                voltage_1_v=params.get("observed_voltage_1_v"),
                voltage_2_v=params.get("observed_voltage_2_v"),
                total_power_w=params.get("observed_total_power_w"),
            )
        elif simulation_type == "coulombs_law":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                charge1_uc=params.get("charge1_uc"),
                charge2_uc=params.get("charge2_uc"),
                coulomb_separation_m=params.get("separation_m"),
                coulomb_force_n=params.get("observed_force_n"),
                is_attractive=params.get("observed_is_attractive"),
                coulomb_potential_energy_j=params.get("observed_potential_energy_j"),
            )
        elif simulation_type == "radioactive_decay":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                initial_count=params.get("initial_count"),
                half_life_s=params.get("half_life_s"),
                time_s=params.get("observed_time_s"),
                remaining_count=params.get("observed_remaining_count"),
                decayed_count=params.get("observed_decayed_count"),
                remaining_fraction=params.get("observed_remaining_fraction"),
                activity_per_s=params.get("observed_activity_per_s"),
            )
        elif simulation_type == "buoyancy":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                force_n=attempt.force_n,
                object_density_kg_m3=params.get("object_density_kg_m3"),
                fluid_density_kg_m3=params.get("fluid_density_kg_m3"),
                volume_m3=params.get("volume_m3"),
                buoyant_force_n=params.get("observed_buoyant_force_n"),
                submerged_fraction=params.get("observed_submerged_fraction"),
                floats=params.get("observed_floats"),
            )
        elif simulation_type == "refraction":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                n1=params.get("n1"),
                n2=params.get("n2"),
                angle1_deg=params.get("angle1_deg"),
                has_critical_angle=params.get("observed_has_critical_angle"),
                critical_angle_deg=params.get("observed_critical_angle_deg"),
                total_internal_reflection=params.get("observed_total_internal_reflection"),
                angle2_deg=params.get("observed_angle2_deg"),
            )
        elif simulation_type == "calorimetry":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                mass1_kg=params.get("mass1_kg"),
                specific_heat1=params.get("specific_heat1"),
                temp1_c=params.get("temp1_c"),
                mass2_kg=params.get("mass2_kg"),
                specific_heat2=params.get("specific_heat2"),
                temp2_c=params.get("temp2_c"),
                equilibrium_temp_c=params.get("observed_equilibrium_temp_c"),
                heat_transferred_j=params.get("observed_heat_transferred_j"),
            )
        elif simulation_type == "ideal_gas_law":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                moles=params.get("moles"),
                temperature_k=params.get("temperature_k"),
                volume_m3=params.get("volume_m3"),
                pressure_pa=params.get("observed_pressure_pa"),
            )
        elif simulation_type == "doppler_effect":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                source_freq_hz=params.get("source_freq_hz"),
                source_velocity_m_s=params.get("source_velocity_m_s"),
                observer_velocity_m_s=params.get("observer_velocity_m_s"),
                observed_freq_hz=params.get("observed_freq_hz"),
            )
        elif simulation_type == "magnetic_force":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            sign_flag = params.get("positive_charge")
            kwargs.update(
                mass_kg=attempt.mass_kg,
                force_n=attempt.force_n,
                charge_magnitude_c=params.get("charge_magnitude_c"),
                is_positive_charge=(sign_flag >= 0.5) if sign_flag is not None else None,
                field_t=params.get("field_t"),
                radius_m=params.get("observed_radius_m"),
                period_s=params.get("observed_period_s"),
                time_s=params.get("observed_time_s"),
                position_x_m=params.get("observed_position_x_m"),
                position_y_m=params.get("observed_position_y_m"),
                velocity_m_s=params.get("speed_m_s"),
            )
        elif simulation_type == "time_dilation":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                velocity_fraction_c=params.get("velocity_fraction_c"),
                proper_time_s=params.get("proper_time_s"),
                proper_length_m=params.get("proper_length_m"),
                lorentz_factor=params.get("observed_lorentz_factor"),
                dilated_time_s=params.get("observed_dilated_time_s"),
                contracted_length_m=params.get("observed_contracted_length_m"),
            )
        elif simulation_type == "photoelectric_effect":
            params = attempt.parameters if isinstance(attempt.parameters, dict) else {}
            kwargs.update(
                wavelength_nm=params.get("wavelength_nm"),
                work_function_ev=params.get("work_function_ev"),
                light_intensity=params.get("intensity"),
                photon_energy_ev=params.get("observed_photon_energy_ev"),
                ejects_electrons=params.get("observed_ejects_electrons"),
                ke_max_ev=params.get("observed_ke_max_ev"),
                photoelectron_rate=params.get("observed_photoelectron_rate"),
            )
        else:
            kwargs.update(mass_kg=attempt.mass_kg, force_n=attempt.force_n)
        return cls(**kwargs)


@dataclass(frozen=True)
class TutorRequest:
    """Immutable context passed to the tutoring service.

    Kept separate from the database models so it can be built and tested
    without persistence.
    """

    lesson_title: str
    topic: str
    grade_level: str
    learning_objectives: tuple[str, ...] = ()
    common_misconceptions: tuple[str, ...] = ()
    concepts: tuple[ConceptContext, ...] = ()
    recent_messages: tuple[TutorConversationMessage, ...] = ()
    candidate_misconceptions: tuple[CandidateHint, ...] = ()
    experiment: "ExperimentContext | None" = None
    student_question: str = ""
    practice_problem: str = ""
    student_attempt: str = ""

    def __post_init__(self):
        object.__setattr__(self, "lesson_title", self.lesson_title.strip())
        object.__setattr__(self, "topic", self.topic.strip())
        object.__setattr__(self, "grade_level", str(self.grade_level).strip())
        object.__setattr__(
            self,
            "learning_objectives",
            tuple(str(item).strip() for item in self.learning_objectives if str(item).strip()),
        )
        object.__setattr__(
            self,
            "common_misconceptions",
            tuple(
                str(item).strip()
                for item in self.common_misconceptions
                if str(item).strip()
            ),
        )
        object.__setattr__(self, "concepts", tuple(self.concepts))
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))
        object.__setattr__(
            self, "candidate_misconceptions", tuple(self.candidate_misconceptions)
        )
        object.__setattr__(self, "student_question", self.student_question.strip())
        object.__setattr__(self, "practice_problem", self.practice_problem.strip())
        object.__setattr__(self, "student_attempt", self.student_attempt.strip())

        if not self.lesson_title:
            raise ValueError("lesson_title is required")
        if not self.topic:
            raise ValueError("topic is required")
        if not self.grade_level:
            raise ValueError("grade_level is required")
        if not self.student_question and not self.student_attempt:
            raise ValueError("a student question or a practice attempt is required")
        if not all(isinstance(concept, ConceptContext) for concept in self.concepts):
            raise ValueError("concepts must be ConceptContext instances")
        if self.experiment is not None and not isinstance(
            self.experiment, ExperimentContext
        ):
            raise ValueError("experiment must be an ExperimentContext instance")

    @property
    def is_practice_turn(self) -> bool:
        return bool(self.student_attempt)

    @classmethod
    def from_session(
        cls,
        session,
        *,
        student_question: str = "",
        practice_problem: str = "",
        student_attempt: str = "",
        candidate_misconceptions: tuple[CandidateHint, ...] = (),
        experiment: "ExperimentContext | None" = None,
        recent_limit: int = RECENT_MESSAGE_LIMIT,
    ) -> "TutorRequest":
        lesson = session.lesson
        messages = list(session.messages.all())
        if recent_limit:
            messages = messages[-recent_limit:]

        return cls(
            lesson_title=lesson.title,
            topic=lesson.topic,
            grade_level=lesson.grade_level,
            learning_objectives=tuple(lesson.learning_objectives or []),
            common_misconceptions=tuple(lesson.common_misconceptions or []),
            concepts=tuple(
                ConceptContext.from_concept(concept)
                for concept in lesson.physics_concepts.all()
            ),
            recent_messages=tuple(
                TutorConversationMessage(role=message.role, content=message.content)
                for message in messages
            ),
            candidate_misconceptions=tuple(candidate_misconceptions),
            experiment=experiment,
            student_question=student_question,
            practice_problem=practice_problem,
            student_attempt=student_attempt,
        )
