"""Liquid Glass widgets — QPainter-based panels with real transparency and effects."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QRadialGradient, QBrush


# ─── AmbientBackground ─────────────────────────────────────────────────────

class AmbientBackground(QWidget):
    """Fundo atmosférico com glows radiais — fica atrás de toda a interface."""

    _BG = QColor(0x04, 0x08, 0x14)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)

        w, h = self.width(), self.height()
        base = max(w, h)

        # Fundo base
        p.fillRect(self.rect(), self._BG)

        def _radial(cx, cy, radius, r, g, b, alpha):
            gr = QRadialGradient(QPointF(cx, cy), radius)
            gr.setColorAt(0.0, QColor(r, g, b, alpha))
            gr.setColorAt(0.45, QColor(r, g, b, int(alpha * 0.4)))
            gr.setColorAt(1.0, QColor(r, g, b, 0))
            path = QPainterPath()
            path.addEllipse(QPointF(cx, cy), radius, radius)
            p.fillPath(path, gr)

        # Glows atmosféricos
        _radial(w * 0.12, h * 0.35, base * 0.50, 20, 80, 200, 30)    # azul esquerda
        _radial(w * 0.50, h * 0.85, base * 0.65, 40, 60, 180, 22)    # azul-roxo inferior
        _radial(w * 0.85, h * 0.30, base * 0.40, 30, 150, 220, 18)   # ciano direita
        _radial(w * 0.50, h * 0.40, base * 0.80, 79, 195, 247, 12)   # accent central sutil

        # Vinheta
        vig = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.70)
        vig.setColorAt(0.40, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.setBrush(QBrush(vig))
        p.drawRect(self.rect())

        p.end()
