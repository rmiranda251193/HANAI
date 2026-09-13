"""Hands-on, real-materials experiment companions for the virtual Physics
Lab -- inspired by physicslab.app's pairing of virtual simulations with
"hands-on experiments... for use at home or in the classroom" (an external
product analyzed for ideas only; no text, code or assets were copied).

Code-defined data only, keyed by ``simulation_type`` -- no model, no
migration, the same pattern as ``depth_layers``. Deliberately populated for
only the 3 simulation types that actually exist today; a new simulation
type gets a companion only when one is written and checked like these,
never a placeholder.

Every experiment here uses ordinary household materials, is safe in an
open indoor or outdoor space, and is written to be compared against --
not replace -- the deterministic virtual lab: the whole point is for a
student to notice where a real, imperfect measurement (friction, air
resistance, timing error) departs from the idealized model, not to expect
an exact match.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandsOnExperiment:
    title: str
    materials: tuple[str, ...]
    steps: tuple[str, ...]
    safety_note: str
    compare_note: str


HANDS_ON_EXPERIMENTS: dict[str, HandsOnExperiment] = {
    "kinematics": HandsOnExperiment(
        title="Time a ball rolling down a ramp",
        materials=(
            "A ball or marble",
            "A book or board to use as a ramp",
            "A stopwatch or phone timer",
            "A tape measure or ruler",
        ),
        steps=(
            "Prop up one end of the board to make a gentle ramp.",
            "Mark a start line near the top and a finish line near the "
            "bottom, and measure the distance between them.",
            "Release the ball from rest at the start line and time how "
            "long it takes to reach the finish line.",
            "Repeat 2-3 times and average your times for a steadier result.",
            "Compute average velocity = distance / time, then set up a "
            "similar starting position and time in the virtual lab and "
            "compare.",
        ),
        safety_note="Use a soft, light ball and keep the ramp low -- this "
        "is about timing, not speed.",
        compare_note="The virtual lab assumes constant acceleration and no "
        "friction; your real ball will likely be a little slower because "
        "of rolling friction and air resistance. That gap is worth "
        "discussing, not a mistake to fix.",
    ),
    "newtons_second_law": HandsOnExperiment(
        title="Pull a book with a rubber band",
        materials=(
            "A small book or box",
            "A rubber band",
            "A ruler",
            "A stopwatch or phone timer",
            "A smooth floor or table",
        ),
        steps=(
            "Loop the rubber band around the book and hold the other end.",
            "Pull so the rubber band stretches to the same length the "
            "whole time -- that keeps the force roughly constant.",
            "Starting from rest, time how long it takes the book to "
            "travel a measured distance.",
            "Estimate acceleration from distance = (1/2) * a * time^2, "
            "solved for a.",
            "Repeat with a heavier book at the same stretch, and compare "
            "how the acceleration changes against a = F / m.",
        ),
        safety_note="Pull along a clear, flat surface, away from the edge "
        "of the table.",
        compare_note="A stretched rubber band applies a roughly constant "
        "force, not a perfectly constant one -- treat your acceleration "
        "estimate as approximate, and compare the trend (heavier object, "
        "same force, smaller acceleration) rather than the exact number.",
    ),
    "projectile_motion": HandsOnExperiment(
        title="Launch a ball and measure its range",
        materials=(
            "A ball",
            "A tape measure",
            "A stopwatch or phone timer",
            "An open, safe outdoor space",
        ),
        steps=(
            "Throw the ball at a comfortable, repeatable angle -- note "
            "roughly how steep it felt (for example, about 45 degrees).",
            "Time how long the ball is in the air, from launch to landing.",
            "Measure the horizontal distance it traveled.",
            "Enter your estimated launch angle and an estimated speed "
            "into the virtual lab and compare its predicted time and "
            "distance to what you measured.",
            "Adjust your estimated speed until the virtual lab's "
            "prediction is close to your real throw.",
        ),
        safety_note="Throw in an open outdoor space, away from people, "
        "windows and traffic.",
        compare_note="A real throw has air resistance and spin that the "
        "virtual lab's idealized model ignores -- this is an "
        "estimate-and-compare exercise, not an exact match.",
    ),
}


def hands_on_experiment_for(simulation_type) -> HandsOnExperiment | None:
    """The real-materials companion for a simulation type, or ``None`` if
    none has been written yet. Never raises, never fabricates one."""

    if not isinstance(simulation_type, str):
        return None
    return HANDS_ON_EXPERIMENTS.get(simulation_type.strip().casefold())
