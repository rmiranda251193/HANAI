# Adding a new Physics simulation to Scenario Studio

Teacher Scenario Studio, the deterministic scenario checker, and the
Physics Lab's experiment lifecycle are all generic. A simulation becomes
usable in all three by registering itself once — nothing in
`scenario_services.py`, `scenario_views.py`, or `lab_scenarios.py` ever
names a specific Physics topic.

## 1. How a simulation registers

Every simulation module (`apps/physics/simulations_*.py`) calls
`simulation_registry.register(SimulationDefinition(...))` once, at import
time. `apps/physics/apps.py` imports every simulation module in
`AppConfig.ready()`.

## 2. How it exposes inputs

`SimulationDefinition.input_fields` names the POST fields the Physics Lab's
Predict/Observe/Explain steps read, and `bounds`/`default_state` give each
field's valid range and starting value. This is also exactly what Scenario
Studio uses to validate a teacher's `initial_state` — no separate input
schema.

## 3. How it exposes authoritative outputs

If the simulation should be scenario-capable, it also builds a
`simulation_registry.ScenarioCapability` and attaches it as
`SimulationDefinition.scenario`:

- `observable_fields`: a `frozenset[str]` naming the state quantities a
  target condition may check (e.g. `{"position_m", "velocity_m_s"}`).
- `state_at(parameters, at_time_s) -> dict`: the simulation's own
  authoritative, deterministic calculation. `parameters` are raw
  submitted-or-stored values keyed by `input_fields`; every value **must be
  clamped inside this function** so a forged value can never overflow a
  check. Returns a dict keyed by `observable_fields`.
- `supports_reverses` / `reverses_at` (optional): only implement this pair
  if the simulation's motion can meaningfully reverse direction.

A simulation with no `scenario=` is simply never offered in Scenario Studio
— everything else about it is unaffected.

## 4. How scenario target conditions are declared

A target condition is plain, validated JSON: `{"kind": ..., "field": ...,
"target": ..., "tolerance": ..., "at_time_s": ...}` (or `range_min`/
`range_max` for `within_range`). `kind` is one of a closed allow-list
(`value`, `greater_than`, `less_than`, `within_range`, `reverses` —
`lab_scenarios._ALLOWED_KINDS`); `field` must be one of the selected
simulation's own `observable_fields`. There is no formula, `eval`, or
`exec` anywhere in this path.

## 5. How the generic evaluator uses the simulation

`lab_scenarios.evaluate_scenario(scenario, *, parameters)` looks up the
scenario's own `SimulationDefinition`, calls its `ScenarioCapability.state_at`
to reconstruct the relevant state, and compares it against the target. This
function is topic-agnostic — it never branches on `simulation_type`.

## 6. How to make a simulation scenario-capable

Add a `ScenarioCapability` to its `SimulationDefinition` (step 3). That's
the entire integration: Teacher Scenario Studio's simulation picker
(`scenario_capable_simulation_types()`), validation, the checker, AI
drafting, experiment persistence, evidence, and `LessonActivity` linking all
already work generically once it's registered.

## 7. How to test a new simulation

`apps/physics/tests_scenario_platform.py` registers a throwaway
`test_mock_pendulum` `SimulationDefinition` (with `addCleanup` to
`unregister` it) and drives it through the real Scenario Studio service
layer, the checker, the experiment endpoint, evidence, and
`LessonActivity` — proving the contract works with zero changes to Scenario
Studio itself. Copy that pattern for a new real simulation's own tests.

## Example: adding "Simple Pendulum Period"

```python
# apps/physics/simulations_pendulum.py
import math
from .simulation_registry import ScenarioCapability, SimulationDefinition, register

def clamp_length(v):   return max(0.1, min(5.0, float(v)))
def clamp_gravity(v):  return max(1.0, min(20.0, float(v)))

def pendulum_state(*, length_m, gravity_m_s2):
    length, gravity = clamp_length(length_m), clamp_gravity(gravity_m_s2)
    return {"period_s": 2 * math.pi * math.sqrt(length / gravity)}

def _scenario_state_at(parameters, at_time_s):
    return pendulum_state(
        length_m=parameters.get("length_m", 1.0),
        gravity_m_s2=parameters.get("gravity_m_s2", 9.8),
    )

register(SimulationDefinition(
    simulation_type="simple_pendulum",
    template="physics/simple_pendulum.html",
    equations=("T = 2π√(L/g)",),
    units={"length_m": "m", "gravity_m_s2": "m/s^2", "period_s": "s"},
    bounds={"length_m": (0.1, 5.0), "gravity_m_s2": (1.0, 20.0)},
    default_state={"length_m": 1.0, "gravity_m_s2": 9.8},
    input_fields=("length_m", "gravity_m_s2"),
    scenario=ScenarioCapability(
        observable_fields=frozenset({"period_s"}),
        state_at=_scenario_state_at,
    ),
))
```

That's the whole integration. A teacher can now build a "make the period
about 2 seconds" scenario for it without touching Scenario Studio, the
checker, or any teacher-evidence code.
