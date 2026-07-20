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

from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import QColor, QPixmap, QPainter, QImage
from PySide6.QtWidgets import QGraphicsScene

from src.engines.map.terrain_layer import TerrainLayer, TerrainBrushParams

# Downsample size used for the cheap area/thumbnail-bounds scan — full-res
# per-pixel counting over a 4096x4096 mask would be far too slow in Python;
# a small downsample gives a good-enough estimate at negligible cost.
_SCAN_SIZE = 64
_ALPHA_THRESHOLD = 10
_BORDER_WIDTH = 3  # px — crisp Cities-Skylines-style outline around the painted shape


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
        """Cities-Skylines-style crisp outline: dilate the mask by
        _BORDER_WIDTH px, subtract the original interior to get a ring,
        tint that ring with a darker shade of the região's own color, and
        stamp it onto a copy of the composited result. Restricted to the
        opaque bounding box (not the full — possibly 4096x4096 — layer),
        so it stays cheap regardless of the layer's overall size."""
        result = self._terrain._result.copy()
        bounds = self._opaque_bounds_local()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return result

        pad = _BORDER_WIDTH + 2
        grown = bounds.adjusted(-pad, -pad, pad, pad).intersected(
            QRect(0, 0, self._terrain._mask.width(), self._terrain._mask.height())
        )
        mask_crop = self._terrain._mask.copy(grown)

        dilated = QImage(mask_crop.size(), QImage.Format.Format_ARGB32_Premultiplied)
        dilated.fill(QColor(0, 0, 0, 0))
        dp = QPainter(dilated)
        dp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        for dx, dy in ((-_BORDER_WIDTH, 0), (_BORDER_WIDTH, 0), (0, -_BORDER_WIDTH), (0, _BORDER_WIDTH),
                       (-_BORDER_WIDTH, -_BORDER_WIDTH), (_BORDER_WIDTH, _BORDER_WIDTH),
                       (-_BORDER_WIDTH, _BORDER_WIDTH), (_BORDER_WIDTH, -_BORDER_WIDTH)):
            dp.drawImage(dx, dy, mask_crop)
        dp.end()

        ring = dilated
        rp = QPainter(ring)
        rp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        rp.drawImage(0, 0, mask_crop)
        rp.end()

        colored = QImage(ring.size(), QImage.Format.Format_ARGB32_Premultiplied)
        colored.fill(self._color.darker(160))
        cp = QPainter(colored)
        cp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        cp.drawImage(0, 0, ring)
        cp.end()

        painter = QPainter(result)
        painter.drawImage(grown.topLeft(), colored)
        painter.end()
        return result

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

    def _opaque_bounds_local(self) -> QRect | None:
        """Cheap approximate bounding rect (local coords) of painted pixels,
        via the same downsampled scan as area_m2 — good enough to crop a
        thumbnail around, not meant to be pixel-exact."""
        mask = self._terrain.mask
        w, h = mask.width(), mask.height()
        if w == 0 or h == 0:
            return None
        small = mask.scaled(_SCAN_SIZE, _SCAN_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        min_x = min_y = None
        max_x = max_y = None
        for y in range(small.height()):
            for x in range(small.width()):
                if small.pixelColor(x, y).alpha() > _ALPHA_THRESHOLD:
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

    def thumbnail(self, size: int = 48) -> QPixmap:
        """Small preview pixmap of the painted shape, cropped to its
        approximate bounds and letterboxed into a size x size square."""
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        bounds = self._opaque_bounds_local()
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

    # ─── Serialization ──────────────────────────────────────────────────────

    def export_mask_png_base64(self) -> tuple[str, float, float]:
        """PNG-encode the cropped raw paint mask (base64 text, alpha only —
        NOT the color-composited result, so reloading + recompositing with
        whatever color is set at the time reproduces the tint correctly)
        plus its local top-left offset, for DB storage. Cropped to opaque
        bounds so an untouched 4096x4096 mostly-transparent layer doesn't
        serialize as a multi-megabyte blob."""
        import base64
        from PySide6.QtCore import QBuffer, QIODevice

        bounds = self._opaque_bounds_local()
        if bounds is None:
            return "", 0.0, 0.0
        cropped = self._terrain._mask.copy(bounds)
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
        from PySide6.QtGui import QImage

        if not data:
            return
        raw = base64.b64decode(data.encode("ascii"))
        img = QImage.fromData(raw, "PNG")
        if img.isNull():
            return
        painter = QPainter(self._terrain._mask)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(QPointF(offset_x, offset_y), img)
        painter.end()
        self._terrain._recomposite_full()
        self._reapply_style()

    def remove_from_scene(self):
        self._terrain.remove_from_scene()
