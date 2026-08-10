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
]

# Types where X/Y actually mean something — sky is ambient, not aimed at a
# point, so LightEditPanel hides the POSIÇÃO row for it (the item still has
# a position on the map, it's just not shown/relevant).
POSITIONED_TYPES = {"point", "spot"}

# "sky" isn't a placeable object at all — picking it in LightPanel opens a
# single global day/night control (SkyEditPanel) instead of arming LightTool
# for placement (see LightMediator._on_type_picked). There's exactly one sky
# setting per map, persisted separately from placed LightItems.
GLOBAL_TYPES = {"sky"}

_DEFAULT_COLORS = {
    "point": "#FFCB6B",
    "spot": "#FFE082",
    "sky": "#0B1533",  # night tint (SkyEditPanel's "Cor da noite"), not a glow color
}


def default_color(light_type: str) -> str:
    return _DEFAULT_COLORS.get(light_type, "#FFCB6B")


# point/spot default dimmer than the dataclass-wide 0.75 — full lights
# placed at the default radius were blowing out too bright/flat; other
# types (sky's day/night tint) don't use this field the same way, so
# they're left at LightProperties' own default.
_DEFAULT_INTENSITY = {
    "point": 0.50,
    "spot": 0.50,
}


def default_intensity(light_type: str) -> float:
    return _DEFAULT_INTENSITY.get(light_type, 0.75)


@dataclass
class LightProperties:
    light_type: str = "point"
    intensity: float = 0.75
    radius: float = 50.0
    color: str = "#FFCB6B"
    shadows: bool = True
    volumetric: bool = False
    # Falloff curve shape, 0-100 (see lighting_compositor.falloff_gamma) —
    # 0 = concentrated (stays near-peak brightness through most of the
    # radius, then cuts off sharply near the edge, reading as a hot little
    # core), 100 = diffuse (fades gradually from the center outward, no hot
    # spot). Not "how far the light reaches" (that's radius) — how evenly
    # its own brightness is spread across that reach.
    falloff: float = 50.0
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
