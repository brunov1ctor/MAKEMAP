"""Cinzas — fragmentos quentes subindo (incandescentes) e frios descendo."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered

_EMBER = QColor(255, 150, 70)
_BASE_MOTION = {
    "kind": "ash", "style": "drift", "count": 30, "dir": -1.0, "axis": "vertical",
    "speed": 0.028, "sway_speed": 0.4, "sway": 0.03,
    "size_min": 1.2, "size_max": 2.6, "alpha": 150, "fade_band": 0.18, "clump": True,
    "wind": {"period": 5.0, "gust_period": 1.5, "speed_mult": 0.3, "lateral": 0.02, "salt": 6},
}
_DEPTHS = [
    {"name": "hot", "count": 10, "dir": -1.0, "speed_mult": 1.3, "size_mult": 0.9,
     "alpha_mult": 1.0, "color": _EMBER, "glow": True, "pulse": {"period": 1.4, "range": (0.5, 1.0), "salt": 7}},
    {"name": "cold", "count": 22, "dir": 1.0, "speed_mult": 0.5, "size_mult": 1.1, "alpha_mult": 0.85},
]


def paint_cinzas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
