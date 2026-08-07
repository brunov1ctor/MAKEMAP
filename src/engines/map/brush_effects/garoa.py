"""Garoa fina quase invisível — deriva lateral, nuvens rasas e leve umidade."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _paint_wash, _subcache


def paint_garoa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_wash(painter, layer, path, bounds, color, alpha=22)

    _paint_particles(painter, _subcache(cache, "haze"), layer, path, bounds, color, {
        "kind": "drizzle_haze", "style": "drift", "count": 8, "dir": 1.0, "axis": "vertical",
        "speed": 0.12, "sway_speed": 0.1, "sway": 0.04,
        "size_min": 30.0, "size_max": 55.0, "alpha": 18, "fade_band": 0.3,
        "wind": {"period": 4.0, "gust_period": 1.3, "speed_mult": 0.3, "lateral": 0.05, "salt": 2},
    })

    _paint_particles(painter, _subcache(cache, "drops"), layer, path, bounds, color, {
        "kind": "drizzle", "style": "drift", "count": 70, "dir": 1.0, "axis": "vertical",
        "speed": 0.55, "sway_speed": 0.15, "sway": 0.008,
        "size_min": 6.0, "size_max": 12.0, "alpha": 55, "fade_band": 0.12,
        "width": 0.8, "angle_deg": 6.0,
        "wind": {"period": 3.0, "gust_period": 0.9, "speed_mult": 0.2, "lateral": 0.12, "salt": 3},
    })
