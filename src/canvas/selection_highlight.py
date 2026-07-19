"""SelectionHighlight — perimeter outline for selected terrain layers.

A terrain layer's QGraphicsItem spans its entire raster canvas (e.g. 2048x2048),
not just the area that's actually been painted — so a bounding-box selection
rectangle around it is misleading (it covers mostly-empty space). This traces
the outer contour of the actually-painted (non-transparent) pixels instead,
unioned across every selected terrain layer into a single outer perimeter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QColor, QPainterPath, QPen, QRegion, QTransform
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsScene

from src.styles.tokens import Colors

if TYPE_CHECKING:
    from src.engines.map.terrain_layer import TerrainLayer

_MAX_CONTOUR_DIM = 512  # cap mask resolution before contour extraction, for speed


class SelectionHighlight:
    """Draws a combined perimeter outline around selected terrain layers' painted pixels."""

    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._item: QGraphicsPathItem | None = None

    def show(self, layers: list[TerrainLayer]):
        path = QPainterPath()
        for layer in layers:
            path = path.united(self._layer_contour_in_scene(layer))
        path = path.simplified()

        if not self._item:
            self._item = QGraphicsPathItem()
            pen = QPen(QColor(Colors.ACCENT), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._item.setPen(pen)
            self._item.setBrush(Qt.BrushStyle.NoBrush)
            self._item.setZValue(9999)
            self._scene.addItem(self._item)
        self._item.setPath(path)
        self._item.show()

    def hide(self):
        if self._item:
            self._item.hide()

    @staticmethod
    def _layer_contour_in_scene(layer: TerrainLayer) -> QPainterPath:
        img = layer.mask
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return QPainterPath()

        scale = min(1.0, _MAX_CONTOUR_DIM / max(w, h))
        small = img.scaled(
            max(1, round(w * scale)), max(1, round(h * scale)),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation,
        ) if scale < 1.0 else img

        bitmap = QBitmap.fromImage(small.createAlphaMask())
        region = QRegion(bitmap)
        path = QPainterPath()
        path.addRegion(region)

        if scale < 1.0:
            t = QTransform()
            t.scale(1.0 / scale, 1.0 / scale)
            path = t.map(path)

        return layer.item.mapToScene(path)
