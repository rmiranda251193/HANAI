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
    "circular_motion": HandsOnExperiment(
        title="Swing a weight in a horizontal circle",
        materials=(
            "A small soft weight (a sock with something light inside works well)",
            "A length of string",
            "A stopwatch or phone timer",
            "A ruler or tape measure",
            "An open, safe space",
        ),
        steps=(
            "Measure the length of the string from your hand to the "
            "weight -- this is your radius.",
            "Swing the weight in a steady horizontal circle above your "
            "head or out in front of you at a comfortable, gentle speed.",
            "Time how long 10 full revolutions take, then divide by 10 "
            "to get the period of one revolution.",
            "Enter your measured radius and period into the virtual lab "
            "and compare the predicted speed and centripetal acceleration.",
            "Try a shorter string at the same period, and see how the "
            "virtual lab predicts the centripetal acceleration should change.",
        ),
        safety_note="Use a soft weight, keep well clear of people and "
        "objects, and stop immediately if the string frays or the weight "
        "slips.",
        compare_note="Keeping the speed perfectly steady by hand is hard, "
        "so treat your period as an average over many spins, and expect "
        "your real acceleration estimate to be rougher than the virtual "
        "lab's exact value.",
    ),
    "simple_harmonic_motion": HandsOnExperiment(
        title="Time a rubber band or spring bouncing a weight",
        materials=(
            "A rubber band or a lightweight spring (a slinky works well)",
            "A small weight (a bag of coins or a small toy)",
            "A ruler",
            "A stopwatch or phone timer",
        ),
        steps=(
            "Hang the rubber band or spring, attach the weight, and let it "
            "settle at rest -- this rest position is the centre.",
            "Pull the weight down a measured distance (your amplitude) and "
            "let go without pushing it.",
            "Time how long 10 full up-and-down cycles take, then divide by "
            "10 to get the period of one cycle.",
            "Enter your measured amplitude and period into the virtual lab "
            "and compare the predicted position and velocity over time.",
            "Watch where the weight moves fastest (through the centre) and "
            "where it pauses (at the top and bottom) -- compare that against "
            "the graph.",
        ),
        safety_note="Keep the weight light and the pull short so it doesn't "
        "snap back forcefully; keep your face and others clear of the path.",
        compare_note="A real rubber band or spring loses a little energy "
        "each cycle (the swings get smaller over time), while the virtual "
        "lab's amplitude never decays -- that difference is itself worth "
        "noticing and explaining.",
    ),
    "momentum_collision": HandsOnExperiment(
        title="Roll two coins or marbles into each other",
        materials=(
            "Two coins or marbles of different sizes (or two of the same size)",
            "A smooth, flat, level surface (a table or hard floor)",
            "A ruler",
        ),
        steps=(
            "Place the second coin or marble at rest on the flat surface.",
            "Flick or roll the first one in a straight line so it hits the "
            "stationary one head-on.",
            "Watch what happens to each one right after the hit: does the "
            "first one stop, bounce back, or keep going slower?",
            "Try it with two objects of very different sizes, then with two "
            "of the same size, and compare the difference.",
            "Enter similar masses and an estimated speed into the virtual "
            "lab and compare its predicted outcome to what you saw.",
        ),
        safety_note="Use small, light objects on a surface clear of edges "
        "so nothing rolls off or hits anyone.",
        compare_note="Real coins and marbles almost never collide perfectly "
        "elastically or perfectly inelastically -- real collisions lose "
        "some energy to sound and deformation without the objects sticking "
        "together. Your result will likely sit somewhere between the "
        "virtual lab's two idealized cases.",
    ),
    "energy_incline": HandsOnExperiment(
        title="Race a ball down a book ramp and measure its speed",
        materials=(
            "A ball or marble",
            "A book or board to use as a ramp",
            "A ruler or tape measure",
            "A stopwatch or phone timer",
        ),
        steps=(
            "Prop up one end of the board to make a ramp, and measure how "
            "high the top of the ramp is above the table.",
            "Release the ball from rest at the top and time how long it "
            "takes to reach the bottom.",
            "Measure the length of the ramp, and use it with your time to "
            "estimate the ball's average speed.",
            "Try a steeper ramp at the same starting height, and time it "
            "again -- does the final speed near the bottom feel different?",
            "Enter your measured height into the virtual lab and compare "
            "its predicted speed at the bottom (v = the square root of "
            "2 times gravity times height) to your estimate.",
        ),
        safety_note="Use a light, soft ball and keep the ramp low and "
        "stable so it can't tip or roll off the table.",
        compare_note="Real rolling balls also store some energy in "
        "spinning, not just moving forward, so their measured speed at the "
        "bottom will usually be a little slower than the virtual lab's "
        "frictionless, non-rolling prediction.",
    ),
}


def hands_on_experiment_for(simulation_type) -> HandsOnExperiment | None:
    """The real-materials companion for a simulation type, or ``None`` if
    none has been written yet. Never raises, never fabricates one."""

    if not isinstance(simulation_type, str):
        return None
    return HANDS_ON_EXPERIMENTS.get(simulation_type.strip().casefold())
