"""Light data model — a map light object the Iluminação panel places (see
src/canvas/light_item.py / src/canvas/tools/light_tool.py).

Simple enough (no enums, no nested dataclasses) that dataclasses.asdict()
round-trips straight to/from the canvas_items.metadata JSON column, same
convention as MarkerProperties (src/engines/marker.py).
"""

from __future__ import annotations

from dataclasses import dataclass

# (key, icon, label)
LIGHT_TYPES: list[tuple[str, str, str]] = [
    ("point", "💡", "Point Light"),
    ("directional", "☀", "Directional Light"),
    ("spot", "🔦", "Spot Light"),
    ("sky", "🌌", "Sky Light"),
    ("fog", "🌫", "Fog"),
]

# Types where X/Y actually mean something — directional/sky are ambient,
# not aimed at a point, so LightEditPanel hides the POSIÇÃO row for them
# (the item still has a position on the map, it's just not shown/relevant).
POSITIONED_TYPES = {"point", "spot", "fog"}

_DEFAULT_COLORS = {
    "point": "#FFCB6B",
    "spot": "#FFE082",
    "directional": "#FFD54F",
    "sky": "#90CAF9",
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
