"""NPC category / filter definitions shared by the panel, card and edit
widgets — kept in one place so labels/icons never drift between them.

Mirrors src/layouts/panels/mobs/categories.py — migration 28 seeds 4 preset
root folders (Mercadores/Hostis/Aliados/Figurante) with colors, covering the
common NPC archetypes directly instead of Mobs' own difficulty-ladder idea
(migration 16/22/23) or a borrowed rarity/reaction scale. Users can still
freely add/rename/delete categories via the CATEGORIAS explorer, same as
mobs.
"""

from __future__ import annotations

# Runtime lookup — refreshed by NPCsPanel every time it (re)loads the
# category folder tree from the DB (see NPCsPanel._reload_categories), so
# code that only has an npc's category id (NPCCard's icon badge, etc.) can
# resolve an icon/name without needing DB access of its own. Starts empty
# (no seed rows, unlike mob_categories) until the first reload populates it.
_category_lookup: dict[str, dict] = {}


def set_category_lookup(categories: list[dict]):
    """`categories` is every row of npc_categories (any depth) — each dict
    needs at least "id", "name", "icon"."""
    global _category_lookup
    _category_lookup = {c["id"]: c for c in categories}


# An npc with no category assigned yet falls back to this — migration 28
# seeds 4 real preset folders (Mercadores/Hostis/Aliados/Figurante) and
# backfills existing NPCs onto "figurante" (the generic/unremarkable
# background-character default), same "default category = the first
# sensible tier" convention mobs/categories.py uses for "normal".
DEFAULT_CATEGORY_ID = "figurante"

# Separate loot-tier scale (items.rarity, npc_assets.rarity) — items already
# existed with this DEFAULT 'common' before the NPCs panel existed, so this
# mirrors that scale/convention (common/uncommon/rare/epic/legendary) rather
# than inventing a new one.
ITEM_RARITY_DEFS: list[tuple[str, str, str]] = [
    ("common", "#9AA5B1", "Comum"),
    ("uncommon", "#66BB6A", "Incomum"),
    ("rare", "#4FC3F7", "Raro"),
    ("epic", "#AB47BC", "Épico"),
    ("legendary", "#FFA726", "Lendário"),
]
ITEM_RARITY_LABELS = {key: label for key, _color, label in ITEM_RARITY_DEFS}
ITEM_RARITY_COLORS = {key: color for key, color, _label in ITEM_RARITY_DEFS}

# npcs.npc_type (DB default 'Mercador', migration 27) — plays the role
# mobs.element used to play in the grid/stats (see panel_data_mixin.py /
# panel_grid_mixin.py's "elementos diferentes" -> npc_type swap), since NPCs
# have no element column at all.
NPC_TYPE_OPTIONS = [
    "Mercador", "Guarda", "Nobre", "Sacerdote", "Ferreiro", "Taverneiro",
    "Curandeiro", "Guia", "Governante", "Artesão", "Informante", "Viajante",
]
TIPO_OPTIONS = ["Inimigo", "Aliado", "Neutro", "Chefe"]
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


# Keeping an id-based color guess here would silently defeat CategoryEdit
# Panel's "✕ Usar cor padrão" clear button — clearing a stored color must
# always land on the same flat neutral gray for every category. Used by
# both the Visão Geral category badge and the grid card's chip (npc_card.py).
def category_badge_color(category_id: str) -> str:
    stored = _category_lookup.get(category_id, {}).get("border_color")
    return stored or "#9AA5B1"


def category_image_border_color(category_id: str) -> str:
    """CategoryEditPanel's "Cor da borda da imagem" — a separate color
    from category_badge_color's "Cor da borda do card" (the card frame +
    category tag), specifically for the border drawn around an npc card's
    thumbnail/image. Falls back to the card border color when unset, not
    straight to a hardcoded guess, so a category with only one color picked
    still looks consistent across both spots."""
    stored = _category_lookup.get(category_id, {}).get("image_border_color")
    if stored:
        return stored
    return category_badge_color(category_id)


def category_tag_text_color(category_id: str) -> str:
    """CategoryEditPanel's "Cor do texto da tag" — the category tag's own
    text color, independent of its background (category_badge_color).
    Defaults to white, same as before this became user-editable."""
    return _category_lookup.get(category_id, {}).get("tag_text_color") or "#FFFFFF"


def item_rarity_label(key: str) -> str:
    return ITEM_RARITY_LABELS.get(key, "Comum")


def item_rarity_color(key: str) -> str:
    return ITEM_RARITY_COLORS.get(key, "#9AA5B1")
