"""Shoreline foam blend (Fase C — land/water foam halo) — a soft white foam
band, or a few concentric cartoon wave lines, wherever a water-tagged
terrain layer meets a non-water one. Only ever runs at stroke-finish, never
live-drag, same cost pattern RegionLayer._bordered_result already uses
(dilate/erode a small cropped region, not the whole layer, only once per
stroke). Owns its own derived overlay items — recomputed from scratch after
every stroke, never written into either layer's own paint mask, so undo/
"Apagar Pintura" of the actual terrain is completely unaffected by this
purely-derived effect.

Split out of BrushTool (see BrushTool._shoreline) — depends only on
BrushTool's terrain_layers/asset_engine/viewport, never the brush/stamp
painting state itself, so it doesn't need to be a BaseTool at all.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem

from src.canvas.item_utils import suppress_selection_decoration
from src.canvas.z_order import ZOrder
from src.engines.map.terrain_layer import TerrainLayer, dilate, morphological_close

if TYPE_CHECKING:
    from src.canvas.tools.brush_tool import BrushTool

logger = logging.getLogger("MAKEMAP")


class ShorelineBlender:
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
    # "cartoon" style water gets a different shoreline effect entirely — a
    # few concentric wave lines hugging the coast (like a stylized map
    # icon) instead of the realistic soft foam glow above, which reads as
    # too photoreal next to flat cartoon terrain. See _blend_shoreline_pair
    # (branches on the water asset's own `style`) and _wave_shoreline_image.
    CARTOON_WAVE_RADII = (5, 12, 20, 29)   # px — distance of each wave line from the coast
    CARTOON_WAVE_THICKNESS = 2             # px — stroke width of each wave line
    CARTOON_WAVE_REACH = 40                # px — how far past the coast waves are allowed to show at all
    CARTOON_WAVE_ALPHA = 215                # white, same as _alpha_stencil's fixed tint color

    def __init__(self, brush_tool: "BrushTool"):
        self._brush = brush_tool
        # (water_asset_id, land_asset_id) -> the standalone foam overlay
        # item for that pair (see apply()) — recomputed from scratch after
        # every stroke, never written into either layer's own paint mask.
        self._shoreline_overlays: dict[tuple[str, str], QGraphicsPixmapItem] = {}

    @property
    def viewport(self):
        return self._brush.viewport

    @property
    def _asset_engine(self):
        return self._brush._asset_engine

    @property
    def _terrain_layers(self):
        return self._brush._terrain_layers

    def is_water_asset(self, asset_id: str) -> bool:
        """Whether `asset_id` belongs to the "water" category — used by
        apply() to find land/water layer pairs. Queried live (not cached)
        every time: this only runs a handful of times per stroke-finish
        (never per-stamp), and an asset's category can change at any moment
        via the Config/Assets panel's drag-and-drop move, independent of
        the Brush tool's own lifecycle — a cache here would just go stale
        the moment that happens mid-session."""
        if not self._asset_engine or not getattr(self._asset_engine, "library", None):
            return False
        return self._asset_engine.library.is_water(asset_id)

    def apply(self):
        """Soft white foam band wherever a water-tagged terrain layer
        meets a non-water one — the Inkarnate-style effect. Checks every
        (water, land) layer pair; a cheap scene-rect intersection test
        skips anything not actually near each other before any of the
        more expensive mask work runs."""
        # is_water_asset() alone would foam every water asset uniformly —
        # fine for ocean/sea, wrong for a calm river. has_shore_foam() is
        # the per-asset opt-out (see AssetEffectsPanel's "🌊 Maresia"
        # toggle, only shown for water-category assets), default True so
        # existing water assets keep looking exactly as before.
        #
        # Water assets are walked even when foam is currently disabled
        # (instead of being filtered out of the loop entirely) so that an
        # asset whose foam was just turned off — but that already has a
        # foam overlay sitting in the scene from before the toggle — gets
        # that stale overlay actively cleared here rather than silently
        # skipped and left behind forever (nothing else ever revisits an
        # excluded pair to clean it up).
        water_ids = [aid for aid in self._terrain_layers if self.is_water_asset(aid)]
        if not water_ids:
            return
        for water_id in water_ids:
            water_layer = self._terrain_layers[water_id]
            foam_enabled = self._asset_engine.library.has_shore_foam(water_id)
            for land_id, land_layer in self._terrain_layers.items():
                if land_id == water_id or self.is_water_asset(land_id):
                    continue
                if foam_enabled:
                    self._blend_shoreline_pair(water_id, water_layer, land_id, land_layer)
                else:
                    self._clear_shoreline_overlay((water_id, land_id))

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
    def _mask_subtract(img: QImage, minus: QImage) -> QImage:
        """A copy of `img` with its alpha punched out wherever `minus` is
        opaque (DestinationOut) — "img, but not where minus is also
        opaque". Used by _wave_shoreline_image to turn a filled dilated
        blob into a thin annulus/shell (outer dilation minus inner
        dilation = a ring right at that distance from the coast)."""
        result = QImage(img)
        p = QPainter(result)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.drawImage(0, 0, minus)
        p.end()
        return result

    def _wave_shoreline_image(self, w_smooth: QImage, l_smooth: QImage) -> QImage | None:
        """Cartoon-style shoreline effect: a few concentric thin wave
        lines hugging the coast, instead of the realistic soft gradient
        glow (see _blend_shoreline_pair, which picks between the two
        based on the water asset's own `style`). Reuses the same
        dilate/AND-mask primitives as the glow — each wave line is the
        thin annulus/shell between two dilation radii of the water mask
        (an "isoline" at that exact distance from the coast), kept only
        where it's still close enough to land (CARTOON_WAVE_REACH) so
        waves don't bleed out into open water far from any shore."""
        l_reach = dilate(l_smooth, self.CARTOON_WAVE_REACH)
        waves = QImage(w_smooth.size(), QImage.Format.Format_ARGB32_Premultiplied)
        waves.fill(QColor(0, 0, 0, 0))
        wp = QPainter(waves)
        any_content = False
        for r in self.CARTOON_WAVE_RADII:
            outer = dilate(w_smooth, r + self.CARTOON_WAVE_THICKNESS)
            inner = dilate(w_smooth, r)
            shell = self._mask_and(self._mask_subtract(outer, inner), l_reach)
            if not self._image_has_opacity(shell):
                continue
            any_content = True
            tinted = self._alpha_stencil(shell, self.CARTOON_WAVE_ALPHA)
            wp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            wp.drawImage(0, 0, tinted)
        wp.end()
        return waves if any_content else None

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

        # Cartoon-style water gets concentric wave lines instead of the
        # realistic soft glow below — see _wave_shoreline_image. Checked
        # per water asset (not per stroke/session) since different water
        # assets painted in the same map can each have their own style.
        library = getattr(self._asset_engine, "library", None)
        is_cartoon = bool(library) and library.get_style(water_id) == "cartoon"
        if is_cartoon:
            foam = self._wave_shoreline_image(w_smooth, l_smooth)
            if foam is None:
                self._clear_shoreline_overlay(key)
                return
            overlay = self._get_or_create_shoreline_overlay(key)
            overlay.setPixmap(QPixmap.fromImage(foam))
            overlay.setPos(overlap_scene.topLeft())
            return

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
            # Between terrain and painted régions/objects — the foam should
            # sit on top of the terrain it's blending but not visually
            # block anything stamped on top of the map.
            overlay.setZValue(ZOrder.SHORELINE_BLEND)
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

    def clear_all(self):
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
