"""Category-folder lookup + item-rarity scale shared by MobsPanel and
NPCsPanel's own categories.py modules (see mobs/categories.py and
npcs/categories.py) — extracted here because the *mechanics* (module-level
lookup dict refreshed on reload, icon/color/label accessors, the
common/uncommon/rare/epic/legendary item-rarity scale) are byte-identical
between the two entities; only the SEED DATA (mob_categories' 12 creature
families vs npc_categories' 4 archetype folders) and a few option lists
(TIPO_OPTIONS/ELEMENT_OPTIONS vs NPC_TYPE_OPTIONS) genuinely differ, and
those stay in each entity's own categories.py.

Each entity module owns its own CategoryLookup INSTANCE (not a shared
global) — mob categories and npc categories are two separate DB tables
with two separate id spaces, so sharing one lookup dict between them would
let an id collision from one entity resolve against the other's data."""

from __future__ import annotations


class CategoryLookup:
    """Runtime {id: row} cache for one entity's category folder tree —
    refreshed by that entity's panel every time it (re)loads the tree from
    the DB (see MobsPanel/NPCsPanel._reload_categories), so code that only
    has a record's category id (a card's icon badge, etc.) can resolve an
    icon/name without needing DB access of its own."""

    def __init__(self, initial: dict[str, dict] | None = None):
        self._lookup: dict[str, dict] = dict(initial or {})

    def set(self, categories: list[dict]):
        """`categories` is every row of the entity's category table (any
        depth) — each dict needs at least "id", "name", "icon"."""
        self._lookup = {c["id"]: c for c in categories}

    def label(self, key: str) -> str:
        return self._lookup.get(key, {}).get("name", "Outros")

    def icon(self, key: str) -> str:
        return self._lookup.get(key, {}).get("icon", "❔")

    # Keeping an id-based color guess here would silently defeat CategoryEdit
    # Panel's "✕ Usar cor padrão" clear button — clearing a stored color must
    # always land on the same flat neutral gray for every category. Used by
    # both the Visão Geral category badge and the grid card's chip.
    def badge_color(self, category_id: str) -> str:
        stored = self._lookup.get(category_id, {}).get("border_color")
        return stored or "#9AA5B1"

    def image_border_color(self, category_id: str) -> str:
        """CategoryEditPanel's "Cor da borda da imagem" — a separate color
        from badge_color's "Cor da borda do card" (the card frame + tag),
        specifically for the border drawn around a card's thumbnail/image.
        Falls back to the card border color when unset, not straight to a
        hardcoded guess, so a category with only one color picked still
        looks consistent across both spots."""
        stored = self._lookup.get(category_id, {}).get("image_border_color")
        if stored:
            return stored
        return self.badge_color(category_id)

    def tag_text_color(self, category_id: str) -> str:
        """CategoryEditPanel's "Cor do texto da tag" — the tag's own text
        color, independent of its background (badge_color). Defaults to
        white, same as before this became user-editable."""
        return self._lookup.get(category_id, {}).get("tag_text_color") or "#FFFFFF"


# Separate loot-tier scale (items.rarity, mob_assets.rarity/npc_assets.
# rarity) — items already existed with this DEFAULT 'common' before either
# the Mobs or NPCs panel's Informações Extras started referencing them, so
# both mirror the same scale/convention (common/uncommon/rare/epic/
# legendary) instead of each inventing their own.
ITEM_RARITY_DEFS: list[tuple[str, str, str]] = [
    ("common", "#9AA5B1", "Comum"),
    ("uncommon", "#66BB6A", "Incomum"),
    ("rare", "#4FC3F7", "Raro"),
    ("epic", "#AB47BC", "Épico"),
    ("legendary", "#FFA726", "Lendário"),
]
ITEM_RARITY_LABELS = {key: label for key, _color, label in ITEM_RARITY_DEFS}
ITEM_RARITY_COLORS = {key: color for key, color, _label in ITEM_RARITY_DEFS}


def item_rarity_label(key: str) -> str:
    return ITEM_RARITY_LABELS.get(key, "Comum")


def item_rarity_color(key: str) -> str:
    return ITEM_RARITY_COLORS.get(key, "#9AA5B1")


# Option lists that happen to be byte-identical between mobs/categories.py
# and npcs/categories.py today (unlike TIPO_OPTIONS/ELEMENT_OPTIONS vs
# NPC_TYPE_OPTIONS, which genuinely differ and stay per-entity).
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
