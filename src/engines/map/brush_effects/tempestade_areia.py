"""Tempestade de areia — múltiplas camadas horizontais, areia rasteira, pedras e haze com flicker."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered, _paint_wash

_BASE_MOTION = {
    "kind": "sand", "style": "drift", "count": 60, "dir": 1.0, "axis": "horizontal",
    "speed": 0.12, "sway_speed": 0.6, "sway": 0.04,
    "size_min": 1.0, "size_max": 2.4, "alpha": 150, "fade_band": 0.12, "clump": True,
    "wind": {"period": 3.0, "gust_period": 0.9, "speed_mult": 1.0, "lateral": 0.0, "salt": 18},
}
_DEPTHS = [
    {"name": "low", "count": 34, "speed_mult": 1.4, "size_mult": 0.6, "alpha_mult": 1.2, "wind_scale": 1.3},
    {"name": "mid", "count": 60, "wind_scale": 1.0},
    {"name": "coarse", "count": 8, "speed_mult": 0.9, "size_mult": 2.4, "alpha_mult": 0.9,
     "rotate": True, "rotate_aspect": (0.9, 0.9), "rot_speed": 20.0, "wind_scale": 0.8},
]


def paint_tempestade_areia(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_wash(painter, layer, path, bounds, color, alpha=70,
                flicker={"period": 2.5, "range": (0.6, 1.0), "salt": 19})
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
