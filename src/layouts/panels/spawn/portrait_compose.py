"""Group-portrait compositing for the Spawn panel's stamp preview/placement.

Turns a single mob "face" pixmap + a quantity into ONE composed image —
never a flat row of N identical copies. A front-and-center portrait plus a
small fan of smaller, dimmed portraits peeking out behind it reads as "a
group of this creature" at a glance, the same visual shorthand group-token
icons use in RPG map tools. Quantities beyond what can stay legible (> 4)
keep the same 4-portrait cluster and add a "+N" count badge instead of
piling on more circles.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap

_MAX_VISIBLE = 4

# (dx, dy, scale, rotation_degrees) as fractions of the final canvas size,
# back-to-front paint order — the LAST entry in each list is the front/
# center portrait (biggest, undimmed, drawn on top of the others).
_LAYOUTS: dict[int, list[tuple[float, float, float, float]]] = {
    1: [(0.0, 0.0, 1.0, 0.0)],
    2: [(-0.20, -0.14, 0.70, -10.0), (0.12, 0.08, 1.0, 6.0)],
    3: [(-0.26, -0.10, 0.60, -14.0), (0.26, -0.10, 0.60, 14.0), (0.0, 0.12, 1.0, 0.0)],
    4: [(-0.30, -0.16, 0.52, -16.0), (0.30, -0.16, 0.52, 16.0),
        (-0.14, 0.10, 0.68, -6.0), (0.16, 0.12, 0.68, 7.0)],
}


_PLATE_COLOR = QColor(32, 37, 46, 235)


def _circular_portrait(source: QPixmap | None, diameter: int) -> QPixmap:
    """A circular "token": a solid backdrop plate (clipped to a circle) with
    `source` CONTAIN-fitted on top, uncropped. No ring outline — a stroked
    border around every token (including the white one on the front/center
    portrait) read as a stray circle sitting on top of the art rather than
    part of it, especially once the plate itself already gives each token
    its round silhouette.

    Deliberately NOT a cover-fit crop (KeepAspectRatioByExpanding) — mob
    portrait assets are almost always already a tightly-cropped character
    on a transparent background, not a square photo that fills its frame.
    Cover-fitting one of those into a circle just zooms in and slices off
    whatever sticks out furthest (ears, horns, wings), which reads as a
    botched crop rather than a portrait. Contain-fitting onto a plate
    keeps the whole character visible."""
    diameter = max(1, diameter)
    out = QPixmap(diameter, diameter)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    clip = QPainterPath()
    clip.addEllipse(0.0, 0.0, float(diameter), float(diameter))
    p.setClipPath(clip)
    p.fillRect(0, 0, diameter, diameter, _PLATE_COLOR)
    if source is not None and not source.isNull():
        # Small inset so the art doesn't touch the plate's own edge.
        inset = max(1, round(diameter * 0.9))
        scaled = source.scaled(
            inset, inset, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (diameter - scaled.width()) // 2
        y = (diameter - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
    p.setClipping(False)
    p.end()
    return out


def _dimmed(portrait: QPixmap, alpha: int = 90) -> QPixmap:
    """Darkens `portrait` in place (new copy) — used for the back portraits
    in a cluster so depth/ordering reads clearly regardless of the
    creature's own art colors."""
    shaded = QPixmap(portrait)
    p = QPainter(shaded)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    p.fillRect(shaded.rect(), QColor(0, 0, 0, alpha))
    p.end()
    return shaded


def compose_group_portrait(face: QPixmap | None, quantity: int, size: int) -> QPixmap:
    """A single `size`x`size` QPixmap representing `quantity` copies of
    `face`, composed as a front-and-center portrait with a fan of smaller,
    dimmed portraits peeking out behind it — not a flat repeated row.
    `face` may be None/null (falls back to a plain gray circle)."""
    quantity = max(1, quantity)
    size = max(8, round(size))
    visible = min(quantity, _MAX_VISIBLE)
    extra = quantity - visible

    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    placements = _LAYOUTS[visible]
    for i, (dx, dy, scale, rot) in enumerate(placements):
        is_front = i == len(placements) - 1
        diameter = max(6, round(size * 0.60 * scale))
        portrait = _circular_portrait(face, diameter)
        if not is_front:
            portrait = _dimmed(portrait)

        cx = size / 2 + dx * size
        cy = size / 2 + dy * size
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(rot)
        painter.drawPixmap(round(-portrait.width() / 2), round(-portrait.height() / 2), portrait)
        painter.restore()

    if extra > 0:
        _draw_count_badge(painter, size, extra)

    painter.end()
    return canvas


def _draw_count_badge(painter: QPainter, size: int, extra: int) -> None:
    """Small red "+N" pill in the bottom-right corner — how quantities
    beyond the 4 visibly-composed portraits are represented, instead of
    cramming more overlapping circles into an unreadable pile."""
    text = f"+{extra}"
    font = QFont()
    font.setBold(True)
    font.setPointSize(max(7, size // 11))
    fm = QFontMetrics(font)
    text_w = fm.horizontalAdvance(text)
    badge_h = fm.height() + 4
    badge_w = max(badge_h, text_w + 10)
    x = size - badge_w - 2
    y = size - badge_h - 2

    painter.save()
    painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
    painter.setBrush(QColor(200, 40, 40, 235))
    painter.drawRoundedRect(QRectF(x, y, badge_w, badge_h), badge_h / 2, badge_h / 2)
    painter.setPen(QColor(255, 255, 255, 255))
    painter.setFont(font)
    painter.drawText(QRectF(x, y, badge_w, badge_h), Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
