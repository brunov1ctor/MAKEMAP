"""PickPointTool — a one-shot "click anywhere on the map to pick a point"
tool. Doesn't place or select anything on the canvas itself; it just reports
the scene position of the next left-click back to whoever armed it (see
ProgressionMediator.begin_pin_pick), then hands control back to the tool
that was active before. Same shape as MarkerTool/TextTool but with no item
creation at all — the point itself is the payload.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, Signal, QObject
from PySide6.QtGui import QMouseEvent, QKeyEvent

from src.canvas.tools.base import BaseTool


class PickPointTool(BaseTool):
    name = "ProgressãoPickPoint"
    cursor = Qt.CursorShape.CrossCursor

    class _Signals(QObject):
        point_picked = Signal(QPointF)
        cancelled = Signal()

    def __init__(self, viewport):
        super().__init__(viewport)
        self._signals = self._Signals()
        self.point_picked = self._signals.point_picked
        self.cancelled = self._signals.cancelled

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.point_picked.emit(scene_pos)

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
