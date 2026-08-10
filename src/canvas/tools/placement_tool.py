"""PlacementTool — shared click-to-place flow for tools that drop a single
graphics object per click: LightTool, MarkerTool, TextTool. Clicking empty
space (or another layer, e.g. a painted região/terrain) places a new item;
clicking an EXISTING instance of item_cls instead selects/drags it via
ItemInteraction (item_filter), same ambiguity each of these tools used to
resolve with its own copy-pasted mouse_press/mouse_move/mouse_release.

Subclasses supply item_cls, z_value, _default_properties()/_make_item(),
and — for placement-time extras like TextTool's inline-edit-on-drop —
override _after_place()."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.canvas.z_order import ZOrder
from src.engines.core.history import PlaceObjectCommand


class PlacementTool(BaseTool):
    item_cls: type = None  # instances of this class are picked up (not replaced) on click
    z_value = ZOrder.PLACED_GIZMO

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
        self._properties_provider = provider

    def set_parent_provider(self, provider):
        """provider() -> QGraphicsItem | None — boundary group para parenting."""
        self._parent_provider = provider

    def _default_properties(self):
        raise NotImplementedError

    def _make_item(self, props):
        raise NotImplementedError

    def _after_place(self, item):
        """Hook run right after the item is added to the scene/parent and
        pushed to history, before it's selected — override for placement-
        time extras (e.g. TextTool's start_editing())."""

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # item_filter: clicking on top of a região/terrain/asset must still
        # place a new item, not hijack the click into selecting that other
        # layer — only an EXISTING item_cls instance should be picked up.
        if self._interaction and self._interaction.try_begin(scene_pos, item_filter=lambda it: isinstance(it, self.item_cls)):
            return

        props = self._properties_provider() if self._properties_provider else self._default_properties()
        parent_item = self._parent_provider() if self._parent_provider else None
        item = self._make_item(props)
        item.setPos(scene_pos if not parent_item else parent_item.mapFromScene(scene_pos))
        item.setZValue(self.z_value)
        if parent_item:
            item.setParentItem(parent_item)
        else:
            self.viewport.scene().addItem(item)
        if self._history:
            self._history.push(PlaceObjectCommand(item))

        self._after_place(item)

        if self._selection:
            self._selection.set([item])
        else:
            self.viewport.scene().clearSelection()
            item.setSelected(True)

        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_placed:
            self._on_placed()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.move(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.release(scene_pos)
