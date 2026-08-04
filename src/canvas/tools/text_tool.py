"""TextTool — click to drop a new draggable/rotatable text object; click an
existing one (or one of its handles) to select/drag/rotate/resize it
instead (a further click/double-click edits it)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.canvas.text_item import TextItem
from src.engines.typography import TextProperties
from src.engines.core.history import PlaceObjectCommand


class TextTool(BaseTool):
    """Professional-editor-style text tool: stays active across placements
    (like Illustrator/Figma's Type tool) so multiple labels can be dropped
    in a row without reselecting the tool each time. Clicking an existing
    text object (or one of its selection handles) manipulates it directly
    instead of creating a new one on top of it."""

    name = "Texto"
    shortcut = "T"
    cursor = Qt.CursorShape.IBeamCursor

    def __init__(
        self, viewport, tool_manager=None, history_engine=None, selection_engine=None,
        transform_engine=None, on_committed=None, properties_provider=None, on_edited=None,
    ):
        super().__init__(viewport)
        self._tool_manager = tool_manager
        self._history = history_engine
        self._selection = selection_engine
        self._on_committed = on_committed
        self._properties_provider = properties_provider
        self._on_edited = on_edited
        self._parent_provider = None
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None

    def set_properties_provider(self, provider):
        """provider() -> TextProperties, read at the moment a new text box
        is placed — lets MainLayout hand over whatever the Text panel is
        currently configured to (color, shadow, outline...) instead of
        always starting from hardcoded defaults."""
        self._properties_provider = provider

    def set_parent_provider(self, provider):
        """provider() -> QGraphicsItem | None — boundary group para parenting."""
        self._parent_provider = provider

    def set_on_edited(self, callback):
        """callback() wired onto every new TextItem's persistent on_edited
        hook — TextMediator uses this to know when to save, since retyping
        an EXISTING text (double-click, not a fresh placement) never touches
        HistoryEngine and would otherwise go unsaved."""
        self._on_edited = callback

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # item_filter=isinstance(TextItem): clicking on top of a painted
        # região/terrain (also selectable layers) must still place a new
        # text box, not hijack the click into selecting/dragging that
        # other layer — only an EXISTING TextItem should be picked up here.
        if self._interaction and self._interaction.try_begin(scene_pos, item_filter=lambda it: isinstance(it, TextItem)):
            return

        props = self._properties_provider() if self._properties_provider else \
            TextProperties(text="Texto", font_size=20, font_weight=600)
        parent_item = self._parent_provider() if self._parent_provider else None
        item = TextItem(props)
        item.setPos(scene_pos if not parent_item else parent_item.mapFromScene(scene_pos))
        item.setZValue(50)
        if parent_item:
            item.setParentItem(parent_item)
        else:
            self.viewport.scene().addItem(item)
        if self._history:
            self._history.push(PlaceObjectCommand(item))

        # start_editing() before selecting: CanvasEngine._on_selection_changed
        # skips showing resize/rotate handles for a TextItem mid inline-edit
        # (is_editing() check) — selecting first would show them a beat too
        # early, then leave them stuck since editing doesn't re-fire
        # selection_changed on its own.
        item.on_commit = self._handle_commit
        item.on_edited = self._on_edited
        item.start_editing()

        if self._selection:
            self._selection.select(item)
        else:
            self.viewport.scene().clearSelection()
            item.setSelected(True)

        # Placement itself (not the later edit-commit) is when the panel's
        # config has been "consumed" — switch to Selecionar right away so
        # the Texto toolbar button turns off and the panel closes, while
        # inline editing (already started above) keeps working independently
        # of which tool is active (see TextItem._InlineTextEditor — it owns
        # its own keyboard focus, not routed through the tool manager).
        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_committed:
            self._on_committed()

    def _handle_commit(self):
        """Fired once, by the item itself, when the very first edit right
        after placement commits (Enter / click outside). Placement already
        switched tools/closed the panel (see mouse_press) — this is now
        just a safety net in case that ever changes."""
        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_committed:
            self._on_committed()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.move(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.release(scene_pos)
