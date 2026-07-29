"""Região "Estilo" shaders — modular post-process effects applied over a
região's already-composited fill+border pixmap (see RegionLayer._reapply_
style). Each style is a plain function that paints into the given QImage
in place; RegionLayer doesn't know or care how many exist.

To add a new style: write an `_apply_xxx(img)` function below and add it
to STYLES with its "Estilo" dropdown label as the key. STYLE_NAMES (which
feeds RegionEditPanel's combo box) and apply_style() both derive from that
one dict, so nothing else needs touching.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtGui import QColor, QImage, QPainter


def _apply_vapor(img: QImage) -> None:
    """Heat-haze look: fades + desaturates the fill toward a pale tint,
    then overlays soft wavy streaks (a multi-frequency sine ripple,
    brightest ridges only) so it reads as rising heat/vapor instead of
    just a flatter, paler copy of the same fill — a plain fade alone read
    as "not doing anything" (see the "vapor não está funcionando" report
    this was written for)."""
    painter = QPainter(img)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.fillRect(img.rect(), QColor(255, 255, 255, 150))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    painter.fillRect(img.rect(), QColor(235, 235, 220, 70))
    painter.end()

    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # Three overlapping sine waves at unrelated frequencies/phases so the
    # streaks read as organic rippling haze instead of one uniform,
    # obviously-repeating pattern.
    ripple = (
        np.sin(yy / 14.0 + xx / 90.0) * 0.5
        + np.sin(yy / 27.0 - xx / 60.0 + 1.7) * 0.3
        + np.sin(yy / 8.0 + 3.1) * 0.2
    )
    ripple = (ripple + 1.0) / 2.0  # 0..1
    # Only the brightest ridges show through (>0.55), so this reads as a
    # handful of soft rising streaks, not a full-image texture wash.
    alpha = (np.clip((ripple - 0.55) / 0.45, 0.0, 1.0) ** 1.5 * 90.0).astype(np.uint8)
    alpha = np.ascontiguousarray(alpha)
    # .copy() detaches from `alpha`'s buffer before it's garbage-collected
    # — see fog_noise.density_to_qimage for the same pattern.
    stripe_mask = QImage(alpha.data, w, h, w, QImage.Format.Format_Alpha8).copy()

    streaks = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    streaks.fill(QColor(255, 255, 255, 255))
    sp = QPainter(streaks)
    sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    sp.drawImage(0, 0, stripe_mask)
    sp.end()

    painter = QPainter(img)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.drawImage(0, 0, streaks)
    painter.end()


# style key ("Estilo" dropdown label) -> in-place QImage effect
STYLES: dict[str, Callable[[QImage], None]] = {
    "Vapor": _apply_vapor,
}

# "Nenhum" first (no effect), then every static bake (STYLES, applied once
# by apply_style below) — this is what RegionEditPanel's "Estilo" combo box
# is populated from (see region_edit_panel.ESTILOS). Animated, time-driven
# effects (Névoa, Poeira, Chuva, ...) live outside Região entirely now — see
# src/engines/map/brush_effects.py, painted with the Brush tool instead.
STYLE_NAMES: list[str] = ["Nenhum"] + list(STYLES.keys())


def apply_style(style_key: str, img: QImage) -> None:
    """No-op for "Nenhum" or any unrecognized key."""
    effect = STYLES.get(style_key)
    if effect is not None:
        effect(img)
