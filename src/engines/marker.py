"""Marker data model — a map "point of interest" pin the Marcador tool
places (see src/canvas/marker_item.py / src/canvas/tools/marker_tool.py).

Simple enough (no enums, no nested dataclasses) that dataclasses.asdict()
round-trips straight to/from the canvas_items.metadata JSON column, unlike
TextProperties (src/engines/typography.py) which needs hand-written
to_dict/from_dict for its enum + nested-dataclass fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# (key, icon, label) — feeds both the "Categoria" dropdown and the default
# icon a fresh marker gets when placed with that icon selected.
CATEGORIES: list[tuple[str, str, str]] = [
    ("poi", "📍", "Ponto de Interesse"),
    ("marco", "⭐", "Marco Importante"),
    ("combate", "⚔", "Zona de Combate"),
    ("tesouro", "💎", "Tesouro"),
    ("perigo", "⚠", "Perigo"),
    ("loja", "🏪", "Loja"),
]

# (key, label) — the "Shaders" multi-select in MarkerEditPanel; each key has
# a matching _draw_<key> routine in marker_item.py.
EFFECTS: list[tuple[str, str]] = [
    ("redemoinhos", "Redemoinhos"),
    ("folhas", "Folhas ao Vento"),
    ("nuvens", "Nuvens Carregadas"),
    ("espinhos", "Espinhos do Chão"),
    ("brilho", "Brilho Mágico"),
]

# Per-effect layer config — same "each active effect is its own independent
# layer" idea as src/engines/asset_effects.py, just without the paintable
# grid (a marker's effect is always radial around the pin, not a region).
# (attr, label) — the tunable strength fields every layer exposes; each has
# a matching row in MarkerEditPanel's per-effect block.
PARAMS: list[tuple[str, str]] = [
    ("intensity", "Intensidade"),
    ("radius", "Raio"),
    ("opacity", "Opacidade"),
]
INTENSITY_MIN, INTENSITY_MAX, INTENSITY_DEFAULT = 0.0, 100.0, 50.0
RADIUS_MIN, RADIUS_MAX, RADIUS_DEFAULT = 0.0, 2000.0, 100.0
OPACITY_MIN, OPACITY_MAX, OPACITY_DEFAULT = 0, 100, 100

# Default tint per effect — used both as a fresh layer's initial "color" and
# as the fallback if a saved value is missing/invalid.
_DEFAULT_COLORS = {
    "redemoinhos": "#78C8FF",
    "folhas": "#5AD73C",
    "nuvens": "#373744",
    "espinhos": "#96785A",
    "brilho": "#FFEB96",
}


def default_layer(key: str = "") -> dict:
    return {
        "intensity": INTENSITY_DEFAULT,
        "radius": RADIUS_DEFAULT,
        "opacity": OPACITY_DEFAULT,
        "color": _DEFAULT_COLORS.get(key, "#FFFFFF"),
    }


def default_layers() -> dict[str, dict]:
    return {key: default_layer(key) for key, _label in EFFECTS}


def _clamp(value, lo, hi, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def normalize_effect_layers(raw, active: list[str], legacy_radius: float = RADIUS_DEFAULT,
                             legacy_intensity: float = INTENSITY_DEFAULT) -> dict[str, dict]:
    """Coerces whatever was loaded from JSON into a complete, safe layers
    dict — every effect key always present with valid types. If `raw` has
    nothing useful for a key that's actually active (an older save, from
    before per-effect layers existed, which only had the flat global
    effect_radius/effect_intensity), seeds that key's layer from those
    legacy values instead of the generic default, so upgrading doesn't
    visibly change existing markers."""
    layers = default_layers()
    saved = raw if isinstance(raw, dict) else {}
    for key, layer in layers.items():
        entry = saved.get(key)
        if not isinstance(entry, dict):
            if key in active:
                layer["radius"] = _clamp(legacy_radius, RADIUS_MIN, RADIUS_MAX, RADIUS_DEFAULT)
                layer["intensity"] = _clamp(legacy_intensity, INTENSITY_MIN, INTENSITY_MAX, INTENSITY_DEFAULT)
            continue
        layer["intensity"] = _clamp(entry.get("intensity"), INTENSITY_MIN, INTENSITY_MAX, layer["intensity"])
        layer["radius"] = _clamp(entry.get("radius"), RADIUS_MIN, RADIUS_MAX, layer["radius"])
        layer["opacity"] = int(_clamp(entry.get("opacity"), OPACITY_MIN, OPACITY_MAX, layer["opacity"]))
        color = entry.get("color")
        if isinstance(color, str) and len(color) in (4, 7) and color.startswith("#"):
            layer["color"] = color
    return layers


# Full emoji palette offered by the icon picker (MarkerToolPanel/
# MarkerEditPanel) — independent from CATEGORIES (whose icons are just each
# category's *default*, still included here so every category has a match).
# Deliberately large: the picker scrolls, so there's no reason to keep this
# short.
ICONS: list[str] = list(dict.fromkeys([
    *[icon for _key, icon, _label in CATEGORIES],
    "🚩", "🏁", "📌", "📍", "🧭", "🗺", "🏰", "🏯", "🏠", "🏚",
    "⛺", "🌉", "🌋", "⛰", "🏔", "🌲", "🌳", "🍄", "🕳", "🌊",
    "⚔", "🛡", "🏹", "🗡", "💣", "🔥", "☠", "👹", "🐉", "🐺",
    "💰", "💎", "🗝", "📦", "🏆", "⚗", "📜", "🔮", "✨", "⭐",
    "⚠", "☣", "🕸", "🚪", "⛩", "🗿", "⚓", "🛶", "🏪", "⚒",
    "🔔", "❓", "❗", "💀", "👑", "🎯", "🧙", "🧝", "🐲",
    "🏛", "⛲", "🛖", "🏗", "⛏", "🪓", "🏺", "🐍", "🦂", "🕷",
    "🩸", "🧿", "🪦", "🕯", "🧪", "🔗", "🌫", "🌀", "⚡", "🔱",
    "🦴", "🐴", "🚢", "🏕", "🎪",
]))


def category_for_icon(icon: str) -> str:
    """The category key whose default icon matches `icon`, else the first
    category — used to give a freshly-placed marker a sensible category
    without forcing the user to also pick one before placing."""
    for key, cat_icon, _label in CATEGORIES:
        if cat_icon == icon:
            return key
    return CATEGORIES[0][0]


def category_label(key: str) -> str:
    for cat_key, _icon, label in CATEGORIES:
        if cat_key == key:
            return label
    return CATEGORIES[0][2]


def category_icon(key: str) -> str:
    for cat_key, icon, _label in CATEGORIES:
        if cat_key == key:
            return icon
    return CATEGORIES[0][1]


@dataclass
class MarkerProperties:
    name: str = "Novo Marcador"
    category: str = "poi"
    icon: str = "📍"
    description: str = ""
    effects: list[str] = field(default_factory=list)
    # Legacy globals — no longer written by MarkerEditPanel (each effect has
    # its own radius/intensity in effect_layers now), kept only so an old
    # save's values can seed the migration in normalize_effect_layers().
    effect_radius: float = 100.0
    effect_intensity: float = 50.0
    # key -> {intensity, radius, opacity, color} — see normalize_effect_layers.
    effect_layers: dict = field(default_factory=default_layers)
    # Contact shadow — a soft dark ellipse under the icon, independent of
    # the 5 shader effects above (grounds the marker instead of decorating
    # around it).
    shadow_enabled: bool = False
    shadow_strength: float = 50.0
