"""MobCrudMixin — creating, saving, duplicating, deleting, and favoriting a
mob. Mixed into MobsPanel (see panel.py) — operates on self.* attributes
MobsPanel owns; not meant to be instantiated on its own.

`_on_cancel_edit`, `_on_test`, `_on_generate_loot`, `_on_locate` (and the 4
MobEditPanel signals they were wired to: cancel_requested, test_requested,
generate_loot_requested, locate_requested) were removed here — the buttons
that used to trigger them were dropped from MobEditPanel's footer a while
back ("Ações Rápidas and Cancelar removed"), leaving these as genuinely
unreachable dead code (confirmed: nothing else in the app emits or connects
to those signals).
"""

from __future__ import annotations

import logging
import uuid

from src.services.project_assets import import_asset

logger = logging.getLogger("MAKEMAP")


class MobCrudMixin:
    """Create/save/duplicate/delete/favorite a mob."""

    def _on_new_mob(self):
        """Opens a blank draft in the edit panel — no card, no DB row, until
        "Salvar Alterações" is actually clicked (see _on_save). Previously
        this created the DB row immediately, so clicking "+ Novo Mob" and
        then clicking away without saving left an orphaned "Novo Mob N" row
        behind; now nothing is written until the user actually saves."""
        if not self._uow:
            return
        mob_id = str(uuid.uuid4())
        draft = {"id": mob_id, "name": f"Novo Mob {len(self._mobs) + 1}"}
        # Same "drop it in the folder you're browsing" behavior as import —
        # see ImportExportMixin._import_mob_dicts.
        if self._current_dir_id is not None:
            draft["category"] = self._current_dir_id
        self._selected_id = ""
        for layout in (self._grid_layout, self._list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if w is not None and hasattr(w, "mob_id"):
                    w.set_selected(False)
        self._edit_panel.load(draft, creating=True)
        logger.info("Novo mob: formulário em branco aberto (id provisório=%s)", mob_id)

    def _on_save(self, values: dict):
        if not self._uow or not values.get("id"):
            return
        mob_id = values.pop("id")
        if values.get("image_path"):
            values["image_path"] = import_asset(
                self._project_dir, values["image_path"], "assets/mobs", mob_id)
        is_new = self._mob_by_id(mob_id) is None
        if is_new:
            self._uow.mobs.create(id=mob_id, **values)
        else:
            self._uow.mobs.update(mob_id, **values)
        self._selected_id = mob_id
        self._reload()
        self._on_card_selected(mob_id)
        logger.info("Mob salvo: id=%s (%d campos, novo=%s)", mob_id, len(values), is_new)

    def _on_rename(self, mob_id: str, new_name: str):
        """The only way to rename an already-saved mob — its Nome field in
        the edit panel becomes read-only once saved (see MobEditPanel);
        this is triggered from the "✏ Renomear" menu action instead."""
        if not self._uow or not new_name:
            return
        self._uow.mobs.update(mob_id, name=new_name)
        for m in self._mobs:
            if m["id"] == mob_id:
                m["name"] = new_name
        self._reload()
        logger.info("Mob renomeado: id=%s novo_nome='%s'", mob_id, new_name)

    def _on_duplicate(self, mob_id: str):
        """Quick-duplicate from the card's own right-click menu — distinct
        from the edit panel's header menu, which dropped Duplicar in favor
        of Renomear (see _on_rename)."""
        mob = self._mob_by_id(mob_id)
        if not mob or not self._uow:
            return
        new_mob = dict(mob)
        new_mob.pop("id", None)
        new_mob.pop("created_at", None)
        new_mob.pop("updated_at", None)
        new_mob["name"] = f"{mob.get('name', 'Mob')} (Cópia)"
        new_id = self._uow.mobs.create(**new_mob)
        self._reload()
        self._on_card_selected(new_id)
        logger.info("Mob duplicado: origem=%s novo=%s", mob_id, new_id)

    def _on_delete(self, mob_id: str):
        if not self._uow:
            return
        self._uow.mobs.delete(mob_id)
        if self._selected_id == mob_id:
            self._selected_id = ""
            self._edit_panel.set_empty(True)
        self._reload()
        logger.info("Mob excluído: id=%s", mob_id)

    def _on_favorite_toggled(self, mob_id: str, favorite: bool):
        if self._uow:
            self._uow.mobs.update(mob_id, favorite=int(favorite))
        for m in self._mobs:
            if m["id"] == mob_id:
                m["favorite"] = int(favorite)
        self._recompute_stats()
        logger.info("Favorito alterado: mob=%s favorito=%s", mob_id, bool(favorite))
