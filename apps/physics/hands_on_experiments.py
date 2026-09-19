"""Hands-on, real-materials experiment companions for the virtual Physics
Lab -- inspired by physicslab.app's pairing of virtual simulations with
"hands-on experiments... for use at home or in the classroom" (an external
product analyzed for ideas only; no text, code or assets were copied).

Code-defined data only, keyed by ``simulation_type`` -- no model, no
migration, the same pattern as ``depth_layers``. Deliberately populated
one simulation type at a time; a new simulation type gets a companion
only when one is written and checked like these, never a placeholder.

Every experiment here uses ordinary, cheap, or already-in-a-classroom
materials, is safe in an open indoor or outdoor space, and is written to
be compared against -- not replace -- the deterministic virtual lab. Most
are a genuine estimate-and-compare exercise: the point is for a student to
notice where a real, imperfect measurement (friction, air resistance,
timing error) departs from the idealized model, not to expect an exact
match. A few (marked explicitly in their own ``compare_note``) are
QUALITATIVE analogs instead -- real, standard classroom demonstrations of
the same underlying law, but not something a home measurement can turn
into a number to compare against the virtual lab's output. Being honest
about which kind each one is matters more than making every entry look
the same.

Four simulation types deliberately have NO entry here, because no genuine
hands-on version exists at ordinary classroom/household scale -- inventing
one would misrepresent the phenomenon rather than demonstrate it:
  - ``time_dilation``: relativistic effects require speeds an enormous
    fraction of light speed; nothing achievable at home comes remotely
    close.
  - ``photoelectric_effect``: the classic vacuum-tube photoelectric setup
    (light source, photocathode, electrometer) is standard lab-kit
    equipment, not household material; a solar cell is a genuinely
    different effect (photovoltaic, not the ejection of free electrons
    into vacuum) and would conflate the two if offered as a substitute.
  - ``hubbles_law``: cosmological redshift is only observable with a
    telescope and spectrograph pointed at other galaxies.
  - ``particle_physics``: relativistic energy-momentum relations for
    subatomic particles are only observable with collider- or
    detector-scale equipment.
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
    "orbital_motion": HandsOnExperiment(
        title="Spin a coin around the inside of a bowl",
        materials=(
            "A large smooth bowl or funnel with sloped sides",
            "A coin or marble",
            "A ruler, to compare heights on the slope",
        ),
        steps=(
            "Hold the bowl still and give the coin a firm spin near the "
            "rim, so it circles around the inside wall.",
            "Watch what happens as it slows down: the circling path "
            "spirals inward, getting smaller, while the coin visibly "
            "speeds up as the circle shrinks.",
            "Try starting the coin at different heights (radii) on the "
            "bowl's slope and compare how fast it circles at each one.",
            "In the virtual lab, shrink the orbital radius at the same "
            "gravitational parameter and see the same trend: a smaller "
            "orbit means a faster orbital speed.",
        ),
        safety_note="Use a bowl with no chips or sharp edges, and keep it "
        "on a stable, flat surface so it can't slide off a table.",
        compare_note="This is a QUALITATIVE analogy, not a number-for-"
        "number match: the bowl's slope is not a true inverse-square "
        "gravity well, so it will not reproduce Kepler's third law "
        "exactly. What it does show honestly is the real, general shape "
        "of orbital motion -- a stable circular path, and a smaller orbit "
        "moving faster than a larger one.",
    ),
    "series_parallel_circuit": HandsOnExperiment(
        title="Wire two bulbs in series, then in parallel",
        materials=(
            "A battery or battery holder (e.g. two AA cells)",
            "Two small flashlight bulbs or LEDs (with any needed resistors for LEDs)",
            "Wires with alligator clips",
            "A multimeter, if you have one (optional)",
        ),
        steps=(
            "Connect the battery and both bulbs in a single loop, one "
            "after the other, so all the current flows through both -- "
            "this is the series circuit.",
            "Notice the brightness of each bulb, then disconnect one bulb "
            "entirely and see what happens to the other.",
            "Now rewire the two bulbs side by side, each with its own "
            "direct path back to the battery -- this is the parallel "
            "circuit.",
            "Compare brightness again, then disconnect one bulb and see "
            "whether the other one is affected this time.",
            "If you have a multimeter, measure the voltage across each "
            "bulb in both setups and compare against the virtual lab's "
            "predicted voltage split (series) and matching voltage "
            "(parallel).",
        ),
        safety_note="Use only low-voltage batteries (a few volts), never "
        "a wall outlet, and disconnect the circuit between changes.",
        compare_note="A real bulb's resistance actually changes with "
        "temperature as it heats up, unlike the virtual lab's fixed "
        "resistors -- so exact brightness comparisons are rougher than "
        "the qualitative pattern (one bulb going out breaks a series "
        "circuit but not a parallel one).",
    ),
    "coulombs_law": HandsOnExperiment(
        title="Charge a balloon and pick up paper bits",
        materials=(
            "A balloon",
            "Your hair, or a wool cloth",
            "Small torn bits of paper or tissue",
        ),
        steps=(
            "Rub the balloon briskly on your hair or the wool cloth for "
            "about 10-20 seconds to build up a static charge.",
            "Slowly bring the balloon close to the paper bits without "
            "touching them, and watch them jump up to meet it.",
            "Move the balloon farther away a little at a time and notice "
            "the distance at which the paper stops responding.",
            "Recharge the balloon and try holding it near a thin, steady "
            "stream of water from a tap -- watch the stream bend toward it.",
        ),
        safety_note="Keep the balloon away from your face when charging "
        "it, and use only a light stream of water near electrical outlets.",
        compare_note="This is a QUALITATIVE demonstration, not a number-"
        "for-number match: there is no practical way to measure the "
        "actual charge on the balloon at home, so it cannot be entered "
        "into the virtual lab's charge inputs. What it does show honestly "
        "is the real behavior Coulomb's law describes: an attractive "
        "force between charges that gets noticeably weaker with distance.",
    ),
    "radioactive_decay": HandsOnExperiment(
        title="Simulate decay by flipping coins",
        materials=(
            "At least 50 coins (the more, the smoother the result)",
            "A flat surface to spread them on",
            "A way to record a count each round (paper and pencil)",
        ),
        steps=(
            "Spread all the coins heads-and-tails-up randomly and record "
            "the total count as your starting sample.",
            "Flip every coin once. Remove every coin that lands heads -- "
            "those have 'decayed' this round.",
            "Record how many coins remain, then repeat: flip all the "
            "remaining coins and remove the heads again.",
            "Keep going for several rounds and plot remaining count "
            "against round number.",
            "Compare your plot's shape to the virtual lab's remaining-"
            "count curve. Since each flip removes about half the coins, "
            "one round here corresponds to one half-life.",
        ),
        safety_note="No special precautions needed beyond a flat, clear "
        "surface to flip and collect coins on.",
        compare_note="This models the mathematical LAW of exponential "
        "decay, not real radioactivity itself -- coins have no physical "
        "half-life, they are just a fair, memoryless 50/50 process, which "
        "is exactly the property real radioactive decay also has. With "
        "only 50-100 coins, expect visible statistical wobble round to "
        "round, unlike the virtual lab's perfectly smooth curve; more "
        "coins make the match smoother.",
    ),
    "buoyancy": HandsOnExperiment(
        title="Sink-or-float test, then shape a sinker into a floater",
        materials=(
            "A sink, basin, or large bowl of water",
            "A lump of modelling clay or aluminium foil",
            "A few small household objects (a coin, a small stone, a "
            "piece of wood, a bottle cap)",
        ),
        steps=(
            "Predict whether each small object will float or sink, then "
            "test each one in the water.",
            "Roll the clay (or foil) into a solid ball and drop it in -- "
            "note whether it floats or sinks.",
            "Now reshape the same piece of clay or foil into a wide, "
            "hollow boat shape and place it gently on the water.",
            "Compare: it is the exact same material and the exact same "
            "weight both times -- only the shape changed.",
            "Enter the object's density and the water's density into the "
            "virtual lab and compare its floats/sinks prediction and "
            "submerged fraction.",
        ),
        safety_note="Use a shallow container and keep electronics well "
        "away from the water.",
        compare_note="Shaping the clay into a boat does not change its "
        "density as a solid lump -- it changes how much water it "
        "displaces, which is exactly the concept's own point: floating "
        "depends on the average density of the whole shape (including the "
        "air it encloses), not on weight alone.",
    ),
    "refraction": HandsOnExperiment(
        title="Make a coin reappear with refracted light",
        materials=(
            "An opaque cup or bowl",
            "A coin",
            "A pitcher of water",
        ),
        steps=(
            "Place the coin flat inside the empty cup, then step back "
            "(or lower your head) until the coin just disappears behind "
            "the rim.",
            "Without moving your head or the cup, slowly pour water into "
            "the cup.",
            "Watch the coin appear to rise into view as the water level "
            "rises, even though neither the coin nor your eye moved.",
            "Also try the classic pencil-in-a-glass-of-water: put a "
            "pencil in a glass, half in water, and look at it from the "
            "side -- it will look bent or broken at the surface.",
            "Enter a light-to-water angle of incidence into the virtual "
            "lab and compare the predicted bend to what you see.",
        ),
        safety_note="Use a container that will not tip over, and clean up "
        "any spilled water promptly.",
        compare_note="Light bends by a fixed, predictable amount at the "
        "water's surface (Snell's law) -- the 'trick' is entirely real "
        "physics, not an illusion, which is exactly why the virtual lab's "
        "angle calculation can predict it.",
    ),
    "calorimetry": HandsOnExperiment(
        title="Mix hot and cold water and predict the final temperature",
        materials=(
            "Two cups or containers",
            "A kitchen or candy thermometer",
            "Warm water and cold water (from the tap is fine)",
            "An insulated cup or a foam cup, if available",
        ),
        steps=(
            "Measure roughly equal amounts of warm water and cold water "
            "into the two containers, and measure and record each "
            "starting temperature.",
            "Before mixing, predict the final temperature using the "
            "virtual lab's equal-mass case.",
            "Pour them together into the insulated cup, stir gently, and "
            "measure the temperature every 15-30 seconds until it stops "
            "changing.",
            "Compare the settled temperature to your prediction and to "
            "the virtual lab's computed equilibrium temperature.",
            "Try again with a much larger amount of one of the two "
            "waters, and see how the equilibrium temperature shifts "
            "toward the larger amount.",
        ),
        safety_note="Use warm tap water, not boiling water, and have an "
        "adult help if using anything hotter.",
        compare_note="Heat lost to the surrounding air and the container "
        "itself (not accounted for in the virtual lab's two-substance "
        "model) usually pulls your real equilibrium temperature a little "
        "toward room temperature compared to the idealized prediction.",
    ),
    "ideal_gas_law": HandsOnExperiment(
        title="Feel gas pressure change with a sealed syringe",
        materials=(
            "A syringe with no needle (a cooking or medicine syringe works)",
            "A way to seal the tip (a fingertip, or a small cap)",
            "A small marshmallow, optional, to visually show it shrink under pressure",
        ),
        steps=(
            "Pull the plunger to about the halfway mark, then seal the "
            "tip so no air can escape.",
            "Slowly push the plunger in further and feel the resistance "
            "build as the trapped air's volume shrinks.",
            "Let go of the plunger and feel it push back out on its own "
            "toward its starting position.",
            "Try pulling the plunger out past the halfway mark instead, "
            "with the tip still sealed, and feel it resist being pulled "
            "as the volume increases.",
            "In the virtual lab, shrink the volume at constant "
            "temperature and moles, and compare the predicted pressure "
            "rise to how much harder the plunger was to push.",
        ),
        safety_note="Do not seal the tip with your mouth, and release the "
        "plunger slowly to avoid it snapping back forcefully.",
        compare_note="This is a QUALITATIVE demonstration -- a syringe has "
        "no way to measure the actual pressure in pascals at home, so "
        "there is no number to enter and compare. What it does show "
        "honestly is Boyle's law's real direction: squeezing a fixed "
        "amount of gas into a smaller space makes it push back harder.",
    ),
    "doppler_effect": HandsOnExperiment(
        title="Swing a sound source and listen to the pitch shift",
        materials=(
            "A phone or small speaker that can play a steady tone (many "
            "free tone-generator or metronome apps work)",
            "A string, shoelace, or lanyard to attach it",
            "A second person to listen from a fixed spot",
        ),
        steps=(
            "Securely tie the phone or speaker to the string so it "
            "cannot slip loose, and start it playing a steady tone.",
            "Standing in an open space, swing it in a wide circle around "
            "you at a safe, steady speed.",
            "Have the listener stand a few metres away, off to the side, "
            "and describe what they hear as the source swings toward and "
            "then away from them.",
            "Enter an estimated source speed into the virtual lab (with "
            "the observer standing still) and compare the predicted "
            "frequency shift to what the listener described.",
        ),
        safety_note="Swing only in a clear, open space well away from "
        "people, walls, and furniture, and make sure the attachment is "
        "secure before swinging.",
        compare_note="The pitch change you hear is real and directly "
        "predicted by the Doppler formula, but a hand-swung source moves "
        "far slower than the virtual lab's more dramatic example speeds -- "
        "expect a noticeable but subtle shift, not a dramatic one.",
    ),
    "magnetic_force": HandsOnExperiment(
        title="Deflect a compass needle with an electric current",
        materials=(
            "A small magnetic compass",
            "A single AA or AAA battery",
            "A length of insulated wire",
            "A small bulb or resistor (to limit the current safely)",
        ),
        steps=(
            "Lay the wire flat, running north-south, directly above and "
            "parallel to the compass, with the small bulb wired in "
            "series partway along it.",
            "Let the compass needle settle pointing north, then briefly "
            "touch the wire's ends to the battery terminals to complete "
            "the circuit.",
            "Watch the compass needle swing away from north while current "
            "flows, then release the connection and watch it swing back.",
            "Reverse which battery terminal each wire end touches, and "
            "notice the needle deflects the opposite way.",
        ),
        safety_note="Keep the connection brief and always include the "
        "bulb or a resistor in the circuit -- a bare wire straight across "
        "a battery is a short circuit and can get hot fast.",
        compare_note="This demonstrates the real link between electric "
        "current and magnetic force (a current is many moving charges, "
        "and this is Oersted's own historic experiment) -- but it shows a "
        "wire's magnetic FIELD deflecting a compass, not the virtual "
        "lab's exact scenario of the magnetic force on one free moving "
        "charge, so treat it as showing the same underlying physics "
        "family, not a numeric match.",
    ),
    "electromagnetic_induction": HandsOnExperiment(
        title="Wind a coil and light an LED by waving a magnet",
        materials=(
            "Thin enameled (magnet) wire, a few metres",
            "A cardboard tube (a toilet paper roll works)",
            "A strong small magnet (a neodymium magnet works well)",
            "An LED, or a multimeter/galvanometer if you have one",
        ),
        steps=(
            "Wind the wire tightly around the cardboard tube many times "
            "(more turns is better), leaving both ends free, and scrape "
            "the enamel off both bare ends.",
            "Connect the two ends to the LED (or multimeter).",
            "Push the magnet quickly in and out of the tube, through the "
            "coil, and watch for a brief flash on the LED (or a needle "
            "movement on the multimeter) each time the magnet moves.",
            "Try moving the magnet faster, and notice the effect gets "
            "stronger the faster the field through the coil changes.",
            "In the virtual lab, shorten the time interval for the same "
            "field change and compare the predicted EMF increase.",
        ),
        safety_note="Keep strong magnets away from electronics, credit "
        "cards, and pacemakers, and away from small children who might "
        "swallow one.",
        compare_note="A hand-wound coil's exact number of turns and area "
        "are hard to measure precisely, so treat this as confirming the "
        "real relationship (faster field change means a bigger induced "
        "effect, and it only happens while the magnet is moving) rather "
        "than a numeric EMF match.",
    ),
    "bohr_model": HandsOnExperiment(
        title="See real atomic spectral lines with a CD",
        materials=(
            "An old CD or DVD (the shiny, unlabelled side)",
            "A fluorescent light bulb or tube (or a neon/sodium street "
            "light after dark)",
            "A dark-ish room",
        ),
        steps=(
            "Hold the CD flat, shiny side toward a fluorescent light, and "
            "tilt it slowly until you see the light's reflection spread "
            "into colours -- the CD's tightly spaced tracks act like a "
            "diffraction grating.",
            "Look closely at the spread of colours: instead of a smooth, "
            "continuous rainbow, you should see distinct bright bands "
            "separated by darker gaps.",
            "If you can compare it to an incandescent (old-style "
            "filament) bulb's spectrum, notice that one IS a smooth, "
            "continuous rainbow instead.",
            "Those separate bright bands are the real observational "
            "evidence for quantised energy levels: each one comes from "
            "electrons in the gas jumping between two specific levels, "
            "exactly the transitions the virtual lab computes.",
        ),
        safety_note="Do not look directly at bright light sources for a "
        "long time, and handle the CD's edge carefully if it is cracked "
        "or chipped.",
        compare_note="A CD is a much cruder diffraction grating than lab "
        "equipment, so the separate bands will look fuzzy rather than "
        "razor-sharp, and you cannot read off exact wavelengths this way. "
        "What it does show honestly, and for real, is the qualitative "
        "fact the Bohr model explains: atoms emit light only at specific, "
        "separated colours, not a smooth spread.",
    ),
}


def hands_on_experiment_for(simulation_type) -> HandsOnExperiment | None:
    """The real-materials companion for a simulation type, or ``None`` if
    none has been written yet. Never raises, never fabricates one."""

    if not isinstance(simulation_type, str):
        return None
    return HANDS_ON_EXPERIMENTS.get(simulation_type.strip().casefold())
