"""Poeira flutuando em micro-nuvens, mistura de finas e maiores."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered

_BASE_MOTION = {
    "kind": "dust", "style": "oscillate", "count": 46,
    "speed": 0.35, "amount": 0.05,
    "size_min": 1.0, "size_max": 2.6, "alpha": 130, "clump": True,
    "wind": {"period": 5.0, "gust_period": 1.6, "speed_mult": 0.4, "lateral": 0.02, "salt": 5},
}
_DEPTHS = [
    {"name": "fine", "count": 55, "speed_mult": 0.5, "size_mult": 0.7, "alpha_mult": 0.8, "wind_scale": 0.5},
    {"name": "clusters", "count": 14, "size_mult": 2.2, "alpha_mult": 1.1,
     "rotate": True, "rotate_aspect": (1.0, 0.75), "rot_speed": 15.0, "wind_scale": 1.2},
]


def paint_poeira(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
