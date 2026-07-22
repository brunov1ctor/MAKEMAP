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

logger = logging.getLogger("MAKEMAP")


class MobCrudMixin:
    """Create/save/duplicate/delete/favorite a mob."""

    def _on_new_mob(self):
        if not self._uow:
            return
        mob_id = str(uuid.uuid4())
        name = f"Novo Mob {len(self._mobs) + 1}"
        fields = {"id": mob_id, "name": name}
        # Same "drop it in the folder you're browsing" behavior as import —
        # see ImportExportMixin._import_mob_dicts.
        if self._current_dir_id is not None:
            fields["category"] = self._current_dir_id
        self._uow.mobs.create(**fields)
        self._reload()
        self._on_card_selected(mob_id)
        logger.info("Novo mob criado: id=%s nome='%s' categoria=%s", mob_id, name, self._current_dir_id)

    def _on_save(self, values: dict):
        if not self._uow or not values.get("id"):
            return
        mob_id = values.pop("id")
        self._uow.mobs.update(mob_id, **values)
        self._selected_id = mob_id
        self._reload()
        self._on_card_selected(mob_id)
        logger.info("Mob salvo: id=%s (%d campos)", mob_id, len(values))

    def _on_duplicate(self, mob_id: str):
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
