from django.core.management.base import BaseCommand, CommandError

from apps.physics.models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsMisconception,
    PhysicsSimulation,
)
from apps.students.recovery_registry import registered_activity_types

_ActivityType = MisconceptionRecoveryActivity.ActivityType

RECOVERY_PATHS = [
    {
        "misconception_code": "FORCE_VS_ACCELERATION",
        "title": "Force and acceleration: seeing the difference",
        "student_summary": (
            "Let's work through force and acceleration side by side in the "
            "Physics Lab, then check your understanding."
        ),
        "activities": [
            {
                "order": 1,
                "activity_type": _ActivityType.PHYSICS_LAB,
                "label": "Run the Newton's Second Law Lab",
                "instructions": (
                    "Think first: if the net force doubles and the mass stays the "
                    "same, what happens to the acceleration? Then predict, run the "
                    "experiment, observe the result and explain what you found."
                ),
                "simulation_type": PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
            },
            {
                "order": 2,
                "activity_type": _ActivityType.CONCEPT_CHECK,
                "label": "Check your understanding",
                "instructions": "One short question about what you just explored.",
                "check_prompt": (
                    "A net force of 20 N acts on a 2 kg cart. If the mass were "
                    "doubled to 4 kg with the same net force, what happens to the "
                    "acceleration?"
                ),
                "check_choices": [
                    "It doubles",
                    "It stays the same",
                    "It is cut in half",
                    "It becomes zero",
                ],
                "check_correct_choice": 2,
            },
        ],
    },
    {
        "misconception_code": "DISTANCE_VS_DISPLACEMENT",
        "title": "Distance and displacement: same trip, different numbers",
        "student_summary": (
            "Let's run a Kinematics experiment and compare the distance travelled "
            "with the displacement, then check your understanding."
        ),
        "activities": [
            {
                "order": 1,
                "activity_type": _ActivityType.PHYSICS_LAB,
                "label": "Run the Kinematics Lab",
                "instructions": (
                    "Think first: if you move away from your start and then come "
                    "back partway, is the distance you travelled the same as your "
                    "displacement? Predict, run the experiment, observe the "
                    "position and velocity, and explain the difference between "
                    "distance and displacement for your setup."
                ),
                "simulation_type": PhysicsSimulation.SimulationType.KINEMATICS,
            },
            {
                "order": 2,
                "activity_type": _ActivityType.CONCEPT_CHECK,
                "label": "Check your understanding",
                "instructions": "One short question about what you just explored.",
                "check_prompt": (
                    "A student walks 8 m east, then walks 3 m back west. Which "
                    "best describes the result?"
                ),
                "check_choices": [
                    "Distance = 11 m, displacement = 11 m east",
                    "Distance = 5 m, displacement = 5 m east",
                    "Distance = 11 m, displacement = 5 m east",
                    "Distance and displacement are always the same, so both are 5 m",
                ],
                "check_correct_choice": 2,
            },
        ],
    },
    {
        "misconception_code": "FREE_FALL_MASS_ACCELERATION",
        "title": "Free fall: does a heavier object fall faster?",
        "student_summary": (
            "Let's talk through a controlled comparison with your Tutor, then "
            "check your understanding."
        ),
        "activities": [
            {
                "order": 1,
                "activity_type": _ActivityType.TUTOR_REFLECTION,
                "label": "Talk it through with your Tutor",
                "instructions": (
                    "Think first: picture a 1 kg ball and a 10 kg ball, released "
                    "together from the same height with no air resistance. Predict "
                    "which one lands first, if either. Then open the Tutor and "
                    "compare their free-fall accelerations."
                ),
            },
            {
                "order": 2,
                "activity_type": _ActivityType.CONCEPT_CHECK,
                "label": "Check your understanding",
                "instructions": "One short question about what you just discussed.",
                "check_prompt": (
                    "In free fall with no air resistance, a 1 kg ball and a 10 kg "
                    "ball are released together from the same height. What happens?"
                ),
                "check_choices": [
                    "The 10 kg ball lands first because it is heavier",
                    "The 1 kg ball lands first because it is lighter",
                    "They land at the same time because free-fall acceleration does not depend on mass",
                    "It depends on which one is dropped first",
                ],
                "check_correct_choice": 2,
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Create or update the initial misconception recovery paths (idempotent)."

    def _resolve_simulation(self, misconception, simulation_type):
        if not simulation_type:
            return None
        return (
            PhysicsSimulation.objects.filter(
                concept=misconception.physics_concept,
                simulation_type=simulation_type,
                is_active=True,
            ).first()
            or PhysicsSimulation.objects.filter(
                simulation_type=simulation_type, is_active=True
            ).first()
        )

    def handle(self, *args, **options):
        known_types = registered_activity_types()
        for entry in RECOVERY_PATHS:
            for activity_entry in entry["activities"]:
                if activity_entry["activity_type"] not in known_types:
                    raise CommandError(
                        f"Unknown recovery activity_type "
                        f"{activity_entry['activity_type']!r} for "
                        f"{entry['misconception_code']} -- register it in "
                        "apps.students.recovery_registry first."
                    )

        created_paths = updated_paths = 0
        activities_written = 0
        skipped = []

        for entry in RECOVERY_PATHS:
            misconception = PhysicsMisconception.objects.filter(
                code=entry["misconception_code"]
            ).first()
            if misconception is None:
                skipped.append(entry["misconception_code"])
                continue

            path, path_created = MisconceptionRecoveryPath.objects.update_or_create(
                misconception=misconception,
                title=entry["title"],
                defaults={
                    "student_summary": entry["student_summary"],
                    "is_active": True,
                },
            )
            created_paths += int(path_created)
            updated_paths += int(not path_created)

            for activity_entry in entry["activities"]:
                simulation = self._resolve_simulation(
                    misconception, activity_entry.get("simulation_type")
                )
                MisconceptionRecoveryActivity.objects.update_or_create(
                    path=path,
                    order=activity_entry["order"],
                    defaults={
                        "activity_type": activity_entry["activity_type"],
                        "label": activity_entry["label"],
                        "instructions": activity_entry.get("instructions", ""),
                        "simulation": simulation,
                        "check_prompt": activity_entry.get("check_prompt", ""),
                        "check_choices": activity_entry.get("check_choices", []),
                        "check_correct_choice": activity_entry.get("check_correct_choice"),
                        "is_active": True,
                    },
                )
                activities_written += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Recovery paths seeded: {created_paths} created, {updated_paths} "
                f"updated, {activities_written} activities written."
            )
        )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped (missing misconception, run seed_misconceptions first): "
                    + ", ".join(skipped)
                )
            )
