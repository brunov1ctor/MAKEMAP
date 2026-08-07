"""Região de sonho — névoa suave, motes coloridos pulsando e pequenas estrelas desfocadas."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _paint_particles, _subcache
from .nevoa import paint_nevoa

_STAR = QColor(255, 255, 245)


def paint_regiao_sonho(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    dreamy = QColor(color).lighter(130)
    paint_nevoa(painter, _subcache(cache, "fog"), layer, path, bounds, dreamy)

    palette = (QColor(255, 140, 220), QColor(140, 200, 255), QColor(255, 230, 140), QColor(180, 140, 255))
    for idx, particle_color in enumerate(palette):
        _paint_particles(painter, _subcache(cache, f"particles_{idx}"), layer, path, bounds, particle_color, {
            "kind": f"dream{idx}", "style": "oscillate", "count": 8,
            "speed": 0.15, "amount": 0.05,
            "size_min": 1.5, "size_max": 2.8, "alpha": 150, "glow": True,
            "pulse": {"period": 4.0 + idx * 0.6, "range": (0.4, 1.0), "salt": 32 + idx},
        })

    _paint_particles(painter, _subcache(cache, "stars"), layer, path, bounds, _STAR, {
        "kind": "dream_star", "style": "oscillate", "count": 12,
        "speed": 0.03, "amount": 0.005,
        "size_min": 0.6, "size_max": 1.4, "alpha": 130, "glow": True,
        "pulse": {"period": 2.4, "range": (0.2, 1.0), "salt": 36},
    })
