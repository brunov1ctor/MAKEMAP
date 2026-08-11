"""Vocabulário e blocos visuais da tela Lore.

Estilo de campo/blocos visuais reaproveitados de dungeons.constants (que já
reexporta de items.constants) — Itens, Dungeons, Quests e Lore compartilham
uma só aparência.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    "category_dot", "category_chip", "relative_date",
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
    """Badge com cor própria por categoria (CATEGORY_COLORS) — fundo e
    borda na cor da categoria deixam cada uma reconhecível de relance,
    mesmo lado a lado num card compacto."""
    label = category or "Sem categoria"
    color = CATEGORY_COLORS.get(category, Colors.TEXT_MUTED)
    lbl = QLabel(label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 1px 8px; "
        f"background: {color}40; color: {color}; border: 1px solid {color}80;"
    )
    return lbl


def relative_date(value: str) -> str:
    """"Hoje às 10:24" / "Ontem às 21:15" / "03/08/2025" — mesmo formato da
    coluna "Última edição" da lista, a partir do `updated_at` (formato
    sqlite `datetime('now')`, "YYYY-MM-DD HH:MM:SS")."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    today = datetime.now().date()
    day = dt.date()
    if day == today:
        return f"Hoje às {dt.strftime('%H:%M')}"
    if day == today - timedelta(days=1):
        return f"Ontem às {dt.strftime('%H:%M')}"
    return dt.strftime("%d/%m/%Y")
