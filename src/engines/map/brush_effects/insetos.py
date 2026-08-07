"""Insetos — enxame atraído pela luz mais próxima, vaga-lumes piscando e mariposas maiores."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _nearest_light_bias, _subcache

_MOTH = QColor(220, 210, 190)


def paint_insetos(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    bias = _nearest_light_bias(cache, bounds)

    _paint_particles(painter, _subcache(cache, "fireflies"), layer, path, bounds, color, {
        "kind": "insect", "style": "insect", "count": 14,
        "speed": 0.6, "amount": 0.03, "attract": 0.55,
        "size_min": 1.0, "size_max": 2.0, "alpha": 200, "glow": True, "clump": True,
        "pulse": {"period": 1.3, "range": (0.15, 1.0), "salt": 16},
        "_bias": bias,
    })
    _paint_particles(painter, _subcache(cache, "moths"), layer, path, bounds, _MOTH, {
        "kind": "moth", "style": "insect", "count": 5,
        "speed": 0.35, "amount": 0.05, "attract": 0.35,
        "size_min": 2.0, "size_max": 3.2, "alpha": 140,
        "rotate": True, "rotate_aspect": (1.0, 0.4), "rot_speed": 25.0,
        "_bias": bias,
    })
