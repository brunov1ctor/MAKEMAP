"""Grid Manager — configurable grid overlay with multiple cell shapes."""

from __future__ import annotations

import math

from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem
from PySide6.QtCore import QRectF, QLineF, QPointF
from PySide6.QtGui import QPen, QColor, QPainterPath


class GridShape:
    SQUARE = "Quadrado"
    HEXAGON = "Hex\u00e1gono"
    TRIANGLE = "Tri\u00e2ngulo"
    DIAMOND = "Losango"
    ISOMETRIC = "Isom\u00e9trico"


class GridManager:
    """Draws and manages a configurable grid on the scene."""

    def __init__(self, scene):
        self._scene = scene
        self._group: QGraphicsItemGroup | None = None

        # Config
        self.cell_size = 64
        self.subdivisions = 4
        self.shape = GridShape.SQUARE
        self.color_major = QColor(255, 255, 255, 25)
        self.color_minor = QColor(255, 255, 255, 10)
        self.visible = True

    def set_visible(self, visible: bool):
        self.visible = visible
        if self._group:
            self._group.setVisible(visible)

    def toggle(self):
        self.set_visible(not self.visible)

    def update(self, view_rect: QRectF):
        """Redraw grid for the visible area."""
        self._clear()
        if not self.visible:
            return

        self._group = QGraphicsItemGroup()
        self._group.setZValue(-1000)

        if self.shape == GridShape.SQUARE:
            self._draw_square(view_rect)
        elif self.shape == GridShape.HEXAGON:
            self._draw_hexagon(view_rect)
        elif self.shape == GridShape.TRIANGLE:
            self._draw_triangle(view_rect)
        elif self.shape == GridShape.DIAMOND:
            self._draw_diamond(view_rect)
        elif self.shape == GridShape.ISOMETRIC:
            self._draw_isometric(view_rect)

        self._scene.addItem(self._group)

    # ─── Square ──────────────────────────────────────────────────────────

    def _draw_square(self, view_rect: QRectF):
        pen_major = QPen(self.color_major, 1)
        pen_major.setCosmetic(True)
        pen_minor = QPen(self.color_minor, 1)
        pen_minor.setCosmetic(True)

        sub_size = self.cell_size / self.subdivisions
        left = int(view_rect.left() / sub_size) * sub_size
        top = int(view_rect.top() / sub_size) * sub_size

        x = left
        while x <= view_rect.right():
            is_major = abs(x % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(x, view_rect.top(), x, view_rect.bottom()))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            x += sub_size

        y = top
        while y <= view_rect.bottom():
            is_major = abs(y % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(view_rect.left(), y, view_rect.right(), y))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            y += sub_size

    # ─── Hexagon ─────────────────────────────────────────────────────────

    def _draw_hexagon(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        h = s * math.sqrt(3) / 2
        col_w = s * 1.5
        row_h = h * 2

        col_start = int(view_rect.left() / col_w) - 1
        col_end = int(view_rect.right() / col_w) + 2
        row_start = int(view_rect.top() / row_h) - 1
        row_end = int(view_rect.bottom() / row_h) + 2

        for col in range(col_start, col_end):
            for row in range(row_start, row_end):
                cx = col * col_w
                cy = row * row_h + (h if col % 2 else 0)
                path = self._hex_path(cx, cy, s)
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    def _hex_path(self, cx: float, cy: float, size: float) -> QPainterPath:
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            px = cx + size * math.cos(angle)
            py = cy + size * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path

    # ─── Triangle ────────────────────────────────────────────────────────

    def _draw_triangle(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        h = s * math.sqrt(3) / 2

        col_start = int(view_rect.left() / (s / 2)) - 1
        col_end = int(view_rect.right() / (s / 2)) + 2
        row_start = int(view_rect.top() / h) - 1
        row_end = int(view_rect.bottom() / h) + 2

        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                x = col * (s / 2)
                y = row * h
                up = (col + row) % 2 == 0
                path = QPainterPath()
                if up:
                    path.moveTo(x, y + h)
                    path.lineTo(x + s / 2, y)
                    path.lineTo(x + s, y + h)
                else:
                    path.moveTo(x, y)
                    path.lineTo(x + s / 2, y + h)
                    path.lineTo(x + s, y)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    # ─── Diamond ─────────────────────────────────────────────────────────

    def _draw_diamond(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        half = s / 2

        col_start = int(view_rect.left() / s) - 1
        col_end = int(view_rect.right() / s) + 2
        row_start = int(view_rect.top() / s) - 1
        row_end = int(view_rect.bottom() / s) + 2

        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                cx = col * s + (half if row % 2 else 0)
                cy = row * half
                path = QPainterPath()
                path.moveTo(cx, cy - half)
                path.lineTo(cx + half, cy)
                path.lineTo(cx, cy + half)
                path.lineTo(cx - half, cy)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    # ─── Isometric ───────────────────────────────────────────────────────

    def _draw_isometric(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        # Diagonal lines at 30° (rise = s/2 for every run = s)
        left = view_rect.left()
        right = view_rect.right()
        top = view_rect.top()
        bottom = view_rect.bottom()
        span = right - left + bottom - top

        # Lines going top-left to bottom-right (\)
        start = int((left + top) / s) * s - int(span / s) * s
        end = int((right + bottom) / s) * s + s
        offset = start
        while offset <= end:
            x1 = offset - top
            x2 = offset - bottom
            line = QGraphicsLineItem(QLineF(x1, top, x2, bottom))
            line.setPen(pen)
            self._group.addToGroup(line)
            offset += s

        # Lines going top-right to bottom-left (/)
        start = int((left - bottom) / s) * s - s
        end = int((right - top) / s) * s + int(span / s) * s
        offset = start
        while offset <= end:
            x1 = offset + top
            x2 = offset + bottom
            line = QGraphicsLineItem(QLineF(x1, top, x2, bottom))
            line.setPen(pen)
            self._group.addToGroup(line)
            offset += s

    # ─── Common ──────────────────────────────────────────────────────────

    def _clear(self):
        if self._group:
            self._scene.removeItem(self._group)
            self._group = None

    def snap(self, x: float, y: float) -> tuple[float, float]:
        """Snap coordinates to nearest grid intersection."""
        sx = round(x / self.cell_size) * self.cell_size
        sy = round(y / self.cell_size) * self.cell_size
        return sx, sy

    def snap_sub(self, x: float, y: float) -> tuple[float, float]:
        """Snap to subdivision grid."""
        sub = self.cell_size / self.subdivisions
        sx = round(x / sub) * sub
        sy = round(y / sub) * sub
        return sx, sy
