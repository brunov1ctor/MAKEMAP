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
from PySide6.QtGui import QColor, QBrush, QPen, QRadialGradient
from PySide6.QtWidgets import QGraphicsItem

from src.engines.asset_effects import EFFECT_GRID_SIZE


class AssetEffectsOverlay(QGraphicsItem):
    def __init__(self, parent_item: QGraphicsItem, cells: list[str]):
        super().__init__(parent_item)
        self.cells = cells
        # Purely decorative — must never steal a click meant for the
        # underlying stamp (selecting/dragging it). Without this, being a
        # child (children hit-test before their parent) would silently
        # break clicking the asset it's attached to.
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        parent_item._effects_overlay = self

    def set_cells(self, cells: list[str]):
        self.cells = cells
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
        cell_size = min(cw, ch)
        phase = time.monotonic()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        for idx, key in enumerate(self.cells):
            if not key:
                continue
            drawer = _EFFECT_DRAWERS.get(key)
            if drawer is None:
                continue
            x, y = idx % n, idx // n
            center = QPointF(rect.left() + (x + 0.5) * cw, rect.top() + (y + 0.5) * ch)
            drawer(painter, center, cell_size, phase, idx)


def _draw_emissivo(painter, center: QPointF, size: float, phase: float, idx: int):
    radius = size * 0.9
    pulse = 0.8 + 0.2 * math.sin(phase * 2 + idx)
    grad = QRadialGradient(center, radius)
    grad.setColorAt(0.0, QColor(255, 220, 150, int(200 * pulse)))
    grad.setColorAt(1.0, QColor(255, 220, 150, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(center, radius, radius)


def _draw_aura(painter, center: QPointF, size: float, phase: float, idx: int):
    r = size * 0.5 * (0.7 + 0.3 * math.sin(phase * 1.5 + idx))
    painter.setPen(QPen(QColor(150, 200, 255, 160), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(center, r, r)


def _draw_glitter(painter, center: QPointF, size: float, phase: float, idx: int):
    painter.setPen(Qt.PenStyle.NoPen)
    n = 4
    for i in range(n):
        twinkle = (math.sin(phase * 4 + idx * 3 + i * 2) + 1) / 2
        if twinkle < 0.5:
            continue
        ang = (2 * math.pi / n) * i + idx
        d = size * 0.4
        p = QPointF(center.x() + d * math.cos(ang), center.y() + d * math.sin(ang))
        s = size * 0.08 * twinkle
        painter.setBrush(QColor(255, 255, 255, int(220 * twinkle)))
        painter.drawEllipse(p, s, s)


def _draw_fumaca(painter, center: QPointF, size: float, phase: float, idx: int):
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(2):
        t = (phase * 0.3 + i * 0.5 + idx * 0.1) % 1.0
        p = QPointF(center.x(), center.y() - size * 1.2 * t)
        r = size * (0.3 + 0.3 * t)
        painter.setBrush(QColor(150, 130, 170, int(120 * (1 - t))))
        painter.drawEllipse(p, r, r)


def _draw_distorcao(painter, center: QPointF, size: float, phase: float, idx: int):
    painter.setPen(QPen(QColor(180, 220, 255, 110), 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(3):
        t = (phase * 0.6 + i / 3 + idx * 0.05) % 1.0
        r = size * 0.9 * t
        painter.drawEllipse(center, r, r)


_EFFECT_DRAWERS = {
    "emissivo": _draw_emissivo,
    "aura": _draw_aura,
    "glitter": _draw_glitter,
    "fumaca": _draw_fumaca,
    "distorcao": _draw_distorcao,
}
