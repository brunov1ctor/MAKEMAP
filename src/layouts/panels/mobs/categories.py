"""Mob category / rarity / filter definitions shared by the panel, card and
edit widgets — kept in one place so labels/icons never drift between them."""

from __future__ import annotations

# Real creature families — stored verbatim in mobs.category.
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
CATEGORY_LABELS = {key: label for key, _icon, label in CATEGORY_DEFS}
CATEGORY_ICONS = {key: icon for key, icon, _label in CATEGORY_DEFS}

# Smart filters — computed over other columns (favorite/rarity), not a
# distinct category value of their own.
SMART_FILTERS: list[tuple[str, str, str]] = [
    ("todos", "📋", "Todos"),
    ("favoritos", "⭐", "Favoritos"),
    ("chefes", "👑", "Chefes (Boss)"),
    ("elite", "💠", "Elite"),
]

RARITY_DEFS: list[tuple[str, str, str]] = [
    ("normal", "#9AA5B1", "Normal"),
    ("raro", "#4FC3F7", "Raro"),
    ("elite", "#AB47BC", "Elite"),
    ("boss", "#FFA726", "Chefe"),
    ("mitico", "#EF5350", "Mítico"),
]
RARITY_LABELS = {key: label for key, _color, label in RARITY_DEFS}
RARITY_COLORS = {key: color for key, color, _label in RARITY_DEFS}

ELEMENT_OPTIONS = ["", "Fogo", "Gelo", "Raio", "Terra", "Água", "Vento", "Sagrado", "Sombrio", "Veneno"]
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
    return CATEGORY_LABELS.get(key, "Outros")


def category_icon(key: str) -> str:
    return CATEGORY_ICONS.get(key, "❔")


def rarity_label(key: str) -> str:
    return RARITY_LABELS.get(key, "Normal")


def rarity_color(key: str) -> str:
    return RARITY_COLORS.get(key, "#9AA5B1")
