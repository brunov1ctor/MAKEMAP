"""PathTool — river and road tracing tools with bezier point editing.

Workflow:
  - Left-click on canvas       → add point (straight segment)
  - Left-click + drag on canvas → add point and drag to set bezier handles
  - Left-drag on a point handle → move existing point
  - Left-drag on a bezier handle → adjust existing curve handle
  - Right-click on point       → remove point
  - Double-click               → finalize path
  - ESC                        → finalize (or discard, if too short) and
                                  switch back to Selecionar
  - Right-click on canvas      → finalize

After finalize the item stays on the scene as a selectable, movable object.
The tool stays active so the user can immediately start a new path — unless
finalized via ESC, which also hands off to Selecionar (see key_press).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QKeyEvent, QPixmap
from PySide6.QtWidgets import QGraphicsEllipseItem

from src.canvas.tools.base import BaseTool
from src.canvas.tools.brush_tool import _DashedCursorMixin
from src.canvas.path_item import RiverPathItem, RoadPathItem

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport


class _BasePathTool(_DashedCursorMixin, BaseTool):
    """Shared logic for RiverPathTool and RoadPathTool."""

    _ITEM_CLASS = None  # set by subclass
    _ITEM_TYPE = None  # set by subclass — "river_path" | "road_path", tags item.data(0)

    def __init__(self, viewport: Viewport, width: float = 24.0,
                 texture: QPixmap | None = None, tool_manager=None):
        super().__init__(viewport)
        self._width = width
        self._texture = texture
        self._asset_id = ""  # backing asset_id, tagged onto each new item — see set_texture
        self._active_item = None
        self._on_finalized: list[Callable] = []
        self._placing = False                        # True while dragging a new point's handles
        self._press_scene_pos: QPointF = QPointF()  # scene pos of last press
        # Dragging an EXISTING point/handle (as opposed to _placing, which
        # is for a just-added point) — CanvasEngine bypasses Qt's normal
        # scene->item event dispatch (see path_item.py's mouseMoveEvent
        # docstring), so the item never sees real mouse events itself; the
        # tool must track drag state and call item.move_point/move_handle
        # directly instead of relying on the item's own mousePressEvent/
        # mouseMoveEvent (which are effectively dead code in this app).
        self._dragging_point_idx: int = -1
        self._dragging_handle: tuple[int, str] | None = None

        # Brush-size cursor circle — same dashed-circle preview BrushTool
        # shows (see BrushTool._show_cursor), sized off self._width. Rio/
        # Estrada previously had no cursor feedback at all once activated,
        # since only BrushTool wired one up.
        self._minimap = None
        self._cursor_item: QGraphicsEllipseItem | None = None
        # Only needed for ESC's finalize-then-switch-back-to-Selecionar (see
        # key_press) — same pattern MarkerTool/LightTool already use to hand
        # off to Selecionar right after placing one object.
        self._tool_manager = tool_manager

    # ─── Public API ──────────────────────────────────────────────────────

    @property
    def active_item(self):
        """The path currently being traced (still in edit mode), or None
        between traces — e.g. so BrushMediator's opacity slider can apply
        live to a mid-edit trace, same as set_width already does above."""
        return self._active_item

    def _cursor_diameter(self) -> float:
        return self._width

    def set_width(self, w: float):
        self._width = max(2.0, w)
        if self._active_item:
            self._active_item.set_width(w)
        self.update_cursor_size()

    def activate(self):
        super().activate()
        self._show_cursor()

    def set_texture(self, pixmap: QPixmap | None, asset_id: str = ""):
        self._texture = pixmap
        self._asset_id = asset_id
        if self._active_item:
            self._active_item.set_texture(pixmap)

    def on_path_finalized(self, callback: Callable):
        """Register callback(item) fired when a path is finalized."""
        self._on_finalized.append(callback)

    # ─── Mouse events ────────────────────────────────────────────────────

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.RightButton:
            if self._active_item and self._active_item.point_count() >= 2:
                self._finalize()
            elif self._active_item:
                self._cancel()
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # If pressing on an existing point/handle, drag it directly — the
        # item's own mousePressEvent/mouseMoveEvent never fire (see
        # _dragging_point_idx's comment in __init__), so this tool has to
        # track the drag itself instead of just handing off to the item.
        if self._active_item and self._active_item._editing:
            item_pos = self._active_item.mapFromScene(scene_pos)
            handle = self._active_item._handle_at(item_pos)
            if handle is not None:
                self._dragging_handle = handle
                self._placing = False
                event.accept()
                return
            idx = self._active_item._point_at(item_pos)
            if idx >= 0:
                self._dragging_point_idx = idx
                self._placing = False
                event.accept()
                return

        # Add a new point — drag will set its handles
        if self._active_item is None or not self._active_item._editing:
            self._start_new(scene_pos)
        else:
            item_pos = self._active_item.mapFromScene(scene_pos)
            self._active_item.add_point(item_pos)
        self._placing = True
        self._press_scene_pos = scene_pos

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._cursor_item:
            r = self._width / 2
            self._cursor_item.setRect(scene_pos.x() - r, scene_pos.y() - r, self._width, self._width)

        if self._active_item is None:
            return
        if self._dragging_handle is not None:
            idx, key = self._dragging_handle
            item_pos = self._active_item.mapFromScene(scene_pos)
            self._active_item.move_handle(idx, key, item_pos)
            return
        if self._dragging_point_idx >= 0:
            item_pos = self._active_item.mapFromScene(scene_pos)
            self._active_item.move_point(self._dragging_point_idx, item_pos)
            return
        if not self._placing:
            return
        # Only start pulling handles after a minimum drag distance
        dx = scene_pos.x() - self._press_scene_pos.x()
        dy = scene_pos.y() - self._press_scene_pos.y()
        if (dx * dx + dy * dy) < 16:  # 4px threshold
            return
        item_pos = self._active_item.mapFromScene(scene_pos)
        self._active_item.drag_last_point_handles(item_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._placing and self._active_item:
                self._active_item.release_drag_lock()
            self._placing = False
            self._dragging_point_idx = -1
            self._dragging_handle = None

    # scene units — how close a double-click must land to the last placed
    # point to read as "finish here" (see mouse_double_click).
    _DOUBLE_CLICK_FINALIZE_RADIUS = 20.0

    def mouse_double_click(self, event: QMouseEvent, scene_pos: QPointF):
        """Qt turns the SECOND of two clicks landing close together in time
        into a mouseDoubleClickEvent instead of an ordinary mousePressEvent
        — tracing a winding river/road with several quick clicks can easily
        produce two clicks that are close in TIME but land at two different
        points along the path, and Qt's own double-click window doesn't
        care which. Treating every double-click as "finalize" used to
        silently end the path early on one of those, then start a brand
        new, disconnected one on the next click — a river traced quickly
        would come out chopped into several unconnected pieces with dead
        (undraggable, since the tool had already moved on to the next
        _active_item) handles left behind on the earlier ones. Only
        finalize when the double-click actually landed near the last
        point (a genuine "click twice in place to finish" gesture);
        otherwise treat it as an ordinary next point, same as a second
        single click would have been."""
        if self._active_item:
            if self._active_item.point_count() >= 2:
                last_scene = self._active_item.mapToScene(self._active_item._points[-1])
                dx = scene_pos.x() - last_scene.x()
                dy = scene_pos.y() - last_scene.y()
                if dx * dx + dy * dy <= self._DOUBLE_CLICK_FINALIZE_RADIUS ** 2:
                    self._finalize()
                    event.accept()
                    return
            item_pos = self._active_item.mapFromScene(scene_pos)
            self._active_item.add_point(item_pos)
        event.accept()

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self._active_item and self._active_item._editing:
                if self._active_item.point_count() >= 2:
                    self._finalize()
                else:
                    self._cancel()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._active_item and self._active_item.point_count() >= 2:
                self._finalize()
            event.accept()

    def deactivate(self):
        # Finalize any in-progress path when switching tools
        if self._active_item and self._active_item._editing:
            if self._active_item.point_count() >= 2:
                self._finalize()
            else:
                self._cancel()
        self._hide_cursor()
        super().deactivate()

    # ─── Internal ────────────────────────────────────────────────────────

    def _start_new(self, scene_pos: QPointF):
        item = self._ITEM_CLASS(
            width=self._width,
            texture=self._texture,
        )
        item.setData(0, {"item_type": self._ITEM_TYPE, "asset_id": self._asset_id})
        self.viewport.scene().addItem(item)
        # Item lives in scene coords — first point at scene_pos
        item.add_point(scene_pos)
        self._active_item = item

    def _finalize(self):
        if not self._active_item:
            return
        self._active_item.finalize()
        for cb in self._on_finalized:
            cb(self._active_item)
        self._active_item = None

    def _cancel(self):
        if self._active_item:
            scene = self._active_item.scene()
            if scene:
                scene.removeItem(self._active_item)
            self._active_item = None


class RiverPathTool(_BasePathTool):
    """Tool for tracing rivers with animated water effect."""

    name = "Rio"
    shortcut = "W"
    _ITEM_CLASS = RiverPathItem
    _ITEM_TYPE = "river_path"

    def __init__(self, viewport: Viewport, width: float = 30.0,
                 texture: QPixmap | None = None, tool_manager=None):
        super().__init__(viewport, width, texture, tool_manager)


class RoadPathTool(_BasePathTool):
    """Tool for tracing roads with animated dust effect."""

    name = "Estrada"
    shortcut = "P"
    _ITEM_CLASS = RoadPathItem
    _ITEM_TYPE = "road_path"

    def __init__(self, viewport: Viewport, width: float = 20.0,
                 texture: QPixmap | None = None, tool_manager=None):
        super().__init__(viewport, width, texture, tool_manager)
