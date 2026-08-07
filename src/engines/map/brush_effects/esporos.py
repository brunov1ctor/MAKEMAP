"""Esporos — agrupamentos flutuando em trajetórias curvas, com brilho pulsante."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered

_BASE_MOTION = {
    "kind": "spore", "style": "oscillate", "count": 24,
    "speed": 0.08, "amount": 0.03,
    "size_min": 1.2, "size_max": 2.2, "alpha": 170, "glow": True, "clump": True,
    "wind": {"period": 6.0, "gust_period": 2.2, "speed_mult": 0.0, "lateral": 0.02, "salt": 11},
    "pulse": {"period": 2.6, "range": (0.55, 1.0), "salt": 12},
}
_DEPTHS = [
    {"name": "main", "count": 24},
    {"name": "haze", "count": 10, "size_mult": 1.8, "alpha_mult": 0.35,
     "pulse": {"period": 3.4, "range": (0.4, 1.0), "salt": 13}},
]


def paint_esporos(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    _paint_particles_layered(painter, cache, layer, path, bounds, color, _BASE_MOTION, _DEPTHS)
