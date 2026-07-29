"""Field sets for the Itens/Habilidades Importar/Exportar tools panel —
mirrors mobs/panel_helpers.py's _MOB_TEMPLATE_FIELDS/_TEMPLATE_FIELD_DOCS,
one dict per entity type since Itens and Habilidades are two separate
catalogs with different shapes.

Item/SkillEditor only persist a handful of real DB columns (see
_ITEM_DB_COLUMNS/_SKILL_DB_COLUMNS below) — everything else lives in the
`stats` JSON blob. For Importar/Exportar to actually round-trip a record
losslessly, every stats sub-field the editors read/write has to show up
here too, not just the DB columns — this used to only list the DB columns,
which meant Exportar silently dropped rank tables, tags, combat stats,
flags etc., and Importar had no documented way to set them even though the
generic "extra keys fall into stats" passthrough in
panel.py._import_item_records/_import_skill_records happened to accept
them anyway.

_ITEM_JSON_FIELDS/_SKILL_JSON_FIELDS mark which stats keys hold a list/dict
(tags, rank_damage) rather than a plain scalar — CSV/Excel cells can't hold
those natively, so the export/import mixin JSON-encodes them into a single
cell (see panel_import_export_mixin.py). _ITEM_BOOL_FIELDS/_SKILL_BOOL_FIELDS
mark the flag keys that need explicit true/false parsing from CSV/Excel
text instead of Python's bool("false") == True trap — see
coerce_import_stats below.
"""

from __future__ import annotations

import json

from src.layouts.panels.items.constants import (
    DAMAGE_TYPES, ELEMENT_OPTIONS, ALLOWED_CLASSES, ITEM_FLAGS, SKILL_FLAGS,
)

# ─── Itens ───────────────────────────────────────────────────────────────

# template key -> real ItemRepository column (everything else lives in stats).
_ITEM_DB_COLUMNS = {
    "name": "name", "description": "description", "category": "item_type",
    "subcategory": "subcategory", "rarity": "rarity", "level": "level_req",
}

_ITEM_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "Arma", "subcategory": "",
    "rarity": "common", "level": 1,
    "priority": 0, "peso": 0.0, "valor": 0, "stack_max": 1, "durabilidade": 100,
    "nivel_min": 1, "drop_rate": 10.0, "drop_qty": 1,
    "classe": "Todas", "uso": "Passivo", "cooldown": 0.0, "efeito_uso": "",
    "attack": 0.0, "atk_speed": 1.0, "crit": 0.0, "range": 0.0,
    "dmg_type": DAMAGE_TYPES[0], "element": ELEMENT_OPTIONS[0],
    "req_forca": 0, "req_destreza": 0, "req_inteligencia": 0, "req_reputacao": "",
    "tags": [],
    **{key: default for key, _label, default in ITEM_FLAGS},
    "consumable": False,
}
_ITEM_JSON_FIELDS = ("tags",)
_ITEM_BOOL_FIELDS = tuple(key for key, _label, _default in ITEM_FLAGS) + ("consumable",)

_ITEM_TEMPLATE_DOCS = [
    ("name", "nome do item (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("category", "veja as categorias válidas abaixo"),
    ("subcategory", "texto livre, opcional"),
    ("rarity", "veja as raridades válidas abaixo"),
    ("level", "nível requerido, 1+"),
    ("priority", "ordem de exibição, opcional"),
    ("peso", "peso em kg"),
    ("valor", "valor de venda"),
    ("stack_max", "tamanho máximo de pilha"),
    ("durabilidade", "durabilidade máxima"),
    ("nivel_min", "nível mínimo pra usar (padrão = level)"),
    ("drop_rate", "chance de drop, em %"),
    ("drop_qty", "quantidade dropada"),
    ("classe", f"{', '.join(ALLOWED_CLASSES)}"),
    ("uso", "Passivo, Ativo, Equipável ou Arremessável"),
    ("cooldown", "segundos de recarga do uso, 0+"),
    ("efeito_uso", "texto livre, o que acontece ao usar"),
    ("attack", "dano de ataque, 0+"),
    ("atk_speed", "velocidade de ataque"),
    ("crit", "chance de crítico, em %"),
    ("range", "alcance em metros"),
    ("dmg_type", f"{', '.join(DAMAGE_TYPES)}"),
    ("element", f"{', '.join(ELEMENT_OPTIONS)}"),
    ("req_forca", "força mínima requerida"),
    ("req_destreza", "destreza mínima requerida"),
    ("req_inteligencia", "inteligência mínima requerida"),
    ("req_reputacao", 'texto livre, ex.: "Aliança: Honrado"'),
    ("tags", 'lista JSON [{"type":"..","label":".."}], ou vazio'),
    *[(key, "true/false — " + label.lower()) for key, label, _default in ITEM_FLAGS],
    ("consumable", "true/false — some ao usar"),
]

# ─── Habilidades ─────────────────────────────────────────────────────────

_SKILL_DB_COLUMNS = {
    "name": "name", "description": "description", "category": "category",
    "rarity": "rarity", "level": "level", "cooldown": "cooldown",
    "mana_cost": "mana_cost", "element": "element",
}

_SKILL_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "Ataque",
    "rarity": "common", "level": 1, "cooldown": 0.0, "mana_cost": 0, "element": "",
    "stamina": 0, "alcance": 0.0, "area": 0.0, "duracao": 0.0, "cast_time": 0.0,
    "dmg_type": DAMAGE_TYPES[0],
    "req_nivel": 1, "req_arma": "Qualquer",
    "recurso": "Mana", "cargas": 0, "notas": "",
    "rank_max": 5, "rank_damage": [],
    "tags": [],
    **{key: default for key, _label, default in SKILL_FLAGS},
}
_SKILL_JSON_FIELDS = ("tags", "rank_damage")
_SKILL_BOOL_FIELDS = tuple(key for key, _label, _default in SKILL_FLAGS)

_SKILL_TEMPLATE_DOCS = [
    ("name", "nome da habilidade (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("category", "veja as categorias válidas abaixo"),
    ("rarity", "tier de progressão — veja as opções válidas abaixo"),
    ("level", "nível requerido, 1+"),
    ("cooldown", "segundos de recarga, 0+"),
    ("mana_cost", "custo de mana, 0+"),
    ("element", "texto livre, ou vazio"),
    ("stamina", "custo de stamina, 0+"),
    ("alcance", "alcance em metros"),
    ("area", "área de efeito em metros"),
    ("duracao", "duração do efeito em segundos"),
    ("cast_time", "tempo de conjuração em segundos"),
    ("dmg_type", f"{', '.join(DAMAGE_TYPES)}"),
    ("req_nivel", "nível mínimo pra usar (padrão = level)"),
    ("req_arma", 'nome de um item cadastrado, ou "Qualquer"/"Desarmado"'),
    ("recurso", "Mana, Stamina, Fúria, Energia ou Nenhum"),
    ("cargas", "número de cargas, 0+"),
    ("notas", "texto livre, opcional"),
    ("rank_max", "até que rank evolui na Árvore de Habilidades, 1-10"),
    ("rank_damage", 'lista JSON [{"dano_base":N,"escalonamento":N}, ...], um item por rank'),
    ("tags", 'lista JSON [{"type":"buff|debuff|..","label":".."}], ou vazio'),
    *[(key, "true/false — " + label.lower()) for key, label, _default in SKILL_FLAGS],
]

# ─── Árvores de Habilidade ───────────────────────────────────────────────

# Trees are a graph (nodes + edges + a theme per guia), not a flat catalog
# of records like items/skills — they don't have a `stats` blob or an
# id/create() shape at all, so there's no _TREE_DB_COLUMNS/_TREE_JSON_FIELDS
# here the way items/skills have. Instead, ONE ROW = ONE NODE: rows sharing
# the same "tree" name are grouped back into one guia on import (see
# panel.py._import_tree_records), and "connects_to" flattens that node's
# outgoing edges into a single ";"-separated cell of skill names — the same
# trick used for CSV/Excel's json-in-cell fields, but plain text works here
# since a skill name has no structure to preserve beyond the list itself.
_TREE_TEMPLATE_FIELDS = {
    "tree": "", "theme_color": "", "text_color": "",
    "skill": "", "rank_current": 0, "rank_max": 5,
    "pos_x": 0.0, "pos_y": 0.0, "connects_to": "",
}
_TREE_TEMPLATE_DOCS = [
    ("tree", "nome da guia/árvore (obrigatório) — linhas com o mesmo nome formam a mesma árvore"),
    ("theme_color", "cor hex da aba/borda dos nós, ex.: #4FC3F7, ou vazio"),
    ("text_color", "cor hex do texto dos nós, ou vazio"),
    ("skill", "nome de uma habilidade já cadastrada (obrigatório — veja a aba Habilidades)"),
    ("rank_current", "rank já investido nesse nó, 0+"),
    ("rank_max", "rank máximo do nó (padrão = Rank Máximo da própria habilidade)"),
    ("pos_x", "posição X do card no canvas"),
    ("pos_y", "posição Y do card no canvas"),
    ("connects_to", 'nomes de outras habilidades DESTA árvore que este nó conecta, separados por ";"'),
]


def coerce_import_stats(raw: dict, json_fields: tuple[str, ...], bool_fields: tuple[str, ...]) -> dict:
    """Normalizes a pasted/dropped record's extra (non-DB-column) keys
    before they're written into the `stats` JSON blob.

    JSON import already hands back real Python types (list/dict/bool), so
    this is mostly a no-op for it. CSV/Excel import hands back plain
    strings for everything (or None for a blank cell, via
    normalize_blank_cells) — without this:
      - a blank cell would store `None` into stats, and the editor's own
        `stats.get(key, default)` returns that None instead of falling
        back to default (dict.get only defaults when the key is MISSING,
        not when it's None) — dropped here instead, so the key doesn't
        exist and the editor's default applies exactly as if it were
        never set.
      - "tags"/"rank_damage" would stay serialized JSON text instead of
        the list of dicts the editor expects.
      - a boolean flag's cell text ("false", "FALSE", "0") would import as
        truthy no matter what, since Python's bool("false") is True for
        any non-empty string.
    """
    out = {}
    for key, value in raw.items():
        if value is None:
            continue
        if key in json_fields and isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
        elif key in bool_fields and isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "sim", "yes", "x")
        elif key in bool_fields and isinstance(value, (int, float)):
            value = bool(value)
        out[key] = value
    return out
