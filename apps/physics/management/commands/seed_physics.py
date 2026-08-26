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


class Command(BaseCommand):
    help = "Create or update the initial Physics concept knowledge set."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for concept in PHYSICS_CONCEPTS:
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
