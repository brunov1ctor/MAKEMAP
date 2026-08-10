"""Shared helpers for QGraphicsItem creation across canvas tools."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsItem, QStyle


def make_non_interactive(item: QGraphicsItem):
    """Purely decorative overlay item — never steals a click/hover meant for
    whatever it's drawn on top of (the item it's attached to, or another
    tool's placement underneath it), and can't be selected/dragged on its
    own. Shared by AssetEffectsOverlay, BrushEffectsOverlay,
    GlobalLightingOverlay and LightGhostItem, which used to each set these
    same four calls individually."""
    item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    item.setAcceptHoverEvents(False)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)


def enable_hover_glow(item: QGraphicsItem, on_hover_changed: Callable[[bool], None]):
    """Wires native Qt hover in/out on `item` to `on_hover_changed(True/False)`.

    Qt's hover dispatch (hoverEnterEvent/hoverLeaveEvent) still works scene-
    wide despite mouse events being monkey-patched to route through the tool
    system instead of QGraphicsView's own dispatch (see CanvasEngine.
    _on_mouse_move's replay of QGraphicsView.mouseMoveEvent whenever no
    button is held) — it just needs `setAcceptHoverEvents(True)` and the two
    handlers, which a plain QGraphicsPixmapItem doesn't have by default.
    Reassigning them directly on the instance (same monkeypatch technique
    suppress_selection_decoration already uses for `.paint` below) avoids
    needing a dedicated subclass for every stamp-like item type that wants
    hover feedback."""
    item.setAcceptHoverEvents(True)

    def hover_enter(event):
        on_hover_changed(True)

    def hover_leave(event):
        on_hover_changed(False)

    item.hoverEnterEvent = hover_enter
    item.hoverLeaveEvent = hover_leave
    # Same glow, triggered programmatically instead of by a real mouse
    # hover — used by ExplorerSyncMediator so hovering a card in the
    # Explorer panel highlights the item on canvas the same way mousing
    # over it directly would.
    item.set_explorer_highlight = on_hover_changed


def suppress_selection_decoration(item: QGraphicsItem):
    """Disable Qt's built-in dashed selection rectangle on this item.

    The app has its own selection UI (TransformEngine's resize/rotate
    handles) — Qt's default "marching ants" rectangle around the item's
    full bounding box is redundant on top of that and, for terrain layers
    especially, misleading (their bounding box is the whole raster canvas,
    not the painted area).
    """
    original_paint = item.paint

    def paint(painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        original_paint(painter, option, widget)

    item.paint = paint
