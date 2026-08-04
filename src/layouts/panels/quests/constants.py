"""Vocabulário e blocos visuais da tela Quests.

Estilo de campo/blocos visuais reaproveitados de dungeons.constants (que já
reexporta de items.constants) — as quatro telas (Itens, Dungeons, Quests,
NPCs) compartilham uma só aparência.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    _INPUT_STYLE, _combo, _spin, _dspin, _no_wheel, _field_row, _section_label,
    panel_frame_style, sub_header, caption, value_label, chip, hrule,
    json_list, json_obj, parse_json_records,
)

__all__ = [
    "_INPUT_STYLE", "_combo", "_spin", "_dspin", "_no_wheel", "_field_row",
    "_section_label", "panel_frame_style", "sub_header", "caption", "value_label",
    "chip", "hrule", "json_list", "json_obj", "parse_json_records",
    "QUEST_TYPES", "QUEST_STATUSES", "STATUS_LABELS", "STATUS_COLORS",
    "PRIORITIES", "CONTENT_TABS", "status_dot", "status_chip",
]

# (rótulo, cor) — a coluna `status` guarda o rótulo diretamente (mesma
# convenção de `dungeons.difficulty`/`dungeon_type`: o valor gravado é o
# texto exibido, sem indireção por chave), então o filtro de status da
# RecordListColumn (que compara por igualdade de texto) funciona sem
# tradução nenhuma.
QUEST_STATUSES = [
    ("Ativa", Colors.SUCCESS),
    ("Em progresso", Colors.WARNING),
    ("Rascunho", Colors.TEXT_MUTED),
    ("Desativada", Colors.ERROR),
]
STATUS_LABELS = [label for label, _c in QUEST_STATUSES]
STATUS_COLORS = {label: color for label, color in QUEST_STATUSES}

QUEST_TYPES = ["Principal", "Secundária", "Diária", "Semanal", "Evento", "Cadeia"]

PRIORITIES = ["Baixa", "Média", "Alta"]

# As 9 abas de conteúdo do meio — só "Geral" tem edição real por enquanto,
# as demais mostram um estado vazio ("Em breve...") até ganharem sua própria
# implementação (ver panel.py._build_placeholder_tab).
CONTENT_TABS = [
    ("fluxo", "🧭", "Fluxo"),
    ("geral", "📄", "Geral"),
    ("objetivos", "🎯", "Objetivos"),
    ("recompensas", "🎁", "Recompensas"),
    ("npcs_dialogos", "💬", "NPCs e Diálogos"),
    ("condicoes", "🔀", "Condições"),
    ("eventos", "🚩", "Eventos"),
    ("scripts", "📜", "Scripts"),
    ("notas", "📝", "Notas"),
]


def status_dot(status: str) -> QLabel:
    dot = QLabel("●")
    dot.setStyleSheet(
        f"color: {STATUS_COLORS.get(status, Colors.TEXT_MUTED)}; font-size: 11px; "
        f"background: transparent; border: none;"
    )
    dot.setToolTip(status or "Rascunho")
    return dot


def status_chip(status: str) -> QLabel:
    label = status or "Rascunho"
    color = STATUS_COLORS.get(status, Colors.TEXT_MUTED)
    lbl = QLabel(label)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 10px; "
        f"background: {color}2E; color: {color}; border: none;"
    )
    return lbl
