"""Clipboard Engine — independent copy/cut/paste system."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF
from PySide6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from src.engines.selection import SelectionEngine


@dataclass
class ClipboardEntry:
    """Serialized snapshot of copied items."""
    items: list[dict] = field(default_factory=list)
    source_center: QPointF = field(default_factory=lambda: QPointF(0, 0))


class ClipboardEngine(QObject):
    """Manages copy, cut, paste, duplicate with history."""

    pasted = Signal(list)  # emits list of new item dicts
    cut_performed = Signal(list)  # emits list of removed item IDs

    HISTORY_LIMIT = 10
    PASTE_OFFSET = 20.0  # pixels offset for smart paste

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._clipboard: ClipboardEntry | None = None
        self._history: list[ClipboardEntry] = []
        self._paste_count = 0

    # --- Core Operations ---

    def copy(self, items: list[QGraphicsItem]):
        """Copy items to clipboard."""
        if not items:
            return

        entry = self._serialize_items(items)
        self._clipboard = entry
        self._paste_count = 0

        # Add to history
        self._history.insert(0, entry)
        if len(self._history) > self.HISTORY_LIMIT:
            self._history.pop()

    def cut(self, items: list[QGraphicsItem]):
        """Copy items then remove from scene."""
        if not items:
            return

        self.copy(items)

        ids = []
        for item in items:
            data = item.data(0)
            if isinstance(data, dict) and "id" in data:
                ids.append(data["id"])
            self._scene.removeItem(item)

        self.cut_performed.emit(ids)

    def paste(self, target_pos: QPointF | None = None) -> list[dict]:
        """Paste clipboard contents. Returns list of new item dicts."""
        if not self._clipboard:
            return []

        self._paste_count += 1
        offset = self.PASTE_OFFSET * self._paste_count

        new_items = []
        for item_data in self._clipboard.items:
            new_data = item_data.copy()
            new_data["id"] = str(uuid.uuid4())

            if target_pos:
                # Paste at specific position
                dx = target_pos.x() - self._clipboard.source_center.x()
                dy = target_pos.y() - self._clipboard.source_center.y()
                new_data["position_x"] = item_data.get("position_x", 0) + dx
                new_data["position_y"] = item_data.get("position_y", 0) + dy
            else:
                # Smart paste with offset
                new_data["position_x"] = item_data.get("position_x", 0) + offset
                new_data["position_y"] = item_data.get("position_y", 0) + offset

            new_items.append(new_data)

        self.pasted.emit(new_items)
        return new_items

    def paste_in_place(self) -> list[dict]:
        """Paste at the exact original position."""
        if not self._clipboard:
            return []

        new_items = []
        for item_data in self._clipboard.items:
            new_data = item_data.copy()
            new_data["id"] = str(uuid.uuid4())
            new_items.append(new_data)

        self.pasted.emit(new_items)
        return new_items

    def duplicate(self, items: list[QGraphicsItem]) -> list[dict]:
        """Copy and immediately paste with offset."""
        self.copy(items)
        return self.paste()

    # --- History ---

    @property
    def history(self) -> list[ClipboardEntry]:
        return list(self._history)

    @property
    def has_content(self) -> bool:
        return self._clipboard is not None and len(self._clipboard.items) > 0

    def paste_from_history(self, index: int, target_pos: QPointF | None = None) -> list[dict]:
        """Paste a specific entry from clipboard history."""
        if index < 0 or index >= len(self._history):
            return []

        self._clipboard = self._history[index]
        self._paste_count = 0
        return self.paste(target_pos)

    def clear_history(self):
        self._history.clear()

    # --- Serialization ---

    def _serialize_items(self, items: list[QGraphicsItem]) -> ClipboardEntry:
        """Serialize graphics items into portable dicts."""
        serialized = []
        positions = []

        for item in items:
            data = item.data(0)
            if isinstance(data, dict):
                item_dict = data.copy()
            else:
                item_dict = {}

            # Always capture position from the item itself
            pos = item.pos()
            item_dict["position_x"] = pos.x()
            item_dict["position_y"] = pos.y()
            item_dict["rotation"] = item.rotation()
            item_dict["scale_x"] = item.transform().m11()
            item_dict["scale_y"] = item.transform().m22()
            item_dict["z_index"] = item.zValue()

            serialized.append(item_dict)
            positions.append(pos)

        # Calculate center of all items
        if positions:
            cx = sum(p.x() for p in positions) / len(positions)
            cy = sum(p.y() for p in positions) / len(positions)
            center = QPointF(cx, cy)
        else:
            center = QPointF(0, 0)

        return ClipboardEntry(items=serialized, source_center=center)
