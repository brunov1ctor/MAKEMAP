"""Default canvas tools — Select, Move, Pan."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QMouseEvent, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsPathItem

from src.canvas.tools.base import BaseTool

if TYPE_CHECKING:
    from src.engines.core.selection import SelectionEngine
    from src.engines.core.transform import TransformEngine
    from src.engines.core.history import HistoryEngine
    from src.canvas.viewport import Viewport


class SelectTool(BaseTool):
    """Selection tool with box and lasso modes."""

    name = "Selecionar"
    shortcut = "V"
    cursor = Qt.CursorShape.ArrowCursor

    def __init__(self, viewport: Viewport, selection_engine: SelectionEngine):
        super().__init__(viewport)
        self._selection = selection_engine
        self._rubber_band: QGraphicsRectItem | None = None
        self._lasso_path: QGraphicsPathItem | None = None
        self._lasso_points: list[QPointF] = []
        self._start: QPointF | None = None
        self._lasso_mode = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        self._start = scene_pos
        self._lasso_mode = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        if self._lasso_mode:
            # Start lasso
            self._lasso_points = [scene_pos]
            self._lasso_path = QGraphicsPathItem()
            self._lasso_path.setPen(QPen(QColor(79, 195, 247, 180), 1.5, Qt.PenStyle.DashLine))
            self._lasso_path.setBrush(QColor(79, 195, 247, 20))
            self._lasso_path.setZValue(9999)
            self.viewport.scene().addItem(self._lasso_path)
        else:
            # Start rubber band
            self._rubber_band = QGraphicsRectItem()
            self._rubber_band.setPen(QPen(QColor(79, 195, 247, 180), 1))
            self._rubber_band.setBrush(QColor(79, 195, 247, 30))
            self._rubber_band.setZValue(9999)
            self.viewport.scene().addItem(self._rubber_band)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._lasso_mode and self._lasso_path:
            self._lasso_points.append(scene_pos)
            path = QPainterPath()
            path.moveTo(self._lasso_points[0])
            for pt in self._lasso_points[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            self._lasso_path.setPath(path)
        elif self._rubber_band and self._start:
            rect = QRectF(self._start, scene_pos).normalized()
            self._rubber_band.setRect(rect)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self._lasso_mode and self._lasso_path:
            # Lasso selection
            if len(self._lasso_points) > 2:
                from PySide6.QtGui import QPolygonF
                polygon = QPolygonF(self._lasso_points)
                self._selection.select_by_polygon(polygon, add=add)
            self.viewport.scene().removeItem(self._lasso_path)
            self._lasso_path = None
            self._lasso_points.clear()
            self._lasso_mode = False

        elif self._rubber_band:
            rect = self._rubber_band.rect()
            self.viewport.scene().removeItem(self._rubber_band)
            self._rubber_band = None

            if rect.width() > 3 or rect.height() > 3:
                # Box selection
                self._selection.select_by_rect(rect, add=add)
            else:
                # Click selection
                item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
                if item and (item.flags() & item.GraphicsItemFlag.ItemIsSelectable):
                    if add:
                        self._selection.toggle(item)
                    else:
                        self._selection.select(item)
                else:
                    if not add:
                        self._selection.clear()

            self._start = None

    def key_press(self, event):
        # Escape to deselect
        if event.key() == Qt.Key.Key_Escape:
            self._selection.clear()
        # Ctrl+A to select all
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._selection.select_all()
        # Ctrl+I to invert
        elif event.key() == Qt.Key.Key_I and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._selection.invert()


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
            self._transform.show_handles(selected)
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
    """Pan the viewport by dragging."""

    name = "Pan"
    shortcut = "H"
    cursor = Qt.CursorShape.OpenHandCursor

    def __init__(self, viewport):
        super().__init__(viewport)
        self._panning = False
        self._start = QPointF()

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._start = event.position()
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
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
        if self._panning:
            self._panning = False
            self.viewport.setCursor(Qt.CursorShape.OpenHandCursor)
