"""MarkerTool — click to drop a "point of interest" pin; click an existing
one to select/drag/rotate/resize it instead (same click-an-existing-item-vs-
place-a-new-one ambiguity TextTool resolves via ItemInteraction)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.canvas.marker_item import MarkerItem
from src.engines.marker import MarkerProperties
from src.engines.core.history import PlaceObjectCommand


class MarkerTool(BaseTool):
    name = "Marcador"
    shortcut = "K"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self, viewport, tool_manager=None, history_engine=None, selection_engine=None,
        transform_engine=None, on_placed=None, properties_provider=None,
    ):
        super().__init__(viewport)
        self._tool_manager = tool_manager
        self._history = history_engine
        self._selection = selection_engine
        self._on_placed = on_placed
        self._properties_provider = properties_provider
        self._parent_provider = None
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None

    def set_properties_provider(self, provider):
        """provider() -> MarkerProperties, read at the moment a new marker
        is placed — MarkerMediator hands over whichever icon is currently
        picked in the Marcador tool panel."""
        self._properties_provider = provider

    def set_parent_provider(self, provider):
        """provider() -> QGraphicsItem | None — returns the boundary group
        to parent new markers into, or None for infinite map."""
        self._parent_provider = provider

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # item_filter=isinstance(MarkerItem): clicking on top of a painted
        # região/terrain/other layer must still place a new marker, not
        # hijack the click into selecting/dragging that other layer (same
        # fix already applied to SpawnTool/TextTool) — only an EXISTING
        # marker should be picked up here.
        if self._interaction and self._interaction.try_begin(scene_pos, item_filter=lambda it: isinstance(it, MarkerItem)):
            return

        props = self._properties_provider() if self._properties_provider else MarkerProperties()
        parent_item = self._parent_provider() if self._parent_provider else None
        item = MarkerItem(props)
        item.setPos(scene_pos if not parent_item else parent_item.mapFromScene(scene_pos))
        item.setZValue(60)
        if parent_item:
            item.setParentItem(parent_item)
        else:
            self.viewport.scene().addItem(item)
        if self._history:
            self._history.push(PlaceObjectCommand(item))

        if self._selection:
            self._selection.select(item)
        else:
            self.viewport.scene().clearSelection()
            item.setSelected(True)

        # One marker per click, then hand off to Selecionar (same as
        # TextTool) so the toolbar button deselects and the item is
        # immediately ready to drag/resize/rotate and edit in the side panel.
        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_placed:
            self._on_placed(item)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.move(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.release(scene_pos)
