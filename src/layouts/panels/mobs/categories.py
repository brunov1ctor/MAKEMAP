"""Mob category / rarity / filter definitions shared by the panel, card and
edit widgets — kept in one place so labels/icons never drift between them.

The lookup mechanics, item-rarity scale and a few option lists that are
byte-identical to npcs/categories.py now live in shared/entity_panel/
category_lookup.py (see CategoryLookup) — this module keeps only what's
genuinely mob-specific: the seed category data, the mob difficulty-tier
default, and TIPO_OPTIONS/ELEMENT_OPTIONS (npcs has no element column at
all, see npcs/categories.py's NPC_TYPE_OPTIONS)."""

from __future__ import annotations

from src.layouts.panels.shared.entity_panel.category_lookup import (
    CategoryLookup,
    ITEM_RARITY_DEFS, ITEM_RARITY_LABELS, ITEM_RARITY_COLORS,
    EFFECT_OPTIONS, AI_TYPE_OPTIONS, BEHAVIOR_OPTIONS, ALIGNMENT_OPTIONS,
    STATUS_OPTIONS, SIZE_OPTIONS, RESISTANCE_KEYS,
    item_rarity_label, item_rarity_color,
)

# Original fixed creature families — now just the seed data migration 5
# (src/database/migrations/schema.py) inserts as root folders in
# mob_categories on first run. Categories are a persisted directory tree
# from that point on (see MobCategoryRepository); this list is kept only
# as a record of what the seed contains; nothing reads it at runtime
# anymore.
CATEGORY_DEFS: list[tuple[str, str, str]] = [
    ("npc_hostil", "☠", "NPC Hostil"),
    ("animais", "🐺", "Animais"),
    ("mortos_vivos", "🧟", "Mortos-vivos"),
    ("maquinas", "🤖", "Máquinas"),
    ("humanoides", "🧑‍🤝‍🧑", "Humanoides"),
    ("dragoes", "🐉", "Dragões"),
    ("insetos", "🐛", "Insetos"),
    ("aquaticos", "🐊", "Aquáticos"),
    ("elementais", "🔥", "Elementais"),
    ("plantas", "🌿", "Plantas"),
    ("demoniacos", "👹", "Demoníacos"),
    ("outros", "❔", "Outros"),
]

# Runtime lookup — refreshed by MobsPanel every time it (re)loads the
# category folder tree from the DB (see MobsPanel._reload_categories), so
# code that only has a mob's category id (MobCard's icon badge, etc.) can
# resolve an icon/name without needing DB access of its own. Seeded from
# the fixed list above so lookups aren't empty before the first reload.
_lookup = CategoryLookup({key: {"icon": icon, "name": label} for key, icon, label in CATEGORY_DEFS})

set_category_lookup = _lookup.set
category_label = _lookup.label
category_icon = _lookup.icon
category_badge_color = _lookup.badge_color
category_image_border_color = _lookup.image_border_color
category_tag_text_color = _lookup.tag_text_color

# Migration 16's seeded root folder new/unassigned mobs fall back to —
# "outros" (the mobs.category DB column's old default, see migration 3)
# stopped resolving to a real folder once migration 7 dropped it, leaving
# every unset mob showing "❔ Sem categoria" instead of a real category.
DEFAULT_CATEGORY_ID = "normal"

# Separate loot-tier scale (items.rarity, mobs.abilities_json entries,
# mob_assets.rarity) — ITEM_RARITY_DEFS/LABELS/COLORS and item_rarity_label/
# item_rarity_color are re-exported as module attributes via the import
# above (see shared/entity_panel/category_lookup.py) so existing `from
# src.layouts.panels.mobs.categories import ITEM_RARITY_DEFS`-style imports
# keep working unchanged.

TIPO_OPTIONS = ["Inimigo", "Aliado", "Neutro", "Chefe"]
ELEMENT_OPTIONS = ["", "Fogo", "Gelo", "Raio", "Terra", "Água", "Vento", "Sagrado", "Sombrio", "Veneno"]
