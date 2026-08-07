"""Cinzas vulcânicas — fumaça escura volumétrica, partículas pretas/vermelhas e brilho vindo de baixo."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles_layered, _paint_glow_edge, _volume_textures, _paint_volume, _subcache

_BLACK = QColor(15, 15, 15)
_EMBER_RED = QColor(210, 60, 30)
_LAYERS = (
    (1.3, 0.08, 0.5),
    (0.9, 0.16, 0.7),
    (0.65, 0.28, 0.9),
)
_BASE_MOTION = {
    "kind": "vash", "style": "drift", "count": 34, "dir": -1.0, "axis": "vertical",
    "speed": 0.03, "sway_speed": 0.3, "sway": 0.03,
    "size_min": 1.2, "size_max": 2.4, "alpha": 170, "fade_band": 0.18, "clump": True,
    "wind": {"period": 4.0, "gust_period": 1.2, "speed_mult": 0.6, "lateral": 0.04, "salt": 8},
}
_DEPTHS = [
    {"name": "black", "count": 26, "size_mult": 1.3, "wind_scale": 1.0},
    {"name": "embers", "count": 6, "speed_mult": 1.4, "size_mult": 0.7, "alpha_mult": 1.1,
     "color": _EMBER_RED, "glow": True, "pulse": {"period": 1.1, "range": (0.4, 1.0), "salt": 9},
     "wind_scale": 1.4},
]


def paint_cinzas_vulcanicas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    entry = _volume_textures(
        cache, layer, path, bounds, _BLACK,
        cache_key="ash_volume", base_cells=4, alpha_gamma=1.6, alpha_scale=0.7,
        blur_px=14, breathe_period=26.0, seed_salt=0x1A5,
    )
    _paint_volume(
        painter, entry, bounds, time.monotonic(),
        layers=_LAYERS, drift_fraction=0.05, breathe_period=26.0, swirl_speed=0.08,
    )
    _paint_glow_edge(painter, layer, path, bounds, _EMBER_RED, alpha=70, edge="bottom", spread=0.35,
                      flicker={"period": 2.2, "range": (0.5, 1.0), "salt": 10})
    _paint_particles_layered(painter, _subcache(cache, "particles"), layer, path, bounds, _BLACK, _BASE_MOTION, _DEPTHS)
