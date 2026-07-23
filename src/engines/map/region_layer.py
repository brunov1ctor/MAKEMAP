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

import math

from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import QColor, QPixmap, QPainter, QImage, QBitmap, QRegion, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene

from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams

# Downsample size used for the cheap area/thumbnail-bounds scan — full-res
# per-pixel counting over a 4096x4096 mask would be far too slow in Python;
# a small downsample gives a good-enough estimate at negligible cost.
_SCAN_SIZE = 64
_ALPHA_THRESHOLD = 10
_BORDER_WIDTH = 3  # px — stroke width of the traced outline
_SMOOTH_RADIUS = 30  # px — morphological close radius, see _morphological_close


class RegionLayer:
    """A single painted região: mask + flat color → composited pixmap item."""

    def __init__(self, scene: QGraphicsScene, color: QColor,
                 map_width: int = 4096, map_height: int = 4096, parent_item=None):
        self._color = QColor(color)
        self._style = "Nenhum"
        self._terrain = TerrainLayer(scene, map_width, map_height, parent_item)
        self._terrain.item.setZValue(5)  # above terrain (z=1), below stamped objects (z=10+)
        self._terrain.item.setData(0, {"item_type": "zone"})
        self._apply_color_texture()

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
        same radius, see _morphological_close) first bridges the gaps/bumps
        between stamps into one smooth blob, and only THEN gets traced as a
        single QRegion-derived path and stroked once — one clean contour
        instead of following every stamp's edge. Restricted to the opaque
        bounding box (not the full — possibly 4096x4096 — layer), so it
        stays cheap regardless of the layer's overall size."""
        result = self._terrain._result.copy()
        bounds = self._terrain.opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return result

        pad = _SMOOTH_RADIUS + _BORDER_WIDTH + 2
        grown = bounds.adjusted(-pad, -pad, pad, pad).intersected(
            QRect(0, 0, self._terrain._mask.width(), self._terrain._mask.height())
        )
        mask_crop = self._terrain._mask.copy(grown)
        closed = self._morphological_close(mask_crop, _SMOOTH_RADIUS)

        region = QRegion(QBitmap.fromImage(closed.createAlphaMask()))
        path = QPainterPath()
        path.addRegion(region)
        # addRegion() adds every constituent scanline rectangle as its own
        # sub-path — stroking that directly shows every internal rectangle
        # seam as a stray line cutting across the shape. simplified()
        # merges them into just the outer silhouette before we stroke it.
        path = path.simplified()

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(grown.topLeft())
        pen = QPen(self._color.darker(160), _BORDER_WIDTH)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
        return result

    @staticmethod
    def _morphological_close(img: QImage, radius: int, steps: int = 16) -> QImage:
        """Dilate then erode by `radius` px — fills small gaps/bumps between
        overlapping brush stamps and rounds the union into one smooth blob,
        without changing its overall size or position. `steps` directional
        composites approximate a circular structuring element (cheap vs a
        true per-pixel circular dilate/erode); dilate unions them
        (Lighten), erode intersects them (repeated DestinationIn)."""
        offsets = [
            (round(radius * math.cos(2 * math.pi * i / steps)),
             round(radius * math.sin(2 * math.pi * i / steps)))
            for i in range(steps)
        ]

        dilated = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        dilated.fill(QColor(0, 0, 0, 0))
        dp = QPainter(dilated)
        dp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        dp.drawImage(0, 0, img)
        for dx, dy in offsets:
            dp.drawImage(dx, dy, img)
        dp.end()

        eroded = QImage(dilated)
        ep = QPainter(eroded)
        ep.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        for dx, dy in offsets:
            ep.drawImage(-dx, -dy, dilated)
        ep.end()
        return eroded

    # ─── Painting (delegates straight to TerrainLayer) ────────────────────

    def paint_at(self, local_pos: QPointF, params: TerrainBrushParams):
        self._terrain.paint_at(local_pos, params)

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
