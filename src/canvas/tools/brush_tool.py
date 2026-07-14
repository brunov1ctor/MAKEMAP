"""Canvas tools — Brush (terrain paint), Region, Road, River."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QMouseEvent, QPen, QColor, QBrush, QPainterPath, QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPolygonItem,
)

from src.canvas.tools.base import BaseTool

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.map.brush import BrushEngine
    from src.engines.core.history import HistoryEngine


# ─── Brush Tool (delegates to BrushEngine) ────────────────────────────────

class BrushTool(BaseTool):
    """Brush — pinta terreno usando o BrushEngine para lógica de stroke."""

    name = "Brush"
    shortcut = "B"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport, brush_engine: BrushEngine, history_engine: HistoryEngine = None):
        super().__init__(viewport)
        self._engine = brush_engine
        self._history = history_engine
        self._cursor_item: QGraphicsEllipseItem | None = None
        self._stroke_items: list[QGraphicsEllipseItem] = []

        # Visual defaults (engine controla tamanho/spacing, aqui só cor visual)
        self.color = QColor(34, 139, 34, 160)

    @property
    def size(self) -> float:
        return self._engine.config.size

    def activate(self):
        super().activate()
        self._show_cursor()

    def deactivate(self):
        super().deactivate()
        self._hide_cursor()

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._stroke_items.clear()
            self._engine.stamp_placed.connect(self._on_stamp)
            self._engine.begin_stroke(scene_pos)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        # Update cursor preview
        if self._cursor_item:
            r = self.size / 2
            self._cursor_item.setRect(scene_pos.x() - r, scene_pos.y() - r, self.size, self.size)

        if self._engine.is_active:
            self._engine.continue_stroke(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton and self._engine.is_active:
            self._engine.end_stroke()
            try:
                self._engine.stamp_placed.disconnect(self._on_stamp)
            except RuntimeError:
                pass

    def _on_stamp(self, stamp):
        """Renderiza um stamp do engine na scene."""
        pos = stamp.position
        r = self.size / 2
        item = QGraphicsEllipseItem(pos.x() - r, pos.y() - r, self.size, self.size)
        item.setPen(QPen(Qt.PenStyle.NoPen))

        grad = QRadialGradient(pos, r)
        grad.setColorAt(0.0, self.color)
        grad.setColorAt(0.7, QColor(self.color.red(), self.color.green(), self.color.blue(), int(self.color.alpha() * 0.5)))
        grad.setColorAt(1.0, QColor(self.color.red(), self.color.green(), self.color.blue(), 0))
        item.setBrush(QBrush(grad))
        item.setZValue(10)

        self.viewport.scene().addItem(item)
        self._stroke_items.append(item)

    def _show_cursor(self):
        if self._cursor_item:
            return
        r = self.size / 2
        self._cursor_item = QGraphicsEllipseItem(-r, -r, self.size, self.size)
        self._cursor_item.setPen(QPen(QColor(255, 255, 255, 150), 1.5, Qt.PenStyle.DashLine))
        self._cursor_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._cursor_item.setZValue(10000)
        self.viewport.scene().addItem(self._cursor_item)

    def _hide_cursor(self):
        if self._cursor_item:
            self.viewport.scene().removeItem(self._cursor_item)
            self._cursor_item = None


# ─── Region Tool ───────────────────────────────────────────────────────────

class RegionTool(BaseTool):
    """Região — desenha polígono fechado ao clicar pontos."""

    name = "Região"
    shortcut = "R"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(79, 195, 247, 60)
        self._border_color = QColor(79, 195, 247, 200)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 3:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for pt in self._points[1:]:
                path.lineTo(pt)
            if cursor_pos:
                path.lineTo(cursor_pos)
            path.closeSubpath()

        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._border_color, 2, Qt.PenStyle.DashLine))
        self._preview.setBrush(QBrush(self._color))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        polygon = QPolygonF(self._points)
        item = QGraphicsPolygonItem(polygon)
        item.setPen(QPen(self._border_color, 2))
        item.setBrush(QBrush(self._color))
        item.setZValue(5)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        self.viewport.scene().addItem(item)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()


# ─── Road Tool ─────────────────────────────────────────────────────────────

class RoadTool(BaseTool):
    """Estrada — desenha path com pontos clicados."""

    name = "Estrada"
    shortcut = "P"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(139, 119, 80, 220)
        self._width = 8.0

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 2:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for pt in self._points[1:]:
                path.lineTo(pt)
            if cursor_pos:
                path.lineTo(cursor_pos)

        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._color, self._width, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        path = QPainterPath()
        path.moveTo(self._points[0])
        for pt in self._points[1:]:
            path.lineTo(pt)

        item = QGraphicsPathItem(path)
        item.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        item.setZValue(8)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        self.viewport.scene().addItem(item)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()


# ─── River Tool ────────────────────────────────────────────────────────────

class RiverTool(BaseTool):
    """Rio — desenha curva suave com pontos clicados."""

    name = "Rio"
    shortcut = "W"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(30, 144, 255, 180)
        self._width = 6.0

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 2:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _build_smooth_path(self, points: list[QPointF]) -> QPainterPath:
        path = QPainterPath()
        if len(points) < 2:
            if points:
                path.moveTo(points[0])
            return path

        path.moveTo(points[0])
        if len(points) == 2:
            path.lineTo(points[1])
            return path

        for i in range(len(points) - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[min(len(points) - 1, i + 1)]
            p3 = points[min(len(points) - 1, i + 2)]

            cp1 = QPointF(
                p1.x() + (p2.x() - p0.x()) / 6,
                p1.y() + (p2.y() - p0.y()) / 6,
            )
            cp2 = QPointF(
                p2.x() - (p3.x() - p1.x()) / 6,
                p2.y() - (p3.y() - p1.y()) / 6,
            )
            path.cubicTo(cp1, cp2, p2)

        return path

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        pts = list(self._points)
        if cursor_pos:
            pts.append(cursor_pos)

        path = self._build_smooth_path(pts)
        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._color, self._width, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        path = self._build_smooth_path(self._points)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        item.setZValue(7)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        self.viewport.scene().addItem(item)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()
