"""Code-defined, allow-listed "Challenge the AI" claims.

HANAI states a Physics claim; the student judges it true or false and
writes their reasoning BEFORE the ground truth (and HANAI's own
explanation) is revealed. This is the "reasoning first" mode: judging a
claim, and defending that judgement, is itself the exercise -- the reveal
only comes after the student has committed to an answer, the same
principle the Predict step already uses ("you commit to a prediction
before running the experiment").

Ground truth (``is_true``) is fixed, code-reviewed data, never an AI/LLM
judgement call -- the same "no LLM decides correctness" rule every other
checker in this project follows (``lab_scenarios.py``, the numeric/choice
question evaluators). Claims are deliberately built from this project's
OWN already-catalogued real misconceptions (see
``apps.physics.management.commands.seed_physics``'s ``common_misconceptions``
for the "Acceleration" concept) rather than invented from scratch, so the
false claims here are genuine, real classroom misconceptions, not
strawmen.

Code-defined data only, keyed by ``claim_id`` -- no model, no migration, no
persistence of the student's answer or reasoning. Exactly like
``lab_scenarios.py``'s Challenge Mode, nothing here is recorded as
learning evidence; the durable record of a student's investigation is
still the explanation they write in the normal Explain step. Deliberately
populated for Kinematics only today -- a new simulation type gets claims
only when they are written and checked like the ones below, never a
placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicsClaim:
    claim_id: str
    simulation_type: str
    statement: str
    is_true: bool
    explanation: str

    @property
    def as_client_dict(self) -> dict:
        """Student-safe description for the page. Deliberately omits
        ``is_true`` and ``explanation`` -- revealing either before the
        student commits to a judgement would defeat the whole exercise."""

        return {"claim_id": self.claim_id, "statement": self.statement}


_CLAIMS: dict[str, PhysicsClaim] = {}


def _register(claim: PhysicsClaim) -> None:
    _CLAIMS[claim.claim_id] = claim


def get_claim(claim_id) -> PhysicsClaim | None:
    if not isinstance(claim_id, str):
        return None
    return _CLAIMS.get(claim_id)


def claims_for(simulation_type) -> tuple[PhysicsClaim, ...]:
    return tuple(c for c in _CLAIMS.values() if c.simulation_type == simulation_type)


# --- the built-in Kinematics claims --------------------------------------

_register(
    PhysicsClaim(
        claim_id="acceleration-means-speeding-up",
        simulation_type="kinematics",
        statement="Acceleration always means an object is speeding up.",
        is_true=False,
        explanation=(
            "Acceleration is any change in velocity over time -- speeding "
            "up, slowing down, or (in more than one dimension) changing "
            "direction. In this lab, set a negative acceleration on a "
            "cart already moving forward (v0 > 0, a < 0): its speed "
            "decreases the whole time, yet its acceleration is exactly a, "
            "clearly not zero. A common shorthand is to call slowing down "
            "'deceleration', but physically it is still acceleration -- "
            "just acceleration that opposes the current velocity, "
            "matching this lab's own formula a = (v - v0) / t regardless "
            "of whether v ends up bigger or smaller than v0."
        ),
    )
)

_register(
    PhysicsClaim(
        claim_id="zero-velocity-means-zero-acceleration",
        simulation_type="kinematics",
        statement=(
            "If an object's velocity is momentarily zero, its acceleration "
            "must also be zero at that instant."
        ),
        is_true=False,
        explanation=(
            "Velocity and acceleration describe different things -- how "
            "fast position is changing, versus how fast velocity itself "
            "is changing -- and either can be zero while the other is "
            "not. In this lab, start the cart with v0 > 0 and a < 0: its "
            "velocity passes through exactly zero at t = -v0 / a, but the "
            "acceleration is still the same constant a the whole time, "
            "not zero -- which is exactly why the cart keeps moving and "
            "reverses direction right after. The classic real-world "
            "version is a ball thrown straight up: at the very top of its "
            "flight its velocity is momentarily zero, but gravity is "
            "still accelerating it downward the entire time."
        ),
    )
)

_register(
    PhysicsClaim(
        claim_id="zero-acceleration-means-constant-velocity",
        simulation_type="kinematics",
        statement=(
            "If an object's acceleration stays at exactly zero, its "
            "velocity never changes."
        ),
        is_true=True,
        explanation=(
            "This one is true, straight from this lab's own formula: "
            "v = v0 + a t. Set a = 0 and the second term vanishes "
            "entirely for every value of t, leaving v = v0 forever -- the "
            "velocity is stuck at whatever it started at. This is also "
            "just Newton's first law in kinematics language: with no "
            "acceleration (which means no net force), velocity has "
            "nothing to change it, so it stays exactly constant."
        ),
    )
)
