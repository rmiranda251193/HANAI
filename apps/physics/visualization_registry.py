"""Deterministic registry of Physics Lab *visualization* definitions.

This is the presentation-layer sibling of ``simulation_registry``. It answers
"which client renderers may draw this simulation type, and which views/controls
they offer" -- nothing more. It holds **only data**: a renderer is named by a
short, fixed slug that the template matches against an allow-list of vendored
static modules. No JavaScript, no callables, and no user input are ever stored
or evaluated here.

The physics stays exactly where it was: ``simulations_kinematics.py`` /
``simulations.py`` on the server, mirrored for live interaction by
``static/js/physics/*.js``. A 3D view is one more way to render the same
authoritative state; it never becomes a second physics engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisualizationDefinition:
    """Everything a template needs to offer 2D/3D views of one simulation type.

    ``renderer`` is a stable slug (e.g. ``"kinematics-3d"``). The template turns
    it into a ``data-renderer`` attribute; the client module matches it against
    its own hard-coded allow-list before loading anything. It is never a URL,
    a path, or code.
    """

    simulation_type: str
    renderer: str
    supported_views: tuple[str, ...] = ("2d",)
    controls: tuple[str, ...] = ()
    summary_hint: str = ""
    #: instrument panels this simulation supports (presentation only)
    #: -- e.g. "hud", "trail", "vectors", "inspector", "measure", "compare",
    #: "graphs", "scenarios".
    instruments: tuple[str, ...] = ()
    #: graph modes offered by the synchronized graph (data only)
    graph_modes: tuple[str, ...] = ()

    @property
    def has_3d(self) -> bool:
        return "3d" in self.supported_views

    def has(self, instrument: str) -> bool:
        return instrument in self.instruments


_RENDERER_SLUG_ALLOWED = frozenset({"kinematics-3d"})

_REGISTRY: dict[str, VisualizationDefinition] = {}


def register(definition: VisualizationDefinition) -> None:
    if definition.renderer not in _RENDERER_SLUG_ALLOWED:
        raise ValueError(
            f"Unknown renderer slug {definition.renderer!r}. Add it to "
            "_RENDERER_SLUG_ALLOWED and vendor its module before registering."
        )
    _REGISTRY[definition.simulation_type] = definition


def get_visualization(simulation_type) -> VisualizationDefinition | None:
    """Return the definition for ``simulation_type``, or ``None``.

    Accepts any value and never raises for an unknown/garbage key -- a missing
    entry simply means "2D only" to the caller.
    """

    if not isinstance(simulation_type, str):
        return None
    return _REGISTRY.get(simulation_type)


def registered_visualization_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


# --- definitions -----------------------------------------------------

register(
    VisualizationDefinition(
        simulation_type="kinematics",
        renderer="kinematics-3d",
        supported_views=("2d", "3d"),
        controls=("play", "pause", "step_forward", "step_back", "reset", "scrub", "camera"),
        summary_hint=(
            "A cart moves along a straight track. Position, velocity and "
            "acceleration are shown as labelled values and vectors."
        ),
        instruments=("hud", "trail", "vectors", "inspector", "measure", "compare", "scenarios"),
        graph_modes=("position", "velocity", "acceleration"),
    )
)
