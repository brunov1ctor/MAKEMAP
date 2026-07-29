"""TerrainLayer — rasterized terrain painting with mask + tiled texture."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QBrush, QTransform,
    QRadialGradient, QPen, QPolygonF, QPainterPath,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene

from src.canvas.item_utils import suppress_selection_decoration


@dataclass
class TerrainBrushParams:
    """Parameters for a single terrain brush stroke."""
    size: float = 100.0
    opacity: float = 1.0
    softness: float = 0.5  # 0=hard edge, 1=fully soft
    roughness: float = 0.0  # 0=perfect circle, 1=jagged edge — only affects paint_at, not paint_cell
    texture_scale: float = 1.0
    texture_rotation: float = 0.0
    erase: bool = False
    mask_only: bool = False  # paint mask without showing texture
    dither: bool = True  # organic noisy edge (see _apply_edge_dither) — off for solid-fill regions


# ±65% radius swing at roughness=1 — needs to read as a clearly jagged/torn
# edge at a glance, not a barely-there wobble. Shared by _jagged_circle_path
# (the actual drawn shape) and paint_at's gradient radius below, so the
# gradient's outer stop reaches at least as far as the jaggedest bulge —
# otherwise bulges beyond the original radius would fall past the
# gradient's last color stop and render fully transparent, invisible.
_ROUGHNESS_JITTER = 0.65


def _jagged_circle_path(center: QPointF, radius: float, roughness: float) -> QPainterPath:
    """A closed path approximating a circle but with the radius perturbed
    per angular segment — used instead of a perfect drawEllipse() when
    roughness > 0, only in the freehand soft-stamp path (paint_at). Snap's
    cell-fill (paint_cell) has no circular edge to begin with, so roughness
    naturally has no effect there."""
    segments = 20
    path = QPainterPath()
    for i in range(segments):
        angle = (i / segments) * 2 * math.pi
        r = radius * (1.0 + roughness * random.uniform(-_ROUGHNESS_JITTER, _ROUGHNESS_JITTER))
        x = center.x() + r * math.cos(angle)
        y = center.y() + r * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _circular_offsets(radius: int, steps: int) -> list[tuple[int, int]]:
    return [
        (round(radius * math.cos(2 * math.pi * i / steps)),
         round(radius * math.sin(2 * math.pi * i / steps)))
        for i in range(steps)
    ]


def dilate(img: QImage, radius: int, steps: int = 16) -> QImage:
    """Grows img's opaque silhouette outward by `radius` px in every
    direction — a true morphological dilate (net size increase), NOT the
    close below (which dilates then eroDES back, netting close to zero
    boundary growth — good for smoothing bumps, useless for making two
    adjacent-but-not-quite-overlapping masks actually overlap). `steps`
    directional composites approximate a circular structuring element
    (cheap vs a true per-pixel circular dilate); Lighten takes the max
    alpha across all offset copies, i.e. the union.

    Used by BrushTool's shoreline-blend pass to expand two different
    terrain layers' masks so they genuinely overlap in a band around
    their (already near-complementary, see build_stamp's docstring)
    shared boundary — morphological_close was tried here first and does
    NOT work for this: closing doesn't grow the outer silhouette at all,
    so two masks that only just touch never end up overlapping no matter
    how large the radius."""
    offsets = _circular_offsets(radius, steps)
    dilated = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
    dilated.fill(QColor(0, 0, 0, 0))
    dp = QPainter(dilated)
    dp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
    dp.drawImage(0, 0, img)
    for dx, dy in offsets:
        dp.drawImage(dx, dy, img)
    dp.end()
    return dilated


def morphological_close(img: QImage, radius: int, steps: int = 16) -> QImage:
    """Dilate then erode by `radius` px — fills small gaps/bumps between
    overlapping brush stamps and rounds the union into one smooth blob,
    WITHOUT growing its overall size (erode undoes dilate's own growth,
    net effect is only filling small concavities/gaps up to `radius`
    wide). Erode intersects the dilated copies (repeated DestinationIn).

    Originally RegionLayer-only (its _bordered_result traces this into a
    single smooth outline around one shape's own silhouette); moved here
    so other callers in this package can reuse the same primitive."""
    offsets = _circular_offsets(radius, steps)
    dilated = dilate(img, radius, steps)

    eroded = QImage(dilated)
    ep = QPainter(eroded)
    ep.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    for dx, dy in offsets:
        ep.drawImage(-dx, -dy, dilated)
    ep.end()
    return eroded


# ─── Organic edge dithering (always on, see build_stamp) ────────────────
# A raw QRadialGradient stamp has a perfectly smooth, geometric edge —
# fine for one isolated layer, but two different terrain types meeting at
# one always leaves a razor-clean curve, reading as an abrupt cut no
# matter how soft the gradient's own falloff is. Punching small random
# holes into the stamp's outer band (see build_stamp) breaks that up into
# a hand-drawn, speckled edge instead — and because paint_at reuses this
# SAME stamp to both paint the active layer and erase every other one
# (see build_stamp's own docstring), whatever gets punched out here lets
# the OTHER terrain's existing paint show through in exactly those spots,
# so the two interleave a little at the border instead of butting up
# against a clean line. Always active, no brush-panel control — the user
# asked for this to just be how the brush behaves, not another slider.
#
# A dragged stroke lays down many overlapping stamps (spaced by
# TERRAIN_SPACING_RATIO, see BrushTool). A hole punched by one stamp only
# survives in the FINAL union if every OTHER overlapping stamp that also
# covers that exact spot agrees it should be a hole too — otherwise
# whichever stamp has full alpha there just paints over it, and the union
# smooths back into a clean edge no matter how ragged each stamp looked
# in isolation. That only happens if the noise is sampled by each output
# PIXEL's own absolute world position, not by which stamp happens to be
# asking — so this uses the exact same "tiled texture pinned to world
# origin" trick TerrainLayer._create_texture_brush already uses for
# terrain materials: a QBrush(tile) with its transform translated by
# -world_pos, so Qt's own brush tiling samples the SAME fixed noise tile
# at the SAME absolute position regardless of which stamp/layer is
# painting — every overlapping stamp along a stroke then reinforces one
# consistent ragged silhouette instead of separately-randomized ones
# cancelling out.
_DITHER_TILE_LOW = 12    # px — raw random source (pre-smoothing)
_DITHER_TILE_SIZE = 48   # px — final tileable pixmap (smoothed once, cached)
_DITHER_STRENGTH = 200  # 0-255 — how deep the punched holes can go
_dither_tile: QPixmap | None = None


def _get_dither_tile() -> QPixmap:
    """Cached once per process — a small random field smoothed up once
    into a reusable tileable pixmap, then sampled via brush tiling (see
    _apply_edge_dither) rather than regenerated per stamp."""
    global _dither_tile
    if _dither_tile is None:
        raw = QImage(_DITHER_TILE_LOW, _DITHER_TILE_LOW, QImage.Format.Format_ARGB32_Premultiplied)
        for y in range(_DITHER_TILE_LOW):
            for x in range(_DITHER_TILE_LOW):
                raw.setPixelColor(x, y, QColor(255, 255, 255, random.randint(0, 255)))
        smooth = raw.scaled(_DITHER_TILE_SIZE, _DITHER_TILE_SIZE,
                             Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        _dither_tile = QPixmap.fromImage(smooth)
    return _dither_tile


def _apply_edge_dither(img: QImage, center: QPointF, gradient_r: float, world_pos: QPointF | None):
    """Punches noise-shaped holes into `img`'s outer band (a fixed
    plateau from 45%-92% of gradient_r, regardless of softness/roughness
    so the gradient stops stay validly ordered no matter what those
    params are set to) — see the module comment above for why this
    happens unconditionally, and why reusing one stamp for paint+erase
    (Fase A) makes this a safe, seam-free interleaving instead of a new
    gap."""
    size = img.width()
    ring = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    ring.fill(QColor(0, 0, 0, 0))
    rp = QPainter(ring)
    rp.setRenderHint(QPainter.RenderHint.Antialiasing)
    ring_gradient = QRadialGradient(center, gradient_r)
    ring_gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
    ring_gradient.setColorAt(0.45, QColor(255, 255, 255, 0))
    ring_gradient.setColorAt(0.62, QColor(255, 255, 255, _DITHER_STRENGTH))
    ring_gradient.setColorAt(0.92, QColor(255, 255, 255, _DITHER_STRENGTH))
    ring_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
    rp.setPen(Qt.PenStyle.NoPen)
    rp.setBrush(QBrush(ring_gradient))
    rp.drawEllipse(center, gradient_r, gradient_r)
    rp.end()

    # Clip the ring's alpha by the world-locked noise tile — SourceIn
    # keeps the noise pattern's own shape but scaled down by the ring's
    # alpha, so holes can only appear within that band, never at the
    # core or past the outer edge.
    noise = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    noise.fill(QColor(0, 0, 0, 0))
    npt = QPainter(noise)
    npt.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    brush = QBrush(_get_dither_tile())
    if world_pos is not None:
        # Stamp-local pixel (0,0) sits at world (world_pos - center) — pin
        # the tile's own (0,0) there so every stamp samples the same
        # absolute grid regardless of its own center.
        transform = QTransform()
        transform.translate(-(world_pos.x() - center.x()), -(world_pos.y() - center.y()))
        brush.setTransform(transform)
    npt.setBrush(brush)
    npt.setPen(Qt.PenStyle.NoPen)
    npt.drawRect(0, 0, size, size)
    npt.end()

    rp2 = QPainter(ring)
    rp2.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    rp2.drawImage(0, 0, noise)
    rp2.end()

    painter = QPainter(img)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    painter.drawImage(0, 0, ring)
    painter.end()


def build_stamp(radius: float, params: TerrainBrushParams, world_pos: QPointF | None = None) -> QImage:
    """Renders one brush stamp's alpha shape (a soft radial-gradient
    circle, or a jagged version when `params.roughness > 0`) into its own
    small ARGB image, centered in the middle of that image, instead of
    drawing straight onto a target mask.

    Callers composite this SAME QImage (via drawImage, see paint_at's
    `stamp` param) onto every mask it touches for one brush point — the
    active layer via SourceOver, every other terrain layer via
    DestinationOut (see BrushTool._erase_other_layers) — rather than each
    target independently recomputing its own gradient/jagged path. Two
    independently recomputed shapes were never guaranteed pixel-
    identical (roughness > 0 in particular calls `random.uniform` fresh
    each time via `_jagged_circle_path`), which is what produced a
    visible double-edge/seam between two adjacent terrain types instead
    of one clean, pixel-complementary boundary.

    `world_pos` (scene coords — the same for every layer touched by one
    brush point, unlike each layer's own local coords, which can drift
    apart once a layer independently expands) drives the organic-edge
    dither's noise sampling (see _apply_edge_dither/_dither_noise) so
    consecutive overlapping stamps along a dragged stroke read the same
    underlying pattern instead of each rolling independent randomness."""
    gradient_r = radius * (1.0 + params.roughness * _ROUGHNESS_JITTER) if params.roughness > 0 else radius
    half = math.ceil(gradient_r) + 2
    size = half * 2
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    center = QPointF(half, half)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QRadialGradient(center, gradient_r)
    alpha = int(255 * params.opacity)
    hardness = 1.0 - params.softness
    if hardness >= 0.99:
        gradient.setColorAt(0.0, QColor(255, 255, 255, alpha))
        gradient.setColorAt(1.0, QColor(255, 255, 255, alpha))
    else:
        gradient.setColorAt(0.0, QColor(255, 255, 255, alpha))
        gradient.setColorAt(max(0.01, hardness), QColor(255, 255, 255, alpha))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    if params.roughness > 0:
        painter.drawPath(_jagged_circle_path(center, radius, params.roughness))
    else:
        painter.drawEllipse(center, radius, radius)
    painter.end()

    if params.dither:
        _apply_edge_dither(img, center, gradient_r, world_pos)
    return img


class TerrainLayer:
    """A single terrain layer: mask + tiled texture → composited pixmap item.

    Supports stencil mask: paint_at writes to the mask, and texture is only
    visible where the mask exists. In mask-only mode, a preview color shows
    the masked area without texture.
    """

    MASK_PREVIEW_COLOR = QColor(255, 255, 255, 80)
    EXPAND_CHUNK = 2048  # growth increment in pixels

    def __init__(self, scene: QGraphicsScene, map_width: int = 4096, map_height: int = 4096,
                 parent_item=None):
        self._scene = scene
        self._width = map_width
        self._height = map_height

        # Stencil mask: defines WHERE painting is allowed
        self._stencil = QImage(map_width, map_height, QImage.Format.Format_ARGB32_Premultiplied)
        self._stencil.fill(QColor(0, 0, 0, 0))

        # Paint mask: actual painted area (clipped by stencil when stencil exists)
        self._mask = QImage(map_width, map_height, QImage.Format.Format_ARGB32_Premultiplied)
        self._mask.fill(QColor(0, 0, 0, 0))

        # Composited result
        self._result = QImage(map_width, map_height, QImage.Format.Format_ARGB32_Premultiplied)
        self._result.fill(QColor(0, 0, 0, 0))

        # Texture
        self._texture: QPixmap | None = None
        self._texture_scale = 1.0
        self._texture_rotation = 0.0

        # Mode tracking
        self._mask_only = False
        self._has_stencil = False

        # Scene item (child of parent_item if provided, so it moves with it)
        self._item = QGraphicsPixmapItem(parent_item)
        self._item.setZValue(1)
        self._item.setPos(0, 0)
        self._item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._item.setData(0, {"item_type": "terrain"})
        suppress_selection_decoration(self._item)
        if not parent_item:
            self._scene.addItem(self._item)

        # Dirty tracking
        self._dirty_rect: QRect | None = None
        self._stroke_dirty: QRect | None = None

    @property
    def mask(self) -> QImage:
        return self._mask

    @property
    def item(self) -> QGraphicsPixmapItem:
        return self._item

    @property
    def texture_scale(self) -> float:
        return self._texture_scale

    @property
    def texture_rotation(self) -> float:
        return self._texture_rotation

    def has_texture(self) -> bool:
        return self._texture is not None and not self._texture.isNull()

    def set_texture(self, pixmap: QPixmap, scale: float = 1.0, rotation: float = 0.0):
        self._texture = pixmap
        self._texture_scale = scale
        self._texture_rotation = rotation
        self._mask_only = False
        self._recomposite_full()

    def set_texture_transform(self, scale: float, rotation: float):
        self._texture_scale = scale
        self._texture_rotation = rotation
        self._recomposite_full()

    def set_mask_only(self, enabled: bool):
        """Toggle mask-only mode (shows preview color instead of texture)."""
        if self._mask_only == enabled:
            return
        self._mask_only = enabled
        self._recomposite_full()

    # ─── Painting ────────────────────────────────────────────────────────

    def paint_at(self, pos: QPointF, params: TerrainBrushParams, clip_path: QPainterPath | None = None,
                 stamp: QImage | None = None):
        """Paint circular stamp into the appropriate mask.

        `stamp`, when given, is a pre-built alpha-stamp image (see
        build_stamp()) drawn as-is instead of building a new gradient/
        jagged-path here — this is what BrushTool passes so the exact
        same footprint gets SourceOver'd into the active layer AND
        DestinationOut'd out of every other terrain layer for one brush
        point (see BrushTool._erase_other_layers), guaranteeing two
        adjacent terrain types meet at a single pixel-complementary
        boundary instead of each independently computing its own (and,
        with roughness > 0, independently randomized) edge. When omitted,
        a stamp is built internally exactly as before — single-layer
        callers (e.g. RegionLayer) are unaffected.

        `clip_path` (layer-local coords), when given, restricts the
        actual painted pixels to it — used by RegionBrushTool so a
        stroke dragged right up to (or slightly past) a bounded terrain's
        edge still fills all the way to that edge instead of the whole
        stamp being rejected the moment its center crosses the boundary
        (see RegionBrushTool._paint)."""
        r = params.size / 2
        size = int(params.size)
        if size < 1:
            return

        if stamp is None:
            stamp = build_stamp(r, params, world_pos=pos)

        cx, cy = pos.x(), pos.y()

        # Expand layer if painting outside current bounds
        if cx - r < 0 or cy - r < 0 or cx + r > self._width or cy + r > self._height:
            old_pos = self._item.pos()
            self._expand_to_fit(cx, cy, r)
            new_pos = self._item.pos()
            # Recalculate local coords after expansion shifted the origin
            shift_x = old_pos.x() - new_pos.x()
            shift_y = old_pos.y() - new_pos.y()
            cx += shift_x
            cy += shift_y
            # Shift accumulated dirty rect to match new coordinate space
            if self._stroke_dirty is not None:
                self._stroke_dirty.translate(int(shift_x), int(shift_y))
            # clip_path was computed in the pre-expansion coordinate space —
            # shift it the same way, or it'd clip against the wrong spot
            # once the mask's origin moves.
            if clip_path is not None:
                clip_path = clip_path.translated(shift_x, shift_y)

        # Choose target: stencil (mask mode) or paint mask (paint/erase mode)
        if params.mask_only:
            target = self._stencil
        else:
            target = self._mask

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if clip_path is not None:
            painter.setClipPath(clip_path)

        if params.erase:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        half_w = stamp.width() / 2.0
        half_h = stamp.height() / 2.0
        painter.drawImage(QPointF(cx - half_w, cy - half_h), stamp)
        painter.end()

        if params.mask_only:
            self._has_stencil = True

        # Track dirty — sized to the stamp's own bounding box (matters
        # once roughness bulges it past the nominal radius r).
        x = max(0, int(cx - half_w))
        y = max(0, int(cy - half_h))
        w = min(self._width - x, stamp.width() + 1)
        h = min(self._height - y, stamp.height() + 1)
        stamp_rect = QRect(x, y, w, h)

        if self._stroke_dirty is None:
            self._stroke_dirty = stamp_rect
        else:
            self._stroke_dirty = self._stroke_dirty.united(stamp_rect)

    def paint_cell(self, polygon: QPolygonF, params: TerrainBrushParams):
        """Flood-fill an entire grid cell — used instead of paint_at() when
        Snap is on: rather than a soft circular stamp, the whole cell you
        clicked in (its exact outline, whatever the grid shape) becomes one
        solid patch, like a tile-based terrain painter."""
        bounds = polygon.boundingRect()
        if bounds.isEmpty():
            return
        r = max(bounds.width(), bounds.height()) / 2
        cx, cy = bounds.center().x(), bounds.center().y()

        # Expand layer if painting outside current bounds (same as paint_at)
        if cx - r < 0 or cy - r < 0 or cx + r > self._width or cy + r > self._height:
            old_pos = self._item.pos()
            self._expand_to_fit(cx, cy, r)
            new_pos = self._item.pos()
            shift_x = old_pos.x() - new_pos.x()
            shift_y = old_pos.y() - new_pos.y()
            polygon = polygon.translated(shift_x, shift_y)
            bounds = polygon.boundingRect()
            if self._stroke_dirty is not None:
                self._stroke_dirty.translate(int(shift_x), int(shift_y))

        target = self._stencil if params.mask_only else self._mask

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if params.erase:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        alpha = int(255 * params.opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
        path = QPainterPath()
        path.addPolygon(polygon)
        path.closeSubpath()
        painter.drawPath(path)
        painter.end()

        if params.mask_only:
            self._has_stencil = True

        stamp_rect = bounds.toAlignedRect().intersected(QRect(0, 0, self._width, self._height))
        if self._stroke_dirty is None:
            self._stroke_dirty = stamp_rect
        else:
            self._stroke_dirty = self._stroke_dirty.united(stamp_rect)

    def update_live(self):
        """Incremental update: recomposite only the dirty region."""
        if not self._stroke_dirty:
            return
        if not self._mask_only and not self._has_stencil and (not self._texture or self._texture.isNull()):
            return

        self._recomposite_rect(self._stroke_dirty)
        self._item.setPixmap(QPixmap.fromImage(self._result))

    def finish_stroke(self):
        """End of stroke — final full-quality update."""
        if self._stroke_dirty:
            self._recomposite_rect(self._stroke_dirty)
            self._item.setPixmap(QPixmap.fromImage(self._result))
            self._stroke_dirty = None

    # ─── Compositing ─────────────────────────────────────────────────────

    def _recomposite_rect(self, rect: QRect):
        """Recomposite only the given rect region.

        Uses an offscreen tile so that texture + mask compositing is isolated,
        then blits the result back. The texture brush transform is offset by
        -rect.topLeft() so the tiling stays aligned to global (0,0).
        """
        w, h = rect.width(), rect.height()
        if w <= 0 or h <= 0:
            return

        # Clear target region
        painter = QPainter(self._result)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.end()

        # Layer 1: texture masked by paint mask (and stencil)
        if self._texture and not self._texture.isNull():
            tile = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            tile.fill(QColor(0, 0, 0, 0))

            tp = QPainter(tile)
            tp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # Draw texture offset so pattern aligns to map origin
            tp.setBrush(self._create_texture_brush(rect.x(), rect.y()))
            tp.setPen(Qt.PenStyle.NoPen)
            tp.drawRect(0, 0, w, h)
            # Clip by paint mask
            tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            tp.drawImage(0, 0, self._mask, rect.x(), rect.y(), w, h)
            # Clip by stencil if present
            if self._has_stencil:
                tp.drawImage(0, 0, self._stencil, rect.x(), rect.y(), w, h)
            tp.end()

            painter = QPainter(self._result)
            painter.drawImage(rect.topLeft(), tile)
            painter.end()

        # Layer 2: stencil preview overlay (only in mask mode)
        if self._mask_only and self._has_stencil:
            stencil_preview = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            stencil_preview.fill(QColor(0, 0, 0, 0))
            sp = QPainter(stencil_preview)
            sp.setBrush(QBrush(self.MASK_PREVIEW_COLOR))
            sp.setPen(Qt.PenStyle.NoPen)
            sp.drawRect(0, 0, w, h)
            sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            sp.drawImage(0, 0, self._stencil, rect.x(), rect.y(), w, h)
            sp.end()

            painter = QPainter(self._result)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawImage(rect.topLeft(), stencil_preview)
            painter.end()

    def _recomposite_full(self):
        """Full recomposite."""
        self._result.fill(QColor(0, 0, 0, 0))
        full_rect = QRect(0, 0, self._width, self._height)
        self._recomposite_rect(full_rect)
        self._item.setPixmap(QPixmap.fromImage(self._result))

    def _create_texture_brush(self, offset_x: int = 0, offset_y: int = 0) -> QBrush:
        """Create texture brush aligned to map origin (0,0).

        offset_x/offset_y: top-left of the tile being painted, used to shift
        the brush so the pattern doesn't restart per dirty rect.
        """
        brush = QBrush(self._texture)
        transform = QTransform()
        # Compensate for the tile offset so texture stays pinned to (0,0)
        transform.translate(-offset_x, -offset_y)
        if self._texture_rotation != 0.0:
            transform.rotate(self._texture_rotation)
        if self._texture_scale != 1.0:
            transform.scale(self._texture_scale, self._texture_scale)
        brush.setTransform(transform)
        return brush

    # ─── Dynamic Expansion ───────────────────────────────────────────────────

    def _expand_to_fit(self, cx: float, cy: float, radius: float):
        """Expand all internal images to fit the painted area.

        Grows in chunks to avoid frequent reallocations.
        Adjusts the item position so existing content stays in place.
        """
        chunk = self.EXPAND_CHUNK

        # Calculate required bounds
        need_left = cx - radius
        need_top = cy - radius
        need_right = cx + radius
        need_bottom = cy + radius

        # How much to grow on each side
        grow_left = max(0, int(math.ceil(-need_left / chunk)) * chunk) if need_left < 0 else 0
        grow_top = max(0, int(math.ceil(-need_top / chunk)) * chunk) if need_top < 0 else 0
        grow_right = max(0, int(math.ceil((need_right - self._width) / chunk)) * chunk) if need_right > self._width else 0
        grow_bottom = max(0, int(math.ceil((need_bottom - self._height) / chunk)) * chunk) if need_bottom > self._height else 0

        if grow_left == 0 and grow_top == 0 and grow_right == 0 and grow_bottom == 0:
            return

        new_w = self._width + grow_left + grow_right
        new_h = self._height + grow_top + grow_bottom

        # Expand each image, copying old content at offset
        self._mask = self._expand_image(self._mask, new_w, new_h, grow_left, grow_top)
        self._stencil = self._expand_image(self._stencil, new_w, new_h, grow_left, grow_top)
        self._result = self._expand_image(self._result, new_w, new_h, grow_left, grow_top)

        # Shift item position so scene coordinates stay consistent
        old_pos = self._item.pos()
        self._item.setPos(old_pos.x() - grow_left, old_pos.y() - grow_top)

        self._width = new_w
        self._height = new_h

    @staticmethod
    def _expand_image(img: QImage, new_w: int, new_h: int, offset_x: int, offset_y: int) -> QImage:
        """Create a larger image and blit the old one at the given offset."""
        new_img = QImage(new_w, new_h, img.format())
        new_img.fill(QColor(0, 0, 0, 0))
        p = QPainter(new_img)
        p.drawImage(offset_x, offset_y, img)
        p.end()
        return new_img

    # ─── Undo ────────────────────────────────────────────────────────────

    def capture_state(self) -> dict:
        """Snapshot full layer state (mask + stencil + bounds) for undo/redo.

        Uses the QImage copy CONSTRUCTOR (not the `.copy()` method) — with
        Format_ARGB32_Premultiplied images the bare `.copy()` call has been
        observed to intermittently return a detached-but-null (0x0) image
        (likely an implicit-sharing/COW detach hiccup through the PySide
        bindings), silently corrupting undo snapshots. The constructor
        form is the more standard deep-copy idiom and doesn't exhibit it.
        """
        return {
            "mask": QImage(self._mask),
            "stencil": QImage(self._stencil),
            "has_stencil": self._has_stencil,
            "width": self._width,
            "height": self._height,
            "pos": self._item.pos(),
        }

    def restore_state(self, state: dict):
        """Restore a previously captured state (undoes/redoes a whole stroke)."""
        self._mask = QImage(state["mask"])
        self._stencil = QImage(state["stencil"])
        self._has_stencil = state["has_stencil"]
        self._width = state["width"]
        self._height = state["height"]
        self._item.setPos(state["pos"])
        self._result = QImage(self._width, self._height, QImage.Format.Format_ARGB32_Premultiplied)
        self._recomposite_full()

    # ─── Serialization ───────────────────────────────────────────────────
    # Moved here from RegionLayer (which now just delegates) so any
    # TerrainLayer — not only the Região-flavored wrapper — can be
    # exported/reimported the same way (see BrushMediator, which persists
    # brush-painted terrain masks the same way RegionMediator already
    # persisted painted zones).

    _OPAQUE_SCAN_SIZE = 64
    _OPAQUE_ALPHA_THRESHOLD = 10

    def opaque_bounds_local(self) -> QRect | None:
        """Bounding box (layer-local coords) of the painted (non-transparent)
        area, via a cheap downsampled alpha scan — good enough to crop an
        export/thumbnail around, not meant to be pixel-exact."""
        w, h = self._mask.width(), self._mask.height()
        if w == 0 or h == 0:
            return None
        small = self._mask.scaled(
            self._OPAQUE_SCAN_SIZE, self._OPAQUE_SCAN_SIZE,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation,
        )
        min_x = min_y = None
        max_x = max_y = None
        for y in range(small.height()):
            for x in range(small.width()):
                if small.pixelColor(x, y).alpha() > self._OPAQUE_ALPHA_THRESHOLD:
                    min_x = x if min_x is None else min(min_x, x)
                    max_x = x if max_x is None else max(max_x, x)
                    min_y = y if min_y is None else min(min_y, y)
                    max_y = y if max_y is None else max(max_y, y)
        if min_x is None:
            return None
        sx, sy = w / small.width(), h / small.height()
        pad = 2
        return QRect(
            int(max(0, (min_x - pad) * sx)), int(max(0, (min_y - pad) * sy)),
            int(min(w, (max_x + 1 + pad) * sx) - max(0, (min_x - pad) * sx)),
            int(min(h, (max_y + 1 + pad) * sy) - max(0, (min_y - pad) * sy)),
        )

    def mask_crop(self, rect: QRect) -> QImage | None:
        """A copy of `_mask` cropped to `rect` (layer-local pixel coords),
        clamped to the mask's actual bounds — None if the clamped rect
        ends up empty (rect entirely outside the mask). Used by
        BrushTool's shoreline-blend pass to grab just the small region
        where two different terrain layers' masks might overlap."""
        bounds = QRect(0, 0, self._mask.width(), self._mask.height())
        clamped = rect.intersected(bounds)
        if clamped.width() <= 0 or clamped.height() <= 0:
            return None
        return self._mask.copy(clamped)

    def export_mask_png_base64(self) -> tuple[str, float, float]:
        """PNG-encode the cropped raw paint mask (base64 text, alpha only —
        NOT the composited/textured result, so reloading + recompositing
        with whatever texture is set at the time reproduces it correctly)
        plus its local top-left offset, for DB storage. Cropped to opaque
        bounds so an untouched 4096x4096 mostly-transparent layer doesn't
        serialize as a multi-megabyte blob."""
        import base64
        from PySide6.QtCore import QBuffer, QIODevice

        bounds = self.opaque_bounds_local()
        if bounds is None:
            return "", 0.0, 0.0
        cropped = self._mask.copy(bounds)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        cropped.save(buf, "PNG")
        data = base64.b64encode(bytes(buf.data())).decode("ascii")
        return data, float(bounds.x()), float(bounds.y())

    def import_mask_png_base64(self, data: str, offset_x: float, offset_y: float):
        """Reverse of export_mask_png_base64 — paints the decoded PNG
        straight into the mask at its saved local offset (SourceOver, no
        brush falloff — this is a raw restore, not a stroke)."""
        import base64

        if not data:
            return
        raw = base64.b64decode(data.encode("ascii"))
        img = QImage.fromData(raw, "PNG")
        if img.isNull():
            return
        painter = QPainter(self._mask)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(QPointF(offset_x, offset_y), img)
        painter.end()
        self._recomposite_full()

    # ─── Cleanup ─────────────────────────────────────────────────────────

    def remove_from_scene(self):
        if self._item.scene():
            self._scene.removeItem(self._item)

    def clear(self):
        self._mask.fill(QColor(0, 0, 0, 0))
        self._stencil.fill(QColor(0, 0, 0, 0))
        self._result.fill(QColor(0, 0, 0, 0))
        self._has_stencil = False
        self._item.setPixmap(QPixmap.fromImage(self._result))
