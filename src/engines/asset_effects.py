"""Asset effect-region data — the paintable grid an asset DEFINITION (not a
placed instance) carries, edited via AssetEffectsPanel and rendered on
every placed instance of that asset by AssetEffectsOverlay.

Each of the 5 effect types (ASSET_EFFECT_TYPES) is its own independent
LAYER — a flat EFFECT_GRID_SIZE*EFFECT_GRID_SIZE boolean grid (which cells
have that effect painted) plus display settings (visible/blend/opacity).
Layers overlap freely: painting "aura" over a cell that already has
"glitter" keeps both, instead of one overwriting the other the way the old
single-exclusive-key-per-cell design did. The whole layers dict round-trips
to/from asset_settings.effects_json via plain json.dumps/loads — no
dataclass needed, same "keep it simple" spirit as MarkerProperties/
LightProperties.
"""

from __future__ import annotations

EFFECT_GRID_SIZE = 24
_CELL_COUNT = EFFECT_GRID_SIZE * EFFECT_GRID_SIZE

# (key, icon, label)
ASSET_EFFECT_TYPES: list[tuple[str, str, str]] = [
    ("emissivo", "💡", "Emissivo"),
    ("aura", "🌀", "Aura Pulsante"),
    ("glitter", "✨", "Glitter"),
    ("fumaca", "🌫", "Fumaça Mística"),
    ("distorcao", "🌊", "Dimensão Distorcida"),
]

# (key, label) — how a layer's cells composite over what's already drawn.
BLEND_MODES: list[tuple[str, str]] = [
    ("normal", "Normal"),
    ("additive", "Additive"),
]

# Default tint per effect — used both as the layer's initial "color" and as
# the fallback if a saved value is missing/invalid.
_DEFAULT_COLORS = {
    "emissivo": "#FFDC96",
    "aura": "#96C8FF",
    "glitter": "#FFFFFF",
    "fumaca": "#96829F",
    "distorcao": "#B4DCFF",
}
# (attr, label) — the 3 tunable strength sliders every effect exposes
# (see AssetEffectsOverlay's drawers, which multiply their own hardcoded
# radius/alpha/brightness constants by these instead of using fixed values).
PARAMS: list[tuple[str, str]] = [
    ("intensity", "Intensidade"),
    ("radius", "Raio"),
    ("brightness", "Brilho"),
]
PARAM_MIN, PARAM_MAX = 0.0, 10.0
PARAM_DEFAULT = 5.0  # the "normal"/neutral strength — see AssetEffectsOverlay, which divides by this to get a x1 multiplier


def effect_label(key: str) -> str:
    for k, _icon, label in ASSET_EFFECT_TYPES:
        if k == key:
            return label
    return key


def _clamp_param(value, default: float = PARAM_DEFAULT) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(PARAM_MIN, min(PARAM_MAX, v))


def _empty_layer(key: str = "") -> dict:
    return {
        "cells": [False] * _CELL_COUNT,
        "visible": True,
        "blend": "normal",
        "opacity": 100,
        "color": _DEFAULT_COLORS.get(key, "#FFFFFF"),
        "intensity": PARAM_DEFAULT,
        "radius": PARAM_DEFAULT,
        "brightness": PARAM_DEFAULT,
    }


def empty_layers() -> dict[str, dict]:
    return {key: _empty_layer(key) for key, _icon, _label in ASSET_EFFECT_TYPES}


def _upsample_cells(cells: list, old_size: int) -> list[bool] | None:
    """Nearest-neighbor upsample from an older, coarser grid resolution
    (this panel used to ship at 8x8, then again at whatever size existed
    before a future resolution bump) into the current EFFECT_GRID_SIZE —
    returns None if it doesn't divide evenly, so the caller can fall back
    to discarding rather than guess at a distorted upsample."""
    if EFFECT_GRID_SIZE % old_size != 0:
        return None
    factor = EFFECT_GRID_SIZE // old_size
    out = [False] * _CELL_COUNT
    for old_idx, val in enumerate(cells):
        if not val:
            continue
        ox, oy = old_idx % old_size, old_idx // old_size
        for dy in range(factor):
            for dx in range(factor):
                nx, ny = ox * factor + dx, oy * factor + dy
                out[ny * EFFECT_GRID_SIZE + nx] = True
    return out


def normalize_layers(raw) -> dict[str, dict]:
    """Coerces whatever was loaded from JSON into a complete, safe layers
    dict — every effect key always present with valid types, regardless
    of what was actually stored. Also upgrades an older save (a flat list
    of exclusive cell-keys, the very first format; or a layers dict saved
    at an older, coarser EFFECT_GRID_SIZE) into the current shape/
    resolution instead of discarding it, so bumping the grid resolution
    doesn't wipe out effects already painted in existing projects."""
    layers = empty_layers()
    if isinstance(raw, list) and raw:
        old_size = int(len(raw) ** 0.5)
        if old_size * old_size == len(raw):
            for idx, key in enumerate(raw):
                if key not in layers:
                    continue
                if old_size == EFFECT_GRID_SIZE:
                    layers[key]["cells"][idx] = True
                else:
                    ox, oy = idx % old_size, idx // old_size
                    factor = EFFECT_GRID_SIZE / old_size if old_size else 1
                    nx, ny = int(ox * factor), int(oy * factor)
                    if 0 <= nx < EFFECT_GRID_SIZE and 0 <= ny < EFFECT_GRID_SIZE:
                        layers[key]["cells"][ny * EFFECT_GRID_SIZE + nx] = True
        return layers
    if isinstance(raw, dict):
        for key, layer in layers.items():
            saved = raw.get(key)
            if not isinstance(saved, dict):
                continue
            cells = saved.get("cells")
            if isinstance(cells, list):
                if len(cells) == _CELL_COUNT:
                    layer["cells"] = [bool(c) for c in cells]
                else:
                    old_size = int(len(cells) ** 0.5)
                    if old_size * old_size == len(cells):
                        upsampled = _upsample_cells(cells, old_size)
                        if upsampled is not None:
                            layer["cells"] = upsampled
            layer["visible"] = bool(saved.get("visible", True))
            layer["blend"] = saved.get("blend") if saved.get("blend") in ("normal", "additive") else "normal"
            try:
                layer["opacity"] = max(0, min(100, int(saved.get("opacity", 100))))
            except (TypeError, ValueError):
                layer["opacity"] = 100
            color = saved.get("color")
            if isinstance(color, str) and len(color) in (4, 7) and color.startswith("#"):
                layer["color"] = color
            for attr, _label in PARAMS:
                layer[attr] = _clamp_param(saved.get(attr), layer[attr])
    return layers


def has_any_effect(layers: dict[str, dict]) -> bool:
    return any(any(layer.get("cells", ())) for layer in layers.values())
