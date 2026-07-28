"""RegionLayer — brush-painted colored area for the Região panel.

Thin wrapper around TerrainLayer: a Região is conceptually the same thing
as a terrain layer (a raster mask, painted with soft circular stamps or
grid-cell fills, erasable, opacity-controlled) except its "texture" is a
flat color tint instead of a tiled material — so instead of re-implementing
brush painting (soft edges, snap-to-cell fill, dynamic expansion, undo
snapshots), a Região reuses TerrainLayer wholesale and just feeds it a 1x1
solid-color pixmap as its "texture".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRect, QRectF
from PySide6.QtGui import (
    QColor, QPixmap, QPainter, QImage, QBitmap, QRegion, QPainterPath, QPen,
    QFont, QFontMetrics,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem

from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams, morphological_close
from src.canvas.item_utils import suppress_selection_decoration, enable_hover_glow

# Downsample size used for the cheap area/thumbnail-bounds scan — full-res
# per-pixel counting over a 4096x4096 mask would be far too slow in Python;
# a small downsample gives a good-enough estimate at negligible cost.
_SCAN_SIZE = 64
_ALPHA_THRESHOLD = 10
_BORDER_WIDTH = 6  # px — stroke width of the traced outline
_SMOOTH_RADIUS = 30  # px — morphological close radius, see terrain_layer.morphological_close
_LABEL_MAX_STARS = 5


class RegionLayer:
    """A single painted região: mask + flat color → composited pixmap item."""

    def __init__(self, scene: QGraphicsScene, color: QColor,
                 map_width: int = 4096, map_height: int = 4096, parent_item=None):
        self._color = QColor(color)
        self._style = "Nenhum"
        self._hovered = False
        self._terrain = TerrainLayer(scene, map_width, map_height, parent_item)
        self._terrain.item.setZValue(5)  # above terrain (z=1), below stamped objects (z=10+)
        self._terrain.item.setData(0, {"item_type": "zone"})
        # Hovering the região directly on the map now brightens/thickens its
        # own border too (set_hover already existed for the card-hover path
        # in the Região panel — see RegionMediator.on_card_hover_entered).
        enable_hover_glow(self._terrain.item, self.set_hover)
        self._apply_color_texture()

        # Cities-Skylines-style name + difficulty-stars label, centered on
        # the região's own largest painted patch — see update_label. A
        # standalone top-level scene item (not a child of self._terrain.
        # item), so it's unaffected by that item's own opacity/pixmap and
        # its position is plain scene coords.
        self._label_item: QGraphicsPixmapItem | None = None
        self._label_name = ""
        self._label_stars = 0

    def _apply_color_texture(self):
        pixmap = QPixmap(1, 1)
        pixmap.fill(self._color)
        self._terrain.set_texture(pixmap, scale=1.0, rotation=0.0)
        self._reapply_style()

    @property
    def item(self):
        return self._terrain.item

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._apply_color_texture()

    def set_opacity(self, opacity: float):
        """The região's own live transparency — a real QGraphicsItem
        opacity, multiplying the already-rendered fill+border uniformly
        at DRAW time. Deliberately NOT the brush's paint-mask alpha
        (which only ever accumulates via SourceOver and can never be
        lowered once painted, see RegionBrushTool._params) — this always
        visibly updates instantly, dragged at any time, regardless of how
        much of the área is already painted. Doesn't touch the name/
        stars label (see update_label), which stays fully legible
        regardless of how faded the fill itself is."""
        self._terrain.item.setOpacity(max(0.0, min(1.0, opacity)))

    def set_hover(self, hovered: bool):
        """Brightens + thickens this região's OWN existing border (see
        _bordered_result) while its card is hovered in the panel — no
        separate outline item drawn on top, which used to read as a
        second, slightly-offset border sitting next to the real one."""
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self._reapply_style()

    # ─── Estilo (visual post-process over the flat color, e.g. "Vapor") ───

    def set_style(self, style_key: str):
        self._style = style_key or "Nenhum"
        self._reapply_style()

    def _reapply_style(self, live: bool = False):
        """Re-derives the item's displayed pixmap from the plain composited
        result — must be re-run after every recomposite (paint, color
        change, mask reload), since those all reset the item's pixmap back
        to the unstyled flat color.

        `live=True` (called from update_live, i.e. every mouse-move while
        dragging) skips the crisp-border pass — it's restricted to the
        opaque bounding box so it's cheap, but not "every mouse-move on a
        4096px layer" cheap. The border always reappears once the stroke
        actually finishes.
        """
        img = QImage(self._terrain._result if live else self._bordered_result())
        if self._style == "Vapor":
            painter = QPainter(img)
            # Heat-haze look: soften the fill (reduced alpha) and desaturate
            # it toward a pale tint — "usa a cor mas diminui a opacidade e
            # aplica vapor", per the requested effect.
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.fillRect(img.rect(), QColor(255, 255, 255, 150))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            painter.fillRect(img.rect(), QColor(235, 235, 220, 70))
            painter.end()
        self._terrain.item.setPixmap(QPixmap.fromImage(img))

    def _bordered_result(self) -> QImage:
        """Cities-Skylines-style single closed outline traced around the
        whole painted shape. A região is painted as many overlapping soft
        circular stamps — tracing their raw union directly produces a
        bumpy, spray-paint-looking edge (every stamp's own little bulge
        stays visible). A morphological close (dilate then erode by the
        same radius, see terrain_layer.morphological_close) first bridges the gaps/bumps
        between stamps into one smooth blob, and only THEN gets traced as a
        single QRegion-derived path and stroked once — one clean contour
        instead of following every stamp's edge. Restricted to the opaque
        bounding box (not the full — possibly 4096x4096 — layer), so it
        stays cheap regardless of the layer's overall size.

        The fill itself is also clipped to this same traced contour before
        the border is drawn — a soft/feathered stamp's alpha falls off
        gradually, and without clipping that falloff tail stays visible
        past the line that's supposed to bound it, reading as the spray
        "leaking" outside the border."""
        result = self._terrain._result.copy()
        bounds = self._terrain.opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return result

        pad = _SMOOTH_RADIUS + _BORDER_WIDTH + 2
        grown = bounds.adjusted(-pad, -pad, pad, pad).intersected(
            QRect(0, 0, self._terrain._mask.width(), self._terrain._mask.height())
        )
        mask_crop = self._terrain._mask.copy(grown)
        closed = morphological_close(mask_crop, _SMOOTH_RADIUS)

        region = QRegion(QBitmap.fromImage(closed.createAlphaMask()))
        path = QPainterPath()
        path.addRegion(region)
        # addRegion() adds every constituent scanline rectangle as its own
        # sub-path — stroking that directly shows every internal rectangle
        # seam as a stray line cutting across the shape. simplified()
        # merges them into just the outer silhouette before we stroke it.
        path = path.simplified()

        # Clip the fill to the contour — draws a solid silhouette of `path`
        # into its own alpha-only stencil, then AND's the cropped fill
        # against it (DestinationIn), so any feathered edge past the line
        # gets cut off instead of bleeding past the border.
        stencil = QImage(grown.size(), QImage.Format.Format_ARGB32_Premultiplied)
        stencil.fill(QColor(0, 0, 0, 0))
        sp = QPainter(stencil)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing)
        sp.setPen(Qt.PenStyle.NoPen)
        sp.setBrush(QColor(255, 255, 255, 255))
        sp.drawPath(path)
        sp.end()

        fill_crop = result.copy(grown)
        fp = QPainter(fill_crop)
        fp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fp.drawImage(0, 0, stencil)
        fp.end()

        clip_painter = QPainter(result)
        clip_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        clip_painter.drawImage(grown.topLeft(), fill_crop)
        clip_painter.end()

        # Border: thicker and fully opaque regardless of the fill's own
        # (often translucent) alpha, so it reads as a clear, deliberately
        # darker-toned line around an otherwise soft-edged airbrush fill.
        # While hovered (see set_hover), the SAME line is drawn brighter
        # and thicker instead of a second outline being added on top of
        # it elsewhere — that read as two slightly-offset borders.
        if self._hovered:
            border_color = QColor(self._color.lighter(150))
            border_color.setAlpha(255)
            border_width = _BORDER_WIDTH + 3
        else:
            border_color = QColor(self._color.darker(170))
            border_color.setAlpha(255)
            border_width = _BORDER_WIDTH
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(grown.topLeft())
        pen = QPen(border_color, border_width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
        return result

    # ─── Painting (delegates straight to TerrainLayer) ────────────────────

    def paint_at(self, local_pos: QPointF, params: TerrainBrushParams, clip_path: QPainterPath | None = None):
        self._terrain.paint_at(local_pos, params, clip_path)

    def paint_cell(self, local_polygon, params: TerrainBrushParams):
        self._terrain.paint_cell(local_polygon, params)

    def update_live(self):
        self._terrain.update_live()
        self._reapply_style(live=True)

    def finish_stroke(self):
        self._terrain.finish_stroke()
        self._reapply_style()

    def scene_to_local(self, scene_pos: QPointF) -> QPointF:
        return self._terrain.item.mapFromScene(scene_pos)

    def clear_paint(self):
        """Wipe the painted mask back to blank — used by the card's
        "Apagar Pintura" action, keeps the card/entry itself intact."""
        self._terrain.clear()
        self._reapply_style()
        self._rebuild_label()  # nothing painted anymore — hides itself

    # ─── Undo (duck-typed for PaintStrokeCommand) ─────────────────────────

    def capture_state(self) -> dict:
        return self._terrain.capture_state()

    def restore_state(self, state: dict):
        self._terrain.restore_state(state)
        self._reapply_style()

    # ─── Queries ───────────────────────────────────────────────────────────

    def contains_point(self, scene_pos: QPointF) -> bool:
        """Whether scene_pos falls on a painted (opaque) part of the mask."""
        local = self.scene_to_local(scene_pos)
        x, y = int(local.x()), int(local.y())
        mask = self._terrain.mask
        if x < 0 or y < 0 or x >= mask.width() or y >= mask.height():
            return False
        return mask.pixelColor(x, y).alpha() > _ALPHA_THRESHOLD

    def largest_blob_center_scene(self) -> QPointF | None:
        """Scene-coords center of the SINGLE LARGEST contiguous painted
        patch — not the centroid/bounding-box of the whole mask. A região
        can be painted as several disconnected patches scattered across
        the map (e.g. the same "Floresta" tag used in three separate
        spots); centering on the overall bounding box in that case lands
        on empty space between them. Used by "Localizar" (see
        RegionMediator.on_locate). None if nothing is painted.

        Connected-component search runs on a small downsampled copy of
        the mask (same reasoning as area_m2's scan) — a per-pixel flood
        fill over the full-res mask would be far too slow in Python."""
        mask = self._terrain.mask
        w, h = mask.width(), mask.height()
        if w == 0 or h == 0:
            return None
        small = mask.scaled(_SCAN_SIZE, _SCAN_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        sw, sh = small.width(), small.height()
        opaque = [[small.pixelColor(x, y).alpha() > _ALPHA_THRESHOLD for x in range(sw)] for y in range(sh)]
        visited = [[False] * sw for _ in range(sh)]

        best_count = 0
        best_bounds = None  # (min_x, min_y, max_x, max_y) in downsampled coords
        for sy in range(sh):
            for sx in range(sw):
                if visited[sy][sx] or not opaque[sy][sx]:
                    visited[sy][sx] = True
                    continue
                stack = [(sx, sy)]
                visited[sy][sx] = True
                min_x = max_x = sx
                min_y = max_y = sy
                count = 0
                while stack:
                    cx, cy = stack.pop()
                    count += 1
                    min_x, max_x = min(min_x, cx), max(max_x, cx)
                    min_y, max_y = min(min_y, cy), max(max_y, cy)
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < sw and 0 <= ny < sh and not visited[ny][nx] and opaque[ny][nx]:
                            visited[ny][nx] = True
                            stack.append((nx, ny))
                if count > best_count:
                    best_count = count
                    best_bounds = (min_x, min_y, max_x, max_y)

        if best_bounds is None:
            return None
        min_x, min_y, max_x, max_y = best_bounds
        sx_scale, sy_scale = w / sw, h / sh
        local = QPointF((min_x + max_x + 1) / 2 * sx_scale, (min_y + max_y + 1) / 2 * sy_scale)
        return self._terrain.item.mapToScene(local)

    # ─── Name/difficulty label (Cities-Skylines-style district label) ────

    def update_label(self, name: str, stars: int):
        """Re-renders and repositions the name+stars label centered on
        this região's largest painted patch (see largest_blob_center_
        scene). Called by RegionMediator on every change that could move
        or change the label: paint (stroke finished/cleared), rename,
        stars, visibility. Hides itself if nothing's painted yet or the
        name is blank."""
        self._label_name = name
        self._label_stars = max(0, min(_LABEL_MAX_STARS, stars))
        self._rebuild_label()

    def set_label_visible(self, visible: bool):
        """Independent of set_opacity — visibility (card's eye toggle)
        should hide the label outright, whereas región opacity should
        leave it fully legible even as the fill fades."""
        if self._label_item:
            self._label_item.setVisible(visible)

    def _rebuild_label(self):
        center = self.largest_blob_center_scene() if self._label_name else None
        if center is None:
            if self._label_item:
                self._label_item.hide()
            return

        pixmap = self._render_label_pixmap()
        if self._label_item is None:
            scene = self._terrain.item.scene()
            if scene is None:
                return
            self._label_item = QGraphicsPixmapItem()
            self._label_item.setZValue(6)  # above the fill/border (5), below stamped objects (10+)
            self._label_item.setData(0, {"item_type": "zone_label"})
            suppress_selection_decoration(self._label_item)
            scene.addItem(self._label_item)
        self._label_item.setPixmap(pixmap)
        self._label_item.setPos(center.x() - pixmap.width() / 2, center.y() - pixmap.height() / 2)
        self._label_item.setVisible(self._terrain.item.isVisible())

    def _render_label_pixmap(self) -> QPixmap:
        """Dark rounded pill: bold name on top, gold ★/☆ stars below (only
        when stars > 0) — same Cities-Skylines district-label idea, drawn
        as one small standalone pixmap rather than rich text, so it stays
        crisp at any zoom (QGraphicsPixmapItem, not a scaled QGraphicsTextItem)."""
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(11)
        name_fm = QFontMetrics(name_font)
        name_w = name_fm.horizontalAdvance(self._label_name)

        stars_text = "★" * self._label_stars + "☆" * (_LABEL_MAX_STARS - self._label_stars) if self._label_stars else ""
        star_font = QFont()
        star_font.setPointSize(9)
        star_fm = QFontMetrics(star_font)
        stars_w = star_fm.horizontalAdvance(stars_text) if stars_text else 0

        pad_x, pad_y = 14, 6
        w = max(name_w, stars_w) + pad_x * 2
        h = name_fm.height() + pad_y * 2 + (star_fm.height() if stars_text else 0)

        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), h / 2.5, h / 2.5)
        p.fillPath(path, QColor(10, 18, 28, 200))
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawPath(path)

        p.setFont(name_font)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(0, pad_y - 2, w, name_fm.height()), Qt.AlignmentFlag.AlignHCenter, self._label_name)

        if stars_text:
            p.setFont(star_font)
            p.setPen(QColor(255, 205, 60, 235))
            p.drawText(
                QRectF(0, pad_y + name_fm.height() - 2, w, star_fm.height()),
                Qt.AlignmentFlag.AlignHCenter, stars_text,
            )
        p.end()
        return pixmap

    def area_m2(self) -> float:
        """Approximate painted area in m² (1 scene unit == 1 meter) via a
        cheap downsampled alpha scan — exact per-pixel counting over a
        multi-megapixel mask would be far too slow in Python."""
        mask = self._terrain.mask
        w, h = mask.width(), mask.height()
        if w == 0 or h == 0:
            return 0.0
        small = mask.scaled(_SCAN_SIZE, _SCAN_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        opaque = 0
        for y in range(small.height()):
            for x in range(small.width()):
                if small.pixelColor(x, y).alpha() > _ALPHA_THRESHOLD:
                    opaque += 1
        cell_area = (w / small.width()) * (h / small.height())
        return opaque * cell_area

    def thumbnail(self, size: int = 48) -> QPixmap:
        """Small preview pixmap of the painted shape, cropped to its
        approximate bounds and letterboxed into a size x size square."""
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        bounds = self._terrain.opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return result
        cropped = self._terrain._result.copy(bounds)
        scaled = QPixmap.fromImage(cropped).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        painter = QPainter(result)
        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return result

    # ─── Serialization (delegates straight to TerrainLayer) ───────────────

    def export_mask_png_base64(self) -> tuple[str, float, float]:
        return self._terrain.export_mask_png_base64()

    def import_mask_png_base64(self, data: str, offset_x: float, offset_y: float):
        self._terrain.import_mask_png_base64(data, offset_x, offset_y)
        self._reapply_style()

    def remove_from_scene(self):
        self._terrain.remove_from_scene()
        if self._label_item is not None and self._label_item.scene() is not None:
            self._label_item.scene().removeItem(self._label_item)
