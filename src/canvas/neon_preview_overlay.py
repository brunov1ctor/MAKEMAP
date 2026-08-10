"""NeonPreviewOverlay — bright pulsing line for the part of a "Livre"
terreno boundary that's still being drawn.

Rides on top of the calm-colored MapBoundary item (which already renders
the whole shape, including the in-progress part, at its own normal pulse)
— this adds a second, faster/brighter "under construction" highlight on
just the newest chain of points, so the segment actively being placed
visibly reads as not-finished-yet. Owned by TerrainMediator, created when
"Livre" is armed and removed once drawing finishes or is cancelled.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene, QStyleOptionGraphicsItem

from src.canvas.z_order import ZOrder


class NeonPreviewOverlay(QGraphicsPathItem):
    PULSE_INTERVAL_MS = 40
    PULSE_MIN_ALPHA = 90
    PULSE_MAX_ALPHA = 255
    PULSE_CYCLE_MS = 700  # faster than MapBoundary's own pulse — reads as "actively being built"
    NEON_COLOR = QColor(255, 0, 210)
    GLOW_WIDTH = 12.0
    CORE_WIDTH = 3.0

    def __init__(self, scene: QGraphicsScene):
        super().__init__()
        self.setZValue(ZOrder.TOOL_PREVIEW)  # above the boundary (ZOrder.BOUNDARY_GROUP) and terrain art
        self._alpha = float(self.PULSE_MIN_ALPHA)
        self._alpha_dir = 1
        scene.addItem(self)
        self._timer = QTimer()
        self._timer.setInterval(self.PULSE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_chain(self, points: list) -> None:
        """Redraws the highlighted chain — `points` is the ordered list of
        scene-space QPointF forming the segment currently under
        construction (empty/single-point clears it to nothing drawn)."""
        path = QPainterPath()
        if len(points) >= 2:
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
        self.setPath(path)

    def remove(self) -> None:
        self._timer.stop()
        if self.scene():
            self.scene().removeItem(self)

    def _tick(self):
        step = (self.PULSE_MAX_ALPHA - self.PULSE_MIN_ALPHA) / (self.PULSE_CYCLE_MS / self.PULSE_INTERVAL_MS / 2)
        self._alpha += step * self._alpha_dir
        if self._alpha >= self.PULSE_MAX_ALPHA:
            self._alpha = float(self.PULSE_MAX_ALPHA)
            self._alpha_dir = -1
        elif self._alpha <= self.PULSE_MIN_ALPHA:
            self._alpha = float(self.PULSE_MIN_ALPHA)
            self._alpha_dir = 1
        self.update()

    def boundingRect(self) -> QRectF:
        # Inflated past the plain path bounds to cover the wider glow stroke.
        return super().boundingRect().adjusted(-self.GLOW_WIDTH, -self.GLOW_WIDTH, self.GLOW_WIDTH, self.GLOW_WIDTH)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        if self.path().elementCount() == 0:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        glow = QColor(self.NEON_COLOR)
        glow.setAlpha(int(self._alpha * 0.35))
        pen_glow = QPen(glow, self.GLOW_WIDTH)
        pen_glow.setCosmetic(True)
        pen_glow.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_glow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_glow)
        painter.drawPath(self.path())

        core = QColor(self.NEON_COLOR)
        core.setAlpha(int(self._alpha))
        pen_core = QPen(core, self.CORE_WIDTH)
        pen_core.setCosmetic(True)
        pen_core.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen_core.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_core)
        painter.drawPath(self.path())
