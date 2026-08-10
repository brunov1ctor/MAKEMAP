"""Lasso-select gesture — the one deliberate multi-select drag kept as an
explicit modifier (Alt+drag), not a plain click. See box_select.py for the
default drag gesture."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPathItem

from src.canvas.z_order import ZOrder
from src.engines.core.selection import queries


class LassoSelectMixin:
    def _lasso_begin(self, scene_pos: QPointF):
        self._lasso_points = [scene_pos]
        self._lasso_path = QGraphicsPathItem()
        self._lasso_path.setPen(QPen(QColor(79, 195, 247, 180), 1.5, Qt.PenStyle.DashLine))
        self._lasso_path.setBrush(QColor(79, 195, 247, 20))
        self._lasso_path.setZValue(ZOrder.CURSOR_GHOST)
        self.viewport.scene().addItem(self._lasso_path)

    def _lasso_update(self, scene_pos: QPointF) -> bool:
        if not (self._lasso_mode and self._lasso_path):
            return False
        self._lasso_points.append(scene_pos)
        path = QPainterPath()
        path.moveTo(self._lasso_points[0])
        for pt in self._lasso_points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        self._lasso_path.setPath(path)
        return True

    def _lasso_finish(self, add: bool):
        if len(self._lasso_points) > 2:
            polygon = QPolygonF(self._lasso_points)
            items = queries.items_in_polygon(self.viewport.scene(), polygon, self._selection.is_selectable)
            if add:
                self._selection.add(items)
            else:
                self._selection.set(items)
        self.viewport.scene().removeItem(self._lasso_path)
        self._lasso_path = None
        self._lasso_points.clear()
        self._lasso_mode = False
        self._start = None
