"""Selection Engine — independent selection system for the entire application."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene
from PySide6.QtGui import QPolygonF


class SelectionMode(Enum):
    CLICK = auto()
    BOX = auto()
    LASSO = auto()
    MAGIC = auto()


class SelectionEngine(QObject):
    """Manages all selection logic independently from the canvas tools."""

    selection_changed = Signal(list)  # emits list of selected item IDs
    focus_requested = Signal(str)  # emits item ID to focus on

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._selected: list[QGraphicsItem] = []
        self._mode = SelectionMode.CLICK
        # None = no filtering. Otherwise, restricts what box/lasso/click
        # selection can pick to items tagged with one of these item_type
        # values — set via the toolbar's layer-filter dropdown.
        self._allowed_types: set[str] | None = None

    # --- Properties ---

    @property
    def mode(self) -> SelectionMode:
        return self._mode

    @mode.setter
    def mode(self, value: SelectionMode):
        self._mode = value

    @property
    def selected_items(self) -> list[QGraphicsItem]:
        return list(self._selected)

    @property
    def count(self) -> int:
        return len(self._selected)

    @property
    def has_selection(self) -> bool:
        return len(self._selected) > 0

    # --- Core Operations ---

    def select(self, item: QGraphicsItem, add: bool = False):
        """Select a single item. If add=True, adds to current selection."""
        if not add:
            self._clear_visual()
            self._selected.clear()

        if item and item not in self._selected:
            item.setSelected(True)
            self._selected.append(item)

        self._emit()

    def deselect(self, item: QGraphicsItem):
        """Remove a single item from selection."""
        if item in self._selected:
            item.setSelected(False)
            self._selected.remove(item)
            self._emit()

    def toggle(self, item: QGraphicsItem):
        """Toggle selection state of an item."""
        if item in self._selected:
            self.deselect(item)
        else:
            self.select(item, add=True)

    def clear(self):
        """Clear all selection."""
        self._clear_visual()
        self._selected.clear()
        self._emit()

    def select_all(self):
        """Select all selectable items in the scene."""
        self._clear_visual()
        self._selected.clear()
        for item in self._scene.items():
            if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)
                self._selected.append(item)
        self._emit()

    # --- Layer filter ---

    def set_layer_filter(self, allowed_types: set[str] | None):
        """Restrict box/lasso/click selection to items tagged with one of
        `allowed_types` (via item.data(0)["item_type"]). None clears the
        filter (everything selectable again)."""
        self._allowed_types = allowed_types

    def is_selectable(self, item: QGraphicsItem) -> bool:
        """Whether `item` can currently be selected — the base Qt
        selectable flag, plus the active layer filter if any. Items with no
        item_type tag always pass the filter: it only restricts categories
        we actually tag (terrain/asset/zone/...), not everything else in
        the scene (untagged decorations, handles, etc.)."""
        if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            return False
        if self._allowed_types is None:
            return True
        data = item.data(0)
        item_type = data.get("item_type") if isinstance(data, dict) else None
        if item_type is None:
            return True
        return item_type in self._allowed_types

    # --- Box Selection ---

    def select_by_rect(self, rect: QRectF, add: bool = False):
        """Select all items within a rectangle."""
        if not add:
            self._clear_visual()
            self._selected.clear()

        items = self._scene.items(rect)
        for item in items:
            if self.is_selectable(item) and item not in self._selected:
                item.setSelected(True)
                self._selected.append(item)

        self._emit()

    # --- Lasso Selection ---

    def select_by_polygon(self, polygon: QPolygonF, add: bool = False):
        """Select all items within a freeform polygon."""
        if not add:
            self._clear_visual()
            self._selected.clear()

        path = polygon.toList() if hasattr(polygon, "toList") else []
        items = self._scene.items(polygon)
        for item in items:
            if self.is_selectable(item) and item not in self._selected:
                item.setSelected(True)
                self._selected.append(item)

        self._emit()

    # --- Magic Selection (by shared property) ---

    def select_similar(self, property_name: str, value):
        """Select all items sharing a property value with the current selection."""
        self._clear_visual()
        self._selected.clear()

        for item in self._scene.items():
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            item_data = item.data(0)  # metadata stored in data(0)
            if isinstance(item_data, dict) and item_data.get(property_name) == value:
                item.setSelected(True)
                self._selected.append(item)

        self._emit()

    def select_by_type(self, item_type: str):
        """Select all items of a given type."""
        self.select_similar("item_type", item_type)

    def select_by_tag(self, tag: str):
        """Select all items with a given tag."""
        self._clear_visual()
        self._selected.clear()

        for item in self._scene.items():
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            item_data = item.data(0)
            if isinstance(item_data, dict):
                tags = item_data.get("tags", [])
                if tag in tags:
                    item.setSelected(True)
                    self._selected.append(item)

        self._emit()

    def select_by_layer(self, layer_id: str):
        """Select all items belonging to a specific layer."""
        self.select_similar("layer_id", layer_id)

    # --- Advanced Operations ---

    def invert(self):
        """Invert the current selection."""
        all_selectable = [
            item for item in self._scene.items()
            if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        ]

        previously_selected = set(self._selected)
        self._clear_visual()
        self._selected.clear()

        for item in all_selectable:
            if item not in previously_selected:
                item.setSelected(True)
                self._selected.append(item)
            else:
                item.setSelected(False)

        self._emit()

    def expand(self):
        """Expand selection to include overlapping items."""
        if not self._selected:
            return

        bounds = QRectF()
        for item in self._selected:
            bounds = bounds.united(item.sceneBoundingRect())

        # Expand bounds slightly
        bounds.adjust(-10, -10, 10, 10)
        self.select_by_rect(bounds, add=True)

    def shrink(self):
        """Remove items on the boundary of the selection bounding box."""
        if len(self._selected) <= 1:
            return

        bounds = QRectF()
        for item in self._selected:
            bounds = bounds.united(item.sceneBoundingRect())

        # Shrink bounds
        shrunk = bounds.adjusted(20, 20, -20, -20)

        to_remove = []
        for item in self._selected:
            if not shrunk.contains(item.sceneBoundingRect()):
                to_remove.append(item)

        for item in to_remove:
            item.setSelected(False)
            self._selected.remove(item)

        self._emit()

    # --- Focus ---

    def focus_on_selected(self):
        """Request the viewport to focus on the first selected item."""
        if self._selected:
            item = self._selected[0]
            item_id = ""
            data = item.data(0)
            if isinstance(data, dict):
                item_id = data.get("id", "")
            self.focus_requested.emit(item_id)

    # --- Helpers ---

    def _clear_visual(self):
        for item in self._selected:
            item.setSelected(False)

    def _emit(self):
        ids = []
        for item in self._selected:
            data = item.data(0)
            if isinstance(data, dict) and "id" in data:
                ids.append(data["id"])
        self.selection_changed.emit(ids)

    def get_selected_ids(self) -> list[str]:
        ids = []
        for item in self._selected:
            data = item.data(0)
            if isinstance(data, dict) and "id" in data:
                ids.append(data["id"])
        return ids

    def get_bounding_rect(self) -> QRectF:
        """Get the combined bounding rect of all selected items."""
        if not self._selected:
            return QRectF()
        bounds = QRectF()
        for item in self._selected:
            bounds = bounds.united(item.sceneBoundingRect())
        return bounds
