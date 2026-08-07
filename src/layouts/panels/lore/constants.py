"""Vocabulário e blocos visuais da tela Lore.

Estilo de campo/blocos visuais reaproveitados de dungeons.constants (que já
reexporta de items.constants) — Itens, Dungeons, Quests e Lore compartilham
uma só aparência.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    _INPUT_STYLE, _combo, _no_wheel, _section_label,
    panel_frame_style, sub_header, caption, value_label, hrule,
    json_list, json_obj,
)

__all__ = [
    "_INPUT_STYLE", "_combo", "_no_wheel", "_section_label",
    "panel_frame_style", "sub_header", "caption", "value_label", "hrule",
    "json_list", "json_obj",
    "LORE_CATEGORIES", "CATEGORY_LABELS", "CATEGORY_COLORS",
    "category_dot", "category_chip",
]

# (nome, cor) — paleta fixa (sem cor editável por categoria, ao contrário de
# Mobs) igual ao QUEST_STATUSES/status_chip de quests/constants.py.
LORE_CATEGORIES = [
    ("Evento", Colors.WARNING),
    ("Reino", "#4FC3F7"),
    ("Facção", "#4DD0E1"),
    ("Personagem", "#FFD54F"),
    ("Local", "#7986CB"),
    ("Artefato", "#FF8A65"),
    ("Criatura", Colors.ERROR),
]
CATEGORY_LABELS = [name for name, _c in LORE_CATEGORIES]
CATEGORY_COLORS = {name: color for name, color in LORE_CATEGORIES}


def category_dot(category: str) -> QLabel:
    dot = QLabel("●")
    dot.setStyleSheet(
        f"color: {CATEGORY_COLORS.get(category, Colors.TEXT_MUTED)}; font-size: 11px; "
        f"background: transparent; border: none;"
    )
    dot.setToolTip(category or "Sem categoria")
    return dot


def category_chip(category: str) -> QLabel:
    label = category or "Sem categoria"
    color = CATEGORY_COLORS.get(category, Colors.TEXT_MUTED)
    lbl = QLabel(label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 10px; "
        f"background: {color}2E; color: {color}; border: none;"
    )
    return lbl
