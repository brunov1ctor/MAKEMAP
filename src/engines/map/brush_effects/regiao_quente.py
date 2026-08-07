"""Região quente — ondas de calor e brasas brilhantes."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _paint_glow_edge, _subcache


def paint_regiao_quente(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_glow_edge(painter, layer, path, bounds, QColor(255, 140, 60), alpha=65, edge="bottom", spread=0.45,
                      flicker={"period": 1.8, "range": (0.6, 1.0), "salt": 22})
    painter.save()
    painter.setClipPath(path)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setPen(Qt.PenStyle.NoPen)
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    for i in range(5):
        phase = i * 1.3
        wobble = math.sin(t * 1.4 + phase) * h * 0.02
        y = bounds.top() + (i + 0.5) / 5 * h + wobble
        painter.setBrush(QColor(255, 200, 120, 32))
        painter.drawRect(QRectF(bounds.left(), y - h * 0.03, w, h * 0.06))
    painter.restore()
    _paint_particles(painter, _subcache(cache, "particles"), layer, path, bounds, QColor(255, 170, 80), {
        "kind": "ember", "style": "oscillate", "count": 14,
        "speed": 0.5, "amount": 0.04,
        "size_min": 1.0, "size_max": 2.2, "alpha": 170, "glow": True, "clump": True,
        "pulse": {"period": 1.0, "range": (0.5, 1.0), "salt": 23},
        "wind": {"period": 3.0, "gust_period": 1.0, "speed_mult": 0.0, "lateral": 0.02, "salt": 24},
    })
    _paint_particles(painter, _subcache(cache, "haze_rise"), layer, path, bounds, QColor(255, 210, 150), {
        "kind": "heat_wisp", "style": "drift", "count": 6, "dir": -1.0, "axis": "vertical",
        "speed": 0.08, "sway_speed": 0.6, "sway": 0.05,
        "size_min": 6.0, "size_max": 12.0, "alpha": 30, "fade_band": 0.25,
    })
