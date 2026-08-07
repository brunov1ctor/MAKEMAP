"""Selection Engine — pure state manager. Qt's own scene.selectedItems() /
item.setSelected() is the single source of truth; this class never keeps a
parallel list. Geometry/query logic (box, lasso, invert, select-all) lives
in queries.py as stateless functions that return item lists — this class
only knows how to apply a list to the scene and notify listeners."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene


class SelectionEngine(QObject):
    """Manages current selection state independently from the canvas tools."""

    selection_changed = Signal(list)  # emits list of selected item IDs

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(parent)
        self._scene = scene
        # None = no filtering. Otherwise, restricts what selection can pick
        # to items tagged with one of these item_type values — set via the
        # toolbar's layer-filter dropdown.
        self._allowed_types: set[str] | None = None

    @property
    def selected_items(self) -> list[QGraphicsItem]:
        return list(self._scene.selectedItems())

    # --- Mutating operations ---

    def set(self, items: list[QGraphicsItem]):
        """Replace the current selection with exactly `items`."""
        for item in self._scene.selectedItems():
            self._clear_anchor(item)
            item.setSelected(False)
        for item in items:
            self._clear_anchor(item)
            item.setSelected(True)
        self.notify_changed()

    def add(self, items: list[QGraphicsItem]):
        for item in items:
            self._clear_anchor(item)
            item.setSelected(True)
        self.notify_changed()

    def remove(self, items: list[QGraphicsItem]):
        for item in items:
            self._clear_anchor(item)
            item.setSelected(False)
        self.notify_changed()

    def toggle(self, items: list[QGraphicsItem]):
        for item in items:
            self._clear_anchor(item)
            item.setSelected(not item.isSelected())
        self.notify_changed()

    def clear(self):
        for item in self._scene.selectedItems():
            self._clear_anchor(item)
            item.setSelected(False)
        self.notify_changed()

    @staticmethod
    def _clear_anchor(item: QGraphicsItem):
        """Reset any "which sub-region was clicked" state an item type may
        keep for its own selection box (currently only terrain's
        _LayerItem, see set_selection_anchor/selection_bounding_rect there)
        — every mutator here except the direct-click path in ItemInteraction.
        select_and_begin_drag goes through this, so a box/lasso/Ctrl+A/
        Ctrl+I selection always falls back to the item's whole bounds
        instead of accidentally reusing whatever sub-region a PREVIOUS,
        unrelated click happened to leave behind. select_and_begin_drag
        re-sets a fresh anchor immediately after calling set()/toggle()
        here, so the direct-click case still ends up scoped correctly."""
        set_anchor = getattr(item, "set_selection_anchor", None)
        if set_anchor is not None:
            set_anchor(None)

    def notify_changed(self):
        """Re-emit selection_changed with the current selection's ids —
        public so callers that mutate selection state outside set/add/
        remove/toggle/clear (e.g. a click on an already-selected item,
        where nothing actually changed) can still trigger listeners."""
        ids = []
        for item in self._scene.selectedItems():
            data = item.data(0)
            if isinstance(data, dict) and "id" in data:
                ids.append(data["id"])
        self.selection_changed.emit(ids)

    # --- Layer filter ---

    def set_layer_filter(self, allowed_types: set[str] | None):
        """Restrict selection to items tagged with one of `allowed_types`
        (via item.data(0)["item_type"]). None clears the filter (everything
        selectable again). Also drops any currently selected item that the
        new filter excludes — unchecking a layer in SelectToolPanel should
        clear its already-selected objects too, not just block new ones."""
        self._allowed_types = allowed_types
        if allowed_types is None:
            return
        dropped = [item for item in self._scene.selectedItems() if not self.is_selectable(item)]
        if not dropped:
            return
        for item in dropped:
            item.setSelected(False)
        self.notify_changed()

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
