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

from PySide6.QtGui import QColor, QImage, QPainter


def _apply_vapor(img: QImage) -> None:
    """Heat-haze look: fade the fill and desaturate it toward a pale tint
    — "usa a cor mas diminui a opacidade e aplica vapor"."""
    painter = QPainter(img)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.fillRect(img.rect(), QColor(255, 255, 255, 150))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    painter.fillRect(img.rect(), QColor(235, 235, 220, 70))
    painter.end()


# style key ("Estilo" dropdown label) -> in-place QImage effect
STYLES: dict[str, Callable[[QImage], None]] = {
    "Vapor": _apply_vapor,
}

# "Nenhum" first (no effect) followed by every registered style, in
# registration order — this is what RegionEditPanel's "Estilo" combo box
# is populated from (see region_edit_panel.ESTILOS).
STYLE_NAMES: list[str] = ["Nenhum"] + list(STYLES.keys())


def apply_style(style_key: str, img: QImage) -> None:
    """No-op for "Nenhum" or any unrecognized key."""
    effect = STYLES.get(style_key)
    if effect is not None:
        effect(img)
