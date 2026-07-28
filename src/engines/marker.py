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

ICONS: list[str] = [icon for _key, icon, _label in CATEGORIES]


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
    effect_radius: float = 100.0
