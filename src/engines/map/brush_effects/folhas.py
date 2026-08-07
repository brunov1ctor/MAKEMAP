"""Folhas — tamanhos e cores variados, giro individual, vento e acúmulo nas bordas."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered, _paint_ground_marks, _subcache

_BASE_MOTION = {
    "kind": "leaf", "style": "drift", "count": 20, "dir": 1.0, "axis": "vertical",
    "speed": 0.045, "sway_speed": 0.5, "sway": 0.07,
    "size_min": 3.5, "size_max": 6.0, "alpha": 190, "fade_band": 0.15,
    "rot_speed": 70.0, "clump": True,
    "wind": {"period": 5.5, "gust_period": 1.6, "speed_mult": 0.8, "lateral": 0.06, "salt": 15},
}
_DEPTHS = [
    {"name": "small", "count": 12, "size_mult": 0.6, "speed_mult": 1.15, "rot_speed": 90.0},
    {"name": "large", "count": 8, "size_mult": 1.5, "speed_mult": 0.8, "alpha_mult": 0.95,
     "color": QColor(150, 110, 55), "rot_speed": 45.0, "wind_scale": 1.3},
]


def paint_folhas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
    _paint_ground_marks(painter, _subcache(cache, "pile"), layer, path, bounds, color, {
        "kind": "leaf_pile", "count": 8, "style": "pile",
        "size_min": 3.0, "size_max": 6.0, "alpha": 110,
    })
