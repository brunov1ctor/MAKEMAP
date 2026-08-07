"""Região amaldiçoada — wash escuro, fumaça preta móvel e rachaduras roxas luminosas."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _volume_textures, _paint_volume, _subcache

_BLACK = QColor(15, 10, 18)
_PURPLE = QColor(150, 60, 200)
_LAYERS = (
    (1.4, 0.06, 0.4),
    (1.0, 0.13, 0.6),
    (0.7, 0.22, 0.8),
)


def paint_regiao_amaldicoada(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    wash = QColor(20, 15, 25)
    wash.setAlpha(90)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, wash)
    painter.restore()

    entry = _volume_textures(
        cache, layer, path, bounds, _BLACK,
        cache_key="curse_volume", base_cells=4, alpha_gamma=1.7, alpha_scale=0.65,
        blur_px=14, breathe_period=35.0, seed_salt=0x3C2,
    )
    _paint_volume(
        painter, entry, bounds, time.monotonic(),
        layers=_LAYERS, drift_fraction=0.04, breathe_period=35.0, swirl_speed=0.04,
    )

    _paint_particles(painter, _subcache(cache, "cracks"), layer, path, bounds, _PURPLE, {
        "kind": "curse_crack", "style": "oscillate", "count": 10,
        "speed": 0.1, "amount": 0.015,
        "size_min": 0.8, "size_max": 1.6, "alpha": 130, "glow": True,
        "pulse": {"period": 3.6, "range": (0.25, 1.0), "salt": 31},
    })
