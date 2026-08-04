"""PointAlignmentGuides — dashed horizontal/vertical guide lines shown
while placing a new "Livre" boundary point that lines up (same X or Y)
with an existing vertex of the shape being drawn.

Same visual language as MapBoundary's own AlignmentGuides (used when
dragging a whole boundary against its siblings) — a separate, smaller
class rather than reusing that one directly, since AlignmentGuides
compares bounding RECTS of MovableBoundaryItems, not discrete points.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QLineF, QPointF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene

GUIDE_COLOR = QColor(255, 200, 50, 180)
GUIDE_WIDTH = 1.5
EXTENT = 50000
SNAP_THRESHOLD = 12.0


class PointAlignmentGuides:
    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._lines: list[QGraphicsLineItem] = []

    def update(self, preview_pos: QPointF, existing_points: list[QPointF]) -> None:
        self.clear()
        for pt in existing_points:
            if abs(pt.x() - preview_pos.x()) < SNAP_THRESHOLD:
                self._add_vline(pt.x())
            if abs(pt.y() - preview_pos.y()) < SNAP_THRESHOLD:
                self._add_hline(pt.y())

    def clear(self) -> None:
        for line in self._lines:
            if line.scene():
                self._scene.removeItem(line)
        self._lines = []

    def _add_vline(self, x: float):
        line = QGraphicsLineItem(QLineF(x, -EXTENT, x, EXTENT))
        pen = QPen(GUIDE_COLOR, GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(9999)
        self._scene.addItem(line)
        self._lines.append(line)

    def _add_hline(self, y: float):
        line = QGraphicsLineItem(QLineF(-EXTENT, y, EXTENT, y))
        pen = QPen(GUIDE_COLOR, GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(9999)
        self._scene.addItem(line)
        self._lines.append(line)

    def remove(self) -> None:
        self.clear()
