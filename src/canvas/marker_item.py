"""MarkerItem — a "point of interest" pin placed by the Marcador tool: a
colored circular plate with the picked emoji centered on it, optionally
surrounded by an animated "shader" effect (see EFFECT_DRAWERS below).

Custom-painted (not a QGraphicsPixmapItem) so its hit area is always the
full boundingRect() — a pixmap-based stamp's default alpha-based hit test
(ShapeMode.MaskShape) is what made mob-spawn stamps miss clicks near their
own transparent padding (see SpawnTool.build_stamp_item's shapeMode fix);
a plain QGraphicsItem never has that problem since it has no pixmap alpha
to test against.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPainterPath, QRadialGradient, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsDropShadowEffect, QStyle

from src.canvas.item_utils import enable_hover_glow
from src.engines.marker import MarkerProperties
from src.styles.tokens import Colors

_HOVER_SCALE = 1.15
_BASE_SIZE = 40.0
_HOVER_PAD = 6.0

_CATEGORY_COLORS = {
    "poi": "#4FC3F7",
    "marco": "#FFD54F",
    "combate": "#EF5350",
    "tesouro": "#AB47BC",
    "perigo": "#FFA726",
    "loja": "#66BB6A",
}


class MarkerItem(QGraphicsItem):
    """Local (0, 0) is the pin's own center — matches TextItem's convention
    so rotate/resize handles behave the same way for both item types."""

    def __init__(self, props: MarkerProperties | None = None, parent=None):
        super().__init__(parent)
        self.props = props or MarkerProperties()
        self._hovered = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setData(0, {"item_type": "marker"})
        enable_hover_glow(self, self._on_hover)

    def _on_hover(self, hovered: bool):
        self._hovered = hovered
        if hovered:
            self.setScale(_HOVER_SCALE)
            glow = QGraphicsDropShadowEffect()
            glow.setColor(QColor(Colors.ACCENT))
            glow.setBlurRadius(24)
            glow.setOffset(0, 0)
            self.setGraphicsEffect(glow)
        else:
            self.setScale(1.0)
            self.setGraphicsEffect(None)
        self.update()

    def boundingRect(self) -> QRectF:
        r = _BASE_SIZE / 2 + _HOVER_PAD
        if self.props.effects:
            r = max(r, self.props.effect_radius + _HOVER_PAD)
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        if self.props.effects:
            phase = time.monotonic()
            for key in self.props.effects:
                drawer = EFFECT_DRAWERS.get(key)
                if drawer:
                    drawer(painter, self.props.effect_radius, phase)

        color = QColor(_CATEGORY_COLORS.get(self.props.category, Colors.ACCENT))
        plate_r = _BASE_SIZE / 2
        painter.setPen(QPen(QColor(255, 255, 255, 220 if self._hovered else 120), 1.5))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(-plate_r, -plate_r, _BASE_SIZE, _BASE_SIZE))

        font = QFont()
        font.setPointSizeF(_BASE_SIZE * 0.42)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            QRectF(-plate_r, -plate_r, _BASE_SIZE, _BASE_SIZE),
            Qt.AlignmentFlag.AlignCenter, self.props.icon or "📍",
        )


# ─── "Shader" effects — stateless, driven purely by time.monotonic() so no
# per-item animation state needs to be tracked; MarkerMediator's timer only
# has to call .update() periodically to schedule the next repaint. ─────────

def _draw_redemoinhos(painter, radius: float, phase: float):
    painter.save()
    painter.setPen(QPen(QColor(120, 200, 255, 140), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    base_angle = (phase * 60) % 360
    steps = 36
    for i in range(2):
        path = QPainterPath()
        start = base_angle + i * 180
        for s in range(steps + 1):
            t = s / steps
            ang = math.radians(start + t * 360 * 1.4)
            r = radius * 0.15 + radius * 0.85 * t
            x, y = r * math.cos(ang), r * math.sin(ang)
            path.moveTo(x, y) if s == 0 else path.lineTo(x, y)
        painter.drawPath(path)
    painter.restore()


def _draw_folhas(painter, radius: float, phase: float):
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(120, 200, 90, 190))
    n = 6
    for i in range(n):
        ang = math.radians((360 / n) * i)
        drift = math.sin(phase * 1.6 + i) * 14
        cx = radius * math.cos(ang) + drift
        cy = radius * math.sin(ang) + math.cos(phase + i) * 6
        painter.save()
        painter.translate(cx, cy)
        painter.rotate((phase * 40 + i * 37) % 360)
        painter.drawEllipse(QRectF(-5, -2.5, 10, 5))
        painter.restore()
    painter.restore()


def _draw_nuvens(painter, radius: float, phase: float):
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    n = 3
    for i in range(n):
        alpha = max(40, min(160, int(90 + 60 * math.sin(phase * 1.2 + i * 2))))
        painter.setBrush(QColor(60, 60, 70, alpha))
        ang = math.radians((360 / n) * i + phase * 8)
        cx = radius * 0.6 * math.cos(ang)
        cy = -radius * 0.7 + radius * 0.15 * math.sin(ang)
        w, h = radius * 0.55, radius * 0.28
        painter.drawEllipse(QRectF(cx - w / 2, cy - h / 2, w, h))
    painter.restore()


def _draw_espinhos(painter, radius: float, phase: float):
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(150, 120, 90, 200))
    n = 8
    breathe = 1.0 + 0.08 * math.sin(phase * 3)
    for i in range(n):
        ang = math.radians((360 / n) * i)
        perp = ang + math.pi / 2
        base_r, tip_r = radius * 0.92, radius * 1.12 * breathe
        bx, by = base_r * math.cos(ang), base_r * math.sin(ang)
        tx, ty = tip_r * math.cos(ang), tip_r * math.sin(ang)
        w = 5
        p1 = QPointF(bx + w * math.cos(perp), by + w * math.sin(perp))
        p2 = QPointF(bx - w * math.cos(perp), by - w * math.sin(perp))
        p3 = QPointF(tx, ty)
        painter.drawPolygon(QPolygonF([p1, p2, p3]))
    painter.restore()


def _draw_brilho(painter, radius: float, phase: float):
    painter.save()
    pulse = 0.5 + 0.5 * math.sin(phase * 2.0)
    grad = QRadialGradient(0, 0, radius)
    grad.setColorAt(0.0, QColor(255, 235, 150, int(140 * pulse) + 20))
    grad.setColorAt(1.0, QColor(255, 235, 150, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
    painter.restore()


EFFECT_DRAWERS = {
    "redemoinhos": _draw_redemoinhos,
    "folhas": _draw_folhas,
    "nuvens": _draw_nuvens,
    "espinhos": _draw_espinhos,
    "brilho": _draw_brilho,
}
