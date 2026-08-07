"""Região radioativa — névoa verde volumétrica com pulsação irregular, flashes e ondas circulares."""

from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _volume_textures, _paint_volume, _subcache

_GREEN = QColor(140, 230, 90)
_FLASH = QColor(230, 255, 190)
_LAYERS = (
    (1.3, 0.1, 0.45),
    (0.9, 0.2, 0.7),
    (0.6, 0.35, 0.9),
)


def paint_regiao_radioativa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    t = time.monotonic()
    entry = _volume_textures(
        cache, layer, path, bounds, _GREEN,
        cache_key="rad_volume", base_cells=4, alpha_gamma=1.9, alpha_scale=0.7,
        blur_px=12, breathe_period=9.0, seed_salt=0x2B0,
    )
    _paint_volume(
        painter, entry, bounds, t,
        layers=_LAYERS, drift_fraction=0.04, breathe_period=9.0, swirl_speed=0.05,
        growth_period=9.0, growth_range=(0.7, 1.15),
    )

    period = 3.4
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    cx, cy = bounds.center().x(), bounds.center().y()
    max_r = min(bounds.width(), bounds.height()) * 0.5
    for i in range(3):
        local_t = ((t / period) + i / 3.0) % 1.0
        radius = local_t * max_r
        ring_alpha = int(90 * (1.0 - local_t))
        if ring_alpha <= 0:
            continue
        ring_color = QColor(_GREEN)
        ring_color.setAlpha(ring_alpha)
        painter.setPen(ring_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)

    count = 12
    flash_cache = _subcache(cache, "flashes")
    seed_entry = flash_cache.get(id(layer))
    if seed_entry is None:
        rng = np.random.default_rng(id(layer) & 0xFFFFFFFF)
        seed_entry = {
            "x0": rng.random(count).astype(np.float32),
            "y0": rng.random(count).astype(np.float32),
            "phase": rng.random(count).astype(np.float32) * 2 * math.pi,
            "flash_speed": 0.6 + rng.random(count).astype(np.float32) * 1.2,
        }
        flash_cache[id(layer)] = seed_entry
    w, h = bounds.width(), bounds.height()
    for i in range(count):
        flash = math.sin(t * seed_entry["flash_speed"][i] + seed_entry["phase"][i])
        if flash < 0.9:
            continue
        strength = (flash - 0.9) / 0.1
        x = bounds.left() + seed_entry["x0"][i] * w
        y = bounds.top() + seed_entry["y0"][i] * h
        flash_color = QColor(_FLASH)
        flash_color.setAlpha(int(200 * strength))
        painter.setBrush(flash_color)
        painter.drawEllipse(QPointF(x, y), 2.0 + 3.0 * strength, 2.0 + 3.0 * strength)
    painter.restore()
