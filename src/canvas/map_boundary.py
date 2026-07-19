"""MapBoundary — pulsing border overlay for finite map limits, movable by edge drag."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QTimer, QPointF, QLineF
from PySide6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import (
    QGraphicsPathItem, QGraphicsScene, QGraphicsItem,
    QGraphicsSceneMouseEvent, QGraphicsLineItem,
)


# ─── Alignment Guides ────────────────────────────────────────────────────────

class AlignmentGuides:
    """Shows snap alignment lines when boundaries align with each other."""

    SNAP_THRESHOLD = 12.0
    GUIDE_COLOR = QColor(255, 200, 50, 180)
    GUIDE_WIDTH = 1.5
    EXTENT = 50000

    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._lines: list[QGraphicsLineItem] = []

    def update(self, moving_item: "MovableBoundaryItem", all_items: list["MovableBoundaryItem"]) -> QPointF:
        """Calculate guides and return snap offset."""
        self.clear()
        if not moving_item:
            return QPointF(0, 0)

        moving_rect = moving_item.mapToScene(moving_item.boundingRect()).boundingRect()
        snap_dx = 0.0
        snap_dy = 0.0

        m_cx = moving_rect.center().x()
        m_cy = moving_rect.center().y()
        m_left = moving_rect.left()
        m_right = moving_rect.right()
        m_top = moving_rect.top()
        m_bottom = moving_rect.bottom()

        for other in all_items:
            if other is moving_item or not other.isVisible():
                continue
            r = other.mapToScene(other.boundingRect()).boundingRect()
            o_cx, o_cy = r.center().x(), r.center().y()
            o_left, o_right = r.left(), r.right()
            o_top, o_bottom = r.top(), r.bottom()

            # Vertical alignment (X axis)
            for m_x, o_x in [(m_cx, o_cx), (m_left, o_left), (m_right, o_right),
                             (m_left, o_right), (m_right, o_left)]:
                if abs(m_x - o_x) < self.SNAP_THRESHOLD:
                    if snap_dx == 0.0:
                        snap_dx = o_x - m_x
                    self._add_vline(o_x)

            # Horizontal alignment (Y axis)
            for m_y, o_y in [(m_cy, o_cy), (m_top, o_top), (m_bottom, o_bottom),
                             (m_top, o_bottom), (m_bottom, o_top)]:
                if abs(m_y - o_y) < self.SNAP_THRESHOLD:
                    if snap_dy == 0.0:
                        snap_dy = o_y - m_y
                    self._add_hline(o_y)

        return QPointF(snap_dx, snap_dy)

    def clear(self):
        for line in self._lines:
            if line.scene():
                self._scene.removeItem(line)
        self._lines.clear()

    def _add_vline(self, x: float):
        line = QGraphicsLineItem(QLineF(x, -self.EXTENT, x, self.EXTENT))
        pen = QPen(self.GUIDE_COLOR, self.GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(9999)
        self._scene.addItem(line)
        self._lines.append(line)

    def _add_hline(self, y: float):
        line = QGraphicsLineItem(QLineF(-self.EXTENT, y, self.EXTENT, y))
        pen = QPen(self.GUIDE_COLOR, self.GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(9999)
        self._scene.addItem(line)
        self._lines.append(line)


# ─── Movable Boundary Item ───────────────────────────────────────────────────

class MovableBoundaryItem(QGraphicsPathItem):
    """Path item that can be moved by dragging its border stroke area."""

    HIT_WIDTH = 20.0

    def __init__(self, path: QPainterPath, parent=None):
        super().__init__(path, parent)
        self._dragging = False
        self._hovered = False
        self._drag_start_scene = QPointF()
        self._drag_start_pos = QPointF()
        self._guides: AlignmentGuides | None = None
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def _hit_border(self, pos: QPointF) -> bool:
        """Check if pos is near the border stroke."""
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        stroke_area = stroker.createStroke(self.path())
        return stroke_area.contains(pos)

    def hoverEnterEvent(self, event):
        if self._hit_border(event.pos()):
            self._set_hovered(True)
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        on_border = self._hit_border(event.pos())
        if on_border:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            if not self._hovered:
                self._set_hovered(True)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._hovered:
                self._set_hovered(False)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_hovered(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def _set_hovered(self, hovered: bool):
        self._hovered = hovered
        pen = self.pen()
        if hovered:
            pen.setWidthF(5.0)
            pen.setStyle(Qt.PenStyle.SolidLine)
            color = pen.color()
            color.setAlpha(255)
            pen.setColor(color)
        else:
            pen.setWidthF(3.0)
            pen.setStyle(Qt.PenStyle.DashDotLine)
        self.setPen(pen)
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._hit_border(event.pos()):
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_pos = self.pos()
            if self.scene():
                self._guides = AlignmentGuides(self.scene())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            new_pos = self._drag_start_pos + delta
            self.setPos(new_pos)
            # Snap to alignment guides
            if self._guides and self.scene():
                others = [item for item in self.scene().items()
                          if isinstance(item, MovableBoundaryItem) and item is not self]
                snap_offset = self._guides.update(self, others)
                if snap_offset.x() != 0 or snap_offset.y() != 0:
                    self.setPos(new_pos + snap_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            self._dragging = False
            if self._guides:
                self._guides.clear()
                self._guides = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# ─── Map Boundary ────────────────────────────────────────────────────────────

class MapBoundary:
    """Draws a pulsing border on the scene to show map limits."""

    PULSE_MIN_ALPHA = 60
    PULSE_MAX_ALPHA = 200
    PULSE_INTERVAL_MS = 50
    PULSE_CYCLE_MS = 1500
    BORDER_WIDTH = 3.0
    BORDER_COLOR_BASE = QColor(79, 195, 247)

    # Keep numerically identical to TerrainSettingsPanel.DEFAULT_* —
    # not cross-imported to avoid coupling canvas/ to layouts/.
    DEFAULT_SHAPE = "rectangle"
    DEFAULT_WIDTH = 4096
    DEFAULT_HEIGHT = 4096

    def __init__(self, scene: QGraphicsScene, color: QColor = None):
        self._scene = scene
        self._item: MovableBoundaryItem | None = None
        self._visible = False
        self._shape = self.DEFAULT_SHAPE
        self._width = self.DEFAULT_WIDTH
        self._height = self.DEFAULT_HEIGHT
        self._color = color or self.BORDER_COLOR_BASE
        self._preview = False

        # Pulse animation state
        self._alpha = self.PULSE_MIN_ALPHA
        self._alpha_dir = 1
        self._timer = QTimer()
        self._timer.setInterval(self.PULSE_INTERVAL_MS)
        self._timer.timeout.connect(self._pulse_tick)

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def shape(self) -> str:
        return self._shape

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def position(self) -> QPointF:
        if self._item:
            return self._item.pos()
        return QPointF(0, 0)

    def set_position(self, pos: QPointF):
        if self._item:
            self._item.setPos(pos)

    def show(self, width: int, height: int, shape: str = "rectangle"):
        self._width = width
        self._height = height
        self._shape = shape
        self._visible = True
        self._preview = False
        self._rebuild()
        self._timer.start()

    def show_preview(self, width: int, height: int, shape: str = "rectangle"):
        """Lightweight draft outline for a terrain that hasn't been
        created yet (no terrain_id/card) — static dashed line, no pulse,
        so it visibly reads as "not real yet" rather than a confirmed
        terrain."""
        self._width = width
        self._height = height
        self._shape = shape
        self._visible = True
        self._preview = True
        self._rebuild()

    def hide(self):
        self._visible = False
        self._preview = False
        self._timer.stop()
        if self._item and self._item.scene():
            self._scene.removeItem(self._item)
            self._item = None

    def update_dimensions(self, width: int, height: int):
        self._width = width
        self._height = height
        if self._visible:
            self._rebuild()

    def update_shape(self, shape: str):
        self._shape = shape
        if self._visible:
            self._rebuild()

    def _rebuild(self):
        old_pos = QPointF(0, 0)
        if self._item and self._item.scene():
            old_pos = self._item.pos()
            self._scene.removeItem(self._item)

        path = self._build_path()
        self._item = MovableBoundaryItem(path)
        self._item.setPos(old_pos)
        self._item.setZValue(-500)
        self._item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._update_pen()
        self._scene.addItem(self._item)

    def _build_path(self) -> QPainterPath:
        path = QPainterPath()
        half_w = self._width / 2
        half_h = self._height / 2

        if self._shape == "circle":
            radius = min(half_w, half_h)
            path.addEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
        elif self._shape == "square":
            side = min(self._width, self._height)
            half_s = side / 2
            path.addRect(QRectF(-half_s, -half_s, side, side))
        elif self._shape == "hexagon":
            radius = min(half_w, half_h)
            path.moveTo(radius, 0)
            for i in range(1, 6):
                angle = math.radians(60 * i)
                path.lineTo(radius * math.cos(angle), radius * math.sin(angle))
            path.closeSubpath()
        elif self._shape == "triangle":
            r = min(half_w, half_h)
            path.moveTo(0, -r)
            path.lineTo(r * math.cos(math.radians(210)), r * math.sin(math.radians(210)))
            path.lineTo(r * math.cos(math.radians(330)), r * math.sin(math.radians(330)))
            path.closeSubpath()
        elif self._shape == "pentagon":
            radius = min(half_w, half_h)
            path.moveTo(radius * math.cos(math.radians(-90)),
                        radius * math.sin(math.radians(-90)))
            for i in range(1, 5):
                angle = math.radians(-90 + 72 * i)
                path.lineTo(radius * math.cos(angle), radius * math.sin(angle))
            path.closeSubpath()
        elif self._shape == "ellipse":
            path.addEllipse(QRectF(-half_w, -half_h, self._width, self._height))
        else:
            path.addRect(QRectF(-half_w, -half_h, self._width, self._height))

        return path

    def _update_pen(self):
        if not self._item:
            return
        if self._preview:
            color = QColor(self._color)
            color.setAlpha(140)
            pen = QPen(color, 2.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._item.setPen(pen)
            return
        color = QColor(self._color)
        color.setAlpha(int(self._alpha))
        pen = QPen(color, self.BORDER_WIDTH, Qt.PenStyle.DashDotLine)
        pen.setCosmetic(True)
        self._item.setPen(pen)

    def _pulse_tick(self):
        step = ((self.PULSE_MAX_ALPHA - self.PULSE_MIN_ALPHA) /
                (self.PULSE_CYCLE_MS / self.PULSE_INTERVAL_MS / 2))
        self._alpha += step * self._alpha_dir

        if self._alpha >= self.PULSE_MAX_ALPHA:
            self._alpha = self.PULSE_MAX_ALPHA
            self._alpha_dir = -1
        elif self._alpha <= self.PULSE_MIN_ALPHA:
            self._alpha = self.PULSE_MIN_ALPHA
            self._alpha_dir = 1

        self._update_pen()
