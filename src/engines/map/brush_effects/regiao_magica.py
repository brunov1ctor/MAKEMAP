"""Região mágica — partículas coloridas em espiral."""

from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ._base import _flicker_sample

_RUNE_COUNT = 5


def paint_regiao_magica(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    entry = cache.get(id(layer))
    count = 30
    if entry is None or entry.get("kind") != "magic":
        rng = np.random.default_rng(id(layer) & 0xFFFFFFFF)
        entry = {
            "kind": "magic", "count": count,
            "radius0": rng.random(count).astype(np.float32),
            "angle0": rng.random(count).astype(np.float32) * 2 * math.pi,
            "speed_jitter": 0.6 + rng.random(count).astype(np.float32) * 0.8,
            "size_jitter": rng.random(count).astype(np.float32),
            "color_pick": rng.integers(0, 3, count),
            "rune_angle0": rng.random(_RUNE_COUNT).astype(np.float32) * 2 * math.pi,
            "rune_radius": 0.55 + rng.random(_RUNE_COUNT).astype(np.float32) * 0.35,
            "rune_period": 2.2 + rng.random(_RUNE_COUNT).astype(np.float32) * 1.6,
            "rune_phase": rng.random(_RUNE_COUNT).astype(np.float32) * 2 * math.pi,
        }
        cache[id(layer)] = entry

    palette = (QColor(120, 160, 255), QColor(190, 120, 255), QColor(255, 215, 110))
    t = time.monotonic()
    cx, cy = bounds.center().x(), bounds.center().y()
    max_r = min(bounds.width(), bounds.height()) * 0.45
    pulse = _flicker_sample(layer, t, period=2.8, salt=30)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(entry["count"]):
        spin_speed = 0.4 * entry["speed_jitter"][i]
        angle = entry["angle0"][i] + t * spin_speed
        radius = entry["radius0"][i] * max_r * (0.6 + 0.4 * math.sin(t * 0.3 + entry["angle0"][i]))
        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius
        size = (1.2 + entry["size_jitter"][i] * 1.8) * (0.85 + 0.3 * pulse)
        particle_color = QColor(palette[int(entry["color_pick"][i])])
        particle_color.setAlpha(190)
        halo = QColor(particle_color)
        halo.setAlpha(int(60 * (0.6 + 0.6 * pulse)))
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(x, y), size * 2.2, size * 2.2)
        painter.setBrush(particle_color)
        painter.drawEllipse(QPointF(x, y), size, size)

    for i in range(_RUNE_COUNT):
        local_t = ((t / entry["rune_period"][i]) + entry["rune_phase"][i] / (2 * math.pi)) % 1.0
        fade = math.sin(local_t * math.pi)
        if fade <= 0.02:
            continue
        rune_angle = entry["rune_angle0"][i]
        rx = cx + math.cos(rune_angle) * max_r * entry["rune_radius"][i]
        ry = cy + math.sin(rune_angle) * max_r * entry["rune_radius"][i]
        rune_color = QColor(palette[i % 3])
        rune_color.setAlpha(int(150 * fade))
        painter.setPen(rune_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        s = 4.0 + 2.0 * fade
        painter.save()
        painter.translate(rx, ry)
        painter.rotate(rune_angle * 57.29577951308232 + local_t * 40.0)
        painter.drawRect(QRectF(-s / 2, -s / 2, s, s))
        painter.drawLine(QPointF(0, -s), QPointF(0, s))
        painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
    painter.restore()
