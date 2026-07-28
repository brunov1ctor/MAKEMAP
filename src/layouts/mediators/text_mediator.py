"""TextMediator — persists TextItem objects (map "Texto" tool) to the
project DB. Mirrors SpawnMediator's canvas_items persistence pattern, minus
any panel wiring (that lives directly in MainLayout's _on_text_* handlers).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer

from src.canvas.text_item import TextItem
from src.engines.typography import text_properties_to_dict, text_properties_from_dict

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_SYNC_DEBOUNCE_MS = 250


class TextMediator:
    """Saves/reloads every TextItem placed on the map."""

    MAP_ID = "default"  # matches BrushMediator/RegionMediator/SpawnMediator

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._items: dict[str, TextItem] = {}  # canvas_items row id -> TextItem

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._on_history_changed)

        # Placement + undo/redo already go through HistoryEngine (caught
        # above), but retyping an EXISTING text (double-click, not a fresh
        # placement) never touches it — TextTool wires this onto every
        # TextItem's persistent on_edited hook (see text_item.py) so that
        # case is covered too.
        self._l.canvas.engine._text_tool.set_on_edited(self._on_history_changed)

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items.clear()
        if not self._uow:
            return

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != "text":
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            item = TextItem(text_properties_from_dict(meta))
            item.setPos(QPointF(row["position_x"], row["position_y"]))
            item.setRotation(row["rotation"] or 0.0)
            item.setZValue(50)
            item.on_edited = self._on_history_changed
            item.setData(1, row["id"])
            scene.addItem(item)
            self._items[row["id"]] = item

    def _on_history_changed(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        """Upserts every currently-placed text item into the project DB,
        and drops rows for ones no longer present (deleted/undone) — same
        shape as BrushMediator/SpawnMediator's own _sync_to_db."""
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            if not isinstance(item, TextItem) or not item.isVisible():
                continue
            fields = dict(
                item_type="text", name=item.props.text[:80],
                position_x=item.pos().x(), position_y=item.pos().y(),
                rotation=item.rotation(),
                metadata=json.dumps(text_properties_to_dict(item.props)),
            )
            row_id = item.data(1)
            # A cached id can go stale (undo hid the item, its row got
            # swept below, then redo brought it back still carrying that
            # dead id) — fall back to creating a fresh row, same as Brush/Spawn.
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            item.on_edited = self._on_history_changed
            self._items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._items[stale_id]
