"""Vocabulário e blocos visuais da tela Dungeons e Construções.

O estilo de campo (input/combo/spin) vem do painel de Mobs, igual ao que
Itens e Habilidades já faz — as três telas compartilham uma só aparência
em vez de cada uma redeclarar a sua.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QFrame, QLabel
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.items.constants import (
    _INPUT_STYLE, _combo, _spin, _dspin, _no_wheel, _field_row, _section_label,
    panel_frame_style, sub_header, caption, value_label,
)

__all__ = [
    "_INPUT_STYLE", "_combo", "_spin", "_dspin", "_no_wheel", "_field_row",
    "_section_label", "panel_frame_style", "sub_header", "caption", "value_label",
    "STRUCTURE_TYPES", "TIER_NAMES", "tier_name",
    "BUILD_STATUSES", "STATUS_LABELS", "STATUS_COLORS", "RESOURCE_ICONS",
    "DIFFICULTIES", "GENERATION_TYPES", "DUNGEON_BIOMES",
    "DUNGEON_MODIFIERS", "status_dot", "chip", "hrule", "json_list", "json_obj",
    "parse_json_records",
]

# ─── Construções ────────────────────────────────────────────────────────────
#
# Categoria (Construções) e Tipo (Dungeons) deixaram de ser listas fixas
# aqui — agora são abas editáveis guardadas em building_categories/
# dungeon_types (ver migration 14), com CRUD via CategoryTabBar. Os nomes
# que estas listas continham viraram só a seed dessa migration.

STRUCTURE_TYPES = ["Simples", "Reforçada", "Mágica", "Fortificada", "Sagrada"]

# Nome de cada faixa da árvore de progressão. Tiers acima do último caem no
# rótulo genérico "Tier N".
TIER_NAMES = ["Básico", "Intermediário", "Avançado", "Especializado", "Supremo"]


def tier_name(tier: int) -> str:
    return TIER_NAMES[tier - 1] if 1 <= tier <= len(TIER_NAMES) else f"Tier {tier}"

# (chave, rótulo, cor) — a mesma legenda que aparece no rodapé da árvore.
BUILD_STATUSES = [
    ("concluida", "Concluída", Colors.SUCCESS),
    ("disponivel", "Disponível", Colors.ACCENT),
    ("bloqueada", "Bloqueada", Colors.TEXT_MUTED),
    ("andamento", "Em Andamento", Colors.WARNING),
]
STATUS_LABELS = {key: label for key, label, _c in BUILD_STATUSES}
STATUS_COLORS = {key: color for key, _l, color in BUILD_STATUSES}

# Emoji por recurso, usado nos chips de custo.
RESOURCE_ICONS = {
    "Madeira": "🪵", "Pedra": "🪨", "Ouro": "🪙", "Cristal": "💎",
    "Essência": "✨", "Ferro": "⛓", "Comida": "🌾", "Couro": "🧵",
}

# ─── Dungeons ───────────────────────────────────────────────────────────────

DIFFICULTIES = ["Fácil", "Normal", "Difícil", "Heroico", "Mítico"]
GENERATION_TYPES = ["Linear", "Ramificada", "Labirinto", "Aberta", "Procedural"]
DUNGEON_BIOMES = [
    "Subterrâneo", "Floresta", "Deserto", "Gelo", "Vulcânico",
    "Aquático", "Ruínas", "Abissal", "Celestial",
]

# (chave, rótulo, ícone, sufixo) — a seção Modificadores é a mesma lista de
# multiplicadores para toda dungeon, então mora aqui em vez de no editor.
DUNGEON_MODIFIERS = [
    ("enemy_hp", "Vida dos Inimigos", "❤", "%"),
    ("enemy_dmg", "Dano dos Inimigos", "🔥", "%"),
    ("xp_gain", "XP Ganho", "⚡", "%"),
    ("drop_rate", "Chance de Drop", "💠", "%"),
]


# ─── Pequenos construtores visuais ──────────────────────────────────────────

def status_dot(status: str) -> QLabel:
    """Bolinha colorida de status usada nas linhas da lista."""
    dot = QLabel("●")
    dot.setStyleSheet(
        f"color: {STATUS_COLORS.get(status, Colors.TEXT_MUTED)}; font-size: 11px; "
        f"background: transparent; border: none;"
    )
    dot.setToolTip(STATUS_LABELS.get(status, status))
    return dot


def chip(text: str, color: str = "") -> QLabel:
    """Etiqueta arredondada — custos, recompensas, tipo de dungeon."""
    color = color or Colors.ACCENT
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 8px; "
        f"background: {color}2E; color: {color}; border: none;"
    )
    return lbl


def hrule() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line


def json_list(raw) -> list:
    """Lê um blob JSON de lista tolerando nulo/texto inválido — custos,
    requisitos e recompensas são todos listas guardadas em colunas TEXT."""
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def json_obj(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_json_records(text: str) -> list[dict]:
    """Parser permissivo (tolera um objeto solto, comentários //, vírgula
    sobrando) → lista de dicts. Levanta ValueError com mensagem amigável.
    Compartilhado pelo bloco "{ } JSON" de Itens/Habilidades e agora de
    Construções/Dungeons, para os quatro módulos aceitarem exatamente o
    mesmo texto colado."""
    import re
    text = re.sub(r'//[^\n]*', '', text).strip()
    if not text:
        raise ValueError("Cole ao menos um registro antes de aplicar.")
    if not text.startswith("["):
        text = f"[{text}]"
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ValueError("Esperava uma lista (array) de registros.")
    records = [d for d in data if isinstance(d, dict) and d.get("name")]
    if not records:
        raise ValueError("Nenhum registro válido (cada um precisa de \"name\").")
    return records
