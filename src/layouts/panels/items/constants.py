"""Constants and small pure helpers for the Itens e Habilidades panel.

The visual language (input style, spin/combo factories, rarity chips) is
shared with the Mobs edit panel — imported from there rather than
re-declared, so the two screens can't drift apart. Only the item/skill
specific option lists live here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QDoubleSpinBox, QComboBox, QAbstractSpinBox, QToolButton, QWidget,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import (
    ITEM_RARITY_DEFS, item_rarity_label, item_rarity_color,
)

# Reuse the Mobs edit panel's field style + factories verbatim so both
# screens share one look. _INPUT_STYLE already covers QLineEdit/QTextEdit/
# QComboBox/QSpin/QDoubleSpin/QLabel.
from src.layouts.panels.mobs.edit_helpers import (
    _INPUT_STYLE, _combo, _spin, _dspin, _no_wheel, _field_row, _section_label,
)

# ─── Item catalog vocabulary ────────────────────────────────────────────────

# Category → its subcategory list. The editor's Categoria field is really
# two combos ("Arma" + "Espada") rendered as one "Arma • Espada" label in
# the list column.
ITEM_CATEGORIES: dict[str, list[str]] = {
    "Arma": ["Espada", "Machado", "Adaga", "Arco", "Cajado", "Lança", "Maça"],
    "Armadura": ["Peito", "Elmo", "Pernas", "Pés", "Mãos", "Escudo"],
    "Consumível": ["Poção", "Comida", "Pergaminho", "Elixir"],
    "Material": ["Minério", "Madeira", "Cristal", "Erva", "Couro", "Tecido"],
    "Receita": ["Arma", "Armadura", "Consumível"],
    "Missão": ["Chave", "Documento", "Relíquia"],
    "Outro": ["Diverso"],
}
ITEM_CATEGORY_NAMES = list(ITEM_CATEGORIES.keys())

DAMAGE_TYPES = ["Corte Físico", "Perfuração", "Impacto", "Mágico", "Elemental", "Verdadeiro"]
ELEMENT_OPTIONS = ["Nenhum", "Fogo", "Gelo", "Raio", "Terra", "Água", "Vento", "Sagrado", "Sombrio", "Veneno"]
ALLOWED_CLASSES = ["Todas", "Guerreiro", "Mago", "Arqueiro", "Ladino", "Clérigo", "Paladino"]

# Item editor boolean toggles (tab Propriedades) — (stats key, label, default).
ITEM_FLAGS = [
    ("can_sell", "Pode Vender", True),
    ("can_destroy", "Pode Destruir", True),
    ("tradeable", "Negociável", True),
    ("bind_on_pickup", "Vincula ao Pegar", False),
]

# ─── Skill vocabulary ───────────────────────────────────────────────────────

SKILL_CATEGORIES = ["Ataque", "Defesa", "Suporte", "Passiva", "Movimento", "Cura"]

# Skill editor boolean toggles (tab Mecânica) — (stats key, label, default).
SKILL_FLAGS = [
    ("break_on_move", "Quebra ao se mover", False),
    ("cancelable", "Pode ser cancelada", True),
    ("uses_weapon", "Usa Arma", True),
    ("air_castable", "Pode ser usada no ar", False),
    ("generates_threat", "Gera Ameaça", True),
]

# ─── Small shared widget builders ───────────────────────────────────────────

def category_display(category: str, subcategory: str) -> str:
    """"Arma • Espada" for the list column / editor header."""
    category = (category or "").strip()
    subcategory = (subcategory or "").strip()
    if category and subcategory:
        return f"{category} • {subcategory}"
    return category or subcategory or "—"


def rarity_pill(rarity_key: str) -> QLabel:
    """Colored raridade chip — used in both list columns."""
    chip = QLabel(item_rarity_label(rarity_key))
    color = item_rarity_color(rarity_key)
    chip.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 5px; padding: 1px 6px; "
        f"background: {color}2E; color: {color}; border: none;"
    )
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return chip


def rarity_options() -> list[tuple[str, str]]:
    """(key, label) pairs for a raridade combo, catalog order."""
    return [(key, label) for key, _color, label in ITEM_RARITY_DEFS]


def panel_frame_style() -> str:
    """The glass card each of the six sub-panels sits in."""
    return (
        f"QFrame#subpanel {{ background: rgba(255,255,255,0.025); "
        f"border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 10px; }}"
    )


def sub_header(title: str) -> QLabel:
    """The small-caps accent title at the top of each sub-panel
    (ITENS / EDITOR DE ITEM / PRÉVIA / …)."""
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color: {Colors.ACCENT}; font-size: 11px; font-weight: bold; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    return lbl


def caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
    return lbl


def value_label(text: str, bold: bool = True) -> QLabel:
    lbl = QLabel(text)
    weight = "bold" if bold else "normal"
    lbl.setStyleSheet(
        f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: {weight}; "
        f"background: transparent; border: none;"
    )
    return lbl
