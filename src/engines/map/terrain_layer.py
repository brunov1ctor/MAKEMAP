"""TerrainLayer — rasterized terrain painting with mask + tiled texture."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QBrush, QTransform,
    QRadialGradient, QPen, QPolygonF, QPainterPath, QRegion, QBitmap,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from src.canvas.item_utils import suppress_selection_decoration, enable_hover_glow
from src.styles.tokens import Colors


class _LayerItem(QGraphicsItem):
    """Drop-in replacement for QGraphicsPixmapItem used as a terrain/region
    layer's scene item, with one addition: `update_region()` blits only a
    dirty sub-rect into the cached pixmap and calls a bounded `update(rect)`,
    instead of `QGraphicsPixmapItem.setPixmap()`'s only option — swapping in
    a brand-new pixmap converted from the FULL layer QImage (multiple
    megapixels once a map has grown) and repainting the item's whole
    boundingRect, on every single mouse-move of a brush stroke. setPixmap()/
    pixmap() are kept so existing full-image call sites (stroke-finish,
    style/texture changes, RegionLayer's border compositing) work unchanged."""

    # Deve bater com SelectTool.name (src/canvas/tools/defaults.py) — não
    # importado direto pra evitar canvas.tools <-> engines.map se
    # entrelaçarem; every other "qual ferramenta está ativa?" check no app
    # já compara por esse mesmo nome em vez de isinstance (ver
    # text_mediator.py, terrain_mediator.py, ...).
    _SELECT_TOOL_NAME = "Selecionar"

    def __init__(self, parent=None, tool_manager=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._shape_cache: QPainterPath | None = None
        self._terrain_layer: "TerrainLayer | None" = None  # set by TerrainLayer after construction
        self._hovered = False
        # Local-coords position of the mouse while hovering — lets the
        # glow (see _paint_hover_glow) trace just the one painted blob
        # under the cursor instead of every blob this asset has anywhere
        # on the map (two separate ponds painted with the same water
        # asset are two blobs of the SAME layer/item — see
        # TerrainLayer._get_or_create_terrain_layer in brush_tool.py).
        self._hover_local_pos: QPointF | None = None
        # Local-coords position of the click that selected this item —
        # same one-layer-many-blobs reasoning as above, read by
        # selection_bounding_rect() so the selection border/handles hug
        # just the clicked blob. None = no specific blob (box/lasso/
        # Ctrl+A selection, or never clicked) — falls back to the whole
        # layer's painted bounds.
        self._selection_anchor_local: QPointF | None = None
        # Item-local rect the user actually dragged a box-select over —
        # same "which blob(s) did they mean" problem as
        # _selection_anchor_local above, but for a box/lasso drag instead
        # of a single click (which can legitimately touch more than one
        # blob at once). Cleared back to None (whole-layer bounds) by
        # SelectionEngine.set/add/toggle/remove/clear, same as the anchor
        # — set fresh by BoxSelectMixin._box_finish right after, mirroring
        # how select_and_begin_drag re-sets the anchor.
        self._selection_rect_local: QRectF | None = None
        # Só acende com a ferramenta Selecionar ativa — pintar/mover/etc.
        # com o mouse passando por cima de um terreno não deveria fazer
        # brilhar um destaque de "isto é selecionável", já que nenhuma
        # dessas outras ferramentas de fato seleciona ao clicar. None (o
        # caso de um TerrainLayer criado sem tool_manager, ex.: dentro de
        # RegionLayer, que sobrescreve esses handlers de hover com os
        # próprios logo em seguida de qualquer forma) mantém o
        # comportamento antigo de "sempre mostrar".
        self._tool_manager = tool_manager
        # Unlike markers/spawn stamps (enable_hover_glow's usual scale+drop-
        # shadow callback), a terrain layer's own item spans its whole
        # raster canvas (up to 4096px) — scaling it or applying a
        # QGraphicsDropShadowEffect over that area would be both visually
        # wrong (the "painted" look would balloon outward past the actual
        # brushed edge) and expensive. Painting a glow outline traced from
        # shape() (the real painted-pixel contour, not the raster bounding
        # box) in our own paint() instead gives every terrain/region/brush-
        # effect layer the same hover feedback markers/mobs/NPCs already
        # have, without those costs — this item type previously had NONE
        # (no setAcceptHoverEvents at all), the one gap enable_hover_glow's
        # other 3 adopters didn't share.
        enable_hover_glow(self, self._on_hover_changed)
        # Override the plain enable_hover_glow wiring above — a real mouse
        # hover only glows with Select active (see _on_hover_changed), but
        # ExplorerSyncMediator driving this from a card hover in the panel
        # is itself a deliberate reference, independent of whatever tool
        # happens to be active, so it should always show. RegionLayer
        # rewires this same attribute again right after constructing its
        # TerrainLayer (see RegionLayer.__init__), pointing it at its own
        # set_hover instead — this line only matters for raw terrain/effect
        # layers, which have no such wrapper.
        self.set_explorer_highlight = self._set_hover_unconditional

    def _set_hover_unconditional(self, hovered: bool):
        self._hovered = hovered
        if not hovered:
            self._hover_local_pos = None
        self.update()

    def _is_select_tool_active(self) -> bool:
        return self._tool_manager is None or self._tool_manager.active_name == self._SELECT_TOOL_NAME

    def _on_hover_changed(self, hovered: bool):
        if hovered and not self._is_select_tool_active():
            return
        self._hovered = hovered
        if not hovered:
            self._hover_local_pos = None
        self.update()

    def hoverMoveEvent(self, event):
        """Track where the cursor is over the layer (item-local coords) so
        _paint_hover_glow can scope its outline to just the blob under it —
        without this, moving the mouse to a different blob after hover-
        enter would keep glowing whichever blob happened to be current at
        enter time (or, before this feature existed, always the whole
        layer)."""
        self._hover_local_pos = event.pos()
        if self._hovered:
            self.update()

    def set_selection_anchor(self, pos_local: "QPointF | None"):
        """Remember the item-local point the user actually clicked to
        select this layer — selection_bounding_rect() uses it to scope the
        selection border to just that blob. Cleared back to None (whole-
        layer bounds) by SelectionEngine whenever the selection changes via
        any path OTHER than a direct click (box/lasso/Ctrl+A), see
        SelectionEngine.set/add/toggle/remove/clear."""
        self._selection_anchor_local = pos_local
        self._selection_rect_local = None

    def set_selection_rect(self, rect_local: "QRectF | None"):
        """Remember the item-local rect the user actually box-selected this
        layer with — selection_bounding_rect()/selected_blobs_local() use it
        to scope the selection border to just the blob(s) the drag rect
        really touched, instead of every blob this asset has anywhere on
        the map. Set by BoxSelectMixin._box_finish right after
        SelectionEngine.set() (which clears both this and the anchor via
        set_selection_anchor(None) for every item it (re)selects)."""
        self._selection_rect_local = rect_local
        self._selection_anchor_local = None

    def selected_blobs_local(self):
        """Every BlobInfo the current selection actually touched, or None if
        that can't be narrowed down (not selected, or selected via lasso/
        Ctrl+A rather than a click or box-drag) — in which case every blob
        this asset has counts as selected. Read by ExplorerSyncMediator so a
        box-select over just one river doesn't light up every river painted
        with the same water asset."""
        if self._terrain_layer is None:
            return None
        if self._selection_anchor_local is not None:
            blob = self._terrain_layer.blob_at_local(self._selection_anchor_local)
            return [blob] if blob is not None else None
        if self._selection_rect_local is not None:
            return self._terrain_layer.blobs_in_rect_local(self._selection_rect_local)
        return None

    def selection_bounding_rect(self) -> QRectF:
        """Tight bounding rect of the actually-painted pixels (item-local
        coords) — used by TransformEngine._item_bounds so the selection
        border/handles hug the painted area instead of the full raster
        canvas (which can be 4096x4096 even for a tiny painted patch).

        Scoped to just the touched blob(s) when a selection anchor/rect is
        set (see set_selection_anchor/set_selection_rect) — two independent
        puddles painted with the same water asset are two blobs of this
        SAME layer/item, and without this the border would span the union
        of both, however far apart they are on the map."""
        if self._terrain_layer is not None:
            blobs = self.selected_blobs_local()
            if blobs:
                rect = QRectF(blobs[0].bounds_local)
                for blob in blobs[1:]:
                    rect = rect.united(blob.bounds_local)
                return rect
            bounds = self._terrain_layer.opaque_bounds_local()
            if bounds is not None:
                return QRectF(bounds)
        return self.boundingRect()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._pixmap.width(), self._pixmap.height())

    def shape(self) -> QPainterPath:
        """Mask-based hit-test region (only the actually-painted/opaque
        pixels), matching QGraphicsPixmapItem's default MaskShape — needed
        so click-select and rubber-band box-select don't treat the whole
        (possibly 4096px) layer bounding rect as "painted" and swallow
        clicks/selections meant for whatever's underneath the unpainted
        area. Computed lazily and cached: cheap on every repaint (just
        drops the cache), only actually rebuilt the next time a hit-test
        is needed (click / hover / box-select), not on every brush stamp.

        Built from the layer's own raw paint mask (see TerrainLayer.mask),
        NOT the composited/textured self._pixmap — a translucent texture
        (water, foliage, ... anything painted at less than full alpha) caps
        the COMPOSITED alpha at wherever it's painted, which can sit well
        below Qt's own mask-from-alpha cutoff even at a spot that's 100%
        painted per the raw mask. That made most/all of a softly-textured
        blob's interior silently unclickable — select_and_begin_drag's
        itemAt()/rect-probe hit-tests would miss it entirely — while
        blob_at_local/opaque_bounds_local (hover glow, box-select's blob
        scoping, Explorer highlighting) stayed correct since those already
        read the raw mask, not the pixmap. Effect layers (Névoa, Poeira,
        ...) already had to use the raw mask for the same underlying reason
        (self._pixmap.isNull() below is stale for them too, and reading it
        would make them permanently unselectable) — that's just the
        stencil-less mask_only case of this exact bug, now handled
        uniformly instead of as its own special case."""
        if self._shape_cache is None:
            layer = self._terrain_layer
            if layer is not None:
                path = QPainterPath()
                path.addRegion(QRegion(QPixmap.fromImage(layer.mask).mask()))
                self._shape_cache = path
            elif self._pixmap.isNull():
                self._shape_cache = QPainterPath()
            else:
                path = QPainterPath()
                path.addRegion(QRegion(self._pixmap.mask()))
                self._shape_cache = path
        return self._shape_cache

    def paint(self, painter, option, widget=None):
        if not self._pixmap.isNull():
            exposed = option.exposedRect.intersected(self.boundingRect())
            painter.drawPixmap(exposed, self._pixmap, exposed)
        if self._hovered:
            self._paint_hover_glow(painter)

    def _paint_hover_glow(self, painter: QPainter):
        """Neon outline traced along the real painted silhouette — same
        layered alpha/width passes FlowCanvas uses for its connection
        lines, for the same "glowing edge" look used everywhere else
        selectable things get highlighted in this app.

        Deliberately NOT shape() here: that path is built from a QRegion
        (a union of many small rectangles, good enough for hit-testing),
        and stroking it directly draws the outline of every one of those
        little rectangles rather than one clean silhouette — on a filled
        area that reads as the whole object glowing solid blue instead of
        just its edge. effect_geometry()'s traced_silhouette (used
        elsewhere for the exact same "clean outline" need — RegionLayer's
        border bake, BrushEffectsOverlay's clip) already solves this with
        a morphological close + single contour trace, in this same
        item-local coordinate space paint() already draws in."""
        if not self._is_select_tool_active():
            # Defensive re-check, not just at hover-enter: if the user
            # switches tools via keyboard shortcut while the cursor sits
            # still over this item (no hoverLeave fires), _hovered stays
            # True — the next repaint this triggers (however it's
            # triggered) should still suppress the glow instead of leaving
            # it stuck on under a tool that never re-checks it.
            return
        if self._terrain_layer is None:
            return
        if self._hover_local_pos is None:
            return
        blob = self._terrain_layer.blob_at_local(self._hover_local_pos)
        if blob is None:
            # Cursor is technically over the item (shape() hit) but landed
            # in a gap the coarse blob-detection grid doesn't resolve to a
            # specific blob — falling back to effect_geometry(bounds=None)
            # here used to trace the WHOLE layer's mask (every blob this
            # asset has anywhere on the map, unioned), which for an effect
            # painted in several separate patches showed up as stray
            # disconnected fragments of far-off patches bleeding into the
            # glow around the one actually under the cursor. No specific
            # blob to point at means no glow this frame, not "glow
            # everything" — same call next repaint tends to resolve once
            # the cursor settles.
            return
        blob_bounds = blob.bounds_local.toAlignedRect()
        traced = self._terrain_layer.effect_geometry(blob_bounds, blob=blob)
        if traced is None:
            return
        path, _bounds = traced
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(Colors.ACCENT)
        for alpha, width in ((60, 7), (160, 3), (255, 1.2)):
            c = QColor(color)
            c.setAlpha(alpha)
            painter.setPen(QPen(c, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def setPixmap(self, pixmap: QPixmap):
        prev_size = self._pixmap.size()
        self._pixmap = pixmap
        self._shape_cache = None
        if pixmap.size() != prev_size:
            self.prepareGeometryChange()
        self.update()

    def pixmap(self) -> QPixmap:
        return self._pixmap

    def invalidate_shape(self):
        """Drop the cached hit-test shape — call after mutating the pixmap
        returned by pixmap() directly (bypassing setPixmap/update_region)."""
        self._shape_cache = None

    def update_region(self, image: QImage, rect: QRect):
        """Blit only `rect` from `image` into the cached pixmap and repaint
        just that rect — the bounded-update fast path for live brush strokes.

        If the layer's canvas just grew (map expanded to fit a stroke near
        its edge), the cached pixmap no longer matches `image`'s size and a
        rect-only blit would lose everything painted outside `rect` on the
        new, bigger canvas — fall back to a full conversion in that case.
        Expansion is rare (only when painting near the current edge), so
        this cost is not part of the normal per-stamp hot path."""
        if self._pixmap.size() != image.size():
            self.setPixmap(QPixmap.fromImage(image))
            return
        painter = QPainter(self._pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(rect.topLeft(), image, rect)
        painter.end()
        # Shape cache is only needed for hit-testing (click/hover/box-select),
        # not for every intermediate stamp during a live stroke — invalidate
        # only at stroke finish (finish_stroke calls setPixmap which already
        # clears it) to avoid rebuilding the expensive QRegion mask per stamp.
        self.update(QRectF(rect))


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


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain — O(n log n), smallest convex polygon
    containing every point, no external deps. Returns the hull vertices in
    CCW order; input order doesn't matter and duplicates are ignored."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


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


@dataclass
class BlobInfo:
    """One contiguous painted patch found by connected_components_local —
    bounds/center in scene coords (via the layer's own item transform) plus
    the downsampled opaque grid-cells (scene + local coords) that make it
    up, cheap enough to reuse as sample points for coverage tests (e.g. "is
    this blob inside a região") without another full flood-fill.
    sampled_points_local also lets blob_at_local test actual cell
    membership instead of the (much looser) bounding box — two winding
    blobs like elongated rivers can have heavily overlapping bounding
    boxes despite never actually touching."""
    bounds_scene: QRectF
    bounds_local: QRectF
    center_scene: QPointF
    sampled_points_scene: list[QPointF]
    sampled_points_local: list[QPointF]
    pixel_count: int  # opaque downsampled cells — proxy for relative area


class TerrainLayer:
    """A single terrain layer: mask + tiled texture → composited pixmap item.

    Supports stencil mask: paint_at writes to the mask, and texture is only
    visible where the mask exists. In mask-only mode, a preview color shows
    the masked area without texture.
    """

    MASK_PREVIEW_COLOR = QColor(255, 255, 255, 80)
    EXPAND_CHUNK = 2048  # growth increment in pixels

    def __init__(self, scene: QGraphicsScene, map_width: int = 4096, map_height: int = 4096,
                 parent_item=None, tool_manager=None):
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
        self._item = _LayerItem(parent_item, tool_manager=tool_manager)
        self._item._terrain_layer = self
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

        # Cache for opaque_bounds_local() — invalidated on mask mutation
        self._opaque_bounds_cache: QRect | None = None

        # Cache for connected_components_local() (default scan_size only) —
        # invalidated alongside _opaque_bounds_cache, see that field.
        self._blobs_cache: list | None = None

        # Cache for _traced_silhouette() — the morphological close it runs
        # is cheap-ish but not free, and effect_geometry() (BrushEffectsOverlay,
        # for animated brush effects like Névoa, plus RegionLayer's border
        # bake) can call it several times a second even while the mask
        # itself sits still. Invalidated wherever the mask is mutated (see
        # invalidate_traced_cache()).
        self._traced_cache: tuple | None = None

    @property
    def mask(self) -> QImage:
        return self._mask

    @property
    def item(self) -> _LayerItem:
        return self._item

    @property
    def texture_scale(self) -> float:
        return self._texture_scale

    @property
    def texture_rotation(self) -> float:
        return self._texture_rotation

    def has_texture(self) -> bool:
        return self._texture is not None and not self._texture.isNull()

    def is_mask_only(self) -> bool:
        return self._mask_only

    def has_stencil_data(self) -> bool:
        return self._has_stencil

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
        self._traced_cache = None
        self._opaque_bounds_cache = None
        self._blobs_cache = None

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
        self._traced_cache = None
        self._opaque_bounds_cache = None
        self._blobs_cache = None

    def update_live(self):
        """Incremental update: recomposite only the dirty region."""
        if not self._stroke_dirty:
            return
        if not self._mask_only and not self._has_stencil and (not self._texture or self._texture.isNull()):
            return

        self._recomposite_rect(self._stroke_dirty)
        self._item.update_region(self._result, self._stroke_dirty)

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
        self._traced_cache = None
        self._opaque_bounds_cache = None
        self._blobs_cache = None
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
        export/thumbnail around, not meant to be pixel-exact. Result is
        cached and invalidated whenever the mask is mutated (paint_at,
        paint_cell, restore_state, clear)."""
        if self._opaque_bounds_cache is not None:
            return self._opaque_bounds_cache
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
        result = QRect(
            int(max(0, (min_x - pad) * sx)), int(max(0, (min_y - pad) * sy)),
            int(min(w, (max_x + 1 + pad) * sx) - max(0, (min_x - pad) * sx)),
            int(min(h, (max_y + 1 + pad) * sy) - max(0, (min_y - pad) * sy)),
        )
        self._opaque_bounds_cache = result
        return result

    def connected_components_local(self, scan_size: int = _OPAQUE_SCAN_SIZE) -> list[BlobInfo]:
        """Every contiguous painted patch in the mask, via a flood fill over
        a small downsampled copy (same reasoning as opaque_bounds_local — a
        per-pixel scan over a possibly 4096x4096 mask would be far too slow
        in Python). Originally lived only inside RegionLayer.
        largest_blob_center_scene (which kept just the largest patch) —
        moved here, generalized to return every patch, so other callers
        (e.g. the Explorer's terrain→região coverage check, blob_at_local's
        hover/selection scoping) can reuse the same scan instead of a third
        copy of this flood fill.

        Cached (only at the default scan_size — callers that pass a custom
        one opt out of caching) and invalidated at the same points as
        opaque_bounds_local, since blob_at_local can now run on every
        hover-move tick and a fresh flood fill every frame would be far too
        slow."""
        use_cache = scan_size == self._OPAQUE_SCAN_SIZE
        if use_cache and self._blobs_cache is not None:
            return self._blobs_cache
        w, h = self._mask.width(), self._mask.height()
        if w == 0 or h == 0:
            return []
        small = self._mask.scaled(scan_size, scan_size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.FastTransformation)
        sw, sh = small.width(), small.height()
        opaque = [[small.pixelColor(x, y).alpha() > self._OPAQUE_ALPHA_THRESHOLD for x in range(sw)] for y in range(sh)]
        visited = [[False] * sw for _ in range(sh)]
        sx_scale, sy_scale = w / sw, h / sh

        blobs: list[BlobInfo] = []
        for sy in range(sh):
            for sx in range(sw):
                if visited[sy][sx] or not opaque[sy][sx]:
                    visited[sy][sx] = True
                    continue
                stack = [(sx, sy)]
                visited[sy][sx] = True
                cells: list[tuple[int, int]] = []
                min_x = max_x = sx
                min_y = max_y = sy
                while stack:
                    cx, cy = stack.pop()
                    cells.append((cx, cy))
                    min_x, max_x = min(min_x, cx), max(max_x, cx)
                    min_y, max_y = min(min_y, cy), max(max_y, cy)
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < sw and 0 <= ny < sh and not visited[ny][nx] and opaque[ny][nx]:
                            visited[ny][nx] = True
                            stack.append((nx, ny))

                sampled_points_local = [
                    QPointF((cx + 0.5) * sx_scale, (cy + 0.5) * sy_scale)
                    for cx, cy in cells
                ]
                sampled_points_scene = [self._item.mapToScene(p) for p in sampled_points_local]
                local_center = QPointF((min_x + max_x + 1) / 2 * sx_scale, (min_y + max_y + 1) / 2 * sy_scale)
                bounds_local = QRectF(min_x * sx_scale, min_y * sy_scale,
                                       (max_x - min_x + 1) * sx_scale, (max_y - min_y + 1) * sy_scale)
                top_left_scene = self._item.mapToScene(bounds_local.topLeft())
                bottom_right_scene = self._item.mapToScene(bounds_local.bottomRight())
                blobs.append(BlobInfo(
                    bounds_scene=QRectF(top_left_scene, bottom_right_scene),
                    bounds_local=bounds_local,
                    center_scene=self._item.mapToScene(local_center),
                    sampled_points_scene=sampled_points_scene,
                    sampled_points_local=sampled_points_local,
                    pixel_count=len(cells),
                ))
        if use_cache:
            self._blobs_cache = blobs
        return blobs

    def blob_at_local(self, pos: QPointF) -> "BlobInfo | None":
        """Which blob (see connected_components_local) `pos` (item-local
        coords) falls inside, or None if it's in unpainted area or between
        two blobs — used to scope hover-glow/selection-box to just the one
        blob under the cursor/click instead of the whole layer, since two
        independent puddles painted with the same water asset are two
        blobs of this SAME shared item (see
        BrushTool._get_or_create_terrain_layer, one TerrainLayer per
        asset_id for the whole map).

        Tests actual opaque-cell membership (sampled_points_local), not
        just bounds_local containment — an elongated/winding blob (a
        river, an S-shaped puddle) has a bounding box far bigger than its
        actual paint, so two such blobs placed near/across each other can
        have bounding boxes that overlap heavily despite never touching.
        A bbox-only test could then match the wrong blob (or, depending on
        iteration order, silently return None for a click squarely on one
        blob's real paint because it landed in the OTHER blob's box
        first) — which is what made clicking a single river highlight/
        select every blob of that asset at once (selected_blobs_local()
        falling back to "every blob" whenever this returned None)."""
        w, h = self._mask.width(), self._mask.height()
        if w == 0 or h == 0:
            return None
        scan = self._OPAQUE_SCAN_SIZE
        half_w, half_h = w / scan / 2, h / scan / 2
        for blob in self.connected_components_local():
            # Cheap bbox pre-filter (padded by half a cell) before the
            # precise per-cell scan below — most blobs reject instantly.
            if not blob.bounds_local.adjusted(-half_w, -half_h, half_w, half_h).contains(pos):
                continue
            for cell in blob.sampled_points_local:
                if abs(cell.x() - pos.x()) <= half_w and abs(cell.y() - pos.y()) <= half_h:
                    return blob
        return None

    def blobs_in_rect_local(self, rect: QRectF) -> list["BlobInfo"]:
        """Which blobs (see connected_components_local) have any actually-
        painted cell inside `rect` (item-local coords) — used to scope a
        box-select to just the blob(s) the drag rect really touched instead
        of the whole layer, same reasoning as blob_at_local. bounds_local
        alone isn't a safe enough test for an elongated/winding blob (a
        river's bounding box can span far past a box that only grazes one
        end of it, or two such blobs can overlap in bbox space without the
        rect touching either one's real paint) — the bbox check here is
        just a cheap pre-filter, same as blob_at_local's."""
        w, h = self._mask.width(), self._mask.height()
        if w == 0 or h == 0:
            return []
        scan = self._OPAQUE_SCAN_SIZE
        half_w, half_h = w / scan / 2, h / scan / 2
        hits = []
        for blob in self.connected_components_local():
            if not blob.bounds_local.adjusted(-half_w, -half_h, half_w, half_h).intersects(rect):
                continue
            for cell in blob.sampled_points_local:
                if rect.adjusted(-half_w, -half_h, half_w, half_h).contains(cell):
                    hits.append(blob)
                    break
        return hits

    # Padding/smoothing for the traced silhouette (see _traced_silhouette) —
    # shared constants so RegionLayer's border bake and effect_geometry()
    # trace the exact same contour.
    _TRACE_SMOOTH_RADIUS = 30  # px — morphological close radius
    _TRACE_PAD = 38  # px — _TRACE_SMOOTH_RADIUS + border width + a couple px

    def invalidate_traced_cache(self):
        self._traced_cache = None

    def _masked_to_blob_cells(self, cropped: QImage, blob: "BlobInfo", crop_origin: QPoint) -> QImage:
        """Zeroes out any pixel in `cropped` that isn't one of `blob`'s own
        opaque downsampled cells (see connected_components_local/
        BlobInfo.sampled_points_local) — see _traced_silhouette for why
        `bounds` alone isn't a safe enough crop for an elongated/winding
        blob."""
        scan = self._OPAQUE_SCAN_SIZE
        cell_w = self._mask.width() / scan
        cell_h = self._mask.height() / scan
        owned = QRegion()
        for p in blob.sampled_points_local:
            cell = QRect(
                round(p.x() - cell_w / 2) - crop_origin.x(),
                round(p.y() - cell_h / 2) - crop_origin.y(),
                round(cell_w) + 1, round(cell_h) + 1,
            )
            owned += cell
        masked = QImage(cropped.size(), QImage.Format.Format_ARGB32_Premultiplied)
        masked.fill(QColor(0, 0, 0, 0))
        painter = QPainter(masked)
        painter.setClipRegion(owned)
        painter.drawImage(0, 0, cropped)
        painter.end()
        return masked

    def _encompass_all(self, path: QPainterPath) -> QPainterPath:
        """Replace multiple disconnected sub-paths with their convex hull.

        A brush stroke's dithered edge (see _apply_edge_dither, on by
        default) is a noisy pattern of fully-opaque and fully-transparent
        pixels, not a smooth gradient — morphological_close bridges the
        gaps between MOST of it into one blob, but a speckle that lands
        just beyond its reach survives as its own tiny, disconnected loop.
        Stroked as a separate sub-path, it draws as a stray little dash/dot
        floating outside the main silhouette (see _paint_hover_glow).

        Rather than guessing which sub-paths are "real" vs. noise by some
        size cutoff (fragile, and quietly drops real paint from the
        outline), wrap ALL of them in one convex hull instead — guaranteed
        to contain every last painted pixel under a single closed, gap-free
        contour, with nothing excluded and no threshold to tune."""
        polygons = path.toSubpathPolygons()
        if len(polygons) <= 1:
            return path
        points = [(p.x(), p.y()) for poly in polygons for p in poly]
        hull = _convex_hull(points)
        if len(hull) < 3:
            return path
        hull_path = QPainterPath()
        hull_path.moveTo(*hull[0])
        for x, y in hull[1:]:
            hull_path.lineTo(x, y)
        hull_path.closeSubpath()
        return hull_path

    def _traced_silhouette(self, bounds: QRect | None = None, blob: "BlobInfo | None" = None) -> tuple[QPainterPath, QRect] | None:
        """The smoothed, single-contour outline of the painted shape within
        `bounds` (item-local, or the whole layer's opaque bounds when
        omitted) — shared by RegionLayer's border bake and effect_geometry()
        (the animated-effect clip, e.g. Névoa, and the hover-glow's per-blob
        outline — see _LayerItem._paint_hover_glow). A layer is painted as
        many overlapping soft circular stamps — tracing their raw union
        directly produces a bumpy, spray-paint-looking edge (every stamp's
        own little bulge stays visible). A morphological close (dilate then
        erode by the same radius, see morphological_close) first bridges
        the gaps/bumps between stamps into one smooth blob, and only THEN
        gets traced as a single QRegion-derived path — one clean contour
        instead of following every stamp's edge. Restricted to `bounds`
        (not the full — possibly 4096x4096 — layer), so it stays cheap
        regardless of the layer's overall size.

        Passing an explicit `bounds` (e.g. one blob's own bounds_local, to
        outline just that puddle instead of every blob this asset has
        anywhere on the map) skips the cache — only the default whole-layer
        call is cached, since that's the one repeated several times a
        second by BrushEffectsOverlay/RegionLayer while the mask sits
        still; a per-blob trace only runs while hovering/selecting.

        `bounds` alone is an axis-aligned box — for a winding/elongated
        blob (a river, an S-shaped puddle) that box is far bigger than the
        blob's actual paint, so cropping to it alone can still include
        real, opaque pixels of a DIFFERENT nearby blob whose box happens to
        overlap this one (two rivers can cross in bounding-box space
        without ever touching in paint) — stray fragments of that neighbor
        would then bleed into the traced outline. Pass the actual `blob`
        alongside `bounds` to mask the crop down to just its own opaque
        cells first; omitted, the crop is used as-is (whole-layer calls
        have no single blob to scope to anyway).

        Returns (path, grown) where `path` is in `grown`-crop-local coords
        (i.e. (0,0) is grown's top-left, NOT the layer's own origin) — every
        caller already needs `grown`'s offset for its own painting, so
        translating here would just make them undo it. None if nothing's
        painted yet."""
        use_cache = bounds is None
        if use_cache and self._traced_cache is not None:
            return self._traced_cache
        if bounds is None:
            bounds = self.opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return None

        pad = self._TRACE_PAD
        grown = bounds.adjusted(-pad, -pad, pad, pad).intersected(
            QRect(0, 0, self._mask.width(), self._mask.height())
        )
        mask_crop = self._mask.copy(grown)
        if blob is not None:
            mask_crop = self._masked_to_blob_cells(mask_crop, blob, grown.topLeft())
        closed = morphological_close(mask_crop, self._TRACE_SMOOTH_RADIUS)

        region = QRegion(QBitmap.fromImage(closed.createAlphaMask()))
        path = QPainterPath()
        path.addRegion(region)
        # addRegion() adds every constituent scanline rectangle as its own
        # sub-path — stroking that directly shows every internal rectangle
        # seam as a stray line cutting across the shape. simplified()
        # merges them into just the outer silhouette before we stroke it.
        path = path.simplified()
        path = self._encompass_all(path)
        result = (path, grown)
        if use_cache:
            self._traced_cache = result
        return result

    def effect_geometry(self, bounds: QRect | None = None, blob: "BlobInfo | None" = None) -> tuple[QPainterPath, QRectF] | None:
        """Traced silhouette (see _traced_silhouette) in this layer's own
        LOCAL item coords (unlike that method's raw return, already
        translated by `grown`'s offset) plus its bounding rect — what
        BrushEffectsOverlay clips an animated brush effect (e.g. Névoa) to,
        via item.sceneTransform() to bring it into scene coords. `bounds`
        (item-local), when given, scopes the trace to just that area — see
        _traced_silhouette. `blob`, when given alongside `bounds`, further
        masks the trace down to that blob's own opaque cells — see
        _traced_silhouette. None if
        nothing's painted yet."""
        traced = self._traced_silhouette(bounds, blob)
        if traced is None:
            return None
        path, grown = traced
        path = QTransform().translate(grown.left(), grown.top()).map(path)
        return path, QRectF(grown)

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
        self._opaque_bounds_cache = None
        self._blobs_cache = None
        self._traced_cache = None
        self._item.setPixmap(QPixmap.fromImage(self._result))
