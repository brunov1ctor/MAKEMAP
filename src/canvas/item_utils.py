"""Shared helpers for QGraphicsItem creation across canvas tools."""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsItem, QStyle


def suppress_selection_decoration(item: QGraphicsItem):
    """Disable Qt's built-in dashed selection rectangle on this item.

    The app has its own selection UI (TransformEngine's resize/rotate handles,
    SelectionHighlight's mask contour for terrain) — Qt's default "marching
    ants" rectangle around the item's full bounding box is redundant on top
    of those and, for terrain layers especially, misleading (their bounding
    box is the whole raster canvas, not the painted area).
    """
    original_paint = item.paint

    def paint(painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        original_paint(painter, option, widget)

    item.paint = paint
