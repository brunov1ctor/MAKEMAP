"""Compass — rosa dos ventos expansível."""

from PySide6.QtWidgets import QFrame, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QRegion

from src.styles.tokens import Colors, Typography

import math


class Compass(QFrame):
    """Rosa dos ventos — clique para expandir/recolher."""

    expanded_changed = Signal(bool)

    COLLAPSED_SIZE = 52
    EXPANDED_SIZE = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setFixedSize(self.COLLAPSED_SIZE, self.COLLAPSED_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self._apply_mask()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

    def _apply_mask(self):
        """Máscara circular — mouse só reage dentro do círculo."""
        size = self.width()
        region = QRegion(0, 0, size, size, QRegion.RegionType.Ellipse)
        self.setMask(region)

    def _apply_style(self):
        size = self.EXPANDED_SIZE if self._expanded else self.COLLAPSED_SIZE
        radius = size // 2
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: {radius}px;
            }}
        """)

    def is_expanded(self) -> bool:
        return self._expanded

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._expanded = not self._expanded
            size = self.EXPANDED_SIZE if self._expanded else self.COLLAPSED_SIZE
            self.setFixedSize(size, size)
            self._apply_style()
            self._apply_mask()
            self.expanded_changed.emit(self._expanded)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = (min(self.width(), self.height()) / 2) - 8

        if self._expanded:
            # Círculo externo
            p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

            # Direções cardinais
            directions = [("N", -90), ("E", 0), ("S", 90), ("W", 180)]
            sub_dirs = [("NE", -45), ("SE", 45), ("SW", 135), ("NW", -135)]

            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            for label, angle in directions:
                rad = math.radians(angle)
                x = cx + (radius - 12) * math.cos(rad)
                y = cy + (radius - 12) * math.sin(rad)
                color = Colors.ACCENT if label == "N" else Colors.TEXT_MUTED
                p.setPen(QColor(color))
                p.drawText(QPointF(x - 5, y + 4), label)

            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QColor(Colors.TEXT_MUTED))
            for label, angle in sub_dirs:
                rad = math.radians(angle)
                x = cx + (radius - 14) * math.cos(rad)
                y = cy + (radius - 14) * math.sin(rad)
                p.drawText(QPointF(x - 5, y + 3), label)

            # Agulha
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.ACCENT))
            needle_len = radius * 0.5
            p.drawPolygon([
                QPointF(cx, cy - needle_len),
                QPointF(cx - 4, cy),
                QPointF(cx + 4, cy),
            ])
            p.setBrush(QColor(Colors.TEXT_MUTED))
            p.drawPolygon([
                QPointF(cx, cy + needle_len * 0.6),
                QPointF(cx - 3, cy),
                QPointF(cx + 3, cy),
            ])
        else:
            # Modo compacto — só "N"
            p.setPen(QColor(Colors.ACCENT))
            p.setFont(QFont("Segoe UI", 18, QFont.Weight.Black))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "N")

        p.end()
