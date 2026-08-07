"""Região subaquática — wash azul, cáusticas em ondas, bolhas subindo e silte em suspensão."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from ._base import _paint_particles, _subcache


def paint_regiao_subaquatica(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    wash = QColor(70, 170, 170)
    wash.setAlpha(70)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, wash)
    painter.restore()

    painter.save()
    painter.setClipPath(path)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    steps = 12
    for i in range(9):
        phase = i * 0.75
        base_y = bounds.top() + (i + 0.5) / 9 * h
        painter.setPen(QPen(QColor(200, 255, 240, 34), 2.0))
        caustic_path = QPainterPath()
        for s in range(steps + 1):
            fx = bounds.left() + s / steps * w
            fy = base_y + math.sin(t * 0.5 + fx * 0.025 + phase) * h * 0.025
            if s == 0:
                caustic_path.moveTo(fx, fy)
            else:
                caustic_path.lineTo(fx, fy)
        painter.drawPath(caustic_path)
    painter.restore()

    _paint_particles(painter, _subcache(cache, "silt"), layer, path, bounds, QColor(220, 240, 235), {
        "kind": "silt", "style": "oscillate", "count": 22,
        "speed": 0.12, "amount": 0.05,
        "size_min": 0.8, "size_max": 1.8, "alpha": 110, "clump": True,
    })
    _paint_particles(painter, _subcache(cache, "bubbles"), layer, path, bounds, QColor(230, 250, 250), {
        "kind": "water_bubble", "style": "drift", "count": 14, "dir": -1.0, "axis": "vertical",
        "speed": 0.09, "sway_speed": 0.55, "sway": 0.025,
        "size_min": 1.0, "size_max": 2.6, "alpha": 130, "fade_band": 0.2, "glow": True,
        "wind": {"period": 3.5, "gust_period": 1.2, "speed_mult": 0.2, "lateral": 0.015, "salt": 40},
    })
    _paint_particles(painter, _subcache(cache, "plankton"), layer, path, bounds, QColor(180, 230, 150), {
        "kind": "plankton", "style": "oscillate", "count": 10,
        "speed": 0.18, "amount": 0.04,
        "size_min": 0.6, "size_max": 1.2, "alpha": 70, "glow": True,
        "pulse": {"period": 2.0, "range": (0.4, 1.0), "salt": 41},
    })
