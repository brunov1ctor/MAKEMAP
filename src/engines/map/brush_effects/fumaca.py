"""Fumaça — volume FBM com redemoinho lento e ciclo de crescimento/dissipação."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _volume_textures, _paint_volume

_LAYERS = (
    (1.3, 0.10, 0.55),
    (0.95, 0.20, 0.75),
    (0.65, 0.35, 0.95),
)


def paint_fumaca(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    entry = _volume_textures(
        cache, layer, path, bounds, color,
        cache_key="smoke_volume", base_cells=4, alpha_gamma=2.6, alpha_scale=0.85,
        blur_px=16, breathe_period=22.0,
    )
    _paint_volume(
        painter, entry, bounds, time.monotonic(),
        layers=_LAYERS, drift_fraction=0.05, breathe_period=22.0,
        swirl_speed=0.15, growth_period=14.0, growth_range=(0.75, 1.2),
    )
