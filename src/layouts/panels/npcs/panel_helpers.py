"""Module-level constants and pure helper functions used by NPCsPanel —
none read/write panel state, split out of panel.py to keep that file
focused on the NPCsPanel class itself.

Mirrors src/layouts/panels/mobs/panel_helpers.py, adapted to the npcs
table's own columns — npcs has no tier/element/damage/defense/drops_json
(mob-specific combat fields), so the template/sort options below are a
narrower, npc-appropriate subset rather than a 1:1 field copy.
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel

from src.styles.tokens import Colors
from src.layouts.panels.shared.import_export_helpers import normalize_name as _normalize_npc_name

_LEVEL_BANDS = [
    (1, 10, "1-10"), (11, 20, "11-20"), (21, 30, "21-30"),
    (31, 40, "31-40"), (41, 50, "41-50"), (51, 9999, "51+"),
]
_SORT_OPTIONS = [
    ("name_asc", "Nome (A-Z)"), ("name_desc", "Nome (Z-A)"),
    ("level_asc", "Nível (crescente)"), ("level_desc", "Nível (decrescente)"),
]


# ─── NPC field subset (Importar/Exportar JSON/CSV/Excel, see
# ImportExportMixin) ───
# A reasonably useful subset of columns, not all ~30+ DB columns — used two
# ways: as the DEFAULTS filled in for an npc missing a given key when
# Exportar builds its output from self._npcs, and as the base values for
# Importar's immutable starting template (see _TEMPLATE_FIELD_DOCS/
# _parse_npcs_json below), same subset either direction.
_NPC_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "", "subcategory": "",
    "npc_type": "Mercador", "level": 1, "role": "", "faction": "",
    "zone_id": "", "health": 100, "mana": 50, "favorite": 0,
}
_TEMPLATE_FIELD_DOCS = [
    ("name", "nome do npc (obrigatório)"),
    ("category", "ID de uma categoria existente — veja a lista abaixo"),
    ("subcategory", "texto livre, opcional"),
    ("npc_type", "texto livre (ex.: Mercador, Guarda, Nobre...)"),
    ("role", "função/papel do npc, texto livre"),
    ("faction", "facção, texto livre ou vazio"),
    ("zone_id", "ID de uma região existente, ou vazio"),
    ("favorite", "0 ou 1"),
]


def _parse_npcs_json(text: str) -> list[dict]:
    """Permissive parser for the hand-edited Importar JSON card — same
    technique as parallax_section.py's _parse_layers_json: strips
    "// ..." line comments, tolerates a bare object (no enclosing []),
    unquoted keys, and trailing commas, rather than requiring strict JSON
    from someone editing this by hand."""
    text = re.sub(r'//[^\n]*', '', text)
    text = text.strip()
    if not text:
        raise ValueError("Preencha ao menos um npc antes de aplicar.")
    if not text.startswith("["):
        text = f"[{text}]"
    text = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    import json
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ValueError("Esperava uma lista de npcs (array).")
    return data


def _stat_chip(icon: str, value: str, label: str) -> QFrame:
    chip = QFrame()
    chip.setStyleSheet(f"""
        QFrame {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
    """)
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(6)
    icon_lbl = QLabel(icon)
    icon_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
    lay.addWidget(icon_lbl)
    col = QVBoxLayout()
    col.setSpacing(0)
    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    label_lbl = QLabel(label)
    label_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
    col.addWidget(value_lbl)
    col.addWidget(label_lbl)
    lay.addLayout(col)
    chip._value_label = value_lbl
    return chip
