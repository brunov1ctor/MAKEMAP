"""Object-stamp placement (non-terrain assets painted as individual
QGraphicsPixmapItems, e.g. trees/props/markers dropped by the Brush tool)
— split out of BrushTool the same way BrushTool already split shoreline
foam blending out into its own collaborator (see shoreline_blend.
ShorelineBlender's own docstring for the pattern this mirrors).

Owns the one piece of state that's genuinely private to this responsibility
(`_stroke_items`, the current object-stroke's placed items — nothing else
in BrushTool ever reads it) and otherwise only reads BrushTool's shared
collaborators (asset_engine, active_boundary, viewport, history, brush
engine) live via properties — never terrain-painting state
(_terrain_layers, _active_terrain_layer, _stroke_snapshots, ...), which is
what makes this a safe, low-risk split unlike the terrain-stroke machinery
itself (that machinery touches nearly every field BrushTool has, the same
reason TerrainLayer's own paint/erase core wasn't split further either).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsPixmapItem

from src.canvas.item_utils import suppress_selection_decoration
from src.canvas.z_order import ZOrder
from src.engines.core.history import PlaceObjectCommand

if TYPE_CHECKING:
    from src.canvas.tools.brush_tool import BrushTool


class ObjectStamper:
    def __init__(self, brush_tool: "BrushTool"):
        self._brush = brush_tool
        self._stroke_items: list = []

    @property
    def viewport(self):
        return self._brush.viewport

    @property
    def _asset_engine(self):
        return self._brush._asset_engine

    @property
    def _active_boundary(self):
        return self._brush._active_boundary

    @property
    def _history(self):
        return self._brush._history

    @property
    def _engine(self):
        return self._brush._engine

    def begin_stroke(self, pos: QPointF):
        self._stroke_items.clear()
        self._engine.stamp_placed.connect(self.on_stamp)
        self._engine.begin_stroke(pos)
        if self._history:
            self._history.begin_group("Pintura de objetos")

    def place_stamp_item(self, asset_id: str, position: QPointF, rotation: float,
                          scale: float, opacity: float) -> QGraphicsPixmapItem | None:
        """Builds+places a single brush-stamped object item — shared by
        live painting (on_stamp) and BrushMediator's DB-reload on project
        switch, so both produce identical items. `position` is in scene
        coordinates regardless of boundary parenting."""
        if not self._asset_engine or not asset_id:
            return None

        pixmap = self._asset_engine.get_pixmap(asset_id)
        if not pixmap or pixmap.isNull():
            return None

        # Parent to boundary group so stamp moves with the terrain
        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary.group

        item = QGraphicsPixmapItem(pixmap, parent_item)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)
        # Default MaskShape hit-tests against opaque pixels only — a click
        # anywhere on a sprite's transparent padding (very common: trees,
        # decorations rarely fill their whole bounding box) missed the item
        # entirely, while a box-select drag still caught it (looser
        # intersection test), making single-click selection feel broken.
        # spawn_tool.py's stamp already does this; asset stamps didn't.
        item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)

        if parent_item:
            local_pos = parent_item.mapFromScene(position)
            item.setPos(
                local_pos.x() - pixmap.width() / 2,
                local_pos.y() - pixmap.height() / 2,
            )
        else:
            item.setPos(
                position.x() - pixmap.width() / 2,
                position.y() - pixmap.height() / 2,
            )
            self.viewport.scene().addItem(item)

        item.setScale(scale)
        item.setRotation(rotation)
        item.setOpacity(opacity)
        # Stamped/generated assets sit at zValue >= 10, above terrain (1)
        # and zones (5) — see terrain_mediator.py/region_mediator.py's own
        # ">= 10" heuristic for counting objects inside boundaries. This
        # used to sit at 0.5, below terrain, so an asset stamp silently
        # painted underneath the terrain layer instead of on top of it
        # whenever both shared the same parent.
        item.setZValue(ZOrder.STAMPED_OBJECT)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        item.setData(0, {"item_type": "asset", "asset_id": asset_id})
        suppress_selection_decoration(item)
        # TransformEngine._item_bounds usa selection_bounding_rect() quando
        # presente — sem isso, sceneBoundingRect() inclui filhos (e.g.
        # AssetEffectsOverlay) e o canvas de seleção fica inflado.
        # Usa lambda com weak-ref implícita via pixmap size para evitar
        # ciclo de referência no Shiboken que poderia deletar o item cedo.
        _w, _h = pixmap.width(), pixmap.height()
        item.selection_bounding_rect = lambda: QRectF(0, 0, _w, _h)
        return item

    def on_stamp(self, stamp):
        """Render object stamp as individual QGraphicsPixmapItem.

        `stamp.scale` (from BrushEngine._generate_stamps) is only ever the
        per-instance 0.8-1.2 random jitter (BrushAssetEntry.scale_min/max)
        — it has no idea how big the asset's source pixmap is, so it never
        made the brush's "Size" slider (self._brush.size) have any visible
        effect on a placed object's size (Size only ever drove spacing/
        scatter, see BrushEngine.continue_stroke/_generate_stamps). Scaling
        by size/native-pixmap-dimension here, on top of that jitter, is
        what makes "Size" actually resize what gets stamped — a small
        stone at a small Size, a big one at a big Size — matching how the
        terrain brush's own size slider already behaves.
        """
        scale = stamp.scale
        pixmap = self._asset_engine.get_pixmap(stamp.asset_id) if self._asset_engine else None
        if pixmap and not pixmap.isNull():
            native = max(pixmap.width(), pixmap.height())
            if native > 0:
                scale *= self._brush.size / native
        item = self.place_stamp_item(stamp.asset_id, stamp.position, stamp.rotation, scale, stamp.opacity)
        if item is None:
            return
        self._stroke_items.append(item)

        if self._history:
            self._history.push(PlaceObjectCommand(item))
