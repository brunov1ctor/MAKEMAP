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

from src.canvas.contact_shadow import draw_contact_shadow
from src.canvas.item_utils import enable_hover_glow
from src.engines.marker import MarkerProperties, normalize_effect_layers
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
            layers = self.props.effect_layers or {}
            radii = [layers.get(k, {}).get("radius", self.props.effect_radius) for k in self.props.effects]
            if radii:
                r = max(r, max(radii) + _HOVER_PAD)
        if self.props.shadow_enabled:
            r = max(r, _BASE_SIZE * 0.9 + _HOVER_PAD)
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        # Normalized once here (not just on load) so edits made live through
        # MarkerEditPanel — which only ever touch the keys it changed — still
        # paint correctly for any effect a menu toggle just activated without
        # an existing layer entry yet.
        layers = normalize_effect_layers(
            self.props.effect_layers, self.props.effects, self.props.effect_radius, self.props.effect_intensity,
        )
        self.props.effect_layers = layers

        if self.props.shadow_enabled:
            _draw_contact_shadow(painter, self.props.shadow_strength)

        if self.props.effects:
            phase = time.monotonic()
            for key in self.props.effects:
                drawer = EFFECT_DRAWERS.get(key)
                layer = layers.get(key)
                if drawer and layer:
                    painter.save()
                    painter.setOpacity(layer["opacity"] / 100)
                    drawer(self, painter, layer, phase)
                    painter.restore()

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


def _draw_contact_shadow(painter, strength: float):
    """Soft dark ellipse under the icon, grounding the marker instead of
    letting it float — independent of the 5 shader effects, so it's always
    drawn first (beneath everything else) regardless of which are active."""
    t = max(0.0, min(100.0, strength)) / 100.0
    if t <= 0:
        return
    w = _BASE_SIZE * (0.7 + 0.4 * t)
    h = w * 0.34
    cy = _BASE_SIZE * 0.4 + h * 0.15
    alpha = int(60 + 110 * t)
    draw_contact_shadow(painter, 0, cy, w, alpha_center=alpha, alpha_mid=int(alpha * 0.35), squash=0.34)


def _draw_redemoinhos(item, painter, layer: dict, phase: float):
    radius, intensity = layer["radius"], layer["intensity"]
    color = QColor(layer["color"])
    count = _intensity_count(intensity, 1, 4)
    arms = item._effect_params("redemoinhos", count, lambda rng: dict(
        offset=rng.uniform(0, 360), speed=rng.uniform(40, 85),
        turns=rng.uniform(1.0, 1.9), spread=rng.uniform(0.75, 1.0),
        direction=rng.choice((1, -1)),
    ))
    painter.save()
    steps = 36
    for arm in arms:
        prev = None
        for s in range(steps + 1):
            t = s / steps
            ang = math.radians(arm["offset"] + arm["direction"] * (phase * arm["speed"] + t * 360 * arm["turns"]))
            r = radius * 0.15 + radius * 0.85 * arm["spread"] * t
            pt = QPointF(r * math.cos(ang), r * math.sin(ang))
            if prev is not None:
                # Fades in from the center outward, like a comet trail,
                # instead of one constant-alpha stroke along the whole arm.
                alpha = int(30 + 170 * t)
                painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), alpha), 2))
                painter.drawLine(prev, pt)
            prev = pt
    painter.restore()


def _draw_folhas(item, painter, layer: dict, phase: float):
    radius, intensity = layer["radius"], layer["intensity"]
    base = QColor(layer["color"])
    base.setAlpha(190)
    count = _intensity_count(intensity, 2, 12)
    leaves = item._effect_params("folhas", count, lambda rng: dict(
        angle=rng.uniform(0, 360), radius_factor=rng.uniform(0.55, 1.1),
        drift_amp=rng.uniform(8, 24), drift_speed=rng.uniform(0.7, 2.3),
        bob_amp=rng.uniform(3, 10), bob_speed=rng.uniform(0.6, 1.9),
        spin_speed=rng.uniform(-70, 70), phase_offset=rng.uniform(0, 6.28),
        size=rng.uniform(7, 14), squash=rng.uniform(0.4, 0.65),
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
        w = leaf["size"]
        h = w * leaf["squash"]
        # Own soft shadow, offset slightly down-right, before the lit leaf
        # itself — gives each leaf a sense of catching light instead of
        # reading as a flat cutout.
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawEllipse(QRectF(-w / 2 + w * 0.12, -h / 2 + h * 0.25, w, h))
        grad = QLinearGradient(-w / 2, -h / 2, w / 2, h / 2)
        grad.setColorAt(0.0, base.lighter(135))
        grad.setColorAt(1.0, base.darker(125))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QRectF(-w / 2, -h / 2, w, h))
        painter.restore()
    painter.restore()


def _draw_nuvens(item, painter, layer: dict, phase: float):
    radius, intensity = layer["radius"], layer["intensity"]
    base = QColor(layer["color"])
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
        ang = math.radians(c["angle"] + phase * c["speed"])
        cx = radius * c["dist_factor"] * math.cos(ang)
        cy = radius * c["height_factor"] + radius * 0.12 * math.sin(ang)
        w, h = radius * c["w"], radius * c["h"] * c["squish"]
        # A darker, offset duplicate underneath reads as the cloud's own
        # shadow/underside instead of one uniform-lit blob.
        painter.setBrush(QColor(0, 0, 0, int(alpha * 0.5)))
        painter.drawEllipse(QRectF(cx - w / 2 + w * 0.08, cy - h / 2 + h * 0.18, w, h))
        painter.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
        painter.drawEllipse(QRectF(cx - w / 2, cy - h / 2, w, h))
    painter.restore()

    if intensity >= 55:
        _draw_neblina(item, painter, layer, phase)
    if intensity >= 80:
        _draw_relampago(item, painter, layer, phase)


def _draw_neblina(item, painter, layer: dict, phase: float):
    """Low drifting fog band — kicks in once Intensidade crosses 55 on the
    "nuvens" effect, growing more opaque up to 100."""
    radius, intensity = layer["radius"], layer["intensity"]
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


def _draw_relampago(item, painter, layer: dict, phase: float):
    """Occasional lightning flash — kicks in once Intensidade crosses 80 on
    the "nuvens" effect, flashing more often as it approaches 100."""
    radius, intensity = layer["radius"], layer["intensity"]
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


def _draw_espinhos(item, painter, layer: dict, phase: float):
    radius, intensity = layer["radius"], layer["intensity"]
    base = QColor(layer["color"])
    base.setAlpha(200)
    count = _intensity_count(intensity, 4, 16)
    spikes = item._effect_params("espinhos", count, lambda rng: dict(
        angle=rng.uniform(0, 360), base_r=rng.uniform(0.85, 0.98), tip_r=rng.uniform(1.04, 1.28),
        width=rng.uniform(3, 7), breathe_speed=rng.uniform(2, 4.5),
        breathe_phase=rng.uniform(0, 6.28), breathe_amp=rng.uniform(0.03, 0.12),
    ))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
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
        # Base-to-tip gradient (dark root, lit tip) instead of one flat
        # fill — gives each spike a sense of volume/directional light.
        grad = QLinearGradient(QPointF(bx, by), QPointF(tx, ty))
        grad.setColorAt(0.0, base.darker(145))
        grad.setColorAt(1.0, base.lighter(140))
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(QPolygonF([p1, p2, p3]))
    painter.restore()


def _draw_brilho(item, painter, layer: dict, phase: float):
    radius, intensity = layer["radius"], layer["intensity"]
    base = QColor(layer["color"])
    t = max(0.0, min(100.0, intensity)) / 100.0
    peak = int(80 + 130 * t)
    pulse = 0.5 + 0.5 * math.sin(phase * 2.0)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    # Wide, dim outer halo behind the tighter core glow — two overlapping
    # gradients read as a softer, deeper glow than one alone.
    outer = QRadialGradient(0, 0, radius * 1.3)
    outer.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), int(peak * pulse * 0.35)))
    outer.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
    painter.setBrush(QBrush(outer))
    painter.drawEllipse(QRectF(-radius * 1.3, -radius * 1.3, radius * 2.6, radius * 2.6))
    grad = QRadialGradient(0, 0, radius)
    grad.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), int(peak * pulse) + 20))
    grad.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
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
