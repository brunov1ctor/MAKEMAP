"""VertexHandlesOverlay — small corner-circle markers at each point of a
"Livre" terreno boundary while it's being drawn/edited.

Matches the Select tool's own hover-handle look (white fill, accent-
colored outline — see TransformEngine._HoverHandle) so editing a terrain's
shape reads with the same "these are the corners" visual language used
everywhere else in the app. Purely visual here (not draggable) — actual
point dragging is TerrainFreehandTool's own last-point-only interaction.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPen, QBrush
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsScene

from src.canvas.z_order import ZOrder
from src.styles.tokens import Colors

HANDLE_SIZE = 10.0


class VertexHandlesOverlay:
    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._handles: list[QGraphicsEllipseItem] = []

    def set_points(self, points: list) -> None:
        while len(self._handles) < len(points):
            handle = QGraphicsEllipseItem(-HANDLE_SIZE / 2, -HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE)
            handle.setBrush(QBrush(QColor("#FFFFFF")))
            pen = QPen(QColor(Colors.ACCENT), 1.5)
            pen.setCosmetic(True)
            handle.setPen(pen)
            handle.setZValue(ZOrder.PLACED_GIZMO)  # above the neon overlay (ZOrder.TOOL_PREVIEW) and the boundary
            self._scene.addItem(handle)
            self._handles.append(handle)
        while len(self._handles) > len(points):
            handle = self._handles.pop()
            if handle.scene():
                self._scene.removeItem(handle)
        for handle, pt in zip(self._handles, points):
            handle.setPos(pt)

    def remove(self) -> None:
        for handle in self._handles:
            if handle.scene():
                self._scene.removeItem(handle)
        self._handles = []
