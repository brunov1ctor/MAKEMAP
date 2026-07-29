"""LightTool — click to drop a light object; click an existing one to
select/drag it instead. Named "Luz" (not "Iluminação") on purpose: the
toolbar's 💡 "Iluminação" button is a toggle that opens LightPanel (see
main_layout._toggle_light_panel), not this tool directly — picking a type
in that panel is what arms this tool (mirrors how "Região" arms
RegionBrushTool from inside RegionSettingsPanel). While armed, a
LightGhostItem (see lighting_overlay.py) follows the cursor showing just the
picked light's glow, so the user can see where/how big it'll land before
clicking — see activate()/deactivate()/mouse_move below."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QCursor, QMouseEvent

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.canvas.light_item import LightItem
from src.canvas.lighting_overlay import LightGhostItem
from src.engines.light import LightProperties
from src.engines.core.history import PlaceObjectCommand


class LightTool(BaseTool):
    name = "Luz"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(
        self, viewport, tool_manager=None, history_engine=None, selection_engine=None,
        transform_engine=None, on_placed=None, properties_provider=None,
    ):
        super().__init__(viewport)
        self._tool_manager = tool_manager
        self._history = history_engine
        self._selection = selection_engine
        self._on_placed = on_placed
        self._properties_provider = properties_provider
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None
        self._ghost: LightGhostItem | None = None

    def set_properties_provider(self, provider):
        self._properties_provider = provider

    def activate(self):
        super().activate()
        self._spawn_ghost()

    def deactivate(self):
        self._remove_ghost()
        super().deactivate()

    def _spawn_ghost(self):
        self._remove_ghost()
        props = self._properties_provider() if self._properties_provider else LightProperties()
        self._ghost = LightGhostItem(props)
        self.viewport.scene().addItem(self._ghost)
        # Position it at the cursor's current spot right away instead of
        # waiting for the next mouse_move, so it doesn't flash at (0, 0).
        local = self.viewport.mapFromGlobal(QCursor.pos())
        self._ghost.setPos(self.viewport.mapToScene(local))

    def _remove_ghost(self):
        if self._ghost is not None:
            scene = self._ghost.scene()
            if scene is not None:
                scene.removeItem(self._ghost)
            self._ghost = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # item_filter: clicking on top of a região/terrain/asset must still
        # place a new light, not hijack the click into selecting that other
        # layer (same fix already applied to Spawn/Texto/Marcador).
        if self._interaction and self._interaction.try_begin(scene_pos, item_filter=lambda it: isinstance(it, LightItem)):
            return

        props = self._properties_provider() if self._properties_provider else LightProperties()
        item = LightItem(props)
        item.setPos(scene_pos)
        # Same "precise click target" z-value MarkerItem uses (60) — a
        # light has no visible icon of its own, just a boundingRect square
        # to click on, and used to sit at z=9, BELOW generic assets/mob
        # stamps (z=10, some with a generous BoundingRectShape hitbox
        # covering their whole padded canvas) — any light placed near one
        # was completely unclickable, itemAt() always returning the
        # asset/mob on top of it instead.
        item.setZValue(60)
        self.viewport.scene().addItem(item)
        if self._history:
            self._history.push(PlaceObjectCommand(item))

        if self._selection:
            self._selection.select(item)
        else:
            self.viewport.scene().clearSelection()
            item.setSelected(True)

        if self._tool_manager:
            self._tool_manager.activate("Selecionar")
        if self._on_placed:
            self._on_placed(item)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        # Hide the ghost while actually dragging an existing light (clicked
        # via the item_filter branch above) — showing a placement preview on
        # top of the real light being repositioned would just be clutter.
        dragging_existing = bool(self._interaction and self._interaction.active)
        if self._ghost is not None:
            self._ghost.setVisible(not dragging_existing)
            if not dragging_existing:
                self._ghost.setPos(scene_pos)
        if self._interaction:
            self._interaction.move(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction:
            self._interaction.release(scene_pos)
