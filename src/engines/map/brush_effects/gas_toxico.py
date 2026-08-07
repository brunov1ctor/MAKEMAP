"""Gás tóxico — nuvens densas em bolsões (FBM) com bolhas subindo."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _volume_textures, _paint_volume, _subcache

_TOXIC = QColor(70, 190, 90)
_LAYERS = (
    (1.2, 0.12, 0.5),
    (0.85, 0.22, 0.75),
    (0.6, 0.4, 0.95),
)


def paint_gas_toxico(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    entry = _volume_textures(
        cache, layer, path, bounds, _TOXIC,
        cache_key="toxic_volume", base_cells=5, alpha_gamma=2.0, alpha_scale=0.75,
        blur_px=12, breathe_period=18.0, seed_salt=0x706,
    )
    _paint_volume(
        painter, entry, bounds, time.monotonic(),
        layers=_LAYERS, drift_fraction=0.05, breathe_period=18.0, swirl_speed=0.1,
    )
    _paint_particles(painter, _subcache(cache, "bubbles"), layer, path, bounds, QColor(150, 230, 150), {
        "kind": "toxic_bubble", "style": "drift", "count": 18, "dir": -1.0, "axis": "vertical",
        "speed": 0.06, "sway_speed": 0.5, "sway": 0.03,
        "size_min": 1.0, "size_max": 2.6, "alpha": 90, "fade_band": 0.2, "glow": True,
        "wind": {"period": 3.0, "gust_period": 1.0, "speed_mult": 0.4, "lateral": 0.03, "salt": 17},
    })
