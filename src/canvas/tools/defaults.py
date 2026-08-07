"""Default canvas tools — Move, Pan. (Select lives in src/canvas/tools/select/.)"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction


class MoveTool(BaseTool):
    """Move selected items by dragging, using TransformEngine."""

    name = "Mover"
    shortcut = "M"
    cursor = Qt.CursorShape.SizeAllCursor

    def __init__(self, viewport, transform_engine, history_engine=None):
        super().__init__(viewport)
        self._transform = transform_engine
        self._history = history_engine
        self._moving = False
        self._last_pos: QPointF | None = None
        self._start_pos: QPointF | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            selected = self.viewport.scene().selectedItems()
            if selected:
                self._moving = True
                self._last_pos = scene_pos
                self._start_pos = scene_pos
                self._transform.begin_transform(selected)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._moving and self._last_pos:
            delta = scene_pos - self._last_pos
            selected = self.viewport.scene().selectedItems()
            self._transform.move(selected, delta.x(), delta.y())
            self._transform.reposition_handles(selected)
            self._last_pos = scene_pos

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._moving:
            # Push to history
            if self._history and self._start_pos:
                total_dx = scene_pos.x() - self._start_pos.x()
                total_dy = scene_pos.y() - self._start_pos.y()
                if abs(total_dx) > 0.1 or abs(total_dy) > 0.1:
                    from src.engines.core.history import MoveItemsCommand
                    selected = self.viewport.scene().selectedItems()
                    cmd = MoveItemsCommand(selected, total_dx, total_dy)
                    # Don't redo — already moved visually
                    self._history._undo_stack.append(cmd)
                    self._history._redo_stack.clear()
                    self._history._emit()

            self._transform.end_transform()
            self._moving = False
            self._last_pos = None
            self._start_pos = None


class PanTool(BaseTool):
    """Pan the viewport by dragging — full stop. No object ever moves in
    this tool, no matter what the press landed on (a marker, an
    already-selected item, the terrain background...). A plain click (press
    + release with no meaningful movement) on a selectable item still
    selects it — that's what lets clicking an object open its edit panel
    (see e.g. MarkerMediator._on_selection_changed) without switching off
    Pan, the default active tool (see CanvasEngine._register_default_tools)
    — but any real drag, wherever it starts, always pans the canvas.
    Moving/resizing/rotating objects is the Selecionar tool's job."""

    name = "Pan"
    shortcut = "H"
    cursor = Qt.CursorShape.OpenHandCursor

    # Below this (screen pixels), a press that landed on a selectable item
    # reads as a plain click (select it) rather than the start of a pan
    # drag — see mouse_move/mouse_release. Needed because the terrain
    # background itself is selectable and covers the whole map, so almost
    # every press "lands on" something.
    _DRAG_THRESHOLD = 4

    def __init__(self, viewport, selection_engine=None, transform_engine=None, history_engine=None):
        super().__init__(viewport)
        self._panning = False
        self._start = QPointF()
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None
        self._pending_item = None  # item hit on press, click-vs-pan not yet decided
        self._empty_press = False  # press hit nothing selectable, click(-> deselect)-vs-pan not yet decided

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Delete/duplicate/rotate/resize handles on an already-selected
        # item must work no matter which tool happens to be active — Pan is
        # the default tool (see class docstring), so without this the
        # selection border's own action bar was only clickable after
        # switching to Selecionar first, even though the border/handles
        # themselves are drawn regardless of active tool.
        if self._interaction and self._interaction.try_begin_handle(scene_pos):
            return

        item = self._interaction.hit_selectable(scene_pos) if self._interaction else None
        if item is not None:
            # Ambiguous — could be a click (select it) or just the start of
            # a pan drag that happens to start over an item. Defer to
            # mouse_move/mouse_release instead of acting on the press.
            self._pending_item = item
            self._start = event.position()
            return

        # Press hit nothing at all — same ambiguity as above (plain click
        # vs. the start of a pan drag), deferred the same way. Committing
        # straight to panning here (the old behavior) meant a plain click
        # on empty space could never clear the current selection while Pan
        # — the default active tool — was active, since nothing ever called
        # selection.clear() for that case (unlike SelectTool's own
        # click-on-empty-space handling).
        self._empty_press = True
        self._start = event.position()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction and self._interaction.move(scene_pos):
            return

        if self._pending_item is not None:
            delta = event.position() - self._start
            if math.hypot(delta.x(), delta.y()) < self._DRAG_THRESHOLD:
                return
            # Moved enough — this is a pan, not a click. Drop the pending
            # item and start panning from here (no jump: this move's delta
            # is applied below like any other pan step).
            self._pending_item = None
            self._panning = True
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)

        if self._empty_press:
            delta = event.position() - self._start
            if math.hypot(delta.x(), delta.y()) < self._DRAG_THRESHOLD:
                return
            self._empty_press = False
            self._panning = True
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)

        if self._panning:
            delta = event.position() - self._start
            self._start = event.position()
            self.viewport.horizontalScrollBar().setValue(
                self.viewport.horizontalScrollBar().value() - int(delta.x())
            )
            self.viewport.verticalScrollBar().setValue(
                self.viewport.verticalScrollBar().value() - int(delta.y())
            )

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction and self._interaction.release(scene_pos):
            return

        if self._pending_item is not None:
            # Released without moving past the threshold — a real click:
            # select the item (shows it in the right-hand panel) without
            # moving it.
            self._interaction.selection.set([self._pending_item])
            self._pending_item = None
            return

        if self._empty_press:
            # Released without moving past the threshold — a real click on
            # empty space: deselect, matching SelectTool's own behavior.
            self._empty_press = False
            if self._interaction:
                self._interaction.selection.clear()
            return

        if self._panning:
            self._panning = False
            self.viewport.setCursor(Qt.CursorShape.OpenHandCursor)
