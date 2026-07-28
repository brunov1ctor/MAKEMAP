"""Asset effect-region data — the paintable grid an asset DEFINITION (not a
placed instance) carries, edited via AssetEffectsDialog and rendered on
every placed instance of that asset by AssetEffectsOverlay.

A flat list of EFFECT_GRID_SIZE*EFFECT_GRID_SIZE cell strings (effect key
or "" for unpainted) round-trips straight to/from asset_settings.
effects_json via json.dumps/loads — no dataclass needed, same "keep it
simple" spirit as MarkerProperties/LightProperties.
"""

from __future__ import annotations

EFFECT_GRID_SIZE = 8

# (key, icon, label)
ASSET_EFFECT_TYPES: list[tuple[str, str, str]] = [
    ("emissivo", "💡", "Emissivo"),
    ("aura", "🌀", "Aura Pulsante"),
    ("glitter", "✨", "Glitter"),
    ("fumaca", "🌫", "Fumaça Mística"),
    ("distorcao", "🌊", "Dimensão Distorcida"),
]


def effect_label(key: str) -> str:
    for k, _icon, label in ASSET_EFFECT_TYPES:
        if k == key:
            return label
    return key


def empty_cells() -> list[str]:
    return [""] * (EFFECT_GRID_SIZE * EFFECT_GRID_SIZE)


def has_any_effect(cells: list[str]) -> bool:
    return any(c for c in cells)
