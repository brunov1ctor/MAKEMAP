"""LightTool — click to drop a light object; click an existing one to
select/drag it instead (see PlacementTool for the shared click-an-existing-
item-vs-place-a-new-one flow). Named "Luz" (not "Iluminação") on purpose: the
toolbar's 💡 "Iluminação" button is a toggle that opens LightPanel (see
main_layout._toggle_light_panel), not this tool directly — picking a type
in that panel is what arms this tool (mirrors how "Região" arms
RegionBrushTool from inside RegionSettingsPanel). While armed, a
LightGhostItem (see lighting_overlay.py) follows the cursor showing just the
picked light's glow, so the user can see where/how big it'll land before
clicking — see activate()/deactivate()/mouse_move below."""

from __future__ import annotations

from PySide6.QtCore import Qt

from PySide6.QtGui import QCursor

from src.canvas.tools.placement_tool import PlacementTool
from src.canvas.light_item import LightItem
from src.canvas.lighting_overlay import LightGhostItem
from src.engines.light import LightProperties


class LightTool(PlacementTool):
    name = "Luz"
    cursor = Qt.CursorShape.CrossCursor
    item_cls = LightItem

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ghost: LightGhostItem | None = None

    def _default_properties(self):
        return LightProperties()

    def _make_item(self, props):
        return LightItem(props)

    def activate(self):
        super().activate()
        self._spawn_ghost()

    def deactivate(self):
        self._remove_ghost()
        super().deactivate()

    def _spawn_ghost(self):
        self._remove_ghost()
        props = self._properties_provider() if self._properties_provider else self._default_properties()
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

    def mouse_move(self, event, scene_pos):
        # Hide the ghost while actually dragging an existing light (clicked
        # via the item_filter branch in PlacementTool.mouse_press) — showing
        # a placement preview on top of the real light being repositioned
        # would just be clutter.
        dragging_existing = bool(self._interaction and self._interaction.active)
        if self._ghost is not None:
            self._ghost.setVisible(not dragging_existing)
            if not dragging_existing:
                self._ghost.setPos(scene_pos)
        super().mouse_move(event, scene_pos)
