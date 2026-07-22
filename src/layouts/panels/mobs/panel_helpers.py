"""Module-level constants and pure helper functions used by MobsPanel —
none read/write panel state, split out of panel.py to keep that file
focused on the MobsPanel class itself.
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel

from src.styles.tokens import Colors

_LEVEL_BANDS = [
    (1, 10, "1-10"), (11, 20, "11-20"), (21, 30, "21-30"),
    (31, 40, "31-40"), (41, 50, "41-50"), (51, 9999, "51+"),
]
_SORT_OPTIONS = [
    ("name_asc", "Nome (A-Z)"), ("name_desc", "Nome (Z-A)"),
    ("level_asc", "Nível (crescente)"), ("level_desc", "Nível (decrescente)"),
    ("tier_desc", "Tier (maior primeiro)"),
]

# Resumo Rápido's donut/legend now breaks mobs down by top-level category
# (see MobDataMixin._recompute_stats) instead of rarity — categories don't
# carry a color of their own like RARITY_DEFS did, so this fixed palette is
# cycled by each root category's position instead.
_CATEGORY_PALETTE = [
    "#4FC3F7", "#AB47BC", "#FFA726", "#66BB6A", "#EF5350",
    "#26C6DA", "#FFCA28", "#8D6E63", "#EC407A", "#7E57C2",
]


def _category_color(index: int) -> str:
    return _CATEGORY_PALETTE[index % len(_CATEGORY_PALETTE)]


# ─── Import/export templates (Importar/Exportar, see ImportExportMixin) ───
# One blank/example mob — never the user's existing mobs, since Aplicar
# always CREATES new rows (see ImportExportMixin._import_mob_dicts), so
# prefilling real data would risk silently duplicating it. A reasonably
# useful subset of fields, not all ~30 DB columns, mirrors config/parallax's
# own JSON template (_JSON_PARAM_DOCS in parallax_section.py) — document the
# fields worth documenting, let short/self-explanatory ones speak for
# themselves.
_TEMPLATE_EXAMPLE = {
    "name": "Novo Mob", "description": "", "category": "", "subcategory": "",
    "tier": 1, "level": 1, "rarity": "normal", "tipo": "Inimigo",
    "element": "", "ambiente": "", "zone_id": "",
    "health": 100, "mana": 50, "damage": 10, "defense": 5, "favorite": 0,
}
_TEMPLATE_FIELD_DOCS = [
    ("name", "nome do mob (obrigatório)"),
    ("category", "ID de uma categoria existente — veja a lista abaixo"),
    ("subcategory", "texto livre, opcional"),
    ("tier", "1 a 10"),
    ("rarity", "normal | raro | elite | boss | mitico"),
    ("tipo", "Inimigo | Aliado | Neutro | Chefe"),
    ("element", "Fogo | Gelo | Raio | Terra | Água | Vento | Sagrado | Sombrio | Veneno (ou vazio)"),
    ("zone_id", "ID de uma região existente, ou vazio"),
    ("favorite", "0 ou 1"),
]


def _parse_mobs_json(text: str) -> list[dict]:
    """Permissive parser for the hand-edited mob template — same technique
    as parallax_section.py's _parse_layers_json: strips "// ..." line
    comments, tolerates a bare object (no enclosing []), unquoted keys, and
    trailing commas, rather than requiring strict JSON from someone editing
    this by hand."""
    text = re.sub(r'//[^\n]*', '', text)
    text = text.strip()
    if not text:
        raise ValueError("Preencha ao menos um mob antes de aplicar.")
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
        raise ValueError("Esperava uma lista de mobs (array).")
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
