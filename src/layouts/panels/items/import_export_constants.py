"""Field sets for the Itens/Habilidades Importar/Exportar tools panel —
mirrors mobs/panel_helpers.py's _MOB_TEMPLATE_FIELDS/_TEMPLATE_FIELD_DOCS,
one dict per entity type since Itens and Habilidades are two separate
catalogs with different shapes. Any key beyond these falls into the
`stats` JSON blob column, same as _import_item_records/_import_skill_records
already do.
"""

from __future__ import annotations

_ITEM_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "Arma", "subcategory": "",
    "rarity": "common", "level": 1, "favorite": 0,
}
_ITEM_TEMPLATE_DOCS = [
    ("name", "nome do item (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("category", "veja as categorias válidas abaixo"),
    ("subcategory", "texto livre, opcional"),
    ("rarity", "veja as raridades válidas abaixo"),
    ("level", "nível requerido, 1+"),
    ("favorite", "0 ou 1"),
]

_SKILL_TEMPLATE_FIELDS = {
    "name": "", "description": "", "category": "Ataque",
    "rarity": "common", "level": 1, "cooldown": 0, "mana_cost": 0,
    "element": "", "favorite": 0,
}
_SKILL_TEMPLATE_DOCS = [
    ("name", "nome da habilidade (obrigatório)"),
    ("description", "texto livre, opcional"),
    ("category", "veja as categorias válidas abaixo"),
    ("rarity", "veja as raridades válidas abaixo"),
    ("level", "nível requerido, 1+"),
    ("cooldown", "segundos, 0+"),
    ("mana_cost", "custo de mana, 0+"),
    ("element", "texto livre, ou vazio"),
    ("favorite", "0 ou 1"),
]
