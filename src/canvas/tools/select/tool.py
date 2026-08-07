"""Selection tool — dispatches to box-select or lasso-select, and also drags
whatever item is clicked directly (move), or drags a handle of the current
selection (rotate/resize) — a single tool covering select/move/rotate/resize
like a standard design app, instead of requiring a separate "Mover" tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.engines.core.selection import queries

from .box_select import BoxSelectMixin
from .lasso_select import LassoSelectMixin

if TYPE_CHECKING:
    from src.engines.core.selection import SelectionEngine
    from src.engines.core.transform import TransformEngine
    from src.engines.core.history import HistoryEngine
    from src.canvas.viewport import Viewport


class SelectTool(LassoSelectMixin, BoxSelectMixin, BaseTool):
    """Selection tool with box/lasso modes — see module docstring."""

    name = "Selecionar"
    shortcut = "V"
    cursor = Qt.CursorShape.ArrowCursor

    def __init__(
        self,
        viewport: Viewport,
        selection_engine: SelectionEngine,
        transform_engine: TransformEngine | None = None,
        history_engine: HistoryEngine | None = None,
        tool_manager=None,
    ):
        super().__init__(viewport)
        self._selection = selection_engine
        self._transform = transform_engine
        self._history = history_engine
        self._tool_manager = tool_manager
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine)
        self._lasso_path: QGraphicsPathItem | None = None
        self._lasso_points: list[QPointF] = []
        self._start: QPointF | None = None
        self._lasso_mode = False
        self._box_pending = False  # press landed on empty space, drag not yet confirmed
        self._box_item: QGraphicsRectItem | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self._lasso_mode = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if not self._lasso_mode and self._interaction.try_begin(scene_pos, add):
            return

        if self._lasso_mode:
            self._lasso_begin(scene_pos)
            return

        # Press landed on empty space — could still turn into either a
        # box-select drag (see mouse_move) or, if released without moving,
        # a plain click that deselects and hands off to Pan (see
        # mouse_release) — matches every other tool's "does one thing,
        # then steps aside" behavior once nothing came of the press.
        self._box_begin(scene_pos)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction.move(scene_pos):
            return

        if self._lasso_mode and self._lasso_update(scene_pos):
            return

        self._box_update(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self._interaction.release(scene_pos):
            return

        if self._lasso_mode and self._lasso_path:
            self._lasso_finish(add)
            return

        self._box_finish()

    def key_press(self, event):
        # Escape to deselect
        if event.key() == Qt.Key.Key_Escape:
            self._selection.clear()
        # Ctrl+A to select all
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            scene = self.viewport.scene()
            items = queries.items_all_selectable(scene, self._selection.is_selectable)
            self._selection.set(items)
        # Ctrl+I to invert
        elif event.key() == Qt.Key.Key_I and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            scene = self.viewport.scene()
            items = queries.items_inverse(scene, self._selection.selected_items, self._selection.is_selectable)
            self._selection.set(items)
