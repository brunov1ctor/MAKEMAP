"""NPC category / filter definitions shared by the panel, card and edit
widgets — kept in one place so labels/icons never drift between them.

The lookup mechanics, item-rarity scale and a few option lists that are
byte-identical to mobs/categories.py now live in shared/entity_panel/
category_lookup.py (see CategoryLookup) — this module keeps only what's
genuinely npc-specific: NPC_TYPE_OPTIONS (npcs has no element column at
all, unlike mobs' ELEMENT_OPTIONS) and the npc default category.

Mirrors src/layouts/panels/mobs/categories.py — migration 28 seeds 4 preset
root folders (Mercadores/Hostis/Aliados/Figurante) with colors, covering the
common NPC archetypes directly instead of Mobs' own difficulty-ladder idea
(migration 16/22/23) or a borrowed rarity/reaction scale. Users can still
freely add/rename/delete categories via the CATEGORIAS explorer, same as
mobs.
"""

from __future__ import annotations

from src.layouts.panels.shared.entity_panel.category_lookup import (
    CategoryLookup,
    ITEM_RARITY_DEFS, ITEM_RARITY_LABELS, ITEM_RARITY_COLORS,
    EFFECT_OPTIONS, AI_TYPE_OPTIONS, BEHAVIOR_OPTIONS, ALIGNMENT_OPTIONS,
    STATUS_OPTIONS, SIZE_OPTIONS, RESISTANCE_KEYS,
    item_rarity_label, item_rarity_color,
)

# Runtime lookup — refreshed by NPCsPanel every time it (re)loads the
# category folder tree from the DB (see NPCsPanel._reload_categories), so
# code that only has an npc's category id (NPCCard's icon badge, etc.) can
# resolve an icon/name without needing DB access of its own. Starts empty
# (no seed rows, unlike mob_categories) until the first reload populates it.
_lookup = CategoryLookup()

set_category_lookup = _lookup.set
category_label = _lookup.label
category_icon = _lookup.icon
category_badge_color = _lookup.badge_color
category_image_border_color = _lookup.image_border_color
category_tag_text_color = _lookup.tag_text_color

# An npc with no category assigned yet falls back to this — migration 28
# seeds 4 real preset folders (Mercadores/Hostis/Aliados/Figurante) and
# backfills existing NPCs onto "figurante" (the generic/unremarkable
# background-character default), same "default category = the first
# sensible tier" convention mobs/categories.py uses for "normal".
DEFAULT_CATEGORY_ID = "figurante"

# Separate loot-tier scale (items.rarity, npc_assets.rarity) — see
# shared/entity_panel/category_lookup.py. ITEM_RARITY_DEFS/LABELS/COLORS
# and item_rarity_label/item_rarity_color are re-exported as module
# attributes via the import above.

# npcs.npc_type (DB default 'Mercador', migration 27) — plays the role
# mobs.element used to play in the grid/stats (see panel_data_mixin.py /
# panel_grid_mixin.py's "elementos diferentes" -> npc_type swap), since NPCs
# have no element column at all.
NPC_TYPE_OPTIONS = [
    "Mercador", "Guarda", "Nobre", "Sacerdote", "Ferreiro", "Taverneiro",
    "Curandeiro", "Guia", "Governante", "Artesão", "Informante", "Viajante",
]
TIPO_OPTIONS = ["Inimigo", "Aliado", "Neutro", "Chefe"]
