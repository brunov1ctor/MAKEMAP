"""Névoa animada com FBM em camadas paralaxe."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from ._base import _fog_textures, _FOG_LAYERS, _FOG_DRIFT_FRACTION, _FOG_BREATHE_PERIOD


def paint_nevoa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    entry = _fog_textures(cache, layer, path, bounds, color)
    t = time.monotonic() + entry["phase_offset"]
    mix = (math.sin(2 * math.pi * t / _FOG_BREATHE_PERIOD) + 1) / 2

    buf_size = entry["buf_size"]
    buf = entry["buf"]
    if buf is None or buf.width() != buf_size:
        buf = QImage(buf_size, buf_size, QImage.Format.Format_ARGB32_Premultiplied)
        entry["buf"] = buf
    buf.fill(0)

    bp = QPainter(buf)
    bp.setRenderHint(QPainter.RenderHint.Antialiasing)
    bp.translate(buf_size / 2, buf_size / 2)
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    diag = max(bounds.width(), bounds.height())
    for draw_scale, drift_speed, alpha_mult in _FOG_LAYERS:
        size = diag * draw_scale
        dx = math.sin(t * drift_speed) * diag * _FOG_DRIFT_FRACTION
        dy = math.cos(t * drift_speed * 0.8) * diag * _FOG_DRIFT_FRACTION
        target = QRectF(-size / 2 + dx, -size / 2 + dy, size, size)
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * (1 - mix))))
        bp.drawImage(target, entry["img_a"])
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * mix)))
        bp.drawImage(target, entry["img_b"])
    bp.setOpacity(1.0)
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    bp.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), entry["mask"])
    bp.end()

    painter.save()
    painter.translate(bounds.center())
    painter.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), buf)
    painter.restore()
