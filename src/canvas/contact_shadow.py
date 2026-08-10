"""Shared "contact shadow" primitive — a soft, squashed dark radial-gradient
ellipse grounding an object on the map. Used by MarkerItem (icon shadow,
strength-driven) and GlobalLightingOverlay (asset/mob-spawn smudges,
size-driven) — same visual technique, different call sites, previously
implemented twice.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient


def draw_contact_shadow(
    painter: QPainter, cx: float, cy: float, w: float,
    alpha_center: int = 100, alpha_mid: int = 55, squash: float = 0.32,
):
    """Paint one soft dark ellipse of width `w` centered at (cx, cy) — a
    circular radial gradient squashed to `squash` * w tall via a scale
    transform, so the gradient falloff stays uniform in all directions
    instead of distorting like a plain wide gradient inside a non-square
    rect would."""
    w = max(6.0, w)
    h = w * squash
    painter.save()
    painter.translate(cx, cy)
    painter.scale(1.0, h / w)
    grad = QRadialGradient(0, 0, w / 2)
    grad.setColorAt(0.0, QColor(0, 0, 0, alpha_center))
    grad.setColorAt(0.7, QColor(0, 0, 0, alpha_mid))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(QPointF(0, 0), w / 2, w / 2)
    painter.restore()
