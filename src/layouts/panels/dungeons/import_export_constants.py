"""Field sets for the Dungeons/Construções Importar/Exportar tools panel —
mirrors items/import_export_constants.py's _ITEM_TEMPLATE_FIELDS/
_SKILL_TEMPLATE_FIELDS, one dict per entity type since Dungeons and
Construções are two separate catalogs with different shapes.

Unlike items/skills (which persist only a handful of real DB columns and
stash everything else in a single `stats` JSON blob), Dungeon/Building
already have a real DB column for every field — migration 13 gave them one
column per field, JSON-blob columns (rewards/encounters/bosses/modifiers,
costs/requirements/visuals/production) included. So there's no stats-blob
split here: _DUNGEON_DB_COLUMNS/_BUILDING_DB_COLUMNS below are identity
maps (template key IS the column name) kept only so
panel_import_export_mixin.py's _current_db_columns() has the same shape to
call as items'/skills' version.

_DUNGEON_JSON_FIELDS/_BUILDING_JSON_FIELDS mark which columns hold a
list/dict (rewards, costs, ...) rather than a plain scalar — CSV/Excel
cells can't hold those natively, so the export/import mixin JSON-encodes
them into a single cell, same as items' tags/rank_damage.
_DUNGEON_BOOL_FIELDS/_BUILDING_BOOL_FIELDS mark the flag columns that need
explicit true/false parsing from CSV/Excel text — see coerce_import_stats
in items/import_export_constants.py (reused as-is here, it's a pure
function with no items-specific behavior).
"""

from __future__ import annotations

from src.layouts.panels.dungeons.constants import DIFFICULTIES, GENERATION_TYPES, DUNGEON_BIOMES, STRUCTURE_TYPES

# ─── Dungeons ────────────────────────────────────────────────────────────

_DUNGEON_TEMPLATE_FIELDS = {
    "name": "", "description": "", "dungeon_type": "Exploração", "difficulty": "Normal",
    "level_min": 1, "level_max": 10, "biome": "", "floors": 1, "rooms": 1,
    "generation": "Linear", "checkpoints": 0, "secret_rooms": 0, "est_time": "00:00",
    "group_min": 1, "group_max": 4,
    "req_level": 1, "req_quest": "", "req_item": "",
    "active": True, "visible_on_map": True, "group_available": False,
    "rewards": [], "encounters": [], "bosses": [], "modifiers": {},
}
_DUNGEON_DB_COLUMNS = {key: key for key in _DUNGEON_TEMPLATE_FIELDS}
_DUNGEON_JSON_FIELDS = ("rewards", "encounters", "bosses", "modifiers")
_DUNGEON_BOOL_FIELDS = ("active", "visible_on_map", "group_available")

_DUNGEON_TEMPLATE_DOCS = [
    ("name", "nome da dungeon (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("dungeon_type", "veja os tipos válidos abaixo (cria uma aba nova se não existir)"),
    ("difficulty", f"{', '.join(DIFFICULTIES)}"),
    ("level_min", "nível mínimo recomendado"),
    ("level_max", "nível máximo recomendado"),
    ("biome", f"{', '.join(DUNGEON_BIOMES)}, ou texto livre"),
    ("floors", "número de andares/pisos"),
    ("rooms", "número de salas"),
    ("generation", f"{', '.join(GENERATION_TYPES)}"),
    ("checkpoints", "número de pontos de checkpoint"),
    ("secret_rooms", "número de salas secretas"),
    ("est_time", 'tempo estimado, formato "HH:MM"'),
    ("group_min", "tamanho mínimo de grupo"),
    ("group_max", "tamanho máximo de grupo"),
    ("req_level", "nível mínimo do jogador para entrar"),
    ("req_quest", "texto livre, nome de uma missão pré-requisito, ou vazio"),
    ("req_item", "texto livre, nome de um item pré-requisito, ou vazio"),
    ("active", "true/false — dungeon disponível no jogo"),
    ("visible_on_map", "true/false — aparece no mapa"),
    ("group_available", "true/false — pode ser feita em grupo"),
    ("rewards", 'lista JSON [{"item":"..","qty":N}, ...], ou vazio'),
    ("encounters", 'lista JSON [{"name":"..","count":N}, ...], ou vazio'),
    ("bosses", 'lista JSON [{"name":"..", ...}, ...], ou vazio'),
    ("modifiers", 'objeto JSON {"enemy_hp":100, "enemy_dmg":100, ...}, ou vazio'),
]

# ─── Construções ─────────────────────────────────────────────────────────

_BUILDING_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "Produção", "subcategory": "",
    "level": 1, "max_level": 5, "build_time": "00:00:00", "structure": "Simples",
    "tier": 1, "status": "disponivel", "sort_order": 0,
    "costs": [], "requirements": [], "visuals": [], "production": {},
}
_BUILDING_DB_COLUMNS = {key: key for key in _BUILDING_TEMPLATE_FIELDS}
_BUILDING_JSON_FIELDS = ("costs", "requirements", "visuals", "production")
_BUILDING_BOOL_FIELDS = ()

_BUILDING_TEMPLATE_DOCS = [
    ("name", "nome da construção (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("category", "veja as categorias válidas abaixo (cria uma aba nova se não existir)"),
    ("subcategory", "texto livre, opcional"),
    ("level", "nível inicial, 1+"),
    ("max_level", "nível máximo de upgrade"),
    ("build_time", 'tempo de construção, formato "HH:MM:SS"'),
    ("structure", f"{', '.join(STRUCTURE_TYPES)}"),
    ("tier", "linha na árvore de progressão, 1+"),
    ("status", "disponivel, bloqueada, andamento ou concluida"),
    ("sort_order", "ordem de exibição dentro do tier, opcional"),
    ("costs", 'lista JSON [{"resource":"Madeira","amount":N}, ...], ou vazio'),
    ("requirements", 'lista JSON [{"label":"..", ...}, ...], ou vazio'),
    ("visuals", 'lista JSON [{"label":"..", ...}, ...], ou vazio'),
    ("production", 'objeto JSON {"resource":"..","amount":N, ...}, ou vazio'),
]
