"""NPCCrudMixin — creating, saving, duplicating, deleting, and favoriting an
NPC. Mixed into NPCsPanel (see panel.py) — operates on self.* attributes
NPCsPanel owns; not meant to be instantiated on its own.

Mirrors src/layouts/panels/mobs/panel_crud_mixin.py.
"""

from __future__ import annotations

import logging
import uuid

from src.services.project_assets import import_asset

logger = logging.getLogger("MAKEMAP")


class NPCCrudMixin:
    """Create/save/duplicate/delete/favorite an npc."""

    def _on_new_npc(self):
        """Opens a blank draft in the edit panel — no card, no DB row, until
        "Salvar Alterações" is actually clicked (see _on_save)."""
        if not self._uow:
            return
        npc_id = str(uuid.uuid4())
        draft = {"id": npc_id, "name": f"Novo NPC {len(self._npcs) + 1}"}
        if self._current_dir_id is not None:
            draft["category"] = self._current_dir_id
        self._selected_id = ""
        for layout in (self._grid_layout, self._list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if w is not None and hasattr(w, "npc_id"):
                    w.set_selected(False)
        self._edit_panel.load(draft, creating=True)
        logger.info("Novo npc: formulário em branco aberto (id provisório=%s)", npc_id)

    def _on_save(self, values: dict):
        if not self._uow or not values.get("id"):
            return
        npc_id = values.pop("id")
        if values.get("image_path"):
            values["image_path"] = import_asset(
                self._project_dir, values["image_path"], "assets/npcs", npc_id)
        is_new = self._npc_by_id(npc_id) is None
        if is_new:
            self._uow.npcs.create(id=npc_id, **values)
        else:
            self._uow.npcs.update(npc_id, **values)
        self._selected_id = npc_id
        self._reload()
        self._on_card_selected(npc_id)
        logger.info("NPC salvo: id=%s (%d campos, novo=%s)", npc_id, len(values), is_new)

    def _on_rename(self, npc_id: str, new_name: str):
        if not self._uow or not new_name:
            return
        self._uow.npcs.update(npc_id, name=new_name)
        for m in self._npcs:
            if m["id"] == npc_id:
                m["name"] = new_name
        self._reload()
        logger.info("NPC renomeado: id=%s novo_nome='%s'", npc_id, new_name)

    def _on_duplicate(self, npc_id: str):
        npc = self._npc_by_id(npc_id)
        if not npc or not self._uow:
            return
        new_npc = dict(npc)
        new_npc.pop("id", None)
        new_npc.pop("created_at", None)
        new_npc.pop("updated_at", None)
        new_npc["name"] = f"{npc.get('name', 'NPC')} (Cópia)"
        new_id = self._uow.npcs.create(**new_npc)
        self._reload()
        self._on_card_selected(new_id)
        logger.info("NPC duplicado: origem=%s novo=%s", npc_id, new_id)

    def _on_delete(self, npc_id: str):
        if not self._uow:
            return
        self._uow.npcs.delete(npc_id)
        if self._selected_id == npc_id:
            self._selected_id = ""
            self._edit_panel.set_empty(True)
        self._reload()
        logger.info("NPC excluído: id=%s", npc_id)

    def _on_favorite_toggled(self, npc_id: str, favorite: bool):
        if self._uow:
            self._uow.npcs.update(npc_id, favorite=int(favorite))
        for m in self._npcs:
            if m["id"] == npc_id:
                m["favorite"] = int(favorite)
        self._recompute_stats()
        logger.info("Favorito alterado: npc=%s favorito=%s", npc_id, bool(favorite))
