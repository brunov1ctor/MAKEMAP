"""Viewport — custom QGraphicsView with zoom, pan, and camera management."""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QWheelEvent, QMouseEvent, QKeyEvent, QPainter, QColor, QTransform, QPixmap,
)

from src.styles.tokens import Colors, Navigation


class Viewport(QGraphicsView):
    """Main canvas viewport with infinite zoom and pan."""

    zoom_changed = Signal(float)  # emits current zoom level (1.0 = 100%)
    cursor_moved = Signal(float, float)  # scene X, Y
    view_changed = Signal()  # emitted on any pan or zoom

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(QRectF(-50000, -50000, 100000, 100000))
        self.setScene(self._scene)

        # Rendering
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        )

        # Appearance
        self.setBackgroundBrush(QColor(Colors.BG_SECONDARY))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Enable mouse tracking so mouseMoveEvent fires without button press
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # State
        self._zoom = 1.0
        self._panning = False
        self._pan_start = QPointF()
        self._space_held = False
        self._bg_color: QColor | None = None
        self._bg_pixmap: QPixmap | None = None

    # --- Background ---

    def set_background(self, color: QColor | None, pixmap: QPixmap | None):
        """Set a solid color or scaled image as the viewport background."""
        self._bg_color = color
        self._bg_pixmap = pixmap
        if color and not pixmap:
            self.setBackgroundBrush(color)
        elif not color and not pixmap:
            self.setBackgroundBrush(QColor(Colors.BG_SECONDARY))
        else:
            # Use transparent brush so drawBackground handles it
            self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        if self._bg_pixmap:
            # Draw the pixmap scaled to fill the visible viewport area
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            painter.drawPixmap(view_rect.toRect(), self._bg_pixmap)
        else:
            super().drawBackground(painter, rect)

    # --- Public API ---

    @property
    def zoom_level(self) -> float:
        return self._zoom

    @property
    def zoom_percent(self) -> int:
        return int(self._zoom * 100)

    def set_zoom(self, level: float, center: QPointF | None = None):
        if level <= 0 or level == self._zoom:
            return

        if center is None:
            center = self.viewport().rect().center()
            center = QPointF(center.x(), center.y())

        # Get scene point under cursor before zoom
        old_scene_pos = self.mapToScene(int(center.x()), int(center.y()))

        # Apply new transform
        self._zoom = level
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)

        # Keep scene point under cursor
        new_screen_pos = self.mapFromScene(old_scene_pos)
        delta = center - QPointF(new_screen_pos.x(), new_screen_pos.y())
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(delta.x())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(delta.y())
        )

        self.zoom_changed.emit(self._zoom)
        self.view_changed.emit()

    def zoom_in(self):
        self.set_zoom(self._zoom * Navigation.ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self._zoom / Navigation.ZOOM_STEP)

    def zoom_reset(self):
        self.set_zoom(1.0)

    def fit_to_content(self):
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isEmpty():
            return
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def center_on_point(self, scene_pos: QPointF):
        self.centerOn(scene_pos)

    # --- Events ---

    def wheelEvent(self, event: QWheelEvent):
        factor = Navigation.ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / Navigation.ZOOM_STEP
        center = QPointF(event.position().x(), event.position().y())
        self.set_zoom(self._zoom * factor, center)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or self._space_held:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Emit scene coordinates
        scene_pos = self.mapToScene(int(event.position().x()), int(event.position().y()))
        self.cursor_moved.emit(scene_pos.x(), scene_pos.y())

        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            self.view_changed.emit()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (self._panning and not self._space_held):
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().keyReleaseEvent(event)
