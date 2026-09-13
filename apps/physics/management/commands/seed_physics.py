from django.core.management.base import BaseCommand

from apps.physics.models import PhysicsConcept


PHYSICS_CONCEPTS = [
    {
        "name": "Position",
        "description": "A location described relative to a chosen reference point or coordinate system.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "common_misconceptions": [
            "Position and distance always mean the same thing.",
            "A position can be stated without a reference point.",
        ],
        "prerequisites": [],
        "equations": [],
        "si_units": ["metre (m)"],
    },
    {
        "name": "Distance",
        "description": "The total length of the path travelled by an object; it is a scalar quantity.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "common_misconceptions": [
            "Distance can be negative.",
            "Distance and displacement are always equal.",
        ],
        "prerequisites": ["Position"],
        "equations": [],
        "si_units": ["metre (m)"],
    },
    {
        "name": "Displacement",
        "description": "The change in position from an initial point to a final point, including direction.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Displacement is the same as the total path length.",
            "A round trip must have a nonzero displacement.",
        ],
        "prerequisites": ["Position"],
        "equations": ["Δx = x_f − x_i"],
        "si_units": ["metre (m)"],
    },
    {
        "name": "Speed",
        "description": "The rate at which distance is travelled; speed is a scalar quantity.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Speed and velocity are interchangeable.",
            "A constant speed always means a constant velocity.",
        ],
        "prerequisites": ["Distance"],
        "equations": ["speed = distance / time"],
        "si_units": ["metre per second (m/s)"],
    },
    {
        "name": "Velocity",
        "description": "The rate of change of displacement; velocity includes both magnitude and direction.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Velocity is just speed with a different name.",
            "An object moving at constant speed cannot have changing velocity.",
        ],
        "prerequisites": ["Displacement", "Speed"],
        "equations": ["v = Δx / Δt"],
        "si_units": ["metre per second (m/s)"],
    },
    {
        "name": "Acceleration",
        "description": "The rate of change of velocity over time; it can result from a change in speed, direction, or both.",
        "topic": "Kinematics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Acceleration only means speeding up.",
            "An object moving at constant speed cannot accelerate.",
        ],
        "prerequisites": ["Velocity"],
        "equations": ["a = Δv / Δt"],
        "si_units": ["metre per second squared (m/s²)"],
    },
    {
        "name": "Force",
        "description": "An interaction that can change an object's motion; the net force determines acceleration.",
        "topic": "Dynamics",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "A moving object needs a force to keep moving at constant velocity.",
            "Forces are properties stored inside moving objects.",
        ],
        "prerequisites": ["Acceleration"],
        "equations": ["F_net = ma"],
        "si_units": ["newton (N)", "1 N = 1 kg·m/s²"],
    },
    {
        "name": "Newton's First Law",
        "description": "An object remains at rest or moves with constant velocity unless acted on by a nonzero net external force.",
        "topic": "Dynamics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "A force is needed to keep an object moving at constant velocity.",
            "No forces act on an object that has zero net force.",
        ],
        "prerequisites": ["Velocity", "Force"],
        "equations": ["ΣF = 0 → velocity is constant"],
        "si_units": ["newton (N)"],
    },
    {
        "name": "Newton's Second Law",
        "description": "An object's acceleration is determined by the net force acting on it and its mass.",
        "topic": "Dynamics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "More mass always means more acceleration.",
            "Any single force, rather than the net force, determines acceleration.",
        ],
        "prerequisites": ["Force", "Acceleration"],
        "equations": ["F_net = ma"],
        "si_units": ["force: newton (N)", "mass: kilogram (kg)", "acceleration: m/s²"],
    },
    {
        "name": "Newton's Third Law",
        "description": "When one object exerts a force on another, the second object exerts an equal-magnitude, opposite-direction force on the first.",
        "topic": "Dynamics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Action and reaction forces cancel because they act on the same object.",
            "The larger or heavier object exerts the larger force in an interaction pair.",
        ],
        "prerequisites": ["Force"],
        "equations": ["F_A on B = −F_B on A"],
        "si_units": ["newton (N)"],
    },
]

# The standard high-school/intro-college topic set for every curriculum domain
# in ``apps.physics.domain_catalog`` beyond Kinematics/Dynamics above -- fills
# out the Physics Library across all 23 domains. Same shape as the entries
# above; ``topic`` matches (or extends) the topic strings in domain_catalog so
# each concept lands under the right domain there. Optional keys are omitted
# rather than set to an empty value -- PhysicsConcept's own field defaults
# (empty list) already cover that.
PHYSICS_TOPICS = [
    # --- Introduction to Physics -------------------------------------------
    {
        "name": "Scalars and vectors",
        "description": (
            "A scalar is fully described by a magnitude alone (e.g. distance, speed, "
            "mass); a vector has both magnitude and direction (e.g. displacement, "
            "velocity, force). Vector quantities must be combined using vector "
            "methods, not simple arithmetic."
        ),
        "topic": "Introduction",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "common_misconceptions": [
            "Treating a vector quantity (like velocity or force) as if only its "
            "size mattered, ignoring direction.",
        ],
    },
    {
        "name": "SI base units",
        "description": (
            "Physics measurements are expressed in the International System of "
            "Units (SI): the metre, kilogram, second, ampere, kelvin, mole and "
            "candela. Every other physical unit is derived from these seven."
        ),
        "topic": "Units",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "si_units": ["m (metre)", "kg (kilogram)", "s (second)", "A (ampere)",
                      "K (kelvin)", "mol (mole)", "cd (candela)"],
    },
    {
        "name": "Measurement uncertainty and significant figures",
        "description": (
            "Every measurement carries some uncertainty. Significant figures "
            "communicate the precision of a measured value, and a calculated "
            "result can be no more precise than the least precise measurement "
            "used to obtain it."
        ),
        "topic": "Measurement",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "common_misconceptions": [
            "Believing a calculator's full decimal display is all 'accurate', "
            "regardless of the precision of the original measurements.",
        ],
    },
    # --- Kinematics (new subtopics) -----------------------------------------
    {
        "name": "Free fall",
        "description": (
            "An object in free fall moves under gravity alone, with no air "
            "resistance. Near Earth's surface, every object in free fall gains "
            "the same downward velocity each second, regardless of its mass."
        ),
        "topic": "Free Fall",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Heavier objects fall faster than lighter ones in free fall (true "
            "only when air resistance dominates, not in true free fall).",
        ],
        "equations": ["v = g t (from rest)", "h = 1/2 g t^2 (from rest)"],
        "si_units": ["m/s^2"],
    },
    {
        "name": "Projectile motion",
        "description": (
            "A projectile's horizontal and vertical motions are independent: "
            "horizontal velocity stays constant (ignoring air resistance) while "
            "the vertical motion accelerates under gravity, giving the classic "
            "parabolic path."
        ),
        "topic": "Projectile Motion",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Believing a projectile's horizontal velocity decreases as it "
            "rises, or that it 'runs out of speed' at the top of its arc.",
        ],
        "equations": ["x = v0 cos(theta) t", "y = v0 sin(theta) t - 1/2 g t^2"],
        "si_units": ["m", "m/s", "s"],
    },
    # --- Dynamics (new subtopics) --------------------------------------------
    {
        "name": "Friction",
        "description": (
            "Friction is a contact force that opposes relative sliding between "
            "two surfaces. Static friction resists the start of motion up to a "
            "maximum value; kinetic friction acts once surfaces are sliding and "
            "is usually smaller than that maximum."
        ),
        "topic": "Friction",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Assuming friction always opposes 'motion' rather than opposing "
            "relative sliding -- friction can act in the direction of motion, "
            "e.g. providing the forward force for walking.",
        ],
        "equations": ["f_s(max) = mu_s N", "f_k = mu_k N"],
        "si_units": ["N"],
    },
    {
        "name": "Motion on an inclined plane",
        "description": (
            "On a frictionless incline, gravity is resolved into a component "
            "along the slope (which accelerates the object) and a component "
            "perpendicular to the slope (balanced by the normal force). Both "
            "depend on the incline angle."
        ),
        "topic": "Inclined Plane",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["a = g sin(theta)", "N = m g cos(theta)"],
        "si_units": ["m/s^2", "N"],
    },
    # --- Work, Energy and Power ----------------------------------------------
    {
        "name": "Work done by a force",
        "description": (
            "Work is done on an object when a force causes a displacement in "
            "the direction of the force. Only the component of the force along "
            "the displacement contributes; a force perpendicular to motion does "
            "no work."
        ),
        "topic": "Work",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Believing that holding a heavy object still, or carrying it at "
            "constant height, does physics 'work' on it.",
        ],
        "equations": ["W = F d cos(theta)"],
        "si_units": ["J"],
    },
    {
        "name": "Kinetic energy",
        "description": (
            "Kinetic energy is the energy an object has because of its motion. "
            "It grows with the square of speed, so doubling an object's speed "
            "quadruples its kinetic energy."
        ),
        "topic": "Energy",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["KE = 1/2 m v^2"],
        "si_units": ["J"],
    },
    {
        "name": "Gravitational potential energy",
        "description": (
            "Gravitational potential energy is stored energy due to an object's "
            "position in a gravitational field. Near Earth's surface it depends "
            "on mass, gravitational field strength and height above a chosen "
            "reference level."
        ),
        "topic": "Energy",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["PE = m g h"],
        "si_units": ["J"],
    },
    {
        "name": "Conservation of mechanical energy",
        "description": (
            "In a system with no friction or other non-conservative forces, "
            "total mechanical energy (kinetic plus potential) stays constant, "
            "even as energy converts between the two forms."
        ),
        "topic": "Work and Energy",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Believing energy is 'used up' or destroyed rather than "
            "transformed or transferred to another form such as heat.",
        ],
        "equations": ["KE_i + PE_i = KE_f + PE_f (no friction)"],
        "si_units": ["J"],
    },
    {
        "name": "Power",
        "description": (
            "Power is the rate at which work is done or energy is transferred. "
            "Two machines can do the same amount of work, but the one that "
            "does it faster has a higher power output."
        ),
        "topic": "Power",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Confusing power with energy or force -- e.g. assuming a more "
            "'powerful' engine necessarily produces more total energy rather "
            "than delivering energy faster.",
        ],
        "equations": ["P = W / t"],
        "si_units": ["W"],
    },
    # --- Momentum and Collisions ----------------------------------------------
    {
        "name": "Impulse and momentum",
        "description": (
            "Momentum is the product of an object's mass and velocity. Impulse "
            "-- the product of a net force and the time it acts -- equals the "
            "change in momentum it produces."
        ),
        "topic": "Momentum",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["p = m v", "J = F t = delta p"],
        "si_units": ["kg m/s", "N s"],
    },
    {
        "name": "Conservation of momentum",
        "description": (
            "In an isolated system (no external net force), the total "
            "momentum before an interaction equals the total momentum after "
            "it, even though momentum can be redistributed between the "
            "objects involved."
        ),
        "topic": "Momentum",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["p_total,before = p_total,after"],
        "si_units": ["kg m/s"],
    },
    {
        "name": "Elastic and inelastic collisions",
        "description": (
            "Momentum is conserved in every collision. In an elastic "
            "collision, kinetic energy is also conserved; in an inelastic "
            "collision, some kinetic energy converts into other forms (heat, "
            "sound, deformation), though momentum is still conserved."
        ),
        "topic": "Collisions",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Assuming kinetic energy is always conserved in a collision, the "
            "way momentum is.",
        ],
    },
    # --- Circular and Rotational Motion ---------------------------------------
    {
        "name": "Uniform circular motion",
        "description": (
            "An object moving at constant speed around a circle is still "
            "accelerating, because its velocity's direction is constantly "
            "changing. This acceleration points toward the centre of the "
            "circle."
        ),
        "topic": "Circular Motion",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Believing an object moving in a circle at constant speed has "
            "zero acceleration because its speed isn't changing.",
        ],
        "equations": ["v = 2 pi r / T"],
        "si_units": ["m/s"],
    },
    {
        "name": "Centripetal force",
        "description": (
            "Centripetal force is the net force directed toward the centre of "
            "a circular path that keeps an object moving in that circle. It is "
            "not a separate new force -- it is whichever real force (tension, "
            "gravity, friction, normal force) happens to point centre-ward."
        ),
        "topic": "Circular Motion",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Treating 'centrifugal force' as a real outward force acting on "
            "the object, rather than centripetal force being the real, "
            "inward net force.",
        ],
        "equations": ["F_c = m v^2 / r"],
        "si_units": ["N"],
    },
    {
        "name": "Torque",
        "description": (
            "Torque is the rotational analogue of force: it measures how "
            "effectively a force causes rotation about a pivot. It depends on "
            "the force's magnitude, the distance from the pivot, and the "
            "angle between the force and the lever arm."
        ),
        "topic": "Torque",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["tau = r F sin(theta)"],
        "si_units": ["N m"],
    },
    {
        "name": "Angular momentum and moment of inertia",
        "description": (
            "Moment of inertia measures an object's resistance to changes in "
            "rotational motion, depending on both its mass and how that mass "
            "is distributed relative to the axis of rotation. Angular "
            "momentum, the rotational analogue of linear momentum, is "
            "conserved in an isolated system -- why a spinning skater speeds "
            "up when pulling their arms in."
        ),
        "topic": "Rotational Motion",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["L = I omega"],
        "si_units": ["kg m^2/s"],
    },
    # --- Gravitation -----------------------------------------------------------
    {
        "name": "Newton's law of universal gravitation",
        "description": (
            "Every pair of masses attracts each other with a force "
            "proportional to the product of their masses and inversely "
            "proportional to the square of the distance between their "
            "centres."
        ),
        "topic": "Gravitation",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["F = G m1 m2 / r^2"],
        "si_units": ["N"],
    },
    {
        "name": "Gravitational field strength",
        "description": (
            "Gravitational field strength is the gravitational force per unit "
            "mass at a point in space. Near Earth's surface it is "
            "approximately constant (about 9.8 N/kg), which is also why all "
            "objects in free fall there share the same acceleration."
        ),
        "topic": "Gravity",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["g = F / m"],
        "si_units": ["N/kg"],
    },
    {
        "name": "Orbital motion and Kepler's laws",
        "description": (
            "A satellite in a stable orbit is in continuous free fall, with "
            "gravity supplying exactly the centripetal force its path needs. "
            "Kepler's laws describe how orbits are elliptical, how orbital "
            "speed varies with distance, and how orbital period relates to "
            "orbital size."
        ),
        "topic": "Orbits",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Believing astronauts in orbit are 'weightless' because they are "
            "far enough from Earth that gravity no longer acts, rather than "
            "because they and their spacecraft are in continuous free fall "
            "together.",
        ],
        "equations": ["T^2 is proportional to a^3 (Kepler's third law)"],
        "si_units": ["s", "m"],
    },
    # --- Fluid Mechanics ---------------------------------------------------
    {
        "name": "Pressure in fluids",
        "description": (
            "Pressure is force distributed over an area. In a fluid at rest, "
            "pressure increases with depth because of the weight of the fluid "
            "above, and at a given depth it acts equally in all directions."
        ),
        "topic": "Pressure",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["P = F / A", "P = P0 + rho g h"],
        "si_units": ["Pa"],
    },
    {
        "name": "Archimedes' principle and buoyancy",
        "description": (
            "An object submerged, fully or partly, in a fluid experiences an "
            "upward buoyant force equal to the weight of the fluid it "
            "displaces. Whether the object floats or sinks depends on how "
            "this compares to its own weight."
        ),
        "topic": "Buoyancy",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Believing heavier objects always sink and lighter objects "
            "always float, rather than it depending on density relative to "
            "the fluid.",
        ],
        "equations": ["F_b = rho g V"],
        "si_units": ["N"],
    },
    {
        "name": "Pascal's principle",
        "description": (
            "A change in pressure applied to an enclosed, incompressible "
            "fluid is transmitted undiminished to every point in the fluid "
            "and to the walls of its container -- the operating principle "
            "behind hydraulic lifts and brakes."
        ),
        "topic": "Fluids",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["P1 = P2 (F1/A1 = F2/A2)"],
        "si_units": ["Pa"],
    },
    {
        "name": "Bernoulli's principle",
        "description": (
            "For a smoothly flowing (non-viscous, incompressible) fluid, an "
            "increase in the fluid's speed occurs together with a decrease in "
            "its pressure or potential energy, reflecting conservation of "
            "energy along a streamline."
        ),
        "topic": "Fluid Mechanics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Believing faster-moving fluid always has higher pressure, "
            "rather than lower, along a streamline.",
        ],
        "equations": ["P + 1/2 rho v^2 + rho g h = constant"],
        "si_units": ["Pa"],
    },
    # --- Thermal Physics ------------------------------------------------------
    {
        "name": "Temperature and thermal equilibrium",
        "description": (
            "Temperature measures the average kinetic energy of the particles "
            "in a substance. Two objects in contact reach thermal equilibrium "
            "-- the same temperature -- as heat flows from the warmer to the "
            "cooler object until net heat flow stops."
        ),
        "topic": "Temperature",
        "difficulty": PhysicsConcept.Difficulty.FOUNDATIONAL,
        "common_misconceptions": [
            "Confusing temperature (average particle kinetic energy) with "
            "heat (energy transferred) or with how much thermal energy an "
            "object contains.",
        ],
        "si_units": ["K", "degC"],
    },
    {
        "name": "Heat transfer",
        "description": (
            "Heat moves between objects or regions by conduction (through "
            "direct contact), convection (through the bulk movement of a "
            "fluid) and radiation (through electromagnetic waves, requiring "
            "no medium)."
        ),
        "topic": "Heat",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Believing materials like a metal spoon feel 'cold' rather than "
            "simply being better conductors that carry heat away from your "
            "hand faster than a wooden spoon at the same temperature.",
        ],
        "si_units": ["J", "W"],
    },
    {
        "name": "Specific heat capacity and calorimetry",
        "description": (
            "Specific heat capacity is the energy needed to raise the "
            "temperature of one kilogram of a substance by one degree. "
            "Calorimetry uses conservation of energy to relate the heat lost "
            "by a warmer substance to the heat gained by a cooler one."
        ),
        "topic": "Thermal Physics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["Q = m c delta T"],
        "si_units": ["J/(kg K)"],
    },
    # --- Thermodynamics ----------------------------------------------------
    {
        "name": "The ideal gas law",
        "description": (
            "The ideal gas law relates the pressure, volume, amount and "
            "absolute temperature of a gas that behaves ideally (particles "
            "with negligible volume and no intermolecular forces)."
        ),
        "topic": "Gas Laws",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["P V = n R T"],
        "si_units": ["Pa", "m^3", "mol", "K"],
    },
    {
        "name": "The first and second laws of thermodynamics",
        "description": (
            "The first law states that energy is conserved: the change in a "
            "system's internal energy equals the heat added minus the work "
            "done by the system. The second law states that in any real "
            "process, the total entropy of an isolated system never "
            "decreases -- energy tends to spread out rather than "
            "concentrate."
        ),
        "topic": "Thermodynamics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Believing the second law forbids order from ever increasing "
            "anywhere, rather than only requiring that total entropy not "
            "decrease overall.",
        ],
        "equations": ["delta U = Q - W"],
        "si_units": ["J"],
    },
    {
        "name": "Heat engines and efficiency",
        "description": (
            "A heat engine converts thermal energy into mechanical work by "
            "moving heat from a hot reservoir to a cold one. No heat engine "
            "can convert all of its input heat into work; its efficiency is "
            "fundamentally limited by the temperatures of the reservoirs it "
            "operates between."
        ),
        "topic": "Heat Engines",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["e = W / Q_h", "e_Carnot = 1 - T_c/T_h"],
    },
    # --- Waves -----------------------------------------------------------------
    {
        "name": "Simple harmonic motion",
        "description": (
            "A mass on a spring (or a pendulum swinging through a small "
            "angle) oscillates with a restoring force proportional to its "
            "displacement from equilibrium, so its acceleration is always "
            "directed back toward the centre. Its position over time traces "
            "the same cosine curve as one axis of uniform circular motion -- "
            "simple harmonic motion is that circular motion's shadow."
        ),
        "topic": "Oscillations",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Believing the restoring force (and so the acceleration) is "
            "constant, rather than proportional to displacement.",
            "Believing the mass moves fastest at the amplitude, rather than "
            "at the centre where displacement is zero.",
        ],
        "prerequisites": ["Uniform circular motion"],
        "equations": ["x = A cos(omega t)", "a = -omega^2 x", "omega = 2 pi / T"],
        "si_units": ["m", "s", "rad/s"],
    },
    {
        "name": "Wave properties: wavelength, frequency and amplitude",
        "description": (
            "A wave transfers energy without transporting matter. Its "
            "wavelength (distance between repeating points), frequency "
            "(cycles per second) and amplitude (maximum displacement) "
            "together describe its shape and the energy it carries."
        ),
        "topic": "Waves",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["v = f lambda"],
        "si_units": ["m", "Hz", "m/s"],
    },
    {
        "name": "Transverse and longitudinal waves",
        "description": (
            "In a transverse wave, particles oscillate perpendicular to the "
            "direction the wave travels (like a wave on a string). In a "
            "longitudinal wave, particles oscillate parallel to the "
            "direction of travel, as compressions and rarefactions (like "
            "sound in air)."
        ),
        "topic": "Wave Motion",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
    },
    {
        "name": "Superposition, interference and standing waves",
        "description": (
            "When two or more waves overlap, their displacements add "
            "algebraically (superposition). Depending on their relative "
            "phase, this produces constructive or destructive interference; "
            "two identical waves travelling in opposite directions can "
            "combine into a standing wave with fixed nodes and antinodes."
        ),
        "topic": "Waves",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
    },
    # --- Sound -----------------------------------------------------------------
    {
        "name": "Sound waves and the speed of sound",
        "description": (
            "Sound is a longitudinal pressure wave that requires a medium to "
            "travel through -- it cannot travel through a vacuum. Its speed "
            "depends on the medium's properties, generally fastest in "
            "solids, slower in liquids, slowest in gases."
        ),
        "topic": "Sound",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Believing sound can travel through the vacuum of space, as it "
            "often appears to in film.",
        ],
        "equations": ["v = f lambda"],
        "si_units": ["m/s"],
    },
    {
        "name": "The Doppler effect",
        "description": (
            "The observed frequency of a wave shifts when there is relative "
            "motion between the source and the observer -- higher when "
            "approaching, lower when receding -- even though the source's "
            "actual emitted frequency never changes."
        ),
        "topic": "Sound",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["f_observed = f_source (v +/- v_observer)/(v -/+ v_source)"],
        "si_units": ["Hz"],
    },
    {
        "name": "Sound intensity and the decibel scale",
        "description": (
            "Sound intensity is the power carried by a sound wave per unit "
            "area. Because the range of intensities the ear can detect is "
            "enormous, loudness is usually expressed on the logarithmic "
            "decibel scale, where every 10 dB increase is a tenfold increase "
            "in intensity."
        ),
        "topic": "Acoustics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["beta = 10 log10(I / I0)"],
        "si_units": ["W/m^2", "dB"],
    },
    # --- Optics ------------------------------------------------------------
    {
        "name": "Reflection and mirrors",
        "description": (
            "Light reflecting off a surface obeys the law of reflection: the "
            "angle of incidence equals the angle of reflection, both "
            "measured from the normal to the surface. Curved mirrors form "
            "images by reflecting many such rays."
        ),
        "topic": "Geometric Optics",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["theta_i = theta_r"],
    },
    {
        "name": "Refraction and Snell's law",
        "description": (
            "Light bends when it passes between materials in which it "
            "travels at different speeds. Snell's law relates the angles of "
            "incidence and refraction to the refractive indices of the two "
            "materials."
        ),
        "topic": "Geometric Optics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["n1 sin(theta1) = n2 sin(theta2)"],
    },
    {
        "name": "Lenses and image formation",
        "description": (
            "A converging lens can form either a real, inverted image (when "
            "the object is beyond the focal point) or a virtual, upright, "
            "magnified image (when the object is within the focal point), "
            "depending on the object's distance from the lens."
        ),
        "topic": "Optics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["1/f = 1/d_o + 1/d_i"],
        "si_units": ["m"],
    },
    {
        "name": "Diffraction and interference of light",
        "description": (
            "Light spreads out (diffracts) when it passes through a narrow "
            "slit or around an obstacle, and overlapping light waves "
            "interfere, producing the characteristic bright-and-dark fringe "
            "patterns seen in experiments like Young's double slit."
        ),
        "topic": "Wave Optics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["d sin(theta) = m lambda"],
        "si_units": ["m"],
    },
    # --- Electrostatics ------------------------------------------------------
    {
        "name": "Electric charge and Coulomb's law",
        "description": (
            "Electric charge comes in two types, positive and negative; like "
            "charges repel and opposite charges attract. Coulomb's law gives "
            "the force between two point charges, which falls off with the "
            "square of the distance between them, just like gravity."
        ),
        "topic": "Charge",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["F = k q1 q2 / r^2"],
        "si_units": ["C", "N"],
    },
    {
        "name": "Electric field",
        "description": (
            "An electric field describes the force per unit charge that "
            "would be felt by a small positive test charge at each point in "
            "space. Field lines point away from positive charges and toward "
            "negative ones, and their spacing shows the field's relative "
            "strength."
        ),
        "topic": "Electric Field",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["E = F / q"],
        "si_units": ["N/C"],
    },
    {
        "name": "Electric potential and potential energy",
        "description": (
            "Electric potential is the electric potential energy per unit "
            "charge at a point. A positive charge moves from higher to lower "
            "potential unless another force does work against it."
        ),
        "topic": "Electric Potential",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Treating voltage (potential difference) and current as the same "
            "quantity, or believing voltage 'flows' through a circuit the "
            "way current does.",
        ],
        "equations": ["V = PE / q"],
        "si_units": ["V"],
    },
    {
        "name": "Capacitance",
        "description": (
            "A capacitor stores electric charge, and energy, on two "
            "conductors separated by an insulator. Its capacitance is the "
            "charge it can store per unit of potential difference, and "
            "depends on its geometry and the insulating material between its "
            "plates."
        ),
        "topic": "Electrostatics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["C = Q / V"],
        "si_units": ["F"],
    },
    # --- Electric Circuits ---------------------------------------------------
    {
        "name": "Electric current",
        "description": (
            "Electric current is the rate of flow of electric charge past a "
            "point in a circuit. In a simple series circuit the same current "
            "flows through every component; in a parallel circuit, current "
            "divides among the branches."
        ),
        "topic": "Current",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "common_misconceptions": [
            "Believing current is 'used up' as it flows around a circuit, "
            "rather than the same current returning to the source while "
            "energy is what gets transferred to each component.",
        ],
        "equations": ["I = Q / t"],
        "si_units": ["A"],
    },
    {
        "name": "Ohm's law and resistance",
        "description": (
            "For an ohmic conductor, the current through it is directly "
            "proportional to the voltage across it, with resistance as the "
            "constant of proportionality. Resistance depends on a "
            "conductor's material, length, cross-sectional area and "
            "temperature."
        ),
        "topic": "Resistance",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["V = I R"],
        "si_units": ["ohm"],
    },
    {
        "name": "Series and parallel circuits",
        "description": (
            "In a series circuit, components share the same current but "
            "divide the total voltage; resistances add directly. In a "
            "parallel circuit, components share the same voltage but divide "
            "the total current; the combined resistance is always less than "
            "the smallest individual resistor."
        ),
        "topic": "Circuits",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["R_series = R1 + R2 + ...", "1/R_parallel = 1/R1 + 1/R2 + ..."],
        "si_units": ["ohm"],
    },
    {
        "name": "Electric power in circuits",
        "description": (
            "Electric power is the rate at which electrical energy is "
            "converted to another form (light, heat, motion) in a circuit "
            "component, and depends on both the current through it and the "
            "voltage across it."
        ),
        "topic": "Electric Circuits",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "equations": ["P = I V", "P = I^2 R"],
        "si_units": ["W"],
    },
    # --- Magnetism -----------------------------------------------------------
    {
        "name": "Magnetic fields and field lines",
        "description": (
            "A magnetic field describes the region around a magnet or "
            "current-carrying conductor where a magnetic force can be "
            "detected. Field lines run from a magnet's north pole to its "
            "south pole outside the magnet, and their spacing indicates the "
            "field's strength."
        ),
        "topic": "Magnetic Field",
        "difficulty": PhysicsConcept.Difficulty.INTRODUCTORY,
        "si_units": ["T"],
    },
    {
        "name": "Magnetic force on a moving charge",
        "description": (
            "A charged particle moving through a magnetic field feels a "
            "force perpendicular to both its velocity and the field, so a "
            "magnetic field can change a moving charge's direction but never "
            "its speed."
        ),
        "topic": "Magnetism",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["F = q v B sin(theta)"],
        "si_units": ["N"],
    },
    {
        "name": "Magnetic force on a current-carrying wire",
        "description": (
            "A current-carrying wire in a magnetic field experiences a force "
            "because the moving charges within it do -- the basis of "
            "electric motors. The force is greatest when the current and "
            "field are perpendicular, and zero when they are parallel."
        ),
        "topic": "Magnetism",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["F = B I L sin(theta)"],
        "si_units": ["N"],
    },
    # --- Electromagnetism ------------------------------------------------------
    {
        "name": "Electromagnetic induction and Faraday's law",
        "description": (
            "A changing magnetic flux through a loop of wire induces an "
            "electromotive force in that loop -- the principle behind "
            "generators and transformers. The induced EMF is proportional to "
            "how quickly the flux changes."
        ),
        "topic": "Electromagnetic Induction",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["EMF = -N (delta Phi / delta t)"],
        "si_units": ["V", "Wb"],
    },
    {
        "name": "Lenz's law",
        "description": (
            "Lenz's law states that an induced current always flows in the "
            "direction that opposes the change in magnetic flux that "
            "produced it -- a direct consequence of conservation of energy."
        ),
        "topic": "Electromagnetic Induction",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "Electromagnetic waves",
        "description": (
            "An electromagnetic wave is a self-propagating oscillation of "
            "electric and magnetic fields, requiring no medium to travel "
            "through. Visible light, radio waves, microwaves and X-rays are "
            "all electromagnetic waves that differ only in frequency and "
            "wavelength."
        ),
        "topic": "Electromagnetism",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["c = f lambda"],
        "si_units": ["m/s", "Hz", "m"],
    },
    # --- Special Relativity ------------------------------------------------
    {
        "name": "Postulates of special relativity",
        "description": (
            "Special relativity rests on two postulates: the laws of physics "
            "are the same in every inertial reference frame, and the speed "
            "of light in a vacuum is the same for every observer, regardless "
            "of the observer's or the source's motion."
        ),
        "topic": "Special Relativity",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "Time dilation",
        "description": (
            "A clock moving relative to an observer runs slower, as measured "
            "by that observer, than an identical clock at rest relative to "
            "them. The effect becomes significant only as relative speed "
            "approaches the speed of light."
        ),
        "topic": "Special Relativity",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["delta t = delta t0 / sqrt(1 - v^2/c^2)"],
        "si_units": ["s"],
    },
    {
        "name": "Length contraction",
        "description": (
            "An object moving relative to an observer is measured as "
            "shorter, along its direction of motion, than its length "
            "measured at rest -- the companion effect to time dilation, from "
            "the same postulates."
        ),
        "topic": "Special Relativity",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["L = L0 sqrt(1 - v^2/c^2)"],
        "si_units": ["m"],
    },
    {
        "name": "Mass-energy equivalence",
        "description": (
            "Mass and energy are equivalent and interconvertible: even an "
            "object at rest has an intrinsic 'rest energy' proportional to "
            "its mass, with the speed of light squared as the constant of "
            "proportionality."
        ),
        "topic": "Relativity",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["E = m c^2"],
        "si_units": ["J"],
    },
    # --- Quantum Physics ---------------------------------------------------
    {
        "name": "Wave-particle duality",
        "description": (
            "Light and matter both display behaviour associated with waves "
            "(such as diffraction and interference) and with particles (such "
            "as discrete, localised interactions). Which aspect is observed "
            "can depend on the experiment performed."
        ),
        "topic": "Quantum Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "The photoelectric effect",
        "description": (
            "Light striking a metal surface can eject electrons, but only if "
            "its frequency exceeds a threshold value -- increasing the "
            "light's intensity alone cannot cause emission below that "
            "threshold. This showed that light delivers energy in discrete "
            "packets (photons) rather than continuously, as classical wave "
            "theory predicted."
        ),
        "topic": "Photoelectric Effect",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Believing that brighter (more intense) light alone, regardless "
            "of its frequency, should always be able to eject electrons from "
            "a metal.",
        ],
        "equations": ["KE_max = h f - phi"],
        "si_units": ["J", "Hz"],
    },
    {
        "name": "Quantisation of energy",
        "description": (
            "At the atomic scale, many physical quantities -- including "
            "energy -- can only take specific, discrete values rather than "
            "any value in a continuous range. This quantisation underlies "
            "atomic spectra and the stability of atoms."
        ),
        "topic": "Quantum",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["E = h f"],
        "si_units": ["J"],
    },
    {
        "name": "The Heisenberg uncertainty principle",
        "description": (
            "There is a fundamental limit to how precisely certain pairs of "
            "properties -- such as a particle's position and momentum -- can "
            "simultaneously be known. This is not a limitation of measuring "
            "instruments; it is a basic feature of quantum systems."
        ),
        "topic": "Quantum Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Believing the uncertainty principle is only a practical "
            "limitation of clumsy measuring equipment, rather than a "
            "fundamental property of quantum systems.",
        ],
        "equations": ["delta x delta p >= h / (4 pi)"],
    },
    # --- Atomic Physics ------------------------------------------------------
    {
        "name": "The Bohr model of the atom",
        "description": (
            "The Bohr model pictures electrons orbiting the nucleus only in "
            "specific, quantised energy levels. An electron can jump between "
            "levels by absorbing or emitting a photon whose energy exactly "
            "matches the gap between them."
        ),
        "topic": "Atomic Structure",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["delta E = h f"],
        "si_units": ["J"],
    },
    {
        "name": "Atomic emission and absorption spectra",
        "description": (
            "Each element produces a unique pattern of spectral lines "
            "because its electrons can only occupy specific energy levels. "
            "An emission spectrum shows the wavelengths emitted as electrons "
            "fall to lower levels; an absorption spectrum shows the "
            "wavelengths absorbed as electrons jump to higher ones."
        ),
        "topic": "Atomic Physics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
    },
    {
        "name": "Energy levels and electron transitions",
        "description": (
            "An atom's electrons occupy discrete energy levels. A transition "
            "between two levels always absorbs or releases a photon whose "
            "energy equals the exact difference between those levels -- no "
            "more, no less."
        ),
        "topic": "Atomic Physics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["E_photon = E_high - E_low"],
        "si_units": ["J"],
    },
    # --- Nuclear Physics -----------------------------------------------------
    {
        "name": "Nuclear structure: protons, neutrons and isotopes",
        "description": (
            "A nucleus is made of protons and neutrons (collectively "
            "nucleons), held together by the strong nuclear force over very "
            "short range. Isotopes of an element share the same number of "
            "protons but differ in their number of neutrons."
        ),
        "topic": "Nuclear Physics",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
    },
    {
        "name": "Radioactive decay",
        "description": (
            "An unstable nucleus can spontaneously transform by emitting "
            "alpha, beta or gamma radiation. Decay is a random process for "
            "any individual nucleus, but a large sample decays at a "
            "statistically predictable rate."
        ),
        "topic": "Nuclear Decay",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "common_misconceptions": [
            "Believing you can predict exactly when a specific unstable "
            "nucleus will decay, rather than only the statistical decay rate "
            "of a large sample.",
        ],
        "equations": ["N = N0 (1/2)^(t / T_half)"],
    },
    {
        "name": "Half-life",
        "description": (
            "The half-life of a radioactive isotope is the time it takes for "
            "half of a sample to decay. It is constant for a given isotope, "
            "regardless of the sample's size or how much has already "
            "decayed."
        ),
        "topic": "Nuclear Decay",
        "difficulty": PhysicsConcept.Difficulty.INTERMEDIATE,
        "equations": ["T_half = ln(2) / lambda"],
        "si_units": ["s"],
    },
    {
        "name": "Nuclear fission and fusion",
        "description": (
            "Fission splits a heavy nucleus into lighter fragments; fusion "
            "combines light nuclei into a heavier one. Both can release "
            "enormous energy because the resulting nuclei can have less mass "
            "than the original, with the difference released as energy."
        ),
        "topic": "Nuclear Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["E = delta m c^2"],
        "si_units": ["J"],
    },
    # --- Particle Physics ----------------------------------------------------
    {
        "name": "Fundamental particles and the Standard Model",
        "description": (
            "The Standard Model classifies the known elementary particles "
            "into quarks and leptons (matter particles) and force-carrying "
            "bosons. Protons and neutrons are not fundamental -- they are "
            "made of quarks bound by the strong force."
        ),
        "topic": "Particle Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "The fundamental forces",
        "description": (
            "All known interactions in nature reduce to four fundamental "
            "forces: gravity, electromagnetism, the strong nuclear force and "
            "the weak nuclear force. Everyday pushes, pulls, friction and "
            "contact forces are all macroscopic manifestations of "
            "electromagnetism."
        ),
        "topic": "Particle Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "Particle interactions and conservation laws",
        "description": (
            "Particle interactions and decays must obey strict conservation "
            "laws -- of energy, momentum, electric charge and other quantum "
            "properties -- which is why some seemingly plausible particle "
            "reactions never actually occur."
        ),
        "topic": "Particle Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    # --- Astrophysics and Space Physics -----------------------------------------
    {
        "name": "Stellar structure and evolution",
        "description": (
            "A star spends most of its life in equilibrium between the "
            "inward pull of gravity and the outward pressure from nuclear "
            "fusion in its core. How a star evolves and ends its life -- as "
            "a white dwarf, neutron star or black hole -- depends chiefly on "
            "its mass."
        ),
        "topic": "Astrophysics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "The Hertzsprung-Russell diagram",
        "description": (
            "The Hertzsprung-Russell diagram plots stars by luminosity "
            "against surface temperature. Most stars, including the Sun, "
            "fall along the diagonal 'main sequence' where they spend the "
            "majority of their lives fusing hydrogen into helium."
        ),
        "topic": "Astrophysics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
    },
    {
        "name": "Cosmology and the expanding universe",
        "description": (
            "Observations show distant galaxies receding from us, with "
            "recession speed roughly proportional to distance (Hubble's "
            "law) -- evidence that space itself is expanding, consistent "
            "with the universe originating from a hot, dense early state."
        ),
        "topic": "Cosmology",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "common_misconceptions": [
            "Picturing the Big Bang as an explosion happening at one point "
            "within a pre-existing empty space, rather than as space itself "
            "expanding everywhere at once.",
        ],
        "equations": ["v = H0 d"],
        "si_units": ["m/s", "m"],
    },
    {
        "name": "Black holes",
        "description": (
            "A black hole is a region of spacetime where gravity is so "
            "strong that nothing, not even light, can escape once inside its "
            "event horizon. They form from the collapse of sufficiently "
            "massive stars, among other pathways."
        ),
        "topic": "Space Physics",
        "difficulty": PhysicsConcept.Difficulty.ADVANCED,
        "equations": ["r_s = 2 G M / c^2"],
        "si_units": ["m"],
    },
]


class Command(BaseCommand):
    help = (
        "Create or update the Physics concept knowledge set: the original "
        "Kinematics/Dynamics basics plus the standard topic set for every "
        "other curriculum domain (PHYSICS_TOPICS). Safe to re-run."
    )

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for concept in PHYSICS_CONCEPTS + PHYSICS_TOPICS:
            _, created = PhysicsConcept.objects.update_or_create(
                name=concept["name"],
                defaults=concept,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Physics concepts seeded: {created_count} created, {updated_count} updated."
            )
        )
