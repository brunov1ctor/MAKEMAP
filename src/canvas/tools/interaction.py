"""Shared drag-to-move / handle-to-rotate / handle-to-resize interaction —
usable by any tool that lets the user directly manipulate objects on the
canvas (Selecionar, Texto, ...) instead of duplicating the same mouse
tracking in every tool that wants it."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF

from src.engines.core.transform import HandleType, HORIZONTAL_HANDLES, VERTICAL_HANDLES

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.core.selection import SelectionEngine
    from src.engines.core.transform import TransformEngine
    from src.engines.core.history import HistoryEngine


RESIZE_HANDLES = {
    HandleType.TOP_LEFT, HandleType.TOP_CENTER, HandleType.TOP_RIGHT,
    HandleType.MIDDLE_LEFT, HandleType.MIDDLE_RIGHT,
    HandleType.BOTTOM_LEFT, HandleType.BOTTOM_CENTER, HandleType.BOTTOM_RIGHT,
}


class ItemInteraction:
    """Click-drag to move an item, drag the rotation handle to spin it, or
    drag a corner/edge handle to resize it (font-size scaling for text
    objects; uniform transform scaling for anything else)."""

    def __init__(
        self,
        viewport: Viewport,
        selection_engine: SelectionEngine,
        transform_engine: TransformEngine | None,
        history_engine: HistoryEngine | None = None,
    ):
        self.viewport = viewport
        self.selection = selection_engine
        self.transform = transform_engine
        self.history = history_engine

        self.dragging = False
        self.rotating = False
        self.resizing = False

        self._drag_items: list = []
        self._drag_start: QPointF | None = None
        self._drag_last: QPointF | None = None

        self._rotate_center: QPointF | None = None
        self._rotate_start_angle = 0.0
        self._rotate_initial: dict = {}

        self._resize_handle: HandleType | None = None
        self._resize_anchor: QPointF | None = None
        self._resize_items: list = []
        self._resize_start_dist = 1.0
        self._resize_last_factor = 1.0
        self._resize_initial: dict = {}

    @property
    def active(self) -> bool:
        return self.dragging or self.rotating or self.resizing

    def try_begin(self, scene_pos: QPointF, add: bool = False) -> bool:
        """Start a drag, rotate, or resize at scene_pos if applicable.
        Returns True if something was started — callers should not fall
        through to their own default press handling (e.g. placing a new
        object) when this returns True."""
        if self.transform is None:
            return False

        selected = self.viewport.scene().selectedItems()
        if selected:
            handle = self.transform.handle_at(scene_pos)
            if handle == HandleType.DELETE_ACTION:
                self._delete_selected(selected)
                return True
            if handle == HandleType.DUPLICATE_ACTION:
                self._duplicate_selected(selected)
                return True
            if handle == HandleType.ROTATION:
                self._begin_rotate(selected, scene_pos)
                return True
            if handle in RESIZE_HANDLES:
                self._begin_resize(selected, handle, scene_pos)
                return True

        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        if item and self.selection.is_selectable(item):
            if item not in selected:
                if add:
                    self.selection.toggle(item)
                else:
                    self.selection.select(item)
            self._begin_drag(self.viewport.scene().selectedItems(), scene_pos)
            return True

        return False

    def move(self, scene_pos: QPointF) -> bool:
        if self.rotating:
            self._do_rotate(scene_pos)
            return True
        if self.resizing:
            self._do_resize(scene_pos)
            return True
        if self.dragging:
            self._do_drag(scene_pos)
            return True
        return False

    def release(self, scene_pos: QPointF) -> bool:
        if self.rotating:
            self._end_rotate()
            return True
        if self.resizing:
            self._end_resize()
            return True
        if self.dragging:
            self._end_drag(scene_pos)
            return True
        return False

    # --- Move ---

    def _begin_drag(self, items: list, scene_pos: QPointF):
        if not items:
            return
        self.dragging = True
        self._drag_items = items
        self._drag_start = scene_pos
        self._drag_last = scene_pos
        self.transform.begin_transform(items)

    def _do_drag(self, scene_pos: QPointF):
        if self._drag_last is None:
            return
        delta = scene_pos - self._drag_last
        self.transform.move(self._drag_items, delta.x(), delta.y())
        self.transform.show_handles(self._drag_items)
        self._drag_last = scene_pos

    def _end_drag(self, scene_pos: QPointF):
        if self.history and self._drag_start is not None:
            total_dx = scene_pos.x() - self._drag_start.x()
            total_dy = scene_pos.y() - self._drag_start.y()
            if abs(total_dx) > 0.1 or abs(total_dy) > 0.1:
                from src.engines.core.history import MoveItemsCommand
                cmd = MoveItemsCommand(self._drag_items, total_dx, total_dy)
                # Items already moved visually — record without redoing.
                self.history._undo_stack.append(cmd)
                self.history._redo_stack.clear()
                self.history._emit()

        self.transform.end_transform()
        self.dragging = False
        self._drag_items = []
        self._drag_last = None
        self._drag_start = None

    # --- Action bar (delete / duplicate) ---

    def _delete_selected(self, items: list):
        from src.engines.core.history import DeleteItemCommand, CompositeCommand

        if not items:
            return
        cmds = [DeleteItemCommand(self.viewport.scene(), item) for item in items]
        cmd = cmds[0] if len(cmds) == 1 else CompositeCommand(cmds, f"Deletar {len(cmds)} item(s)")
        if self.history:
            self.history.push(cmd)
        else:
            cmd.redo()

        self.transform.hide_handles()
        if self.selection:
            self.selection.clear()

    def _duplicate_selected(self, items: list):
        """Clone each selected TextItem (deep-copying its TextProperties,
        including any painted color patterns) a few pixels off from the
        original. Only wired for TextItem so far — other item types
        (regions, brush stamps, boundaries) have their own scene-graph
        bookkeeping outside this class and aren't safe to clone generically
        yet, so the action button is a no-op for them for now, same as the
        (also unfinished) Ctrl+D clipboard duplicate."""
        import copy
        from src.canvas.text_item import TextItem
        from src.engines.core.history import CreateItemCommand, CompositeCommand

        clones = []
        cmds = []
        for item in items:
            if not isinstance(item, TextItem):
                continue
            clone = TextItem(copy.deepcopy(item.props))
            clone.setPos(item.pos().x() + 20, item.pos().y() + 20)
            clone.setRotation(item.rotation())
            clone.setTransform(item.transform())
            clone.setZValue(item.zValue())
            cmds.append(CreateItemCommand(self.viewport.scene(), clone))
            clones.append(clone)

        if not clones:
            return

        cmd = cmds[0] if len(cmds) == 1 else CompositeCommand(cmds, f"Duplicar {len(cmds)} item(s)")
        if self.history:
            self.history.push(cmd)
        else:
            cmd.redo()

        if self.selection:
            for i, it in enumerate(clones):
                self.selection.select(it, add=(i > 0))
        self.transform.show_handles(clones)

    # --- Rotate ---

    def _begin_rotate(self, items: list, scene_pos: QPointF):
        self.rotating = True
        self._rotate_center = self.transform._get_bounds(items).center()
        self._rotate_start_angle = self._angle(self._rotate_center, scene_pos)
        self._rotate_initial = {item: (QPointF(item.pos()), item.rotation()) for item in items}
        self.transform.begin_transform(items)

    def _do_rotate(self, scene_pos: QPointF):
        if self._rotate_center is None:
            return
        angle_now = self._angle(self._rotate_center, scene_pos)
        delta = angle_now - self._rotate_start_angle
        self._rotate_start_angle = angle_now
        items = list(self._rotate_initial.keys())
        self.transform.rotate(items, delta, self._rotate_center)
        self.transform.show_handles(items)

    def _end_rotate(self):
        if self.history and self._rotate_initial:
            from src.engines.core.history import TransformItemCommand, CompositeCommand
            cmds = []
            for item, (old_pos, old_rot) in self._rotate_initial.items():
                moved = (item.pos() - old_pos).manhattanLength() > 0.05
                rotated = abs(item.rotation() - old_rot) > 0.05
                if moved or rotated:
                    cmds.append(TransformItemCommand(
                        item, old_pos, QPointF(item.pos()),
                        item.transform(), item.transform(),
                        old_rot, item.rotation(),
                    ))
            if cmds:
                cmd = cmds[0] if len(cmds) == 1 else CompositeCommand(cmds, f"Girar {len(cmds)} item(s)")
                self.history._undo_stack.append(cmd)
                self.history._redo_stack.clear()
                self.history._emit()

        self.transform.end_transform()
        self.rotating = False
        self._rotate_center = None
        self._rotate_initial = {}

    # --- Resize ---

    def _begin_resize(self, items: list, handle: HandleType, scene_pos: QPointF):
        bounds = self.transform._get_bounds(items)
        anchors = {
            HandleType.TOP_LEFT: bounds.bottomRight(),
            HandleType.TOP_RIGHT: bounds.bottomLeft(),
            HandleType.BOTTOM_LEFT: bounds.topRight(),
            HandleType.BOTTOM_RIGHT: bounds.topLeft(),
            HandleType.TOP_CENTER: QPointF(bounds.center().x(), bounds.bottom()),
            HandleType.BOTTOM_CENTER: QPointF(bounds.center().x(), bounds.top()),
            HandleType.MIDDLE_LEFT: QPointF(bounds.right(), bounds.center().y()),
            HandleType.MIDDLE_RIGHT: QPointF(bounds.left(), bounds.center().y()),
        }
        self.resizing = True
        self._resize_handle = handle
        self._resize_anchor = anchors[handle]
        self._resize_items = items
        self._resize_start_dist = max(1.0, self._dist(self._resize_anchor, scene_pos))
        self._resize_last_factor = 1.0
        self._resize_initial = {item: getattr(getattr(item, "props", None), "font_size", None) for item in items}
        self.transform.begin_transform(items)

    def _do_resize(self, scene_pos: QPointF):
        if self._resize_anchor is None:
            return
        total_factor = max(0.1, self._dist(self._resize_anchor, scene_pos) / self._resize_start_dist)
        step_factor = total_factor / self._resize_last_factor
        self._resize_last_factor = total_factor

        # Corner handles scale proportionally (both axes); edge midpoints
        # stretch a single axis only — matching how a professional editor
        # differentiates the two instead of every handle behaving the same.
        if self._resize_handle in HORIZONTAL_HANDLES:
            sx, sy = step_factor, 1.0
        elif self._resize_handle in VERTICAL_HANDLES:
            sx, sy = 1.0, step_factor
        else:
            sx, sy = step_factor, step_factor

        for item in self._resize_items:
            props = getattr(item, "props", None)
            if props is not None and hasattr(props, "font_size") and sx == sy:
                # Proportional (corner) drag on text: scale the font size for
                # a crisp re-render instead of stretching the glyph shapes.
                props.font_size = max(4.0, props.font_size * sx)
                item.prepareGeometryChange()
                item.update()
            else:
                self.transform.scale([item], sx, sy, self._resize_anchor)
        self.transform.show_handles(self._resize_items)

    def _end_resize(self):
        self.transform.end_transform()
        self.resizing = False
        self._resize_anchor = None
        self._resize_items = []
        self._resize_initial = {}

    @staticmethod
    def _angle(center: QPointF, pos: QPointF) -> float:
        return math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return math.hypot(b.x() - a.x(), b.y() - a.y())
