"""Liquid Glass widgets — QPainter-based panels with real transparency and effects."""

from PySide6.QtWidgets import QWidget, QPushButton, QGraphicsDropShadowEffect, QSizePolicy
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSize, QTimer,
    QPropertyAnimation, QEasingCurve, Property, Signal,
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QFont, QFontMetrics, QCursor,
)

from src.styles.tokens import Colors


# ─── Helpers ────────────────────────────────────────────────────────────────

def _shadow(widget: QWidget, radius=32, opacity=160, dy=8):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(radius)
    c = QColor(0, 0, 0, opacity)
    fx.setColor(c)
    fx.setOffset(0, dy)
    widget.setGraphicsEffect(fx)
    return fx


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


# ─── GlassPanel ────────────────────────────────────────────────────────────

class GlassPanel(QWidget):
    """Painel com fundo frosted glass pintado via QPainter — sem QSS."""

    def __init__(self, parent=None, radius=16, tint_alpha=180, border_opacity=50):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self._radius = radius
        self._tint = QColor(20, 36, 60, tint_alpha)
        self._border_opacity = border_opacity

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)

        p.setClipPath(path)

        # Base tint
        p.fillPath(path, self._tint)

        # Gradiente vertical (reflexo de luz no topo)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(255, 255, 255, 12))
        grad.setColorAt(0.15, QColor(255, 255, 255, 5))
        grad.setColorAt(0.5, QColor(255, 255, 255, 1))
        grad.setColorAt(1.0, QColor(0, 0, 0, 8))
        p.fillPath(path, QBrush(grad))

        # Specular highlight no topo
        spec_h = min(self._radius * 1.5, h * 0.25)
        spec = QRectF(self._radius * 0.5, 1.5, w - self._radius, spec_h)
        sp = QPainterPath()
        sp.addRoundedRect(spec, self._radius * 0.5, self._radius * 0.5)
        sg = QLinearGradient(0, spec.top(), 0, spec.bottom())
        sg.setColorAt(0.0, QColor(255, 255, 255, 45))
        sg.setColorAt(0.5, QColor(255, 255, 255, 15))
        sg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.fillPath(sp, QBrush(sg))

        p.setClipping(False)

        # Borda luminosa
        bc = QColor(255, 255, 255, self._border_opacity)
        p.setPen(QPen(bc, 1.0))
        p.drawPath(path)

        p.end()


# ─── GlassCard ─────────────────────────────────────────────────────────────

class GlassCard(QWidget):
    """Card compacto com hover animado."""

    clicked = Signal()

    def __init__(self, parent=None, radius=12):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self._radius = radius
        self._hover_t = 0.0
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._anim = QPropertyAnimation(self, b"_hover_val")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        _shadow(self, radius=16, opacity=100, dy=4)

    def _get_hover_val(self):
        return int(self._hover_t * 100)

    def _set_hover_val(self, val):
        self._hover_t = val / 100.0
        self.update()

    _hover_val = Property(int, _get_hover_val, _set_hover_val)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._get_hover_val())
        self._anim.setEndValue(100)
        self._anim.start()

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._get_hover_val())
        self._anim.setEndValue(0)
        self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        t = self._hover_t
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)

        # Fill interpolado
        base = QColor(20, 36, 60, 140)
        hover = QColor(30, 50, 80, 180)
        fill = QColor(
            int(base.red() * (1 - t) + hover.red() * t),
            int(base.green() * (1 - t) + hover.green() * t),
            int(base.blue() * (1 - t) + hover.blue() * t),
            int(base.alpha() * (1 - t) + hover.alpha() * t),
        )
        p.fillPath(path, fill)

        # Highlight topo
        ref = QRectF(self._radius * 0.4, 0.5, w - self._radius * 0.8, h * 0.3)
        ref_path = QPainterPath()
        ref_path.addRoundedRect(ref, self._radius * 0.4, self._radius * 0.4)
        rg = QLinearGradient(0, 0, 0, h * 0.3)
        rg.setColorAt(0.0, QColor(255, 255, 255, int(18 + t * 16)))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.fillPath(ref_path, QBrush(rg))

        # Borda
        bc = QColor(255, 255, 255, int(45 + t * 60))
        p.setPen(QPen(bc, 1.0))
        p.drawPath(path)

        p.end()


# ─── GlassButton ──────────────────────────────────────────────────────────

class GlassButton(QPushButton):
    """Botão com fundo glass, reflexo e animação de hover/press."""

    def __init__(self, text="", parent=None, accent=False, radius=10, height=32):
        super().__init__(text, parent)
        self._accent = accent
        self._radius = radius
        self._hover_t = 0.0
        self._press_scale = 1.0
        self.setFixedHeight(height)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFlat(True)
        self.setStyleSheet("background: transparent; border: none;")

        self._anim = QPropertyAnimation(self, b"_hover_val")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_hover_val(self):
        return int(self._hover_t * 100)

    def _set_hover_val(self, val):
        self._hover_t = val / 100.0
        self.update()

    _hover_val = Property(int, _get_hover_val, _set_hover_val)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._get_hover_val())
        self._anim.setEndValue(100)
        self._anim.start()

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._get_hover_val())
        self._anim.setEndValue(0)
        self._anim.start()

    def mousePressEvent(self, event):
        self._press_scale = 0.96
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_scale = 1.0
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        t = self._hover_t
        w, h = self.width(), self.height()

        if self._press_scale < 1.0:
            p.translate(w / 2, h / 2)
            p.scale(self._press_scale, self._press_scale)
            p.translate(-w / 2, -h / 2)

        r = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)

        if self._accent:
            base = QColor(79, 195, 247, 200)
            hover = QColor(129, 212, 250, 230)
            text_color = QColor(7, 17, 31)
        else:
            base = QColor(20, 36, 60, 160)
            hover = QColor(30, 50, 80, 200)
            text_color = QColor(255, 255, 255, int(180 + t * 75))

        fill = QColor(
            int(base.red() * (1 - t) + hover.red() * t),
            int(base.green() * (1 - t) + hover.green() * t),
            int(base.blue() * (1 - t) + hover.blue() * t),
            int(base.alpha() * (1 - t) + hover.alpha() * t),
        )

        # Gradiente
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, fill.lighter(112))
        grad.setColorAt(1.0, fill)
        p.fillPath(path, QBrush(grad))

        # Highlight topo
        ref = QRectF(self._radius * 0.5, 1, w - self._radius, h * 0.35)
        ref_path = QPainterPath()
        ref_path.addRoundedRect(ref, self._radius * 0.4, self._radius * 0.4)
        rg = QLinearGradient(0, 0, 0, ref.height())
        rg.setColorAt(0.0, QColor(255, 255, 255, int(25 + t * 20)))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.fillPath(ref_path, QBrush(rg))

        # Borda
        if self._accent:
            bc = QColor(79, 195, 247, int(150 + t * 105))
        else:
            bc = QColor(255, 255, 255, int(50 + t * 80))
        p.setPen(QPen(bc, 1.0))
        p.drawPath(path)

        # Texto
        p.setPen(text_color)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.text())

        p.end()

    def sizeHint(self):
        fm = QFontMetrics(QFont("Segoe UI", 10, QFont.Weight.Bold))
        tw = fm.horizontalAdvance(self.text()) + 32
        return QSize(max(tw, 80), self.height())
