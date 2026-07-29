"""Canvas tools — Brush (terrain + object paint), Region, Road, River."""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QMouseEvent, QPen, QColor, QBrush, QPainterPath, QPolygonF,
    QRadialGradient, QImage, QPixmap, QPainter,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPolygonItem,
    QGraphicsPixmapItem,
)

from src.canvas.tools.base import BaseTool
from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams, build_stamp, dilate, morphological_close
from src.engines.core.history import PaintStrokeCommand, PlaceObjectCommand, CompositeCommand
from src.canvas.item_utils import suppress_selection_decoration

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport
    from src.engines.map.brush import BrushEngine
    from src.engines.assets.engine import AssetEngine
    from src.engines.core.history import HistoryEngine

logger = logging.getLogger("MAKEMAP")


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
    # asset_id prefix for the virtual "Effects" category assets (see
    # BrushMediator.populate_assets) — these aren't real library files, so
    # they're routed here by id prefix instead of a DB category lookup
    # (see _check_is_terrain, which DOES hit the DB).
    EFFECT_ASSET_PREFIX = "effect:"
    MAX_FADE_SECONDS = 3.0        # smoothness=1.0 fade-in duration, real seconds
    SHORELINE_DILATE = 70         # px — outer reach of the foam glow from a land/water boundary
    SHORELINE_SMOOTH = 12         # px — rounds the edge-dither's jagged notches before glowing
    # (radius fraction of SHORELINE_DILATE, alpha) rings, outer/faintest
    # first — painted in this order so each smaller+stronger ring lands
    # on top (SourceOver), reading as one smooth gradient glow instead of
    # a flat-opacity band. See _blend_shoreline_pair. Kept translucent even
    # at its strongest (peak ~25%) — a solid opaque stripe reads as a
    # painted-on ribbon, not a faint glow the terrain still shows through.
    # Many closer-spaced, low-alpha rings so the falloff reads as one long,
    # soft gradient across the full DILATE reach instead of visible steps.
    SHORELINE_RINGS = (
        (1.00, 2),
        (0.80, 4),
        (0.60, 6),
        (0.42, 10),
        (0.26, 13),
        (0.12, 17),
    )

    def __init__(self, viewport: Viewport, brush_engine: BrushEngine,
                 asset_engine: AssetEngine = None, history_engine: HistoryEngine = None):
        super().__init__(viewport)
        self._engine = brush_engine
        self._asset_engine = asset_engine
        self._history = history_engine
        self._minimap = None
        self._sound_engine = None
        self._snap_manager = None
        self._cursor_item: QGraphicsEllipseItem | None = None
        self._stroke_items: list = []

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

        # (water_asset_id, land_asset_id) -> the standalone foam overlay
        # item for that pair (see _apply_shoreline_blend) — recomputed
        # from scratch after every stroke, never written into either
        # layer's own paint mask, so undo/"Apagar Pintura" of the actual
        # terrain is completely unaffected by this purely-derived overlay.
        self._shoreline_overlays: dict[tuple[str, str], QGraphicsPixmapItem] = {}

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
        self.mask_mode = False
        # True only while a stroke started with the right mouse button is
        # in progress — right-click is a momentary "erase" shortcut that
        # doesn't touch the erase_mode toggle itself.
        self._stroke_force_erase = False

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

    def _check_is_terrain(self, asset_id: str) -> bool:
        """Check if asset belongs to 'terrain' OR 'water' category — both
        paint into a TerrainLayer mask (see _get_or_create_terrain_layer),
        water is just a terrain material tagged for the shoreline blend
        (see is_water_asset), not a different paint mechanism."""
        if not self._asset_engine or not asset_id:
            return False
        lib = getattr(self._asset_engine, 'library', None)
        if not lib:
            return False
        row = lib._db.execute(
            "SELECT category FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return row["category"] in ("terrain", "water") if row else False

    # ─── Mouse Events ─────────────────────────────────────────────────

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        is_right = event.button() == Qt.MouseButton.RightButton
        if event.button() != Qt.MouseButton.LeftButton and not is_right:
            return
        if not self._is_within_bounds(scene_pos):
            return

        is_terrain = self._is_terrain_mode or self._is_effect_mode or (self.mask_mode and self._active_asset_id)
        # Right-click is an "erase" shortcut — only meaningful for terrain
        # painting, which is the only mode that supports erasing.
        if is_right and not is_terrain:
            return
        self._stroke_force_erase = is_right

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
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return

        if self._active_terrain_layer:
            self._end_terrain_stroke()
            self._stroke_force_erase = False
        elif self._engine.is_active:
            self._engine.end_stroke()
            try:
                self._engine.stamp_placed.disconnect(self._on_object_stamp)
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
            self._apply_shoreline_blend()
        except Exception:
            logger.exception("Falha ao aplicar halo de espuma terra-água")

    # ─── Shoreline blend (Fase C — land/water foam halo) ────────────────
    # Only ever runs here, at stroke-finish — never live-drag, same cost
    # pattern RegionLayer._bordered_result already uses (dilate/erode a
    # small cropped region, not the whole layer, only once per stroke).

    def _apply_shoreline_blend(self):
        """Soft white foam band wherever a water-tagged terrain layer
        meets a non-water one — the Inkarnate-style effect. Checks every
        (water, land) layer pair; a cheap scene-rect intersection test
        skips anything not actually near each other before any of the
        more expensive mask work runs."""
        water_ids = [aid for aid in self._terrain_layers if self.is_water_asset(aid)]
        if not water_ids:
            return
        for water_id in water_ids:
            water_layer = self._terrain_layers[water_id]
            for land_id, land_layer in self._terrain_layers.items():
                if land_id == water_id or self.is_water_asset(land_id):
                    continue
                self._blend_shoreline_pair(water_id, water_layer, land_id, land_layer)

    def _shared_scene_overlap(self, layer_a: TerrainLayer, layer_b: TerrainLayer,
                               pad: int) -> QRectF | None:
        """Bounding rect (scene coords) covering wherever two terrain
        layers' painted areas are within `pad` px of each other — None if
        neither overlaps nor is even close. Used by _blend_shoreline_pair
        as the cheap pre-check that skips the more expensive mask/dilate
        work for any pair that's nowhere near touching."""
        a_bounds = layer_a.opaque_bounds_local()
        b_bounds = layer_b.opaque_bounds_local()
        if a_bounds is None or b_bounds is None:
            return None
        a_scene = layer_a.item.mapToScene(QRectF(a_bounds)).boundingRect().adjusted(-pad, -pad, pad, pad)
        b_scene = layer_b.item.mapToScene(QRectF(b_bounds)).boundingRect().adjusted(-pad, -pad, pad, pad)
        overlap = a_scene.intersected(b_scene)
        return overlap if not overlap.isEmpty() else None

    @staticmethod
    def _mask_and(img: QImage, mask: QImage) -> QImage:
        """A copy of `img` with its alpha further clipped by `mask`'s own
        alpha (DestinationIn) — e.g. "img, but only where mask is also
        opaque". Used by _blend_shoreline_pair."""
        result = QImage(img)
        p = QPainter(result)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, mask)
        p.end()
        return result

    @staticmethod
    def _alpha_stencil(ring: QImage, alpha: int) -> QImage:
        """A flat, `alpha`-strength alpha-only stencil shaped like `ring`'s
        own silhouette — scales a ring's already-graded/binary alpha down
        to one fixed strength. Used by _blend_shoreline_pair."""
        stencil = QImage(ring.size(), QImage.Format.Format_ARGB32_Premultiplied)
        stencil.fill(QColor(0, 0, 0, 0))
        sp = QPainter(stencil)
        sp.fillRect(stencil.rect(), QColor(255, 255, 255, alpha))
        sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        sp.drawImage(0, 0, ring)
        sp.end()
        return stencil

    def _blend_shoreline_pair(self, water_id: str, water_layer: TerrainLayer,
                               land_id: str, land_layer: TerrainLayer):
        key = (water_id, land_id)
        pad = self.SHORELINE_DILATE + 4
        overlap_scene = self._shared_scene_overlap(water_layer, land_layer, pad)
        if overlap_scene is None:
            self._clear_shoreline_overlay(key)
            return

        w_local_rect = water_layer.item.mapFromScene(overlap_scene).boundingRect().toAlignedRect()
        l_local_rect = land_layer.item.mapFromScene(overlap_scene).boundingRect().toAlignedRect()
        w_crop = water_layer.mask_crop(w_local_rect)
        l_crop = land_layer.mask_crop(l_local_rect)
        if w_crop is None or l_crop is None or w_crop.size() != l_crop.size():
            # Mismatched crop sizes only happens if one layer's bounds
            # needed clamping and the other didn't (e.g. right at the very
            # edge of an independently-expanded layer) — skip this stroke
            # rather than risk compositing two different-sized images;
            # the halo reappears on the next stroke once it realigns.
            self._clear_shoreline_overlay(key)
            return

        # Pre-smooth each mask before dilating — the edge-dither (organic
        # terrain-to-terrain mixing, see build_stamp) deliberately tears
        # small notches into the raw paint mask, and dilating THAT
        # directly (plus dilate's own 16-facet approximation of a circle)
        # produced a spiky, jagged halo instead of a calm glow. Closing
        # first rounds those notches away for the glow's own computation
        # only — the actual painted terrain keeps its organic edge.
        w_smooth = morphological_close(w_crop, self.SHORELINE_SMOOTH)
        l_smooth = morphological_close(l_crop, self.SHORELINE_SMOOTH)

        # Built from several nested dilate radii, largest/faintest first —
        # SourceOver painting order means each smaller, more opaque ring
        # lands on top of the previous, larger, fainter one, so the net
        # result reads as a soft gradient glow (strongest right at the
        # boundary, fading outward) instead of one flat-opacity band.
        foam = QImage(w_smooth.size(), QImage.Format.Format_ARGB32_Premultiplied)
        foam.fill(QColor(0, 0, 0, 0))
        fp = QPainter(foam)
        any_content = False
        for radius_fraction, alpha in self.SHORELINE_RINGS:
            r = max(1, round(self.SHORELINE_DILATE * radius_fraction))
            w_dilated = dilate(w_smooth, r)
            l_dilated = dilate(l_smooth, r)

            ring = self._mask_and(w_dilated, l_dilated)
            if not self._image_has_opacity(ring):
                continue
            any_content = True

            tinted = self._alpha_stencil(ring, alpha)

            fp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            fp.drawImage(0, 0, tinted)
        fp.end()

        if not any_content:
            self._clear_shoreline_overlay(key)
            return

        overlay = self._get_or_create_shoreline_overlay(key)
        overlay.setPixmap(QPixmap.fromImage(foam))
        overlay.setPos(overlap_scene.topLeft())

    def _get_or_create_shoreline_overlay(self, key: tuple[str, str]) -> QGraphicsPixmapItem:
        overlay = self._shoreline_overlays.get(key)
        if overlay is None:
            overlay = QGraphicsPixmapItem()
            # Between terrain (z=1) and painted régions/objects (z=5/10+)
            # — the foam should sit on top of the terrain it's blending
            # but not visually block anything stamped on top of the map.
            overlay.setZValue(1.5)
            overlay.setData(0, {"item_type": "shoreline_blend"})
            suppress_selection_decoration(overlay)
            self.viewport.scene().addItem(overlay)
            self._shoreline_overlays[key] = overlay
        return overlay

    def _clear_shoreline_overlay(self, key: tuple[str, str]):
        overlay = self._shoreline_overlays.pop(key, None)
        if overlay is not None:
            scene = overlay.scene()
            if scene is not None:
                scene.removeItem(overlay)

    def _clear_all_blend_overlays(self):
        """Drops every derived shoreline-foam overlay — called when the
        underlying terrain layers themselves are wiped (see
        BrushCanvasEngine.clear_terrain_layers), so a project reload
        doesn't leave the previous project's overlays orphaned in the
        scene."""
        for key in list(self._shoreline_overlays):
            self._clear_shoreline_overlay(key)

    @staticmethod
    def _image_has_opacity(img: QImage) -> bool:
        """Cheap downsampled alpha scan (same technique as RegionLayer.
        area_m2) — whether `img` has any non-transparent pixel at all."""
        if img.width() == 0 or img.height() == 0:
            return False
        small = img.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        for y in range(small.height()):
            for x in range(small.width()):
                if small.pixelColor(x, y).alpha() > 10:
                    return True
        return False

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
        if not self._asset_engine or not asset_id:
            return asset_id
        lib = getattr(self._asset_engine, 'library', None)
        if not lib:
            return asset_id
        try:
            row = lib._db.execute(
                "SELECT category FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
            return row["category"] if row and row["category"] else asset_id
        except Exception:
            return asset_id

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
            parent_item = self._active_boundary._item

        map_size = self.INITIAL_LAYER_SIZE
        layer = TerrainLayer(self.viewport.scene(), map_size, map_size, parent_item=parent_item)
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

    def is_water_asset(self, asset_id: str) -> bool:
        """Whether `asset_id` belongs to the "water" category — used by
        _apply_shoreline_blend to find land/water layer pairs. Queried
        live (not cached) every time: this only runs a handful of times
        per stroke-finish (never per-stamp), and an asset's category can
        change at any moment via the Config/Assets panel's drag-and-drop
        move, independent of the Brush tool's own lifecycle — a cache
        here would just go stale the moment that happens mid-session."""
        if not self._asset_engine or not getattr(self._asset_engine, "library", None):
            return False
        return self._asset_engine.library.is_water(asset_id)

    # ─── Object Stroke ───────────────────────────────────────────────

    def _begin_object_stroke(self, pos: QPointF):
        self._stroke_items.clear()
        self._engine.stamp_placed.connect(self._on_object_stamp)
        self._engine.begin_stroke(pos)
        if self._history:
            self._history.begin_group("Pintura de objetos")

    def place_stamp_item(self, asset_id: str, position: QPointF, rotation: float,
                          scale: float, opacity: float) -> QGraphicsPixmapItem | None:
        """Builds+places a single brush-stamped object item — shared by
        live painting (_on_object_stamp) and BrushMediator's DB-reload on
        project switch, so both produce identical items. `position` is in
        scene coordinates regardless of boundary parenting."""
        if not self._asset_engine or not asset_id:
            return None

        pixmap = self._asset_engine.get_pixmap(asset_id)
        if not pixmap or pixmap.isNull():
            return None

        # Parent to boundary item so stamp moves with the terrain
        parent_item = None
        if self._active_boundary and self._active_boundary._item:
            parent_item = self._active_boundary._item

        item = QGraphicsPixmapItem(pixmap, parent_item)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)

        if parent_item:
            # Convert scene position to parent-local
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
        item.setZValue(10)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
        item.setData(0, {"item_type": "asset", "asset_id": asset_id})
        suppress_selection_decoration(item)
        return item

    def _on_object_stamp(self, stamp):
        """Render object stamp as individual QGraphicsPixmapItem."""
        item = self.place_stamp_item(stamp.asset_id, stamp.position, stamp.rotation, stamp.scale, stamp.opacity)
        if item is None:
            return
        self._stroke_items.append(item)

        if self._history:
            self._history.push(PlaceObjectCommand(item))

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
        suppress_selection_decoration(item)
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
        suppress_selection_decoration(item)
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
        suppress_selection_decoration(item)
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


# ─── Region Brush Tool (Região panel — paint/edit a colored área) ─────────

class RegionBrushTool(BaseTool):
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

    # ─── Cursor — same dashed-circle preview as BrushTool (see
    # BrushTool._show_cursor/_hide_cursor above), diameter driven by
    # radius*2 instead of a `size` property. ──────────────────────────

    def set_minimap(self, minimap):
        self._minimap = minimap

    def update_cursor_size(self):
        if self._cursor_item:
            rect = self._cursor_item.rect()
            cx = rect.x() + rect.width() / 2
            cy = rect.y() + rect.height() / 2
            d = self.radius * 2
            self._cursor_item.setRect(cx - self.radius, cy - self.radius, d, d)

    def activate(self):
        super().activate()
        self._show_cursor()

    def deactivate(self):
        super().deactivate()
        self._hide_cursor()

    def _show_cursor(self):
        if self._cursor_item:
            return
        d = self.radius * 2
        self._cursor_item = QGraphicsEllipseItem(-self.radius, -self.radius, d, d)
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
