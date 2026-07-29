"""Light data model — a map light object the Iluminação panel places (see
src/canvas/light_item.py / src/canvas/tools/light_tool.py), except "sky"
(see GLOBAL_TYPES below) which is a single global day/night setting rather
than a placeable object (see src/layouts/panels/light/sky_panel.py).

Simple enough (no enums, no nested dataclasses) that dataclasses.asdict()
round-trips straight to/from the canvas_items.metadata JSON column (or, for
the global sky settings, a UIStateRepository key — see LightMediator), same
convention as MarkerProperties (src/engines/marker.py).
"""

from __future__ import annotations

from dataclasses import dataclass

# (key, icon, label)
LIGHT_TYPES: list[tuple[str, str, str]] = [
    ("point", "💡", "Point Light"),
    ("spot", "🔦", "Spot Light"),
    ("sky", "🌌", "Sky Light"),
    ("fog", "🌫", "Fog"),
]

# Types where X/Y actually mean something — sky is ambient, not aimed at a
# point, so LightEditPanel hides the POSIÇÃO row for it (the item still has
# a position on the map, it's just not shown/relevant).
POSITIONED_TYPES = {"point", "spot", "fog"}

# "sky" isn't a placeable object at all — picking it in LightPanel opens a
# single global day/night control (SkyEditPanel) instead of arming LightTool
# for placement (see LightMediator._on_type_picked). There's exactly one sky
# setting per map, persisted separately from placed LightItems.
GLOBAL_TYPES = {"sky"}

_DEFAULT_COLORS = {
    "point": "#FFCB6B",
    "spot": "#FFE082",
    "sky": "#0B1533",  # night tint (SkyEditPanel's "Cor da noite"), not a glow color
    "fog": "#B0BEC5",
}


def default_color(light_type: str) -> str:
    return _DEFAULT_COLORS.get(light_type, "#FFCB6B")


def light_label(key: str) -> str:
    for t_key, _icon, label in LIGHT_TYPES:
        if t_key == key:
            return label
    return LIGHT_TYPES[0][2]


def light_icon(key: str) -> str:
    for t_key, icon, _label in LIGHT_TYPES:
        if t_key == key:
            return icon
    return LIGHT_TYPES[0][1]


@dataclass
class LightProperties:
    light_type: str = "point"
    intensity: float = 0.75
    radius: float = 50.0
    color: str = "#FFCB6B"
    shadows: bool = True
    volumetric: bool = False
    # Aim, only meaningful for "spot" (restricts the lit area to a cone) —
    # see src/engines/lighting_compositor.py::cone_path. Degrees, Qt arc
    # convention (0 at 3 o'clock, sweeping through the scene's y-down axis).
    direction_deg: float = 0.0
    cone_angle_deg: float = 45.0
    # Only meaningful for the global "sky" settings object (see
    # GLOBAL_TYPES) — 100 = full day (no darkening at all, the map's normal
    # look), 0 = full night (`color` used as the darkening tint, painted
    # under every other light so placed lights still cut through it). See
    # GlobalLightingOverlay._paint_sky.
    day_amount: float = 100.0
