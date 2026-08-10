"""Shared persistence/wiring skeletons reused by several small
tool mediators (MarkerMediator, LightMediator, TextMediator, ...).

Two independent duplications this collapses:

- CanvasItemSyncMixin: the remove-all-then-reload (`_load_from_db`) /
  upsert-with-fallback-insert-then-sweep-stale-rows (`_sync_to_db`) pattern
  every canvas_items-backed placed-object mediator implemented on its own,
  differing only in the item class constructed, the item_type tag, and
  which fields get read/written. Subclasses plug in the differing bits via
  a handful of hook methods instead of re-implementing the whole loop.

- TerrainAwareMediator: the identical 3-line `set_active_terrain` every
  placement mediator defines to sync its own tool panel's terrain combo +
  `_active_boundary` whenever TerrainMediator reports a new selection.
"""

from __future__ import annotations


class CanvasItemSyncMixin:
    """Shared load/sync skeleton for a mediator that persists one kind of
    placed object into the generic `canvas_items` table.

    A subclass sets:
      _SYNC_ITEM_TYPE  — the `canvas_items.item_type` value this mediator
                          owns (e.g. "marker").
      _SYNC_ITEM_CLASS — the QGraphicsItem subclass placed on the scene,
                          used both to recognize "one of mine" during sync
                          and (implicitly) constructed by _make_sync_item.
    and implements:
      _make_sync_item(row) -> item — build+position (but do not add to the
          scene or tag with a row id) the item for one loaded row.
      _sync_fields(item) -> dict — the canvas_items columns to upsert for
          one currently-placed item.
    A subclass also needs a plain `self._items: dict[str, ItemClass]`
    (row id -> item) attribute, matching what every one of these mediators
    already tracked under that name.

    Optional hooks for per-mediator side effects that don't fit the
    generic shape:
      _after_sync_load() — called once after every row has been reloaded
          (e.g. LightMediator marking its overlay's light cache dirty).
      _after_sync_item(item, row_id) — called for each item right after an
          upsert during _sync_to_db (e.g. TextMediator re-binding
          on_edited, which needs rebinding after a fresh id was assigned).
    """

    _SYNC_ITEM_TYPE: str = ""
    _SYNC_ITEM_CLASS: type = object

    def _make_sync_item(self, row):
        raise NotImplementedError

    def _sync_fields(self, item) -> dict:
        raise NotImplementedError

    def _after_sync_load(self):
        pass

    def _after_sync_item(self, item, row_id):
        pass

    def _load_from_db(self):
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items.clear()
        if not self._uow:
            return

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != self._SYNC_ITEM_TYPE:
                continue
            item = self._make_sync_item(row)
            item.setData(1, row["id"])
            scene.addItem(item)
            self._items[row["id"]] = item
        self._after_sync_load()

    def _sync_to_db(self):
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            if not isinstance(item, self._SYNC_ITEM_CLASS) or not item.isVisible():
                continue
            fields = self._sync_fields(item)
            row_id = item.data(1)
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            self._after_sync_item(item, row_id)
            self._items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._items[stale_id]


class TerrainAwareMediator:
    """Shared `set_active_terrain` for mediators whose own tool panel
    carries a TerrainCombo (Marcador/Luz/Texto/Spawn) — called by
    TerrainMediator.on_selected to sync the placement boundary and the
    combo's label whenever the selected terreno changes.

    A subclass sets `_TERRAIN_PANEL_ATTR` to the MainLayout attribute name
    of its own tool panel (e.g. "marker_panel").
    """

    _TERRAIN_PANEL_ATTR: str = ""

    def set_active_terrain(self, terrain_id: str):
        """Chamado por TerrainMediator.on_selected para sincronizar o label e o boundary ativo."""
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._active_boundary = boundary
        getattr(self._l, self._TERRAIN_PANEL_ATTR).terrain_combo.set_terrain(terrain_id)
