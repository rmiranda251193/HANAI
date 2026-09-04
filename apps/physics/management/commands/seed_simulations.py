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
