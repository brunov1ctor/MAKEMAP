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
        transform_engine=None, on_committed=None,
    ):
        super().__init__(viewport)
        self._tool_manager = tool_manager
        self._history = history_engine
        self._selection = selection_engine
        self._on_committed = on_committed
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._interaction and self._interaction.try_begin(scene_pos):
            return

        item = TextItem(TextProperties(text="Texto", font_size=20, font_weight=600))
        item.setPos(scene_pos)
        item.setZValue(50)
        self.viewport.scene().addItem(item)
        if self._history:
            self._history.push(PlaceObjectCommand(item))

        if self._selection:
            self._selection.select(item)
        else:
            self.viewport.scene().clearSelection()
            item.setSelected(True)
        item.on_commit = self._handle_commit
        item.start_editing()

    def _handle_commit(self):
        """Fired once, by the item itself, when the very first edit right
        after placement commits (Enter / click outside) — switches to the
        Selection tool (not Pan) so the Texto button turns off in the
        toolbar AND the just-placed, still-selected object stays fully
        interactive (drag/rotate/resize handles) — Pan has no
        ItemInteraction wired at all, which left the object undraggable."""
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
