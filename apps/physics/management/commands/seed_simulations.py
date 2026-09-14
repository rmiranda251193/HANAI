from django.core.management.base import BaseCommand

from apps.physics.models import PhysicsConcept, PhysicsSimulation

PHYSICS_SIMULATIONS = [
    {
        "slug": "newtons-second-law",
        "title": "Newton's Second Law Lab",
        "concept_name": "Newton's Second Law",
        "simulation_type": PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        "description": (
            "Adjust the mass and the net force on a cart and watch the "
            "acceleration respond through a = F / m. Idealized model: the net "
            "force is treated as constant and friction and air resistance are "
            "ignored."
        ),
    },
    {
        "slug": "kinematics",
        "title": "Kinematics -- Straight-Line Motion",
        "concept_name": "Acceleration",
        "simulation_type": PhysicsSimulation.SimulationType.KINEMATICS,
        "description": (
            "Set an initial position, an initial velocity and a constant "
            "acceleration, then watch position and velocity change over time "
            "through v = v0 + at and x = x0 + v0*t + (1/2)*a*t^2. Idealized "
            "model: motion is along a single straight line and there is no "
            "friction or air resistance."
        ),
    },
    {
        "slug": "projectile-motion",
        "title": "Projectile Motion Lab",
        "concept_name": "Projectile motion",
        "simulation_type": PhysicsSimulation.SimulationType.PROJECTILE_MOTION,
        "description": (
            "Launch a projectile at a chosen speed, angle and starting height "
            "and watch its horizontal and vertical position change over time "
            "through x = v0*cos(theta)*t and y = y0 + v0*sin(theta)*t - "
            "(1/2)*g*t^2. Idealized model: there is no air resistance and "
            "gravity is constant."
        ),
    },
    {
        "slug": "circular-motion",
        "title": "Circular Motion Lab",
        "concept_name": "Uniform circular motion",
        "simulation_type": PhysicsSimulation.SimulationType.CIRCULAR_MOTION,
        "description": (
            "Set a radius and a period and watch an object move at constant "
            "speed around a circle through v = 2*pi*r / T, while its "
            "centripetal acceleration a_c = v^2 / r keeps pointing toward "
            "the centre. Idealized model: perfectly circular motion at a "
            "perfectly constant speed, with no friction or air resistance."
        ),
    },
    {
        "slug": "simple-harmonic-motion",
        "title": "Simple Harmonic Motion Lab",
        "concept_name": "Simple harmonic motion",
        "simulation_type": PhysicsSimulation.SimulationType.SIMPLE_HARMONIC_MOTION,
        "description": (
            "Set an amplitude and a period and watch a mass oscillate on a "
            "spring through x = A*cos(omega*t), with acceleration always "
            "pulling it back toward the centre through a = -omega^2*x. "
            "Idealized model: no friction or air resistance, and the "
            "oscillation never loses amplitude."
        ),
    },
    {
        "slug": "momentum-collision",
        "title": "Momentum and Collisions Lab",
        "concept_name": "Elastic and inelastic collisions",
        "simulation_type": PhysicsSimulation.SimulationType.MOMENTUM_COLLISION,
        "description": (
            "A moving cart collides with a stationary one. Choose the "
            "masses, the moving cart's initial speed, and whether the "
            "collision is elastic or perfectly inelastic, and watch "
            "momentum m1*v1 + m2*v2 stay conserved either way -- while "
            "kinetic energy is only conserved in the elastic case. "
            "Idealized model: no friction or air resistance."
        ),
    },
    {
        "slug": "energy-incline",
        "title": "Energy on an Incline Lab",
        "concept_name": "Conservation of mechanical energy",
        "simulation_type": PhysicsSimulation.SimulationType.ENERGY_INCLINE,
        "description": (
            "A block starts from rest at a chosen height on a frictionless "
            "ramp and slides down, then continues across frictionless flat "
            "ground. Watch kinetic and potential energy trade off while "
            "their total, KE + PE = mgh, stays exactly constant. Idealized "
            "model: no friction or air resistance anywhere."
        ),
    },
    {
        "slug": "orbital-motion",
        "title": "Orbital Motion Lab",
        "concept_name": "Orbital motion and Kepler's laws",
        "simulation_type": PhysicsSimulation.SimulationType.ORBITAL_MOTION,
        "description": (
            "Set a central body's gravitational parameter and an orbital "
            "radius and watch a small body move at constant speed around a "
            "stable circular orbit through v = sqrt(mu / r), while gravity "
            "itself supplies the centripetal force (a_g = mu / r^2). Watch "
            "the orbital period follow T = 2*pi*sqrt(r^3 / mu) -- Kepler's "
            "third law. Idealized model: a perfectly circular orbit (real "
            "orbits are generally elliptical) around a central body so much "
            "more massive that its own motion is ignored."
        ),
    },
    {
        "slug": "series-parallel-circuit",
        "title": "Series and Parallel Circuits Lab",
        "concept_name": "Series and parallel circuits",
        "simulation_type": PhysicsSimulation.SimulationType.SERIES_PARALLEL_CIRCUIT,
        "description": (
            "Wire a voltage source to two resistors in series or in "
            "parallel and see how the current and voltage split. In "
            "series, R = R1 + R2 and the same current flows through both; "
            "in parallel, 1/R = 1/R1 + 1/R2 and both resistors share the "
            "same voltage. Idealized model: an ideal voltage source with no "
            "internal resistance, ideal (zero-resistance) wires, and no "
            "transients -- the circuit reaches its steady state instantly."
        ),
    },
    {
        "slug": "coulombs-law",
        "title": "Coulomb's Law Lab",
        "concept_name": "Electric charge and Coulomb's law",
        "simulation_type": PhysicsSimulation.SimulationType.COULOMBS_LAW,
        "description": (
            "Set two point charges and the distance between them and watch "
            "the force between them follow F = k|q1 q2| / r^2 -- the same "
            "inverse-square shape as gravity, except this force can be "
            "either attractive (opposite signs) or repulsive (same sign). "
            "Idealized model: two point charges with no size, in a vacuum, "
            "with no other charges nearby."
        ),
    },
    {
        "slug": "radioactive-decay",
        "title": "Radioactive Decay Lab",
        "concept_name": "Half-life",
        "simulation_type": PhysicsSimulation.SimulationType.RADIOACTIVE_DECAY,
        "description": (
            "Set a sample's starting size and its half-life and watch it "
            "shrink through N(t) = N0 * (1/2)^(t / T_half) -- half of "
            "whatever remains decays every half-life, no matter how much "
            "has already decayed. Idealized model: a statistically "
            "predictable large sample, not a prediction about any single "
            "unstable nucleus."
        ),
    },
    {
        "slug": "buoyancy",
        "title": "Buoyancy Lab",
        "concept_name": "Archimedes' principle and buoyancy",
        "simulation_type": PhysicsSimulation.SimulationType.BUOYANCY,
        "description": (
            "Set an object's density, a fluid's density and the object's "
            "volume and see whether it floats or sinks -- it depends only "
            "on density, not on weight or size, through the buoyant force "
            "F_b = rho_fluid * V * g. Idealized model: the object reaches "
            "its floating equilibrium (or keeps sinking) essentially "
            "instantly, with no drag or surface-tension effects."
        ),
    },
    {
        "slug": "refraction",
        "title": "Refraction Lab",
        "concept_name": "Refraction and Snell's law",
        "simulation_type": PhysicsSimulation.SimulationType.REFRACTION,
        "description": (
            "Set two refractive indices and an angle of incidence and "
            "watch a light ray bend at the interface through "
            "n1 sin(theta1) = n2 sin(theta2). Going from a denser to a "
            "less dense medium past the critical angle, watch it undergo "
            "total internal reflection instead -- no refracted ray at "
            "all. Idealized model: a single ray at a flat interface "
            "between two uniform, transparent media, with no absorption "
            "or dispersion."
        ),
    },
]


class Command(BaseCommand):
    help = "Create or update the built-in Physics Lab simulations. Safe to re-run."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped = []

        for entry in PHYSICS_SIMULATIONS:
            concept = PhysicsConcept.objects.filter(name=entry["concept_name"]).first()
            if concept is None:
                skipped.append(entry["slug"])
                continue

            _, created = PhysicsSimulation.objects.update_or_create(
                slug=entry["slug"],
                defaults={
                    "title": entry["title"],
                    "description": entry["description"],
                    "concept": concept,
                    "simulation_type": entry["simulation_type"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Physics simulations seeded: {created_count} created, "
                f"{updated_count} updated."
            )
        )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped (missing concept, run seed_physics first): "
                    + ", ".join(skipped)
                )
            )
