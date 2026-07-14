"""Grid Manager — configurable grid overlay with subdivisions."""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsLineItem
from PySide6.QtCore import QRectF, QLineF
from PySide6.QtGui import QPen, QColor


class GridManager:
    """Draws and manages a configurable grid on the scene."""

    def __init__(self, scene):
        self._scene = scene
        self._group: QGraphicsItemGroup | None = None

        # Config
        self.cell_size = 64
        self.subdivisions = 4
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

        left = int(view_rect.left() / self.cell_size) * self.cell_size
        top = int(view_rect.top() / self.cell_size) * self.cell_size
        right = view_rect.right()
        bottom = view_rect.bottom()

        pen_major = QPen(self.color_major, 1)
        pen_major.setCosmetic(True)
        pen_minor = QPen(self.color_minor, 1)
        pen_minor.setCosmetic(True)

        sub_size = self.cell_size / self.subdivisions

        # Vertical lines
        x = left
        while x <= right:
            is_major = abs(x % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(x, view_rect.top(), x, view_rect.bottom()))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            x += sub_size

        # Horizontal lines
        y = top
        while y <= bottom:
            is_major = abs(y % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(view_rect.left(), y, view_rect.right(), y))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            y += sub_size

        self._scene.addItem(self._group)

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
