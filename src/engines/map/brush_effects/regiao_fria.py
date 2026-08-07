"""Região fria — névoa azulada com cristais de gelo cintilantes ao vento."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _subcache
from .nevoa import paint_nevoa


def paint_regiao_fria(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    ice_tint = QColor(190, 220, 255)
    paint_nevoa(painter, _subcache(cache, "fog"), layer, path, bounds, ice_tint)
    _paint_particles(painter, _subcache(cache, "particles"), layer, path, bounds, QColor(230, 245, 255), {
        "kind": "ice", "style": "oscillate", "count": 22,
        "speed": 0.15, "amount": 0.02,
        "size_min": 1.0, "size_max": 2.0, "alpha": 190, "glow": True, "clump": True,
        "pulse": {"period": 1.8, "range": (0.5, 1.0), "salt": 20},
        "wind": {"period": 4.5, "gust_period": 1.3, "speed_mult": 0.0, "lateral": 0.03, "salt": 21},
    })
