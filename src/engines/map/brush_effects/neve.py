"""Neve caindo — flocos calmos e flocos girando, com rajadas e acúmulo na base."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered, _paint_ground_marks, _subcache

_BASE_MOTION = {
    "kind": "snow", "style": "drift", "count": 40, "dir": 1.0, "axis": "vertical",
    "speed": 0.05, "sway_speed": 0.35, "sway": 0.09,
    "size_min": 2.0, "size_max": 4.0, "alpha": 210, "fade_band": 0.15,
    "wind": {"period": 7.0, "gust_period": 1.8, "speed_mult": 1.4, "lateral": 0.05, "salt": 4},
}
_DEPTHS = [
    {"name": "calm", "count": 40},
    {"name": "spin", "count": 16, "size_mult": 0.7, "alpha_mult": 0.9,
     "rotate": True, "rotate_aspect": (1.0, 0.4), "rot_speed": 40.0, "wind_scale": 1.5},
]


def paint_neve(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
    _paint_ground_marks(painter, _subcache(cache, "pile"), layer, path, bounds, color, {
        "kind": "snow_pile", "count": 14, "style": "pile",
        "size_min": 5.0, "size_max": 11.0, "alpha": 120,
    })
