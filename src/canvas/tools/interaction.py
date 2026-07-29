"""Shared drag-to-move / handle-to-rotate / handle-to-resize interaction —
usable by any tool that lets the user directly manipulate objects on the
canvas (Selecionar, Texto, ...) instead of duplicating the same mouse
tracking in every tool that wants it."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF

from src.canvas.light_item import LightItem
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

    def try_begin(self, scene_pos: QPointF, add: bool = False, item_filter=None) -> bool:
        """Start a drag, rotate, or resize at scene_pos if applicable.
        Returns True if something was started — callers should not fall
        through to their own default press handling (e.g. placing a new
        object) when this returns True.

        `item_filter(item) -> bool`, if given, gates ONLY the "click an
        existing item to select+drag it" fallback below — a placement tool
        (Spawn, Texto) passes one that only accepts its own item type, so
        clicking on top of an unrelated selectable layer (a painted região,
        terrain, another asset stamp...) still places a new object instead
        of hijacking the click into selecting/dragging that other layer.
        Handle hits (resize/rotate/delete on an already-selected item) are
        unaffected — those are independent of what's directly under the
        cursor."""
        if self.try_begin_handle(scene_pos):
            return True

        item = self.hit_selectable(scene_pos, item_filter)
        if item is not None:
            self.select_and_begin_drag(item, scene_pos, add)
            return True

        if not add and self.pos_in_selection_bounds(scene_pos):
            self.begin_selection_drag(scene_pos)
            return True

        return False

    def try_begin_handle(self, scene_pos: QPointF) -> bool:
        """Delete/duplicate/rotate/resize handles on an already-selected
        item — a small, precise, deliberate target, so this always commits
        immediately (no drag-threshold deferral, unlike hit_selectable)."""
        if self.transform is None:
            return False

        selected = self.viewport.scene().selectedItems()
        if not selected:
            return False

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

        return False

    def hit_selectable(self, scene_pos: QPointF, item_filter=None):
        """Pure test — the selectable item directly under scene_pos (honoring
        the layer filter and item_filter), or None. Does not select or start
        a drag; callers that want to defer the select/drag decision (e.g.
        PanTool, to disambiguate a click from the start of a pan drag) test
        with this first and commit later via select_and_begin_drag."""
        if self.transform is None:
            return None
        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        if item and self.selection.is_selectable(item) and (item_filter is None or item_filter(item)):
            return item
        return None

    def select_and_begin_drag(self, item, scene_pos: QPointF, add: bool = False):
        """Commit a hit_selectable() result: select `item` (unless already
        selected) and start dragging it from scene_pos."""
        selected = self.viewport.scene().selectedItems()
        if item not in selected:
            if add:
                self.selection.toggle(item)
            else:
                self.selection.select(item)
        self._begin_drag(self.viewport.scene().selectedItems(), scene_pos)

    def pos_in_selection_bounds(self, scene_pos: QPointF) -> bool:
        """Whether scene_pos falls inside one of the selected items' own
        (tight, rotation-aware) bounds — used as a fallback so clicking
        inside the selection still grabs/drags it even when itemAt() misses
        (a hollow shape like a zone outline with no fill, a gap between
        several selected items, ...), matching how a design app treats
        "anywhere in the marquee" as a hit on the selection, not empty
        canvas.

        Tested per-item in each item's own local coordinates (not the
        union's axis-aligned scene bounding box) — a rotated item's
        sceneBoundingRect() is its axis-aligned envelope, which is
        noticeably bigger than the rotated shape itself, so the union rect
        would keep "grabbing" the selection (instead of deselecting) for
        clicks that are visibly outside the rotated object but still inside
        that envelope's empty corners."""
        if self.transform is None:
            return False
        selected = self.viewport.scene().selectedItems()
        for item in selected:
            rect_fn = getattr(item, "selection_bounding_rect", None)
            local_rect = rect_fn() if rect_fn else item.boundingRect()
            if local_rect.contains(item.mapFromScene(scene_pos)):
                return True
        return False

    def begin_selection_drag(self, scene_pos: QPointF):
        """Start dragging the entire current selection from scene_pos,
        without changing what's selected — the pos_in_selection_bounds()
        fallback path."""
        self._begin_drag(self.viewport.scene().selectedItems(), scene_pos)

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
        self.transform.reposition_handles(self._drag_items)
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

        # A light has no visible graphic of its own to spin — its cone's
        # actual aim is props.direction_deg, read directly by
        # GlobalLightingOverlay (never by the item's own QGraphicsItem
        # transform). Rotating it the generic way (transform.rotate(),
        # which calls item.setRotation()) only spun the invisible item
        # transform — the on-canvas dashed gizmo (drawn in the item's own,
        # now-rotated, local space) visibly followed the drag, but the
        # REAL glow rendered elsewhere never moved, reading as "rotation
        # doesn't do anything." Same fix pattern as _do_resize's own
        # LightItem special-case for radius below.
        lights = [it for it in items if isinstance(it, LightItem)]
        others = [it for it in items if it not in lights]
        for light in lights:
            light.props.direction_deg = (light.props.direction_deg + delta) % 360
            light.prepareGeometryChange()
            light.update()
        if others:
            self.transform.rotate(others, delta, self._rotate_center)
        self.transform.reposition_handles(items)

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
            if isinstance(item, LightItem):
                # A light has no visible size of its own to stretch — its
                # radius IS its size (GlobalLightingOverlay reads
                # props.radius, not the item's QTransform), and a circle has
                # no "horizontal" or "vertical" axis, so every handle (edge
                # or corner) scales it uniformly by step_factor instead of
                # applying a generic (possibly non-uniform) transform scale,
                # or the glow would just sit there unchanged.
                item.props.radius = max(4.0, item.props.radius * step_factor)
                item.prepareGeometryChange()
                item.update()
            elif props is not None and hasattr(props, "font_size") and sx == sy:
                # Proportional (corner) drag on text: scale the font size for
                # a crisp re-render instead of stretching the glyph shapes.
                props.font_size = max(4.0, props.font_size * sx)
                item.prepareGeometryChange()
                item.update()
            else:
                self.transform.scale([item], sx, sy, self._resize_anchor)
        self.transform.reposition_handles(self._resize_items)

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
