"""TerrainEffectGeometry — blob-detection + traced-silhouette geometry
queries derived from a TerrainLayer's own paint mask (opaque_bounds_local,
connected_components_local, blob_at_local, blobs_in_rect_local,
effect_geometry and friends).

Split out of TerrainLayer (see terrain_layer.py) — mirrors how BrushTool
split ShorelineBlender out into its own collaborator (see
canvas/tools/shoreline_blend.py): this class only ever READS the owning
TerrainLayer's mask/item, live via `self._layer.mask`/`self._layer.item`
on every call — never a cached reference to the QImage object itself,
since TerrainLayer reassigns `self._mask` wholesale (a brand-new QImage)
on both dynamic expansion (_expand_to_fit) and undo/redo (restore_state),
which would silently go stale if cached here instead. Owns its own
derived caches (opaque bounds / blobs / traced silhouette), invalidated
by TerrainLayer via invalidate()/invalidate_traced_cache() at every point
the mask is mutated — entirely independent of the paint/erase/stencil/
undo-snapshot machinery TerrainLayer itself still owns directly (that
machinery touches nearly every field TerrainLayer has — mask, stencil,
result, texture, item, width/height — so, unlike this read-mostly query
layer, it doesn't have a clean seam to split along without just moving
the same coupling elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBitmap, QColor, QImage, QPainter, QPainterPath, QRegion, QTransform

if TYPE_CHECKING:
    from src.engines.map.terrain_layer import TerrainLayer


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


class TerrainEffectGeometry:
    """Blob/silhouette queries for one TerrainLayer's mask. Constructed and
    held by TerrainLayer (`self._geometry`), which delegates its own
    opaque_bounds_local/connected_components_local/blob_at_local/
    blobs_in_rect_local/_traced_silhouette/effect_geometry/
    invalidate_traced_cache calls straight here, keeping TerrainLayer's own
    public API unchanged for every external caller (RegionLayer,
    BrushEffectsOverlay, ExplorerSyncMediator, _LayerItem's hover glow, ...)."""

    _OPAQUE_SCAN_SIZE = 64
    _OPAQUE_ALPHA_THRESHOLD = 10

    # Padding/smoothing for the traced silhouette (see _traced_silhouette) —
    # shared constants so RegionLayer's border bake and effect_geometry()
    # trace the exact same contour.
    _TRACE_SMOOTH_RADIUS = 30  # px — morphological close radius
    _TRACE_PAD = 38  # px — _TRACE_SMOOTH_RADIUS + border width + a couple px

    def __init__(self, layer: "TerrainLayer"):
        self._layer = layer

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

    def invalidate(self):
        """Drop every cache — call whenever the mask/stencil is mutated
        (paint_at, paint_cell, clear_stencil, restore_state, clear)."""
        self._opaque_bounds_cache = None
        self._blobs_cache = None
        self._traced_cache = None

    def invalidate_traced_cache(self):
        self._traced_cache = None

    # ─── Serialization-adjacent bounds/blob queries ─────────────────────

    def opaque_bounds_local(self) -> QRect | None:
        """Bounding box (layer-local coords) of the painted (non-transparent)
        area, via a cheap downsampled alpha scan — good enough to crop an
        export/thumbnail around, not meant to be pixel-exact. Result is
        cached and invalidated whenever the mask is mutated (paint_at,
        paint_cell, restore_state, clear)."""
        if self._opaque_bounds_cache is not None:
            return self._opaque_bounds_cache
        mask = self._layer.mask
        w, h = mask.width(), mask.height()
        if w == 0 or h == 0:
            return None
        small = mask.scaled(
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
        moved onto TerrainLayer, generalized to return every patch, so other
        callers (e.g. the Explorer's terrain→região coverage check,
        blob_at_local's hover/selection scoping) can reuse the same scan
        instead of a third copy of this flood fill.

        Cached (only at the default scan_size — callers that pass a custom
        one opt out of caching) and invalidated at the same points as
        opaque_bounds_local, since blob_at_local can now run on every
        hover-move tick and a fresh flood fill every frame would be far too
        slow."""
        use_cache = scan_size == self._OPAQUE_SCAN_SIZE
        if use_cache and self._blobs_cache is not None:
            return self._blobs_cache
        mask = self._layer.mask
        item = self._layer.item
        w, h = mask.width(), mask.height()
        if w == 0 or h == 0:
            return []
        small = mask.scaled(scan_size, scan_size, Qt.AspectRatioMode.IgnoreAspectRatio,
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
                sampled_points_scene = [item.mapToScene(p) for p in sampled_points_local]
                local_center = QPointF((min_x + max_x + 1) / 2 * sx_scale, (min_y + max_y + 1) / 2 * sy_scale)
                bounds_local = QRectF(min_x * sx_scale, min_y * sy_scale,
                                       (max_x - min_x + 1) * sx_scale, (max_y - min_y + 1) * sy_scale)
                top_left_scene = item.mapToScene(bounds_local.topLeft())
                bottom_right_scene = item.mapToScene(bounds_local.bottomRight())
                blobs.append(BlobInfo(
                    bounds_scene=QRectF(top_left_scene, bottom_right_scene),
                    bounds_local=bounds_local,
                    center_scene=item.mapToScene(local_center),
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
        mask = self._layer.mask
        w, h = mask.width(), mask.height()
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
        mask = self._layer.mask
        w, h = mask.width(), mask.height()
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

    # ─── Traced silhouette / effect geometry ─────────────────────────────

    def _masked_to_blob_cells(self, cropped: QImage, blob: "BlobInfo", crop_origin: QPoint) -> QImage:
        """Zeroes out any pixel in `cropped` that isn't one of `blob`'s own
        opaque downsampled cells (see connected_components_local/
        BlobInfo.sampled_points_local) — see _traced_silhouette for why
        `bounds` alone isn't a safe enough crop for an elongated/winding
        blob."""
        scan = self._OPAQUE_SCAN_SIZE
        mask = self._layer.mask
        cell_w = mask.width() / scan
        cell_h = mask.height() / scan
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

        A brush stroke's dithered edge (see terrain_layer._apply_edge_dither,
        on by default) is a noisy pattern of fully-opaque and fully-
        transparent pixels, not a smooth gradient — morphological_close
        bridges the gaps between MOST of it into one blob, but a speckle
        that lands just beyond its reach survives as its own tiny,
        disconnected loop. Stroked as a separate sub-path, it draws as a
        stray little dash/dot floating outside the main silhouette (see
        _LayerItem._paint_hover_glow).

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
        erode by the same radius, see terrain_layer.morphological_close)
        first bridges the gaps/bumps between stamps into one smooth blob,
        and only THEN gets traced as a single QRegion-derived path — one
        clean contour instead of following every stamp's edge. Restricted
        to `bounds` (not the full — possibly 4096x4096 — layer), so it
        stays cheap regardless of the layer's overall size.

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
        # Deferred import — terrain_layer.py imports THIS module at load
        # time (to construct TerrainLayer's own TerrainEffectGeometry), so
        # a module-level import back the other way would be circular;
        # morphological_close is only ever needed once a trace actually
        # runs, well after both modules have finished loading.
        from src.engines.map.terrain_layer import morphological_close

        use_cache = bounds is None
        if use_cache and self._traced_cache is not None:
            return self._traced_cache
        mask = self._layer.mask
        if bounds is None:
            bounds = self.opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return None

        pad = self._TRACE_PAD
        grown = bounds.adjusted(-pad, -pad, pad, pad).intersected(
            QRect(0, 0, mask.width(), mask.height())
        )
        mask_crop = mask.copy(grown)
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
