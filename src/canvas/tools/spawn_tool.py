"""SpawnTool — stamps a composed mob group-portrait onto the map.

Armed by SpawnMediator once a mob is picked in the Spawn panel (see
src/layouts/panels/spawn/panel.py + mob_sub_panel.py). Unlike BrushTool's
object-stamp mode (which scatters several INDEPENDENT copies of one asset
per dab via BrushEngine's density param), a single click/dab here places
ONE composed image — see portrait_compose.compose_group_portrait — that
already encodes "quantity" as a front-and-center portrait plus a fan of
smaller ones behind it, not a row of identical faces.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsPixmapItem, QGraphicsItem

from src.canvas.tools.base import BaseTool
from src.canvas.tools.interaction import ItemInteraction
from src.canvas.item_utils import suppress_selection_decoration, enable_hover_glow
from src.engines.core.history import PlaceObjectCommand
from src.layouts.panels.spawn.portrait_compose import compose_group_portrait
from src.styles.tokens import Colors

_HOVER_SCALE = 1.12

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.core.history import HistoryEngine


class SpawnTool(BaseTool):
    """Circular stamp tool — click (or drag) to place composed mob-group
    portraits on the map, one per dab, spaced by their own size like the
    terrain Brush's stroke spacing."""

    name = "Spawn"
    cursor = Qt.CursorShape.CrossCursor
    SPACING_RATIO = 1.1  # fraction of size between dabs while dragging

    def __init__(
        self, viewport: Viewport, history_engine: HistoryEngine | None = None,
        selection_engine=None, transform_engine=None,
    ):
        super().__init__(viewport)
        self._history = history_engine
        # Clicking an EXISTING mob stamp selects it (so it shows up in the
        # Inspector, drags, etc.) instead of always stamping a new one on
        # top — same try-select-first pattern TextTool uses for its own
        # click-to-place-vs-click-to-edit ambiguity.
        self._interaction = ItemInteraction(viewport, selection_engine, transform_engine, history_engine) \
            if selection_engine and transform_engine else None

        self.entity_kind: str = "mob"  # "mob" | "npc" — picked in SpawnPanel's toggle
        self.mob_id: str | None = None
        self.mob_name: str = ""
        self.face_pixmap: QPixmap | None = None
        self.size: float = 64.0
        self.quantity: int = 1
        self.height: float = 0.0

        self._painting = False
        self._last_pos: QPointF | None = None
        self._stroke_had_items = False
        self._stamp_placed_callbacks: list = []

    def on_stamp_placed(self, callback):
        """Registers callback(entity_id, scene_pos) fired after every stamp —
        SpawnMediator uses this to auto-tag the entity with whichever região
        (if any) it was just stamped into (see RegionMediator.region_at_point)."""
        self._stamp_placed_callbacks.append(callback)

    def set_entity(self, kind: str, entity_id: str, name: str, face_pixmap: QPixmap | None, height: float = 0.0):
        self.entity_kind = kind
        self.mob_id = entity_id
        self.mob_name = name
        self.face_pixmap = face_pixmap
        self.height = height

    def set_size(self, size: float):
        self.size = max(8.0, size)

    def set_quantity(self, quantity: int):
        self.quantity = max(1, int(quantity))

    @staticmethod
    def _is_own_stamp(item) -> bool:
        data = item.data(0)
        return isinstance(data, dict) and data.get("item_type") in ("mob_spawn", "npc_spawn")

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._interaction and self._interaction.try_begin(scene_pos, item_filter=self._is_own_stamp):
            return
        if self.face_pixmap is None:
            return
        self._painting = True
        self._stroke_had_items = False
        if self._history:
            self._history.begin_group("Spawn de npcs" if self.entity_kind == "npc" else "Spawn de mobs")
        self._place(scene_pos)
        self._last_pos = scene_pos

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._interaction and self._interaction.move(scene_pos):
            return
        if not self._painting or self._last_pos is None:
            return
        spacing = max(6.0, self.size * self.SPACING_RATIO)
        dist = math.hypot(scene_pos.x() - self._last_pos.x(), scene_pos.y() - self._last_pos.y())
        if dist >= spacing:
            self._place(scene_pos)
            self._last_pos = scene_pos

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._interaction and self._interaction.release(scene_pos):
            return
        self._painting = False
        self._last_pos = None
        if self._history and self._stroke_had_items:
            self._history.end_group()
        self._stroke_had_items = False

    def _place(self, scene_pos: QPointF):
        item = self.build_stamp_item(
            self.mob_id, self.mob_name, self.quantity, self.size, self.face_pixmap, scene_pos,
            height=self.height, entity_kind=self.entity_kind,
        )
        self.viewport.scene().addItem(item)
        self._stroke_had_items = True
        if self._history:
            self._history.push(PlaceObjectCommand(item))
        for cb in self._stamp_placed_callbacks:
            cb(self.mob_id, scene_pos)

    @staticmethod
    def build_stamp_item(mob_id: str | None, name: str, quantity: int, size: float,
                          face_pixmap: QPixmap | None, scene_pos: QPointF,
                          height: float = 0.0, entity_kind: str = "mob") -> QGraphicsPixmapItem:
        """Pure factory — builds one entity-group-portrait stamp item without
        touching the scene or undo history. Shared by `_place()` (live
        placement, which adds it + pushes undo) and SpawnMediator.
        _load_from_db() (project reload, which just adds it to the scene
        the way BrushMediator's own stamp reload does), so the flags/
        zValue/data(0) shape and hover wiring only exist in one place.
        `entity_kind` ("mob"/"npc") only changes item_type — the data dict's
        "mob_id" key is reused for both kinds (avoids touching every reader)."""
        pixmap = compose_group_portrait(face_pixmap, quantity, round(size))
        item = QGraphicsPixmapItem(pixmap)
        item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
        item.setPos(scene_pos)
        item.setZValue(10)
        # compose_group_portrait draws the front token at only ~60% of the
        # canvas (room for the dimmed fan behind it — see _LAYOUTS), so a
        # big transparent margin surrounds the visible circle. The default
        # QGraphicsPixmapItem hit-test (ShapeMode.MaskShape) only counts
        # opaque pixels, so clicking that margin — which still reads as
        # "the icon" to the eye — silently missed the item entirely and
        # fell through to whatever's underneath instead of selecting it.
        item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        item.setData(0, {
            "item_type": f"{entity_kind}_spawn", "mob_id": mob_id,
            "name": name, "quantity": quantity, "size": size, "height": height,
        })
        suppress_selection_decoration(item)

        def on_hover(hovered: bool):
            if hovered:
                item.setScale(_HOVER_SCALE)
                glow = QGraphicsDropShadowEffect()
                glow.setColor(QColor(Colors.ACCENT))
                glow.setBlurRadius(28)
                glow.setOffset(0, 0)
                item.setGraphicsEffect(glow)
            else:
                item.setScale(1.0)
                item.setGraphicsEffect(None)

        enable_hover_glow(item, on_hover)
        return item
