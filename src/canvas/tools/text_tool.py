"""TextTool — click to drop a new draggable/rotatable text object; click an
existing one (or one of its handles) to select/drag/rotate/resize it
instead (a further click/double-click edits it). See PlacementTool for the
shared click-an-existing-item-vs-place-a-new-one flow."""

from __future__ import annotations

from PySide6.QtCore import Qt

from src.canvas.tools.placement_tool import PlacementTool
from src.canvas.text_item import TextItem
from src.canvas.z_order import ZOrder
from src.engines.typography import TextProperties


class TextTool(PlacementTool):
    """Professional-editor-style text tool: stays active across placements
    (like Illustrator/Figma's Type tool) so multiple labels can be dropped
    in a row without reselecting the tool each time. Clicking an existing
    text object (or one of its selection handles) manipulates it directly
    instead of creating a new one on top of it."""

    name = "Texto"
    shortcut = "T"
    cursor = Qt.CursorShape.IBeamCursor
    item_cls = TextItem
    z_value = ZOrder.TOOL_PREVIEW

    def __init__(
        self, viewport, tool_manager=None, history_engine=None, selection_engine=None,
        transform_engine=None, on_committed=None, properties_provider=None, on_edited=None,
    ):
        super().__init__(
            viewport, tool_manager, history_engine, selection_engine, transform_engine,
            on_placed=on_committed, properties_provider=properties_provider,
        )
        self._on_edited = on_edited

    def set_on_edited(self, callback):
        """callback() wired onto every new TextItem's persistent on_edited
        hook — TextMediator uses this to know when to save, since retyping
        an EXISTING text (double-click, not a fresh placement) never touches
        HistoryEngine and would otherwise go unsaved."""
        self._on_edited = callback

    def _default_properties(self):
        return TextProperties(text="Texto", font_size=20, font_weight=600)

    def _make_item(self, props):
        return TextItem(props)

    def _after_place(self, item):
        # start_editing() before selecting: CanvasEngine._on_selection_changed
        # skips showing resize/rotate handles for a TextItem mid inline-edit
        # (is_editing() check) — selecting first would show them a beat too
        # early, then leave them stuck since editing doesn't re-fire
        # selection_changed on its own.
        item.on_commit = self._handle_commit
        item.on_edited = self._on_edited
        item.start_editing()

    def _handle_commit(self):
        """Fired once, by the item itself, when the very first edit right
        after placement commits (Enter / click outside). Placement already
        switched tools/closed the panel (see PlacementTool.mouse_press) —
        this is now just a safety net in case that ever changes."""
        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_placed:
            self._on_placed()
