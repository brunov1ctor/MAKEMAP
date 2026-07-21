"""DonutChart — small painted ring chart for the sidebar's "Resumo Rápido",
with the total drawn in the center like the reference mock."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from src.styles.tokens import Colors

_THICKNESS = 12


class DonutChart(QWidget):
    """Renders `segments` — a list of (value, color_hex) — as a ring, with
    `total` printed in the center."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[tuple[float, str]] = []
        self._total = 0
        self.setFixedSize(96, 96)

    def set_data(self, segments: list[tuple[float, str]], total: int):
        self._segments = segments
        self._total = total
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        rect = QRectF((self.width() - side) / 2 + _THICKNESS / 2,
                       (self.height() - side) / 2 + _THICKNESS / 2,
                       side - _THICKNESS, side - _THICKNESS)

        base_pen = QPen(QColor(255, 255, 255, 20), _THICKNESS)
        base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(base_pen)
        p.drawArc(rect, 0, 360 * 16)

        grand_total = sum(v for v, _c in self._segments) or 1
        start_angle = 90 * 16
        for value, color in self._segments:
            if value <= 0:
                continue
            span = int(round(360 * 16 * value / grand_total))
            pen = QPen(QColor(color), _THICKNESS)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, start_angle, -span)
            start_angle -= span

        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._total))
        p.end()
