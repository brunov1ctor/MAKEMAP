"""Stateless selection queries — pure functions that find candidate items
and return them as a list. Never mutate selection state; the caller decides
what to do with the result (SelectionEngine.set/add/...). Each function
takes `is_selectable` as an explicit predicate so this module stays free of
any engine/UI state (see SelectionEngine.is_selectable for the live one,
which folds in the current layer filter)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

IsSelectable = Callable[[QGraphicsItem], bool]


def items_in_rect(scene: QGraphicsScene, rect: QRectF, is_selectable: IsSelectable) -> list[QGraphicsItem]:
    """Items within a rectangle.

    Uses the default IntersectsItemShape mode (each item's real shape(),
    not just its coarse axis-aligned boundingRect()) — required for raster
    layers (TerrainLayer/_LayerItem, RegionLayer's zone fill) whose
    boundingRect() covers their whole raster canvas (up to 4096px)
    regardless of how little is actually painted; their shape() traces just
    the painted pixels instead. IntersectsItemShape gives identical results
    to IntersectsItemBoundingRect for ordinary sprites (asset/mob/npc
    stamps), since those opt into ShapeMode.BoundingRectShape precisely so
    their shape() already equals their bounding rect — see
    place_stamp_item/build_stamp_item.
    """
    return [
        item for item in scene.items(rect, Qt.ItemSelectionMode.IntersectsItemShape)
        if is_selectable(item) and item.parentItem() is None and item.isVisible()
    ]


def items_in_polygon(scene: QGraphicsScene, polygon: QPolygonF, is_selectable: IsSelectable) -> list[QGraphicsItem]:
    """Items within a freeform polygon."""
    return [
        item for item in scene.items(polygon)
        if is_selectable(item) and item.parentItem() is None and item.isVisible()
    ]


def items_all_selectable(scene: QGraphicsScene, is_selectable: IsSelectable) -> list[QGraphicsItem]:
    """Every currently selectable item in the scene."""
    return [
        item for item in scene.items()
        if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        and is_selectable(item) and item.isVisible()
    ]


def items_inverse(scene: QGraphicsScene, currently_selected: list[QGraphicsItem],
                   is_selectable: IsSelectable) -> list[QGraphicsItem]:
    """Every selectable item NOT in `currently_selected`."""
    selected = set(currently_selected)
    return [
        item for item in scene.items()
        if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        and is_selectable(item) and item not in selected and item.isVisible()
    ]
