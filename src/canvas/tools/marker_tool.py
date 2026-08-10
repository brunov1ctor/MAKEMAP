"""MarkerTool — click to drop a "point of interest" pin; click an existing
one to select/drag/rotate/resize it instead (see PlacementTool for the
shared click-an-existing-item-vs-place-a-new-one flow)."""

from __future__ import annotations

from PySide6.QtCore import Qt

from src.canvas.tools.placement_tool import PlacementTool
from src.canvas.marker_item import MarkerItem
from src.engines.marker import MarkerProperties


class MarkerTool(PlacementTool):
    """set_properties_provider(provider): provider() -> MarkerProperties,
    read at the moment a new marker is placed — MarkerMediator hands over
    whichever icon is currently picked in the Marcador tool panel."""

    name = "Marcador"
    shortcut = "K"
    cursor = Qt.CursorShape.CrossCursor
    item_cls = MarkerItem

    def _default_properties(self):
        return MarkerProperties()

    def _make_item(self, props):
        return MarkerItem(props)
