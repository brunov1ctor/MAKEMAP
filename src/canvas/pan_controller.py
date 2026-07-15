"""KeyboardPanController — continuous pan with acceleration."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QObject, Signal
from PySide6.QtWidgets import QGraphicsView

from src.styles.tokens import Navigation


# Keys grouped by direction
_LEFT_KEYS = {Qt.Key.Key_Left, Qt.Key.Key_A}
_RIGHT_KEYS = {Qt.Key.Key_Right, Qt.Key.Key_D}
_UP_KEYS = {Qt.Key.Key_Up, Qt.Key.Key_W}
_DOWN_KEYS = {Qt.Key.Key_Down, Qt.Key.Key_S}
PAN_KEYS = _LEFT_KEYS | _RIGHT_KEYS | _UP_KEYS | _DOWN_KEYS


class KeyboardPanController(QObject):
    """Handles continuous keyboard panning with quadratic acceleration.

    Emits `panned(dx, dy)` each tick with the scene-space delta so that
    external systems (e.g. active brush strokes) can compensate.
    """

    panned = Signal(float, float)  # scene delta x, y

    def __init__(self, viewport: QGraphicsView, parent=None):
        super().__init__(parent)
        self._viewport = viewport
        self._keys_held: set[int] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(max(1, 1000 // Navigation.PAN_FPS))
        self._timer.timeout.connect(self._tick)
        self._elapsed = QElapsedTimer()

    # ─── Public API ──────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return bool(self._keys_held)

    def key_pressed(self, key: int):
        """Call on key press (non-autorepeat only)."""
        self._keys_held.add(key)
        if not self._timer.isActive():
            self._elapsed.start()
            self._timer.start()

    def key_released(self, key: int):
        """Call on key release (non-autorepeat only)."""
        self._keys_held.discard(key)
        if not self._keys_held:
            self._timer.stop()

    def stop(self):
        """Force stop (e.g. on focus loss)."""
        self._keys_held.clear()
        self._timer.stop()

    # ─── Internal ────────────────────────────────────────────────────

    def _tick(self):
        t = min(1.0, self._elapsed.elapsed() / Navigation.PAN_ACCEL_MS)
        speed = Navigation.PAN_MIN_SPEED + (Navigation.PAN_MAX_SPEED - Navigation.PAN_MIN_SPEED) * (t * t)

        dx, dy = 0.0, 0.0
        if self._keys_held & _LEFT_KEYS:
            dx -= speed
        if self._keys_held & _RIGHT_KEYS:
            dx += speed
        if self._keys_held & _UP_KEYS:
            dy -= speed
        if self._keys_held & _DOWN_KEYS:
            dy += speed

        if dx == 0.0 and dy == 0.0:
            return

        # Measure scene delta
        center = self._viewport.viewport().rect().center()
        old_scene = self._viewport.mapToScene(center)

        h_bar = self._viewport.horizontalScrollBar()
        v_bar = self._viewport.verticalScrollBar()
        h_bar.setValue(h_bar.value() + int(dx))
        v_bar.setValue(v_bar.value() + int(dy))

        new_scene = self._viewport.mapToScene(center)
        scene_dx = new_scene.x() - old_scene.x()
        scene_dy = new_scene.y() - old_scene.y()

        if scene_dx != 0.0 or scene_dy != 0.0:
            self.panned.emit(scene_dx, scene_dy)
