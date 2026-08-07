"""Pólen — pequenos grupos caóticos, cor variando entre amarelo, dourado e branco."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered

_GOLD = QColor(235, 200, 90)
_YELLOW = QColor(250, 225, 130)
_WHITE = QColor(245, 240, 220)
_BASE_MOTION = {
    "kind": "pollen", "style": "oscillate", "count": 40,
    "speed": 0.2, "amount": 0.04,
    "size_min": 0.8, "size_max": 1.6, "alpha": 55, "glow": True, "clump": True,
    "wind": {"period": 3.5, "gust_period": 1.1, "speed_mult": 0.0, "lateral": 0.05, "salt": 14},
}
_DEPTHS = [
    {"name": "gold", "count": 20, "color": _GOLD},
    {"name": "yellow", "count": 12, "color": _YELLOW, "size_mult": 0.85},
    {"name": "white", "count": 8, "color": _WHITE, "size_mult": 0.7, "alpha_mult": 0.7},
]


def paint_polen(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, _GOLD, _BASE_MOTION, _DEPTHS)
