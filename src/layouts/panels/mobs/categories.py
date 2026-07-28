"""Mob category / rarity / filter definitions shared by the panel, card and
edit widgets — kept in one place so labels/icons never drift between them."""

from __future__ import annotations

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
_category_lookup: dict[str, dict] = {key: {"icon": icon, "name": label} for key, icon, label in CATEGORY_DEFS}


def set_category_lookup(categories: list[dict]):
    """`categories` is every row of mob_categories (any depth) — each dict
    needs at least "id", "name", "icon"."""
    global _category_lookup
    _category_lookup = {c["id"]: c for c in categories}


# Migration 16's seeded root folder new/unassigned mobs fall back to —
# "outros" (the mobs.category DB column's old default, see migration 3)
# stopped resolving to a real folder once migration 7 dropped it, leaving
# every unset mob showing "❔ Sem categoria" instead of a real category.
DEFAULT_CATEGORY_ID = "normal"

# Separate loot-tier scale (items.rarity, mobs.abilities_json entries,
# mob_assets.rarity) — items already existed with this DEFAULT 'common'
# before the Mobs panel's Informações Extras started referencing them, so
# this mirrors that scale/convention (common/uncommon/rare/epic/legendary)
# rather than reusing RARITY_DEFS above, which is mob-difficulty specific
# (Normal/Raro/Elite/Chefe/Mítico) and has no "Épico" tier at all.
ITEM_RARITY_DEFS: list[tuple[str, str, str]] = [
    ("common", "#9AA5B1", "Comum"),
    ("uncommon", "#66BB6A", "Incomum"),
    ("rare", "#4FC3F7", "Raro"),
    ("epic", "#AB47BC", "Épico"),
    ("legendary", "#FFA726", "Lendário"),
]
ITEM_RARITY_LABELS = {key: label for key, _color, label in ITEM_RARITY_DEFS}
ITEM_RARITY_COLORS = {key: color for key, color, _label in ITEM_RARITY_DEFS}

TIPO_OPTIONS = ["Inimigo", "Aliado", "Neutro", "Chefe"]
ELEMENT_OPTIONS = ["", "Fogo", "Gelo", "Raio", "Terra", "Água", "Vento", "Sagrado", "Sombrio", "Veneno"]
EFFECT_OPTIONS = ["", "Aura", "Brilho", "Fumaça", "Chamas", "Partículas", "Névoa"]
AI_TYPE_OPTIONS = ["Agressivo", "Defensivo", "Passivo", "Covarde", "Territorial"]
BEHAVIOR_OPTIONS = ["Territorial", "Errante", "Em Bando", "Solitário", "Emboscada"]
ALIGNMENT_OPTIONS = ["Hostil", "Neutro", "Cauteloso"]
STATUS_OPTIONS = ["Ativo", "Inativo"]
SIZE_OPTIONS = ["Pequeno", "Médio", "Grande", "Enorme"]

# Ordered so the 2-column "Resistências" grid reads Água/Terra, Fogo/Veneno,
# Gelo/Sagrado, Raio/Sombrio, matching the reference layout.
RESISTANCE_KEYS = [
    ("agua", "Água"),
    ("terra", "Terra"),
    ("fogo", "Fogo"),
    ("veneno", "Veneno"),
    ("gelo", "Gelo"),
    ("sagrado", "Sagrado"),
    ("raio", "Raio"),
    ("sombra", "Sombrio"),
]


def category_label(key: str) -> str:
    return _category_lookup.get(key, {}).get("name", "Outros")


def category_icon(key: str) -> str:
    return _category_lookup.get(key, {}).get("icon", "❔")


# Migration 16 seeds the 5 difficulty-tier category folders with ids
# normal/raro/elite/epico/boss — migrations 22/23 seed sensible
# border_color values directly onto those rows now, so this no longer
# needs its own id->color guesses as a fallback (it used to, back when
# categories had nowhere to store a color at all). Keeping an id-based
# guess here would silently defeat CategoryEditPanel's "✕ Usar cor
# padrão" clear button for exactly those 5 categories — clearing a
# stored color must always land on the same flat neutral gray for every
# category, not a per-id color that happens to look identical to what
# was just cleared. Used by both the Visão Geral category badge
# (edit_overview_mixin.py) and the grid card's chip (mob_card.py).
def category_badge_color(category_id: str) -> str:
    stored = _category_lookup.get(category_id, {}).get("border_color")
    return stored or "#9AA5B1"


def category_image_border_color(category_id: str) -> str:
    """CategoryEditPanel's "Cor da borda da imagem" — a separate color
    from category_badge_color's "Cor da borda do card" (the card frame +
    rarity tag), specifically for the border drawn around a mob card's
    thumbnail/image. Falls back to the card border color when unset, not
    straight to the hardcoded id->color guesses, so a category with only
    one color picked still looks consistent across both spots."""
    stored = _category_lookup.get(category_id, {}).get("image_border_color")
    if stored:
        return stored
    return category_badge_color(category_id)


def category_tag_text_color(category_id: str) -> str:
    """CategoryEditPanel's "Cor do texto da tag" — the rarity tag's own
    text color, independent of its background (category_badge_color).
    Defaults to white, same as before this became user-editable."""
    return _category_lookup.get(category_id, {}).get("tag_text_color") or "#FFFFFF"


def item_rarity_label(key: str) -> str:
    return ITEM_RARITY_LABELS.get(key, "Comum")


def item_rarity_color(key: str) -> str:
    return ITEM_RARITY_COLORS.get(key, "#9AA5B1")
