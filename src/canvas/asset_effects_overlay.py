"""AssetEffectsOverlay — a decorative child item attached (via
setParentItem) to a placed asset stamp (a QGraphicsPixmapItem with
data(0)["item_type"] == "asset") whenever that asset's definition has
painted effect cells (see src/engines/asset_effects.py). Being a child, it
follows the stamp's position/rotation/scale for free — no coordinate
bookkeeping needed. See AssetEffectsMediator for how/when these get
attached (reactive scan, no changes to brush_tool.py's placement code).
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QRadialGradient, QPainter
from PySide6.QtWidgets import QGraphicsItem

from src.engines.asset_effects import ASSET_EFFECT_TYPES, EFFECT_GRID_SIZE, PARAM_DEFAULT, normalize_layers

_BLEND_COMPOSITION_MODES = {
    "normal": QPainter.CompositionMode.CompositionMode_SourceOver,
    "additive": QPainter.CompositionMode.CompositionMode_Plus,
}

# How much bigger than "one raw grid cell" every drawer's glow/spark/ring
# actually renders — see paint()'s cell_size calculation.
_CELL_VISUAL_BOOST = 3.5


class AssetEffectsOverlay(QGraphicsItem):
    def __init__(self, parent_item: QGraphicsItem, layers: dict[str, dict]):
        super().__init__(parent_item)
        self.layers = normalize_layers(layers)
        # Purely decorative — must never steal a click meant for the
        # underlying stamp (selecting/dragging it). Without this, being a
        # child (children hit-test before their parent) would silently
        # break clicking the asset it's attached to.
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        parent_item._effects_overlay = self

    def set_cells(self, layers: dict[str, dict]):
        self.layers = normalize_layers(layers)
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        parent = self.parentItem()
        return parent.boundingRect() if parent is not None else QRectF()

    def paint(self, painter, option, widget=None):
        parent = self.parentItem()
        if parent is None:
            return
        rect = parent.boundingRect()
        n = EFFECT_GRID_SIZE
        cw, ch = rect.width() / n, rect.height() / n
        # Every drawer below sizes its glow/spark/ring as a fraction of
        # this ONE grid cell (1/24th of the asset), which reads fine in
        # the editor panel's fixed 280x280 preview (cell_size ~11-12px)
        # but shrinks to just a couple pixels — effectively invisible —
        # once placed on the actual map, where the asset (and therefore
        # each cell) is often only a few dozen px on screen. Boosting it
        # here (not tuning all 5 drawers' own constants separately) keeps
        # painted regions overlapping into one visible glow/cloud instead
        # of 24x24 near-invisible dots.
        cell_size = min(cw, ch) * _CELL_VISUAL_BOOST
        phase = time.monotonic()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        # One effect type at a time, in a fixed order, so two overlapping
        # layers always composite the same way regardless of paint order —
        # each layer gets its own opacity/blend mode applied to the whole
        # pass, then painter state is restored before the next layer.
        for key, _icon, _label in ASSET_EFFECT_TYPES:
            layer = self.layers.get(key)
            if not layer or not layer["visible"]:
                continue
            drawer = _EFFECT_DRAWERS.get(key)
            if drawer is None:
                continue
            cells = layer["cells"]
            if not any(cells):
                continue
            # Sliders are 0-10 with 5 as the neutral/default value (see
            # _EffectConfigBlock) — dividing by PARAM_DEFAULT here turns
            # that into the x1-at-5 multiplier every drawer below actually
            # expects (0 = no effect, 5 = normal, 10 = double), so the
            # drawers' own hardcoded alpha/size constants don't need to
            # know anything changed. Brilho lightens/darkens the layer's
            # own Cor the same way (QColor.lighter's 100=no-change scale).
            base_color = QColor(layer.get("color", "#FFFFFF"))
            if not base_color.isValid():
                base_color = QColor(255, 255, 255)
            brightness_mult = layer.get("brightness", PARAM_DEFAULT) / PARAM_DEFAULT
            brightness_factor = max(10, round(100 * brightness_mult))
            tint = base_color if brightness_factor == 100 else base_color.lighter(brightness_factor)
            params = {
                "color": tint,
                "intensity": layer.get("intensity", PARAM_DEFAULT) / PARAM_DEFAULT,
                "radius": layer.get("radius", PARAM_DEFAULT) / PARAM_DEFAULT,
            }

            painter.save()
            painter.setOpacity(layer["opacity"] / 100.0)
            painter.setCompositionMode(_BLEND_COMPOSITION_MODES.get(layer["blend"], _BLEND_COMPOSITION_MODES["normal"]))
            for idx, on in enumerate(cells):
                if not on:
                    continue
                x, y = idx % n, idx // n
                center = QPointF(rect.left() + (x + 0.5) * cw, rect.top() + (y + 0.5) * ch)
                drawer(painter, center, cell_size, phase, idx, params)
            painter.restore()


def _draw_emissivo(painter, center: QPointF, size: float, phase: float, idx: int, params: dict):
    radius = size * 0.9 * params["radius"]
    pulse = 0.8 + 0.2 * math.sin(phase * 2 + idx)
    color = params["color"]
    inner = QColor(color); inner.setAlpha(min(255, round(200 * pulse * params["intensity"])))
    outer = QColor(color); outer.setAlpha(0)
    grad = QRadialGradient(center, radius)
    grad.setColorAt(0.0, inner)
    grad.setColorAt(1.0, outer)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(center, radius, radius)


def _draw_aura(painter, center: QPointF, size: float, phase: float, idx: int, params: dict):
    r = size * 0.5 * params["radius"] * (0.7 + 0.3 * math.sin(phase * 1.5 + idx))
    color = QColor(params["color"]); color.setAlpha(min(255, round(160 * params["intensity"])))
    painter.setPen(QPen(color, 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(center, r, r)


def _draw_glitter(painter, center: QPointF, size: float, phase: float, idx: int, params: dict):
    painter.setPen(Qt.PenStyle.NoPen)
    n = 4
    for i in range(n):
        twinkle = (math.sin(phase * 4 + idx * 3 + i * 2) + 1) / 2
        if twinkle < 0.5:
            continue
        ang = (2 * math.pi / n) * i + idx
        d = size * 0.4 * params["radius"]
        p = QPointF(center.x() + d * math.cos(ang), center.y() + d * math.sin(ang))
        s = size * 0.08 * params["radius"] * twinkle
        color = QColor(params["color"]); color.setAlpha(min(255, round(220 * twinkle * params["intensity"])))
        painter.setBrush(color)
        painter.drawEllipse(p, s, s)


def _draw_fumaca(painter, center: QPointF, size: float, phase: float, idx: int, params: dict):
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(2):
        t = (phase * 0.3 + i * 0.5 + idx * 0.1) % 1.0
        p = QPointF(center.x(), center.y() - size * 1.2 * params["radius"] * t)
        r = size * params["radius"] * (0.3 + 0.3 * t)
        color = QColor(params["color"]); color.setAlpha(min(255, round(120 * (1 - t) * params["intensity"])))
        painter.setBrush(color)
        painter.drawEllipse(p, r, r)


def _draw_distorcao(painter, center: QPointF, size: float, phase: float, idx: int, params: dict):
    color = QColor(params["color"]); color.setAlpha(min(255, round(110 * params["intensity"])))
    painter.setPen(QPen(color, 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(3):
        t = (phase * 0.6 + i / 3 + idx * 0.05) % 1.0
        r = size * 0.9 * params["radius"] * t
        painter.drawEllipse(center, r, r)


_EFFECT_DRAWERS = {
    "emissivo": _draw_emissivo,
    "aura": _draw_aura,
    "glitter": _draw_glitter,
    "fumaca": _draw_fumaca,
    "distorcao": _draw_distorcao,
}
