"""Canvas tools — Brush (terrain + object paint), Region, Road, River."""

from __future__ import annotations

import logging
import math
import sqlite3
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import (
    QMouseEvent, QPen, QColor, QBrush, QPainterPath, QPolygonF, QImage,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPolygonItem,
    QGraphicsPixmapItem,
)

from src.canvas.tools.base import BaseTool
from src.canvas.tools.shoreline_blend import ShorelineBlender
from src.canvas.tools.object_stamper import ObjectStamper
from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams, build_stamp
from src.engines.core.history import PaintStrokeCommand, CompositeCommand
from src.canvas.item_utils import suppress_selection_decoration
from src.canvas.z_order import ZOrder

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.map.brush import BrushEngine
    from src.engines.assets.engine import AssetEngine
    from src.engines.core.history import HistoryEngine

logger = logging.getLogger("MAKEMAP")


class _DashedCursorMixin:
    """Dashed-circle cursor preview shared by BrushTool and RegionBrushTool
    — same look, diameter driven by whatever the subclass calls its brush
    size (`_cursor_diameter()`)."""

    def _cursor_diameter(self) -> float:
        raise NotImplementedError

    def set_minimap(self, minimap):
        self._minimap = minimap

    def _show_cursor(self):
        if self._cursor_item:
            return
        d = self._cursor_diameter()
        r = d / 2
        self._cursor_item = QGraphicsEllipseItem(-r, -r, d, d)
        self._cursor_item.setPen(QPen(QColor(255, 255, 255, 150), 1.5, Qt.PenStyle.DashLine))
        self._cursor_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._cursor_item.setZValue(ZOrder.TRANSFORM_HANDLE)
        self.viewport.scene().addItem(self._cursor_item)
        if self._minimap:
            self._minimap.register_hidden_item(self._cursor_item)

    def _hide_cursor(self):
        if self._cursor_item:
            if self._minimap:
                self._minimap.unregister_hidden_item(self._cursor_item)
            self.viewport.scene().removeItem(self._cursor_item)
            self._cursor_item = None

    def update_cursor_size(self):
        """Refresh cursor circle diameter when brush size changes."""
        if self._cursor_item:
            rect = self._cursor_item.rect()
            cx = rect.x() + rect.width() / 2
            cy = rect.y() + rect.height() / 2
            d = self._cursor_diameter()
            r = d / 2
            self._cursor_item.setRect(cx - r, cy - r, d, d)


# ─── Brush Tool (terrain + object) ──────────────────────────────────────

class BrushTool(_DashedCursorMixin, BaseTool):
    """Brush — terrain mask painting + object stamp placement.

    Terrain assets (category='terrain'): paints into a TerrainLayer mask.
    Object assets (all others): places individual QGraphicsPixmapItems.
    """

    name = "Brush"
    shortcut = "B"
    cursor = Qt.CursorShape.CrossCursor
    TERRAIN_SPACING_RATIO = 0.08  # fraction of brush size between stamps
    INITIAL_LAYER_SIZE = 2048     # starting layer dimensions
    # asset_id prefix for the virtual "Effects" category assets (see
    # BrushMediator.populate_assets) — these aren't real library files, so
    # they're routed here by id prefix instead of a DB category lookup
    # (see _check_is_terrain, which DOES hit the DB).
    EFFECT_ASSET_PREFIX = "effect:"
    MAX_FADE_SECONDS = 3.0        # smoothness=1.0 fade-in duration, real seconds

    def __init__(self, viewport: Viewport, brush_engine: BrushEngine,
                 asset_engine: AssetEngine = None, history_engine: HistoryEngine = None,
                 tool_manager=None):
        super().__init__(viewport)
        self._engine = brush_engine
        self._asset_engine = asset_engine
        self._history = history_engine
        # Handed to every TerrainLayer this tool creates, so painted
        # terrain/brush-effect layers only show their hover glow while
        # Selecionar is the active tool — hovering one mid-stroke while
        # actively painting/erasing shouldn't light up a "click me" cue.
        self._tool_manager = tool_manager
        self._minimap = None
        self._sound_engine = None
        self._snap_manager = None
        self._cursor_item: QGraphicsEllipseItem | None = None

        # Object-stamp placement (non-terrain assets placed as individual
        # QGraphicsPixmapItems) — see object_stamper.ObjectStamper's own
        # docstring; split out since it only ever reads BrushTool's shared
        # collaborators (asset_engine/active_boundary/viewport/history/
        # brush engine), never the terrain-painting state itself.
        self._object_stamper = ObjectStamper(self)

        # Terrain layers: asset_id -> TerrainLayer
        self._terrain_layers: dict[str, TerrainLayer] = {}
        # Brush-painted animated effect layers (Névoa, Poeira, ...):
        # asset_id ("effect:<key>") -> TerrainLayer, mask-only, painted
        # per-frame by BrushEffectsOverlay instead of a static texture.
        # Kept separate from _terrain_layers so painting terrain never
        # erases an effect stroke (_erase_other_layers only loops
        # _terrain_layers) and vice versa.
        self._effect_layers: dict[str, TerrainLayer] = {}
        self._active_terrain_layer: TerrainLayer | None = None
        self._active_asset_id: str = ""
        self._is_terrain_mode = False
        self._is_effect_mode = False

        # Shoreline foam blend — see shoreline_blend.ShorelineBlender's own
        # docstring; split out since it only reads terrain_layers/
        # asset_engine/viewport, never the brush/stamp painting state.
        self._shoreline = ShorelineBlender(self)

        # Undo state — asset_id -> pre-stroke layer snapshot, for layers
        # touched (painted or erased-into) during the current stroke.
        self._stroke_snapshots: dict[str, dict] = {}

        # Stroke interpolation for terrain
        self._last_terrain_pos: QPointF | None = None
        self._last_filled_cell: tuple[float, float] | None = None  # cell-fill mode (Snap on)

        # Brush params (synced from panel)
        self.softness = 0.5
        self.roughness = 0.0    # 0=perfect circle edge, 1=jagged — no effect when Snap cell-fills
        self.smoothness = 0.0   # 0=instant swap, 1=long fade-in when the painted asset changes
        self.texture_scale = 0.5
        self.texture_rotation = 0.0
        self.erase_mode = False
        self._mask_mode = False
        # True only while a stroke started with the right mouse button is
        # in progress — right-click is a momentary "erase" shortcut that
        # doesn't touch the erase_mode toggle itself.
        self._stroke_force_erase = False
        # Button that started the current stroke — mirrors RegionBrushTool's
        # _stroke_button so releasing a *different* button mid-stroke (e.g.
        # pressing left, then right, then releasing one of them) doesn't end
        # the stroke early or leave it stuck active.
        self._stroke_button = None

        # Smoothness cross-fade state — reset whenever a *new* stroke starts
        # painting a different asset than the previous stroke did, so
        # re-painting the same material back-to-back never re-fades. Ramps
        # over real elapsed time (not stamp count): terrain stamps land
        # every ~8% of brush size while dragging, so a handful of *stamps*
        # can fly by in a fraction of a second — time keeps the fade
        # perceptible no matter how fast the stroke is dragged.
        self._last_stroke_asset_id: str = ""
        self._fade_start_time: float | None = None
        self._fade_duration = 0.0

        # Map bounds (None = infinite)
        self._bounds_width: int | None = None
        self._bounds_height: int | None = None
        self._bounds_shape: str | None = None

        # Active boundary item (selected terrain panel)
        self._active_boundary: object | None = None  # MapBoundary
        # All bounded terrains currently shown — used by the grid overlay to
        # clip across every terrain at once, not just the active one.
        self._all_boundaries: list = []

        # Plain callback (BaseTool isn't a QObject, same convention as
        # MapBoundary.on_moved) fired from mouse_press when the map is
        # bounded (not "Mapa Infinito") but no terrain is selected to
        # paint into — BrushMediator wires this to show an info panel
        # instead of silently falling back to a generic centered shape.
        self.on_bounds_missing = None

    @property
    def size(self) -> float:
        return self._engine.config.size

    @property
    def mask_mode(self) -> bool:
        return self._mask_mode

    @mask_mode.setter
    def mask_mode(self, value: bool):
        if self._mask_mode and not value:
            # Leaving Mask mode — discard the stencil clip so Paint/Erase
            # strokes on this asset's layer aren't left permanently confined
            # to whatever shape was last stenciled (see clear_stencil()).
            layer = self._terrain_layers.get(self._active_asset_id)
            if layer:
                layer.clear_stencil()
        self._mask_mode = value

    def _cursor_diameter(self) -> float:
        return self.size

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

    def set_snap_manager(self, snap_manager):
        """Inject SnapManager — when enabled, terrain painting fills whole
        grid cells (see GridManager.cell_polygon) instead of a soft stamp."""
        self._snap_manager = snap_manager

    def set_map_bounds(self, width: int | None, height: int | None, shape: str | None):
        """Set map painting bounds. None = infinite."""
        self._bounds_width = width
        self._bounds_height = height
        self._bounds_shape = shape

    def set_active_boundary(self, boundary):
        """Set the active boundary (selected terrain panel). None = no constraint."""
        self._active_boundary = boundary

    def set_all_boundaries(self, boundaries: list):
        """All currently shown bounded terrains — kept separate from
        _active_boundary (which still targets painting/edits at the
        selected terrain only) so the grid overlay can clip across all of
        them at once."""
        self._all_boundaries = list(boundaries)

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
        self._is_effect_mode = asset_id.startswith(self.EFFECT_ASSET_PREFIX)
        self._is_terrain_mode = False if self._is_effect_mode else self._check_is_terrain(asset_id)

    def _get_asset_category(self, asset_id: str) -> str | None:
        """Look up an asset's category from the library DB, or None if the
        asset engine/library/row isn't available."""
        if not self._asset_engine or not asset_id:
            return None
        lib = getattr(self._asset_engine, 'library', None)
        if not lib:
            return None
        row = lib._db.execute(
            "SELECT category FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return row["category"] if row else None

    def _check_is_terrain(self, asset_id: str) -> bool:
        """Check if asset belongs to 'terrain', 'water' or 'road' category
        — all three paint into a TerrainLayer mask."""
        return self._get_asset_category(asset_id) in ("terrain", "water", "road")

    # ─── Mouse Events ─────────────────────────────────────────────────

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        is_right = event.button() == Qt.MouseButton.RightButton
        if event.button() != Qt.MouseButton.LeftButton and not is_right:
            return
        if self._bounds_width is not None and self._active_boundary is None:
            # Bounded map, but no terreno selected to paint into — without
            # this check _is_within_bounds falls back to a generic centered
            # rectangle/circle, which would silently paint into nothing in
            # particular instead of telling the user why nothing happened.
            if self.on_bounds_missing:
                self.on_bounds_missing()
            return
        if not self._is_within_bounds(scene_pos):
            return

        is_terrain = self._is_terrain_mode or self._is_effect_mode or (self.mask_mode and self._active_asset_id)
        # Right-click is an "erase" shortcut — only meaningful for terrain
        # painting, which is the only mode that supports erasing.
        if is_right and not is_terrain:
            return
        self._stroke_force_erase = is_right
        self._stroke_button = event.button()

        if is_terrain:
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
        if event.button() != self._stroke_button:
            return
        self._stroke_button = None

        if self._active_terrain_layer:
            self._end_terrain_stroke()
            self._stroke_force_erase = False
        elif self._engine.is_active:
            self._engine.end_stroke()
            try:
                self._engine.stamp_placed.disconnect(self._object_stamper.on_stamp)
            except (RuntimeError, TypeError):
                pass
            if self._history:
                self._history.end_group()

    # ─── Terrain Stroke ──────────────────────────────────────────────

    def _begin_terrain_stroke(self, pos: QPointF):
        self._stroke_snapshots = {}
        layer = self._get_or_create_terrain_layer(self._active_asset_id)
        self._active_terrain_layer = layer
        self._last_terrain_pos = pos
        self._last_filled_cell: tuple[float, float] | None = None
        self._snapshot_layer(self._active_asset_id, layer)

        # Smoothness: only ramp opacity in when this stroke's asset is
        # actually different from the last stroke's — repainting the same
        # material across separate strokes shouldn't keep re-fading.
        if self.smoothness > 0 and self._active_asset_id != self._last_stroke_asset_id:
            self._fade_start_time = time.monotonic()
            self._fade_duration = self.smoothness * self.MAX_FADE_SECONDS
        else:
            self._fade_start_time = None
        self._last_stroke_asset_id = self._active_asset_id

        # Notify sound engine
        if self._sound_engine:
            self._sound_engine.on_brush_stroke_start(self._active_asset_id)

        params = self._terrain_params()
        painted, stamp = self._paint_terrain_at(pos, layer, params)
        if painted:
            layer.update_live()
            if not self._is_effect_mode:
                self._erase_other_layers(pos, params, stamp)

    def _snapshot_layer(self, asset_id: str, layer: TerrainLayer):
        """Capture a layer's pre-stroke state once, for undo."""
        if self._history and asset_id not in self._stroke_snapshots:
            self._stroke_snapshots[asset_id] = layer.capture_state()

    def _paint_terrain_at(self, scene_pos: QPointF, layer: TerrainLayer,
                           params: TerrainBrushParams) -> tuple[bool, QImage | None]:
        """Paint at scene_pos — a soft circular stamp, or (Snap on) a flood
        fill of the grid cell scene_pos falls in. Returns (painted, stamp):
        `painted` is False if cell-fill mode skipped a repeat fill of the
        same cell (dragging across it doesn't keep re-painting it);
        `stamp` is the alpha-stamp image just used, or None for cell-fill
        (a hard polygon fill has no comparable soft shape to share).
        Callers pass `stamp` straight through to _erase_other_layers so
        every other terrain layer gets carved out with the exact same
        footprint instead of computing its own independent edge."""
        if self._snap_manager and self._snap_manager.enabled:
            grid = self._snap_manager.grid
            cell = grid.cell_polygon(scene_pos.x(), scene_pos.y()) if grid else None
            if cell is not None:
                center = cell.boundingRect().center()
                key = (round(center.x(), 3), round(center.y(), 3))
                if key == self._last_filled_cell:
                    return False, None
                self._last_filled_cell = key
                local_poly = layer.item.mapFromScene(cell)
                layer.paint_cell(local_poly, params)
                return True, None

        local = self._scene_to_layer(scene_pos, layer)
        stamp = build_stamp(params.size / 2, params, world_pos=scene_pos)
        layer.paint_at(local, params, stamp=stamp)
        return True, stamp

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

        if self._snap_manager and self._snap_manager.enabled:
            # Cell-fill mode: check the cell under the cursor every move
            # instead of interpolating circular stamps along the path —
            # _paint_terrain_at already no-ops if it's the same cell as last time.
            painted, stamp = self._paint_terrain_at(pos, layer, params)
            if painted:
                layer.update_live()
                if not self._is_effect_mode:
                    self._erase_other_layers(pos, params, stamp)
            self._last_terrain_pos = pos
            return

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
            stamp = build_stamp(params.size / 2, params, world_pos=scene_pt)
            layer.paint_at(local, params, stamp=stamp)
            # Erase same area from other terrain layers, with the exact
            # same stamp footprint just painted above — skipped for an
            # effect stroke (Névoa etc. shouldn't erase the grass under it).
            if not self._is_effect_mode:
                self._erase_other_layers(scene_pt, params, stamp)

        layer.update_live()
        self._last_terrain_pos = pos

    def _scene_to_layer(self, scene_pos: QPointF, layer: TerrainLayer) -> QPointF:
        """Convert scene coordinates to layer-local pixel coordinates."""
        # mapFromScene handles parent transforms (boundary position)
        item_local = layer.item.mapFromScene(scene_pos)
        return item_local

    def _erase_other_layers(self, scene_pos: QPointF, params: TerrainBrushParams,
                             stamp: QImage | None = None):
        """Erase the painted (or erased) area from all other terrain layers.

        Runs on every stroke regardless of params.erase: while painting, it
        carves the new material's footprint out of every other terrain so
        two materials never overlap; while erasing, it means the eraser
        clears whatever asset(s) actually occupy that spot on the canvas
        instead of only the currently-selected asset's own layer.

        `stamp`, when given, is the EXACT alpha-stamp image just painted
        into the active layer (see _paint_terrain_at/_continue_terrain_
        stroke) — reusing it here instead of letting each other layer
        build its own erase gradient guarantees the erased edge is
        pixel-identical to the painted edge, so two adjacent terrain
        types meet at one clean complementary boundary instead of two
        independently-computed (and, with roughness > 0, independently
        randomized) edges producing a visible seam. None only for
        cell-fill mode (paint_cell has no comparable soft stamp)."""
        erase_params = TerrainBrushParams(
            size=params.size,
            opacity=params.opacity,
            softness=params.softness,
            roughness=params.roughness,
            erase=True,
        )
        r = params.size / 2
        for asset_id, layer in self._terrain_layers.items():
            if asset_id == self._active_asset_id:
                continue
            local = self._scene_to_layer(scene_pos, layer)
            # Skip layers the stamp footprint doesn't even reach — cheap
            # bounds check against the layer's own (downsampled, already-
            # cached-by-caller-frequency-tolerant) opaque_bounds_local(),
            # instead of unconditionally running snapshot+paint_at+
            # update_live (a full erase pass) on every other terrain type
            # ever used on the map, on every single mouse-move of a stroke.
            bounds = layer.opaque_bounds_local()
            if bounds is None:
                continue
            stamp_rect = QRect(int(local.x() - r), int(local.y() - r), int(params.size), int(params.size))
            if not bounds.intersects(stamp_rect):
                continue
            self._snapshot_layer(asset_id, layer)
            layer.paint_at(local, erase_params, stamp=stamp)
            layer.update_live()

    def _end_terrain_stroke(self):
        if self._active_terrain_layer:
            self._active_terrain_layer.finish_stroke()
        # Finish stroke on other affected layers too
        for asset_id, layer in self._terrain_layers.items():
            if asset_id != self._active_asset_id:
                layer.finish_stroke()

        self._push_stroke_history()
        # Reset BEFORE the shoreline blend pass, not after — mouse_move
        # keeps painting for as long as _active_terrain_layer is truthy
        # (there's no separate "is the button still held" check), so if
        # anything below ever raised, the tool would keep applying
        # terrain on every mouse move after release with no way to stop
        # short of picking a new asset. The blend is a purely cosmetic
        # extra on top of an already-finished stroke — it must never be
        # able to leave painting stuck "on".
        self._active_terrain_layer = None
        self._last_terrain_pos = None
        try:
            self._shoreline.apply()
        except Exception:
            logger.exception("Falha ao aplicar halo de espuma terra-água")

    # ─── Shoreline blend (Fase C — land/water foam halo) — see
    # shoreline_blend.ShorelineBlender. Kept as BrushTool delegators below
    # since engine.py/brush_mediator.py call these directly after
    # reloading terrain from the DB. ────────────────────────────────────

    def _apply_shoreline_blend(self):
        self._shoreline.apply()

    def _clear_all_blend_overlays(self):
        self._shoreline.clear_all()

    def _push_stroke_history(self):
        if not self._history or not self._stroke_snapshots:
            self._stroke_snapshots = {}
            return
        commands = []
        for asset_id, before_state in self._stroke_snapshots.items():
            layer = self._terrain_layers.get(asset_id) or self._effect_layers.get(asset_id)
            if layer:
                commands.append(PaintStrokeCommand(layer, before_state, layer.capture_state()))
        self._stroke_snapshots = {}
        if len(commands) == 1:
            self._history.push(commands[0])
        elif commands:
            self._history.push(CompositeCommand(commands, "Pintura de terreno"))

        # Notify sound engine stroke ended
        if self._sound_engine:
            self._sound_engine.on_brush_stroke_end()

    def _get_asset_sound_key(self, asset_id: str) -> str:
        """Get the sound key for an asset — returns the asset category."""
        try:
            category = self._get_asset_category(asset_id)
        except sqlite3.Error:
            return asset_id
        return category or asset_id

    def _terrain_params(self) -> TerrainBrushParams:
        opacity = self._engine.config.opacity
        if self._fade_start_time is not None and self._fade_duration > 0:
            elapsed = time.monotonic() - self._fade_start_time
            if elapsed < self._fade_duration:
                opacity *= max(0.05, elapsed / self._fade_duration)
            else:
                self._fade_start_time = None
        return TerrainBrushParams(
            size=self.size,
            opacity=opacity,
            softness=self.softness,
            roughness=self.roughness,
            texture_scale=self.texture_scale,
            texture_rotation=self.texture_rotation,
            erase=self.erase_mode or self._stroke_force_erase,
            mask_only=self.mask_mode,
        )

    def _get_or_create_terrain_layer(self, asset_id: str) -> TerrainLayer:
        """Get existing terrain layer for this asset or create new one."""
        if asset_id.startswith(self.EFFECT_ASSET_PREFIX):
            return self._get_or_create_effect_layer(asset_id)
        if asset_id in self._terrain_layers:
            layer = self._terrain_layers[asset_id]
            layer.set_mask_only(self.mask_mode)
            # Ensure texture is loaded when switching back to paint mode
            if not self.mask_mode and not layer.has_texture() and self._asset_engine:
                pixmap = self._asset_engine.get_pixmap(asset_id)
                if pixmap and not pixmap.isNull():
                    layer.set_texture(pixmap, self.texture_scale, self.texture_rotation)
            return layer

        # Determine parent item (boundary group if active)
        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary.group

        # Create layer — starts small and expands dynamically
        map_size = self.INITIAL_LAYER_SIZE
        layer = TerrainLayer(self.viewport.scene(), map_size, map_size, parent_item=parent_item, tool_manager=self._tool_manager)

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

    def _get_or_create_effect_layer(self, asset_id: str) -> TerrainLayer:
        """Brush-painted animated effect (Névoa, Poeira, ...) — `asset_id`
        is "effect:<key>" (see EFFECT_ASSET_PREFIX). Always mask_only: it
        has no texture of its own, and with no stencil set either, its
        `_result` composites to fully empty (see TerrainLayer.
        _recomposite_rect) — the item itself paints nothing, only its raw
        `_mask` matters, read by BrushEffectsOverlay via effect_geometry()
        to paint the actual animated look on top every frame."""
        if asset_id in self._effect_layers:
            return self._effect_layers[asset_id]
        effect_key = asset_id[len(self.EFFECT_ASSET_PREFIX):]

        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary.group

        map_size = self.INITIAL_LAYER_SIZE
        layer = TerrainLayer(self.viewport.scene(), map_size, map_size, parent_item=parent_item, tool_manager=self._tool_manager)
        layer.item.setPos(-map_size / 2, -map_size / 2)
        layer.set_mask_only(True)
        # Overrides TerrainLayer's own default {"item_type": "terrain"} —
        # tagged "asset" (falls under the Select tool's "Assets" layer
        # filter, same as any other brush-painted asset) plus the
        # effect_key BrushEffectsOverlay scans for. data(3) is a
        # self-reference (same back-reference pattern RegionLayer used to
        # use) so the overlay can get from the bare scene item back to
        # this TerrainLayer instance.
        layer.item.setData(0, {"item_type": "asset", "effect_key": effect_key})
        layer.item.setData(3, layer)

        self._effect_layers[asset_id] = layer
        return layer

    # ─── Object Stroke — delegated to ObjectStamper (see
    # object_stamper.py). place_stamp_item is kept as a same-named method
    # here (not just on the collaborator) since CanvasEngine.place_stamp_item
    # calls it directly on this BrushTool instance. ─────────────────────

    def _begin_object_stroke(self, pos: QPointF):
        self._object_stamper.begin_stroke(pos)

    def place_stamp_item(self, asset_id: str, position: QPointF, rotation: float,
                          scale: float, opacity: float) -> QGraphicsPixmapItem | None:
        return self._object_stamper.place_stamp_item(asset_id, position, rotation, scale, opacity)

    # ─── Cursor (see _DashedCursorMixin) ───────────────────────────────


# ─── Polyline Draw Tool (base for RegionTool) ──────────────────────────────

class PolylineDrawTool(BaseTool):
    """Common click-to-add-point / right-click-to-finalize / Escape-to-cancel
    flow used by RegionTool — supplies its own _update_preview/_finalize
    and, if it needs more than 2 points to commit, overrides
    _min_points_to_finalize."""

    _min_points_to_finalize = 2

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._preview: QGraphicsPathItem | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(scene_pos)
            self._update_preview()
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= self._min_points_to_finalize:
                self._finalize()
            self._clear_preview()

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._points:
            self._update_preview(scene_pos)

    def _update_preview(self, cursor_pos: QPointF = None):
        raise NotImplementedError

    def _finalize(self):
        raise NotImplementedError

    def _clear_preview(self):
        if self._preview:
            self.viewport.scene().removeItem(self._preview)
            self._preview = None
        self._points.clear()

    def key_press(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._clear_preview()


# ─── Region Tool ───────────────────────────────────────────────────────────

class RegionTool(PolylineDrawTool):
    """Região — desenha polígono fechado ao clicar pontos.

    Chama callbacks registrados via on_region_finalized(callback) quando fechado.
    """

    name = "Região"
    shortcut = "R"
    cursor = Qt.CursorShape.CrossCursor
    _min_points_to_finalize = 3

    def __init__(self, viewport: Viewport):
        super().__init__(viewport)
        self._color = QColor(79, 195, 247, 60)
        self._border_color = QColor(79, 195, 247, 200)
        self._finalize_callbacks: list = []

    def on_region_finalized(self, callback):
        """Registra callback(QPolygonF) chamado ao finalizar região."""
        self._finalize_callbacks.append(callback)

    def _update_preview(self, cursor_pos: QPointF = None):
        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for pt in self._points[1:]:
                path.lineTo(pt)
            if cursor_pos:
                path.lineTo(cursor_pos)
            path.closeSubpath()

        if self._preview is None:
            self._preview = QGraphicsPathItem()
            self._preview.setPen(QPen(self._border_color, 2, Qt.PenStyle.DashLine))
            self._preview.setBrush(QBrush(self._color))
            self._preview.setZValue(ZOrder.TOOL_PREVIEW)
            self.viewport.scene().addItem(self._preview)
        self._preview.setPath(path)

    def _finalize(self):
        polygon = QPolygonF(self._points)
        item = QGraphicsPolygonItem(polygon)
        item.setPen(QPen(self._border_color, 2))
        item.setBrush(QBrush(self._color))
        item.setZValue(ZOrder.ZONE_FILL)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        suppress_selection_decoration(item)
        self.viewport.scene().addItem(item)
        for cb in self._finalize_callbacks:
            cb(polygon)
        self._points.clear()


# ─── Region Brush Tool (Região panel — paint/edit a colored área) ─────────

class RegionBrushTool(_DashedCursorMixin, BaseTool):
    """Circular brush that paints (or erases) into a target RegionLayer.

    Distinct from RegionTool above — that one is the toolbar's click-point
    polygon tool used for Estrada/Rio/Bioma. This one is armed exclusively
    by the Região panel (Nova Região / clicking a card) via `set_target`,
    and reuses TerrainLayer's soft-stamp + snap-to-cell-fill painting
    (see RegionLayer) instead of a boolean polygon path — same mechanism
    the terrain Brush already uses for radius/softness/opacity/erase.
    """

    name = "RegiãoPincel"
    cursor = Qt.CursorShape.CrossCursor
    SPACING_RATIO = 0.08  # fraction of diameter between interpolated stamps along a drag

    def __init__(self, viewport: Viewport, history_engine=None):
        super().__init__(viewport)
        self._history = history_engine
        self._target = None  # RegionLayer | None
        self._active_boundary = None  # MapBoundary | None — constrains painting, like BrushTool
        self._mode = "add"  # "add" | "remove"
        self.radius = 50.0
        # Hard-edged stamp (no radial alpha falloff) — a região's fill is
        # meant to read as a solid, opaque area (Cities-Skylines district
        # style), with "Opacidade" (RegionLayer.set_opacity) as the ONLY
        # transparency control. Dither is disabled too (see _params) since
        # it punches noisy partial-alpha holes near each stamp's edge —
        # fine for a single organic terrain stamp, but region strokes
        # overlap heavily while growing an area, so those holes land
        # inside the fill at uneven spots per stamp and read as blotchy
        # color/opacity instead of one solid fill. The organic-looking
        # silhouette instead comes from the traced/morphological-closed
        # outline in RegionLayer._bordered_result.
        self.softness = 0.0
        self._painting = False
        self._stroke_button: Qt.MouseButton | None = None
        self._before_state: dict | None = None
        self._stroke_finished_callbacks: list = []
        self._minimap = None
        self._cursor_item: QGraphicsEllipseItem | None = None
        self._last_pos: QPointF | None = None

    def on_stroke_finished(self, callback):
        """Registra callback() chamado ao soltar o botão após pintar."""
        self._stroke_finished_callbacks.append(callback)

    # ─── Cursor (see _DashedCursorMixin) — diameter driven by radius*2
    # instead of a `size` property. ─────────────────────────────────────

    def _cursor_diameter(self) -> float:
        return self.radius * 2

    def activate(self):
        super().activate()
        self._show_cursor()

    def deactivate(self):
        super().deactivate()
        self._hide_cursor()

    def set_target(self, layer):
        """RegionLayer to paint into, or None to disarm painting."""
        self._target = layer

    @property
    def target(self):
        return self._target

    def set_active_boundary(self, boundary):
        """MapBoundary to constrain painting to, or None for an infinite
        map — same `_active_boundary` idea as BrushTool's own, so a
        Região painted "on" a bounded terrain can't spill past it (see
        _boundary_clip_path_local for how that's actually enforced)."""
        self._active_boundary = boundary

    def _boundary_clip_path_local(self) -> QPainterPath | None:
        """The active boundary's shape, converted into the target
        RegionLayer's own local coordinate space — used to CLIP each
        stamp (see _paint) instead of the old all-or-nothing approach of
        rejecting the whole stamp the instant its center crossed the
        boundary. That point-only check left a permanently unpaintable
        strip near the edge on anything but a perfect rectangle (a
        stamp's center has to clear the boundary check before its radius
        can even reach the border, so corners/curves never got fully
        covered) — clipping the actual painted pixels instead means
        dragging right along (or slightly past) the edge fills all the
        way up to it, same as Cities Skylines' district painting.
        None (no clip) for an infinite map."""
        if self._active_boundary is None or self._active_boundary._item is None or self._target is None:
            return None
        boundary_item = self._active_boundary._item
        scene_path = boundary_item.mapToScene(boundary_item.path())
        return self._target.item.mapFromScene(scene_path)

    def set_mode(self, mode: str):
        self._mode = mode

    def set_params(self, radius: float | None = None, softness: float | None = None):
        if radius is not None:
            self.radius = max(1.0, radius)
            self.update_cursor_size()
        if softness is not None:
            self.softness = max(0.0, min(1.0, softness))

    def _params(self, erase: bool) -> TerrainBrushParams:
        # opacity is always 1.0 here — a região's visible transparency is
        # the LAYER's own live opacity now (RegionLayer.set_opacity),
        # not the paint mask's alpha. The mask's own alpha only ever
        # accumulates via SourceOver and can never be lowered once
        # painted, which is exactly why the old "Opacidade" brush param
        # (this used to read self.opacity here) visibly did nothing once
        # you'd already painted over an area.
        return TerrainBrushParams(
            size=self.radius * 2, opacity=1.0, softness=self.softness, erase=erase,
            dither=False,
        )

    def _paint(self, scene_pos: QPointF, erase: bool):
        if self._target is None:
            return
        params = self._params(erase)
        # Deliberately always the circular stamp, never a grid-cell fill —
        # a região is a freeform painted area (Cities Skylines style), not
        # grid-tile placement. Snap/Grid is shared engine-wide (see
        # CanvasEngine.snap) for the terrain Brush tool's own tile
        # alignment; this tool never wired into it, precisely so leaving
        # Snap on from terrain painting doesn't silently turn the next
        # região stroke into one giant rectangular grid-cell fill instead
        # of a small circular stamp.
        local = self._target.scene_to_local(scene_pos)
        clip_path = self._boundary_clip_path_local()
        self._target.paint_at(local, params, clip_path)
        self._target.update_live()

    def _continue_paint(self, scene_pos: QPointF, erase: bool):
        """Interpolates stamps between the last painted point and
        `scene_pos` instead of stamping only at `scene_pos` itself — a
        fast drag can jump farther between two mouse-move events than one
        stamp's own footprint, leaving unpainted gaps inside the stroke
        (worse now that stamps are hard-edged, see RegionBrushTool.
        __init__'s softness note — there's no soft overlap to paper over
        the seam anymore). Same gap-closing idea as BrushTool's own
        _continue_terrain_stroke."""
        if self._target is None or self._last_pos is None:
            return
        dx = scene_pos.x() - self._last_pos.x()
        dy = scene_pos.y() - self._last_pos.y()
        dist = math.hypot(dx, dy)
        spacing = max(1.0, self.radius * 2 * self.SPACING_RATIO)
        if dist < spacing:
            return
        params = self._params(erase)
        clip_path = self._boundary_clip_path_local()
        steps = max(1, math.ceil(dist / spacing))
        for i in range(1, steps + 1):
            t = i / steps
            pt = QPointF(self._last_pos.x() + dx * t, self._last_pos.y() + dy * t)
            local = self._target.scene_to_local(pt)
            self._target.paint_at(local, params, clip_path)
        self._target.update_live()
        self._last_pos = scene_pos

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        # Left = paint (add), Right = erase — no on-screen mode toggle
        # anymore, so the mouse button itself picks the mode per stroke.
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        if self._target is None:
            return
        self._painting = True
        self._stroke_button = event.button()
        if self._history:
            self._before_state = self._target.capture_state()
        self._paint(scene_pos, erase=(self._stroke_button == Qt.MouseButton.RightButton))
        self._last_pos = scene_pos

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._cursor_item:
            self._cursor_item.setRect(
                scene_pos.x() - self.radius, scene_pos.y() - self.radius,
                self.radius * 2, self.radius * 2,
            )
        if self._painting:
            self._continue_paint(scene_pos, erase=(self._stroke_button == Qt.MouseButton.RightButton))

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() != self._stroke_button or not self._painting:
            return
        self._painting = False
        self._stroke_button = None
        self._last_pos = None
        if self._target is not None:
            self._target.finish_stroke()
            if self._history and self._before_state is not None:
                from src.engines.core.history import PaintStrokeCommand
                after_state = self._target.capture_state()
                self._history.push(PaintStrokeCommand(self._target, self._before_state, after_state))
        self._before_state = None
        for cb in self._stroke_finished_callbacks:
            cb()
