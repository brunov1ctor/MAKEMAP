"""Canvas tools — Brush (terrain + object paint), Region, Road, River."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QMouseEvent, QPen, QColor, QBrush, QPainterPath, QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPolygonItem,
    QGraphicsPixmapItem,
)

from src.canvas.tools.base import BaseTool
from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.map.brush import BrushEngine
    from src.engines.assets.engine import AssetEngine
    from src.engines.core.history import HistoryEngine


# ─── Brush Tool (terrain + object) ──────────────────────────────────────

class BrushTool(BaseTool):
    """Brush — terrain mask painting + object stamp placement.

    Terrain assets (category='terrain'): paints into a TerrainLayer mask.
    Object assets (all others): places individual QGraphicsPixmapItems.
    """

    name = "Brush"
    shortcut = "B"
    cursor = Qt.CursorShape.CrossCursor
    TERRAIN_SPACING_RATIO = 0.08  # fraction of brush size between stamps
    INITIAL_LAYER_SIZE = 2048     # starting layer dimensions

    def __init__(self, viewport: Viewport, brush_engine: BrushEngine,
                 asset_engine: AssetEngine = None, history_engine: HistoryEngine = None):
        super().__init__(viewport)
        self._engine = brush_engine
        self._asset_engine = asset_engine
        self._history = history_engine
        self._minimap = None
        self._sound_engine = None
        self._cursor_item: QGraphicsEllipseItem | None = None
        self._stroke_items: list = []

        # Terrain layers: asset_id -> TerrainLayer
        self._terrain_layers: dict[str, TerrainLayer] = {}
        self._active_terrain_layer: TerrainLayer | None = None
        self._active_asset_id: str = ""
        self._is_terrain_mode = False

        # Undo state
        self._undo_rect: QRect | None = None
        self._undo_snapshot = None

        # Stroke interpolation for terrain
        self._last_terrain_pos: QPointF | None = None

        # Brush params (synced from panel)
        self.softness = 0.5
        self.texture_scale = 1.0
        self.texture_rotation = 0.0
        self.erase_mode = False
        self.mask_mode = False

        # Map bounds (None = infinite)
        self._bounds_width: int | None = None
        self._bounds_height: int | None = None
        self._bounds_shape: str | None = None

        # Active boundary item (selected terrain panel)
        self._active_boundary: object | None = None  # MapBoundary

    @property
    def size(self) -> float:
        return self._engine.config.size

    def update_cursor_size(self):
        """Refresh cursor circle diameter when brush size changes."""
        if self._cursor_item:
            rect = self._cursor_item.rect()
            cx = rect.x() + rect.width() / 2
            cy = rect.y() + rect.height() / 2
            r = self.size / 2
            self._cursor_item.setRect(cx - r, cy - r, self.size, self.size)

    def activate(self):
        super().activate()
        self._show_cursor()

    def deactivate(self):
        super().deactivate()
        self._hide_cursor()

    def set_asset_engine(self, asset_engine: AssetEngine):
        self._asset_engine = asset_engine

    def set_sound_engine(self, sound_engine):
        """Inject SoundEngine for brush audio feedback."""
        self._sound_engine = sound_engine

    def set_map_bounds(self, width: int | None, height: int | None, shape: str | None):
        """Set map painting bounds. None = infinite."""
        self._bounds_width = width
        self._bounds_height = height
        self._bounds_shape = shape

    def set_active_boundary(self, boundary):
        """Set the active boundary (selected terrain panel). None = no constraint."""
        self._active_boundary = boundary

    def _is_within_bounds(self, scene_pos: QPointF) -> bool:
        """Check if a scene position is within the active boundary."""
        # Infinite mode — no constraint
        if self._bounds_width is None:
            return True
        # If there's an active boundary item, use its shape for hit-testing
        if self._active_boundary and self._active_boundary._item:
            item = self._active_boundary._item
            local_pos = item.mapFromScene(scene_pos)
            return item.path().contains(local_pos)
        # Fallback to simple bounds
        x, y = scene_pos.x(), scene_pos.y()
        hw = self._bounds_width / 2
        hh = self._bounds_height / 2
        if self._bounds_shape == "circle":
            r = min(hw, hh)
            return (x * x + y * y) <= r * r
        elif self._bounds_shape == "square":
            s = min(hw, hh)
            return -s <= x <= s and -s <= y <= s
        else:  # rectangle
            return -hw <= x <= hw and -hh <= y <= hh

    def set_active_asset(self, asset_id: str):
        """Called when user selects an asset in the panel."""
        self._active_asset_id = asset_id
        self._is_terrain_mode = self._check_is_terrain(asset_id)

    def _check_is_terrain(self, asset_id: str) -> bool:
        """Check if asset belongs to 'terrain' category."""
        if not self._asset_engine or not asset_id:
            return False
        lib = getattr(self._asset_engine, 'library', None)
        if not lib:
            return False
        row = lib._db.execute(
            "SELECT category FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return row["category"] == "terrain" if row else False

    # ─── Mouse Events ─────────────────────────────────────────────────

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._is_within_bounds(scene_pos):
            return

        if self._is_terrain_mode or (self.mask_mode and self._active_asset_id):
            self._begin_terrain_stroke(scene_pos)
        elif self._active_asset_id:
            self._begin_object_stroke(scene_pos)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        # Update cursor
        if self._cursor_item:
            r = self.size / 2
            self._cursor_item.setRect(scene_pos.x() - r, scene_pos.y() - r, self.size, self.size)

        if self._active_terrain_layer:
            self._continue_terrain_stroke(scene_pos)
        elif self._engine.is_active:
            self._engine.continue_stroke(scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._active_terrain_layer:
            self._end_terrain_stroke()
        elif self._engine.is_active:
            self._engine.end_stroke()
            try:
                self._engine.stamp_placed.disconnect(self._on_object_stamp)
            except (RuntimeError, TypeError):
                pass

    # ─── Terrain Stroke ──────────────────────────────────────────────

    def _begin_terrain_stroke(self, pos: QPointF):
        layer = self._get_or_create_terrain_layer(self._active_asset_id)
        self._active_terrain_layer = layer
        self._last_terrain_pos = pos

        # Notify sound engine
        if self._sound_engine:
            # Use asset name as sound key (e.g. "terrain" from folder name)
            asset_key = self._get_asset_sound_key(self._active_asset_id)
            self._sound_engine.on_brush_stroke_start(asset_key)

        # Paint first point — convert scene pos to layer-local coords
        params = self._terrain_params()
        local = self._scene_to_layer(pos, layer)
        layer.paint_at(local, params)
        layer.update_live()

        # Erase same area from other terrain layers
        if not params.erase:
            self._erase_other_layers(pos, params)

    def _continue_terrain_stroke(self, pos: QPointF):
        if not self._last_terrain_pos:
            self._last_terrain_pos = pos
            return

        # Skip if outside bounds
        if not self._is_within_bounds(pos):
            self._last_terrain_pos = pos
            return

        layer = self._active_terrain_layer
        params = self._terrain_params()

        dx = pos.x() - self._last_terrain_pos.x()
        dy = pos.y() - self._last_terrain_pos.y()
        dist = math.hypot(dx, dy)

        spacing = max(1.0, self.size * self.TERRAIN_SPACING_RATIO)

        if dist < spacing:
            return

        steps = max(1, math.ceil(dist / spacing))

        for i in range(1, steps + 1):
            t = i / steps
            scene_pt = QPointF(
                self._last_terrain_pos.x() + dx * t,
                self._last_terrain_pos.y() + dy * t,
            )
            local = self._scene_to_layer(scene_pt, layer)
            layer.paint_at(local, params)
            # Erase same area from other terrain layers
            if not params.erase:
                self._erase_other_layers(scene_pt, params)

        layer.update_live()
        self._last_terrain_pos = pos

    def _scene_to_layer(self, scene_pos: QPointF, layer: TerrainLayer) -> QPointF:
        """Convert scene coordinates to layer-local pixel coordinates."""
        # mapFromScene handles parent transforms (boundary position)
        item_local = layer.item.mapFromScene(scene_pos)
        return item_local

    def _erase_other_layers(self, scene_pos: QPointF, params: TerrainBrushParams):
        """Erase the painted area from all other terrain layers."""
        erase_params = TerrainBrushParams(
            size=params.size,
            opacity=params.opacity,
            softness=params.softness,
            erase=True,
        )
        for asset_id, layer in self._terrain_layers.items():
            if asset_id == self._active_asset_id:
                continue
            local = self._scene_to_layer(scene_pos, layer)
            layer.paint_at(local, erase_params)
            layer.update_live()

    def _end_terrain_stroke(self):
        if self._active_terrain_layer:
            self._active_terrain_layer.finish_stroke()
        # Finish stroke on other affected layers too
        for asset_id, layer in self._terrain_layers.items():
            if asset_id != self._active_asset_id:
                layer.finish_stroke()
        self._active_terrain_layer = None
        self._last_terrain_pos = None

        # Notify sound engine stroke ended
        if self._sound_engine:
            self._sound_engine.on_brush_stroke_end()

    def _get_asset_sound_key(self, asset_id: str) -> str:
        """Get the sound folder key for an asset (category name)."""
        if not self._asset_engine or not asset_id:
            return "terrain"
        lib = getattr(self._asset_engine, 'library', None)
        if not lib:
            return "terrain"
        row = lib._db.execute(
            "SELECT category FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return row["category"] if row else "terrain"

    def _terrain_params(self) -> TerrainBrushParams:
        return TerrainBrushParams(
            size=self.size,
            opacity=self._engine.config.opacity,
            softness=self.softness,
            texture_scale=self.texture_scale,
            texture_rotation=self.texture_rotation,
            erase=self.erase_mode,
            mask_only=self.mask_mode,
        )

    def _get_or_create_terrain_layer(self, asset_id: str) -> TerrainLayer:
        """Get existing terrain layer for this asset or create new one."""
        if asset_id in self._terrain_layers:
            layer = self._terrain_layers[asset_id]
            layer.set_mask_only(self.mask_mode)
            # Ensure texture is loaded when switching back to paint mode
            if not self.mask_mode and not layer.has_texture() and self._asset_engine:
                pixmap = self._asset_engine.get_pixmap(asset_id)
                if pixmap and not pixmap.isNull():
                    layer.set_texture(pixmap, self.texture_scale, self.texture_rotation)
            return layer

        # Determine parent item (boundary item if active)
        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary._item

        # Create layer — starts small and expands dynamically
        map_size = self.INITIAL_LAYER_SIZE
        layer = TerrainLayer(self.viewport.scene(), map_size, map_size, parent_item=parent_item)

        if parent_item:
            # Position relative to parent (boundary center is 0,0)
            layer.item.setPos(-map_size / 2, -map_size / 2)
        else:
            layer.item.setPos(-map_size / 2, -map_size / 2)

        if self.mask_mode:
            layer.set_mask_only(True)
        elif self._asset_engine:
            pixmap = self._asset_engine.get_pixmap(asset_id)
            if pixmap and not pixmap.isNull():
                layer.set_texture(pixmap, self.texture_scale, self.texture_rotation)

        self._terrain_layers[asset_id] = layer
        return layer

    # ─── Object Stroke ───────────────────────────────────────────────

    def _begin_object_stroke(self, pos: QPointF):
        self._stroke_items.clear()
        self._engine.stamp_placed.connect(self._on_object_stamp)
        self._engine.begin_stroke(pos)

    def _on_object_stamp(self, stamp):
        """Render object stamp as individual QGraphicsPixmapItem."""
        if not self._asset_engine or not stamp.asset_id:
            return

        pixmap = self._asset_engine.get_pixmap(stamp.asset_id)
        if not pixmap or pixmap.isNull():
            return

        # Parent to boundary item so stamp moves with the terrain
        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary._item

        item = QGraphicsPixmapItem(pixmap, parent_item)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)

        if parent_item:
            # Convert scene position to parent-local
            local_pos = parent_item.mapFromScene(stamp.position)
            item.setPos(
                local_pos.x() - pixmap.width() / 2,
                local_pos.y() - pixmap.height() / 2,
            )
        else:
            item.setPos(
                stamp.position.x() - pixmap.width() / 2,
                stamp.position.y() - pixmap.height() / 2,
            )
            self.viewport.scene().addItem(item)

        item.setScale(stamp.scale)
        item.setRotation(stamp.rotation)
        item.setOpacity(stamp.opacity)
        item.setZValue(10)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        self._stroke_items.append(item)

    # ─── Cursor ─────────────────────────────────────────────────────

    def set_minimap(self, minimap):
        """Set minimap reference so cursor can be hidden from it."""
        self._minimap = minimap

    def _show_cursor(self):
        if self._cursor_item:
            return
        r = self.size / 2
        self._cursor_item = QGraphicsEllipseItem(-r, -r, self.size, self.size)
        self._cursor_item.setPen(QPen(QColor(255, 255, 255, 150), 1.5, Qt.PenStyle.DashLine))
        self._cursor_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._cursor_item.setZValue(10000)
        self.viewport.scene().addItem(self._cursor_item)
        if self._minimap:
            self._minimap.register_hidden_item(self._cursor_item)

    def _hide_cursor(self):
        if self._cursor_item:
            if self._minimap:
                self._minimap.unregister_hidden_item(self._cursor_item)
            self.viewport.scene().removeItem(self._cursor_item)
            self._cursor_item = None


# ─── Region Tool ───────────────────────────────────────────────────────────

class RegionTool(BaseTool):
    """Região — desenha polígono fechado ao clicar pontos.
    
    Chama callbacks registrados via on_region_finalized(callback) quando fechado.
    """

    name = "Região"
    shortcut = "R"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(79, 195, 247, 60)
        self._border_color = QColor(79, 195, 247, 200)
        self._finalize_callbacks: list = []

    def on_region_finalized(self, callback):
        """Registra callback(QPolygonF) chamado ao finalizar região."""
        self._finalize_callbacks.append(callback)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 3:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for pt in self._points[1:]:
                path.lineTo(pt)
            if cursor_pos:
                path.lineTo(cursor_pos)
            path.closeSubpath()

        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._border_color, 2, Qt.PenStyle.DashLine))
        self._preview.setBrush(QBrush(self._color))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        polygon = QPolygonF(self._points)
        item = QGraphicsPolygonItem(polygon)
        item.setPen(QPen(self._border_color, 2))
        item.setBrush(QBrush(self._color))
        item.setZValue(5)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        self.viewport.scene().addItem(item)
        for cb in self._finalize_callbacks:
            cb(polygon)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()


# ─── Road Tool ─────────────────────────────────────────────────────────────

class RoadTool(BaseTool):
    """Estrada — desenha path com pontos clicados."""

    name = "Estrada"
    shortcut = "P"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(139, 119, 80, 220)
        self._width = 8.0

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 2:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for pt in self._points[1:]:
                path.lineTo(pt)
            if cursor_pos:
                path.lineTo(cursor_pos)

        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._color, self._width, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        path = QPainterPath()
        path.moveTo(self._points[0])
        for pt in self._points[1:]:
            path.lineTo(pt)

        item = QGraphicsPathItem(path)
        item.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        item.setZValue(8)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        self.viewport.scene().addItem(item)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()


# ─── River Tool ────────────────────────────────────────────────────────────

class RiverTool(BaseTool):
    """Rio — desenha curva suave com pontos clicados."""

    name = "Rio"
    shortcut = "W"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None
        self._color = QColor(30, 144, 255, 180)
        self._width = 6.0

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 2:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _build_smooth_path(self, points: list[QPointF]) -> QPainterPath:
        path = QPainterPath()
        if len(points) < 2:
            if points:
                path.moveTo(points[0])
            return path

        path.moveTo(points[0])
        if len(points) == 2:
            path.lineTo(points[1])
            return path

        for i in range(len(points) - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[min(len(points) - 1, i + 1)]
            p3 = points[min(len(points) - 1, i + 2)]

            cp1 = QPointF(
                p1.x() + (p2.x() - p0.x()) / 6,
                p1.y() + (p2.y() - p0.y()) / 6,
            )
            cp2 = QPointF(
                p2.x() - (p3.x() - p1.x()) / 6,
                p2.y() - (p3.y() - p1.y()) / 6,
            )
            path.cubicTo(cp1, cp2, p2)

        return path

    def _update_preview(self, cursor_pos: QPointF = None):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)

        pts = list(self._points)
        if cursor_pos:
            pts.append(cursor_pos)

        path = self._build_smooth_path(pts)
        self._preview = QGraphicsPathItem(path)
        self._preview.setPen(QPen(self._color, self._width, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self._preview.setZValue(50)
        self.viewport.scene().addItem(self._preview)

    def _finalize(self):
        path = self._build_smooth_path(self._points)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        item.setZValue(7)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        self.viewport.scene().addItem(item)
        self._points.clear()

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()
