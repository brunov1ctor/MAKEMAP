"""MarkerItem — a "point of interest" pin placed by the Marcador tool: just
the picked emoji glyph (no background plate — the emoji's own art reads
fine directly on the map), optionally surrounded by an animated "shader"
effect (see EFFECT_DRAWERS below).

Custom-painted (not a QGraphicsPixmapItem) so its hit area is always the
full boundingRect() — a pixmap-based stamp's default alpha-based hit test
(ShapeMode.MaskShape) is what made mob-spawn stamps miss clicks near their
own transparent padding (see SpawnTool.build_stamp_item's shapeMode fix);
a plain QGraphicsItem never has that problem since it has no pixmap alpha
to test against.
"""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPen, QBrush, QFont, QPainterPath, QRadialGradient, QLinearGradient, QPolygonF,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsDropShadowEffect, QStyle

from src.canvas.item_utils import enable_hover_glow
from src.engines.marker import MarkerProperties
from src.styles.tokens import Colors

_HOVER_SCALE = 1.15
_BASE_SIZE = 40.0
_HOVER_PAD = 6.0


class MarkerItem(QGraphicsItem):
    """Local (0, 0) is the pin's own center — matches TextItem's convention
    so rotate/resize handles behave the same way for both item types."""

    def __init__(self, props: MarkerProperties | None = None, parent=None):
        super().__init__(parent)
        self.props = props or MarkerProperties()
        self._hovered = False

        # Per-marker randomness for the shader effects below — a fresh,
        # unseeded RNG so no two markers' leaves/spikes/clouds land in the
        # same spots or move in lockstep. _effect_cache holds each effect's
        # generated element params (angle/size/speed/phase/...), keyed by
        # element count, so they stay put frame-to-frame instead of
        # re-randomizing (which would just look like flicker) — only
        # regenerated when Intensidade changes the element count.
        self._rng = random.Random()
        self._effect_cache: dict[str, tuple[int, list]] = {}

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setData(0, {"item_type": "marker"})
        enable_hover_glow(self, self._on_hover)

    def _effect_params(self, key: str, count: int, factory) -> list:
        cached = self._effect_cache.get(key)
        if cached is not None and cached[0] == count:
            return cached[1]
        params = [factory(self._rng) for _ in range(count)]
        self._effect_cache[key] = (count, params)
        return params

    def _on_hover(self, hovered: bool):
        self._hovered = hovered
        if hovered:
            self.setScale(_HOVER_SCALE)
            glow = QGraphicsDropShadowEffect()
            glow.setColor(QColor(Colors.ACCENT))
            glow.setBlurRadius(24)
            glow.setOffset(0, 0)
            self.setGraphicsEffect(glow)
        else:
            self.setScale(1.0)
            self.setGraphicsEffect(None)
        self.update()

    def boundingRect(self) -> QRectF:
        r = _BASE_SIZE / 2 + _HOVER_PAD
        if self.props.effects:
            r = max(r, self.props.effect_radius + _HOVER_PAD)
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        if self.props.effects:
            phase = time.monotonic()
            for key in self.props.effects:
                drawer = EFFECT_DRAWERS.get(key)
                if drawer:
                    drawer(self, painter, self.props.effect_radius, phase, self.props.effect_intensity)

        plate_r = _BASE_SIZE / 2
        font = QFont()
        font.setPointSizeF(_BASE_SIZE * 0.65)
        painter.setFont(font)
        glyph_rect = QRectF(-plate_r, -plate_r, _BASE_SIZE, _BASE_SIZE)
        painter.drawText(glyph_rect, Qt.AlignmentFlag.AlignCenter, self.props.icon or "📍")


# ─── "Shader" effects — driven by time.monotonic() (no per-frame state to
# track; MarkerMediator's timer just calls .update() periodically) plus a
# per-marker random seed (MarkerItem._effect_params) so element count comes
# from Intensidade (0-100, see _intensity_count) while each element's
# angle/size/speed/phase is fixed-but-random instead of evenly spaced
# around a perfect circle — that regularity was what made every marker's
# effect look like the same looping stamp. ─────────────────────────────────

def _intensity_count(intensity: float, lo: int, hi: int) -> int:
    t = max(0.0, min(100.0, intensity)) / 100.0
    return max(lo, round(lo + (hi - lo) * t))


def _draw_redemoinhos(item, painter, radius: float, phase: float, intensity: float):
    count = _intensity_count(intensity, 1, 4)
    arms = item._effect_params("redemoinhos", count, lambda rng: dict(
        offset=rng.uniform(0, 360), speed=rng.uniform(40, 85),
        turns=rng.uniform(1.0, 1.9), spread=rng.uniform(0.75, 1.0),
        direction=rng.choice((1, -1)),
    ))
    painter.save()
    painter.setPen(QPen(QColor(120, 200, 255, 140), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    steps = 36
    for arm in arms:
        path = QPainterPath()
        for s in range(steps + 1):
            t = s / steps
            ang = math.radians(arm["offset"] + arm["direction"] * (phase * arm["speed"] + t * 360 * arm["turns"]))
            r = radius * 0.15 + radius * 0.85 * arm["spread"] * t
            x, y = r * math.cos(ang), r * math.sin(ang)
            path.moveTo(x, y) if s == 0 else path.lineTo(x, y)
        painter.drawPath(path)
    painter.restore()


def _draw_folhas(item, painter, radius: float, phase: float, intensity: float):
    count = _intensity_count(intensity, 2, 12)
    leaves = item._effect_params("folhas", count, lambda rng: dict(
        angle=rng.uniform(0, 360), radius_factor=rng.uniform(0.55, 1.1),
        drift_amp=rng.uniform(8, 24), drift_speed=rng.uniform(0.7, 2.3),
        bob_amp=rng.uniform(3, 10), bob_speed=rng.uniform(0.6, 1.9),
        spin_speed=rng.uniform(-70, 70), phase_offset=rng.uniform(0, 6.28),
        size=rng.uniform(7, 14), squash=rng.uniform(0.4, 0.65),
        green=rng.uniform(150, 215),
    ))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for leaf in leaves:
        ang = math.radians(leaf["angle"])
        drift = math.sin(phase * leaf["drift_speed"] + leaf["phase_offset"]) * leaf["drift_amp"]
        bob = math.cos(phase * leaf["bob_speed"] + leaf["phase_offset"]) * leaf["bob_amp"]
        cx = radius * leaf["radius_factor"] * math.cos(ang) + drift
        cy = radius * leaf["radius_factor"] * math.sin(ang) + bob
        painter.save()
        painter.translate(cx, cy)
        painter.rotate((phase * leaf["spin_speed"] + leaf["phase_offset"] * 57) % 360)
        painter.setBrush(QColor(90, int(leaf["green"]), 60, 190))
        w = leaf["size"]
        painter.drawEllipse(QRectF(-w / 2, -w * leaf["squash"] / 2, w, w * leaf["squash"]))
        painter.restore()
    painter.restore()


def _draw_nuvens(item, painter, radius: float, phase: float, intensity: float):
    count = _intensity_count(intensity, 1, 8)
    clouds = item._effect_params("nuvens", count, lambda rng: dict(
        angle=rng.uniform(0, 360), dist_factor=rng.uniform(0.3, 0.85),
        height_factor=rng.uniform(-0.9, -0.5), speed=rng.uniform(3, 15),
        w=rng.uniform(0.35, 0.8), h=rng.uniform(0.16, 0.34), squish=rng.uniform(0.8, 1.3),
        alpha_base=rng.uniform(70, 130), alpha_amp=rng.uniform(25, 65), alpha_phase=rng.uniform(0, 6.28),
    ))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for c in clouds:
        alpha = max(30, min(180, int(c["alpha_base"] + c["alpha_amp"] * math.sin(phase * 1.1 + c["alpha_phase"]))))
        painter.setBrush(QColor(55, 55, 68, alpha))
        ang = math.radians(c["angle"] + phase * c["speed"])
        cx = radius * c["dist_factor"] * math.cos(ang)
        cy = radius * c["height_factor"] + radius * 0.12 * math.sin(ang)
        w, h = radius * c["w"], radius * c["h"] * c["squish"]
        painter.drawEllipse(QRectF(cx - w / 2, cy - h / 2, w, h))
    painter.restore()

    if intensity >= 55:
        _draw_neblina(item, painter, radius, phase, intensity)
    if intensity >= 80:
        _draw_relampago(item, painter, radius, phase, intensity)


def _draw_neblina(item, painter, radius: float, phase: float, intensity: float):
    """Low drifting fog band — kicks in once Intensidade crosses 55 on the
    "nuvens" effect, growing more opaque up to 100."""
    strands = item._effect_params("neblina", 2, lambda rng: dict(
        speed=rng.uniform(0.3, 0.7), phase_offset=rng.uniform(0, 6.28), y_offset=rng.uniform(0.18, 0.32),
    ))
    t = max(0.0, min(1.0, (intensity - 55) / 45.0))
    alpha = int(25 + 55 * t)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for strand in strands:
        drift = math.sin(phase * strand["speed"] + strand["phase_offset"]) * radius * 0.25
        cy = radius * strand["y_offset"]
        w, h = radius * 1.6, radius * 0.22
        grad = QLinearGradient(-w / 2 + drift, cy, w / 2 + drift, cy)
        grad.setColorAt(0.0, QColor(210, 210, 220, 0))
        grad.setColorAt(0.5, QColor(210, 210, 220, alpha))
        grad.setColorAt(1.0, QColor(210, 210, 220, 0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QRectF(-w / 2 + drift, cy - h / 2, w, h))
    painter.restore()


def _draw_relampago(item, painter, radius: float, phase: float, intensity: float):
    """Occasional lightning flash — kicks in once Intensidade crosses 80 on
    the "nuvens" effect, flashing more often as it approaches 100."""
    seed = item._effect_params("relampago", 1, lambda rng: dict(
        offset=rng.uniform(0, 10), x=rng.uniform(-0.3, 0.3),
    ))[0]
    cycle = 4.0
    freq = 0.3 + 1.6 * max(0.0, min(1.0, (intensity - 80) / 20.0))
    t = (phase * freq + seed["offset"]) % cycle
    if t >= 0.14:
        return
    flash = 1.0 - t / 0.14
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, int(160 * flash)))
    painter.drawEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
    bx = seed["x"] * radius
    bolt = QPainterPath()
    bolt.moveTo(bx, -radius * 0.85)
    bolt.lineTo(bx + radius * 0.08, -radius * 0.5)
    bolt.lineTo(bx - radius * 0.05, -radius * 0.35)
    bolt.lineTo(bx + radius * 0.1, -radius * 0.05)
    painter.setPen(QPen(QColor(255, 255, 190, int(220 * flash) + 30), 2))
    painter.drawPath(bolt)
    painter.restore()


def _draw_espinhos(item, painter, radius: float, phase: float, intensity: float):
    count = _intensity_count(intensity, 4, 16)
    spikes = item._effect_params("espinhos", count, lambda rng: dict(
        angle=rng.uniform(0, 360), base_r=rng.uniform(0.85, 0.98), tip_r=rng.uniform(1.04, 1.28),
        width=rng.uniform(3, 7), breathe_speed=rng.uniform(2, 4.5),
        breathe_phase=rng.uniform(0, 6.28), breathe_amp=rng.uniform(0.03, 0.12),
    ))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(150, 120, 90, 200))
    for s in spikes:
        breathe = 1.0 + s["breathe_amp"] * math.sin(phase * s["breathe_speed"] + s["breathe_phase"])
        ang = math.radians(s["angle"])
        perp = ang + math.pi / 2
        base_r, tip_r = radius * s["base_r"], radius * s["tip_r"] * breathe
        bx, by = base_r * math.cos(ang), base_r * math.sin(ang)
        tx, ty = tip_r * math.cos(ang), tip_r * math.sin(ang)
        w = s["width"]
        p1 = QPointF(bx + w * math.cos(perp), by + w * math.sin(perp))
        p2 = QPointF(bx - w * math.cos(perp), by - w * math.sin(perp))
        p3 = QPointF(tx, ty)
        painter.drawPolygon(QPolygonF([p1, p2, p3]))
    painter.restore()


def _draw_brilho(item, painter, radius: float, phase: float, intensity: float):
    t = max(0.0, min(100.0, intensity)) / 100.0
    peak = int(80 + 130 * t)
    pulse = 0.5 + 0.5 * math.sin(phase * 2.0)
    painter.save()
    grad = QRadialGradient(0, 0, radius)
    grad.setColorAt(0.0, QColor(255, 235, 150, int(peak * pulse) + 20))
    grad.setColorAt(1.0, QColor(255, 235, 150, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
    painter.restore()


EFFECT_DRAWERS = {
    "redemoinhos": _draw_redemoinhos,
    "folhas": _draw_folhas,
    "nuvens": _draw_nuvens,
    "espinhos": _draw_espinhos,
    "brilho": _draw_brilho,
}
