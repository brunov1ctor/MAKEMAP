"""Field set for the Quests Importar/Exportar tools panel — mirrors
dungeons/import_export_constants.py's shape (one flat dict of column
defaults + a JSON-fields tuple + a bool-fields tuple + per-field docs).

Quests differs from Dungeons/Construções in one way: `region` isn't a
column of its own, it's resolved to `region_id` by name at import time (see
panel_import_export_mixin._import_quest_records) — unlike dungeon_type/
building_category, a Região is a full world/kingdom-scoped record the
Quests panel has no "create on the fly" capability for, so an unmatched
region name is simply left blank rather than inventing a new Região.

`flow_json` (o grafo da aba Fluxo) fica de fora deste export — é um grafo
com posições de nós, não uma linha plana de campos escalares, mesma razão
pela qual a Árvore de Habilidades de Itens tem seu próprio export separado
(_tree_export_rows) em vez de entrar no export de itens.
"""

from __future__ import annotations

QUEST_TEMPLATE_FIELDS = {
    "name": "", "title": "", "description": "", "quest_type": "Principal",
    "region": "", "level_req": 1, "level_max": 1, "status": "Rascunho", "priority": "Média",
    "repeatable": False, "time_limit_seconds": 0,
    "fail_on_abandon": False, "auto_accept": False, "hide_on_map": False,
    "tags": [], "objectives": [], "rewards": {}, "conditions": [], "events": [],
    "notes": "", "scripts": "", "dialogue": "",
}

# chave do template -> coluna real da tabela quests. "region" fica de fora
# (None) porque não é uma coluna 1-pra-1 — ver docstring acima.
QUEST_DB_COLUMNS: dict[str, str | None] = {
    "name": "name", "title": "title", "description": "description", "quest_type": "quest_type",
    "region": None,
    "level_req": "level_req", "level_max": "level_max", "status": "status", "priority": "priority",
    "repeatable": "repeatable", "time_limit_seconds": "time_limit_seconds",
    "fail_on_abandon": "fail_on_abandon", "auto_accept": "auto_accept", "hide_on_map": "hide_on_map",
    "tags": "tags_json", "objectives": "objectives", "rewards": "rewards",
    "conditions": "conditions_json", "events": "events_json",
    "notes": "notes", "scripts": "scripts", "dialogue": "dialogue",
}

QUEST_JSON_FIELDS = ("tags", "objectives", "rewards", "conditions", "events")
QUEST_BOOL_FIELDS = ("repeatable", "fail_on_abandon", "auto_accept", "hide_on_map")

QUEST_TEMPLATE_DOCS = [
    ("name", "nome da quest (obrigatório)"),
    ("title", "subtítulo/título de exibição, opcional"),
    ("description", "descrição curta, opcional"),
    ("quest_type", "Principal, Secundária, Diária, Semanal, Evento ou Cadeia"),
    ("region", "nome de uma região já cadastrada, ou vazio (não cria região nova)"),
    ("level_req", "nível mínimo recomendado"),
    ("level_max", "nível máximo recomendado"),
    ("status", "Ativa, Em progresso, Rascunho ou Desativada"),
    ("priority", "Baixa, Média ou Alta"),
    ("repeatable", "true/false — quest pode ser repetida"),
    ("time_limit_seconds", "tempo limite em segundos, 0 = sem limite"),
    ("fail_on_abandon", "true/false — abandonar conta como falha"),
    ("auto_accept", "true/false — aceita automaticamente ao ficar disponível"),
    ("hide_on_map", "true/false — não mostra ícone no mapa"),
    ("tags", 'lista JSON ["tag1", "tag2", ...], ou vazio'),
    ("objectives", 'lista JSON [{"description":"..","type":"..","count":N}, ...], ou vazio'),
    ("rewards", 'objeto JSON {"exp":N,"gold":N,"reputation":N,"items":[{"item_id":"..","name":"..","qty":N}]}, ou vazio'),
    ("conditions", 'lista JSON [{"condition_type":"..","value":".."}, ...], ou vazio'),
    ("events", 'lista JSON [{"trigger":"..","description":".."}, ...], ou vazio'),
    ("notes", "anotações livres do designer, opcional"),
    ("scripts", "hooks de script, opcional"),
    ("dialogue", "texto de diálogo do NPC, opcional"),
]
