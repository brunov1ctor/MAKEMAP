"""find_ref_item — acha o QGraphicsItem de um stamp de NPC/Mob já colocado no
mapa, dado o (ref_type, ref_id) que um nó de Fluxo guarda. Não existe tabela
de busca id->item, então percorre `scene.items()` na hora, igual a como
SpawnMediator._sync_to_db já faz. Usado tanto pelo QuestMapPreview (só
localizar) quanto pelo QuestMediator (selecionar/mover a partir do mapa
real)."""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsScene


def _matches(item, ref_type: str, ref_id: str) -> bool:
    data = item.data(0)
    if not isinstance(data, dict):
        return False
    return data.get("item_type") == f"{ref_type}_spawn" and data.get("mob_id") == ref_id


def find_ref_item(scene: QGraphicsScene | None, ref_type: str, ref_id: str):
    if scene is None or not ref_id or ref_type not in ("npc", "mob"):
        return None
    for item in scene.items():
        if _matches(item, ref_type, ref_id):
            return item
    return None
