"""Box-select drag gesture — press on empty space, drag past a small
threshold, release to select everything the rect touches."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from src.canvas.z_order import ZOrder
from src.engines.core.selection import queries


class BoxSelectMixin:
    # Below this (scene units), a press+release on empty space reads as a
    # plain click (deselect + hand off to Pan) rather than a box-select drag.
    _DRAG_THRESHOLD = 3

    def _box_begin(self, scene_pos: QPointF):
        self._start = scene_pos
        self._box_pending = True

    def _box_update(self, scene_pos: QPointF) -> bool:
        if not (self._box_pending and self._start is not None):
            return False
        delta = scene_pos - self._start
        if self._box_item is None:
            if math.hypot(delta.x(), delta.y()) < self._DRAG_THRESHOLD:
                return True
            self._box_item = QGraphicsRectItem()
            self._box_item.setPen(QPen(QColor(79, 195, 247, 180), 1.5, Qt.PenStyle.DashLine))
            self._box_item.setBrush(QColor(79, 195, 247, 20))
            self._box_item.setZValue(ZOrder.CURSOR_GHOST)
            self.viewport.scene().addItem(self._box_item)
        self._box_item.setRect(QRectF(self._start, scene_pos).normalized())
        return True

    def _box_finish(self):
        if not self._box_pending:
            return
        if self._box_item is not None:
            # Real drag — box selection, stay on Select so the result can be
            # immediately moved/resized (matches lasso). Always replaces the
            # selection — Shift made no observed difference here (box-select
            # already unions everything the rect touches) and was just dead
            # weight on this path.
            scene = self.viewport.scene()
            box_rect = self._box_item.rect()
            items = queries.items_in_rect(scene, box_rect, self._selection.is_selectable)
            self._selection.set(items)
            # Remember which item-local rect actually touched each item —
            # same "which blob(s) did they mean" narrowing set_selection_
            # anchor does for a direct click, but for a box-select drag
            # (see set_selection_rect on _LayerItem). set() above already
            # fired selection_changed with the whole-layer fallback, so
            # re-notify once every rect is in place, same reasoning as
            # select_and_begin_drag's own re-notify.
            had_scoped = False
            for item in items:
                set_rect = getattr(item, "set_selection_rect", None)
                if set_rect is not None:
                    set_rect(item.mapRectFromScene(box_rect))
                    had_scoped = True
            if had_scoped:
                self._selection.notify_changed()
            self.viewport.scene().removeItem(self._box_item)
            self._box_item = None
        else:
            # Released without moving — a plain click on empty space,
            # nothing here to select or drag. Unlike a placement tool
            # (Texto/Spawn) handing off to Pan after placing one object,
            # Select's whole job is clicking things — bouncing it to Pan on
            # every miss turned a near-miss (e.g. a click landing on a
            # sprite's transparent margin, just outside its opaque pixels)
            # into "the tool switches itself off", making it look like
            # clicking an object deselects instead of selecting it. Just
            # clear the selection and stay put.
            self._selection.clear()
        self._box_pending = False
        self._start = None
