from django.core.management.base import BaseCommand

from apps.physics.models import PhysicsConcept, PhysicsMisconception

PHYSICS_MISCONCEPTIONS = [
    {
        "code": "FREE_FALL_MASS_ACCELERATION",
        "title": "Mass determines free-fall acceleration",
        "concept_name": "Acceleration",
        "description": (
            "A learner may believe that a heavier object necessarily has a "
            "greater gravitational acceleration in free fall, so it falls faster."
        ),
        "detection_guidance": (
            "Statements or reasoning that link greater mass to a faster fall, or "
            "that predict a heavier object reaching the ground first (ignoring air "
            "resistance)."
        ),
        "intervention_guidance": (
            "Use a controlled comparison: ask the student to predict two different "
            "masses released together in a vacuum, then reason from the free-fall "
            "result rather than from weight."
        ),
    },
    {
        "code": "FORCE_VS_ACCELERATION",
        "title": "Force and acceleration are the same quantity",
        "concept_name": "Newton's Second Law",
        "description": (
            "A learner may treat force and acceleration as interchangeable, rather "
            "than as distinct quantities related by F = ma."
        ),
        "detection_guidance": (
            "Language that equates force with acceleration, uses the words "
            "interchangeably, or skips mass when relating them."
        ),
        "intervention_guidance": (
            "Work a short numerical example where the same net force gives "
            "different accelerations for different masses, keeping the two "
            "quantities and their units clearly separate."
        ),
    },
    {
        "code": "DISTANCE_VS_DISPLACEMENT",
        "title": "Distance and displacement are always identical",
        "concept_name": "Displacement",
        "description": (
            "A learner may believe distance and displacement are always the same, "
            "overlooking direction and the path taken."
        ),
        "detection_guidance": (
            "Claims that distance and displacement are always equal or "
            "interchangeable, with no mention of direction or of a changing path."
        ),
        "intervention_guidance": (
            "Compare a there-and-back walk: the distance travelled is nonzero "
            "while the displacement is zero. Then vary the path."
        ),
    },
]


class Command(BaseCommand):
    help = "Create or update the initial Physics misconception catalog."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped = []

        for entry in PHYSICS_MISCONCEPTIONS:
            concept = PhysicsConcept.objects.filter(name=entry["concept_name"]).first()
            if concept is None:
                skipped.append(entry["code"])
                continue

            defaults = {
                "title": entry["title"],
                "description": entry["description"],
                "physics_concept": concept,
                "detection_guidance": entry["detection_guidance"],
                "intervention_guidance": entry["intervention_guidance"],
                "is_active": True,
            }
            _, created = PhysicsMisconception.objects.update_or_create(
                code=entry["code"],
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Misconception catalog seeded: {created_count} created, "
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
