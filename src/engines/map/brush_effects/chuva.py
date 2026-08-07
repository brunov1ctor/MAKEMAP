"""Chuva localizada em 3 profundidades, com rajadas de vento e respingos."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered, _paint_ground_marks, _subcache

_BASE_MOTION = {
    "kind": "rain", "style": "drift", "count": 55, "dir": 1.0, "axis": "vertical",
    "speed": 1.1, "sway_speed": 0.2, "sway": 0.01,
    "size_min": 14.0, "size_max": 26.0, "alpha": 170, "fade_band": 0.10,
    "width": 1.6, "angle_deg": 8.0, "clump": True,
    "wind": {"period": 6.0, "gust_period": 1.4, "speed_mult": 0.5, "lateral": 0.03, "salt": 1},
}
_DEPTHS = [
    {"name": "far", "count": 30, "speed_mult": 0.6, "size_mult": 0.6, "alpha_mult": 0.5, "wind_scale": 0.6},
    {"name": "mid", "count": 55, "wind_scale": 1.0},
    {"name": "near", "count": 12, "speed_mult": 1.35, "size_mult": 1.8, "alpha_mult": 1.1,
     "width": 2.6, "wind_scale": 1.3},
]


def paint_chuva(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
    _paint_ground_marks(painter, _subcache(cache, "splash"), layer, path, bounds, color, {
        "kind": "rain_splash", "count": 18, "style": "splash", "period": 0.9,
        "size_min": 3.0, "size_max": 8.0, "alpha": 150,
    })
