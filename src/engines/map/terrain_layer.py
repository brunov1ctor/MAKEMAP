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

    def paint_at(self, pos: QPointF, params: TerrainBrushParams):
        """Paint circular stamp into the appropriate mask."""
        r = params.size / 2
        size = int(params.size)
        if size < 1:
            return

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

        # Choose target: stencil (mask mode) or paint mask (paint/erase mode)
        if params.mask_only:
            target = self._stencil
        else:
            target = self._mask

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if params.erase:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        else:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        center = QPointF(cx, cy)
        # When roughness bulges the drawn shape past r, the gradient's own
        # radius has to reach at least as far, or those bulges would fall
        # beyond its last color stop and paint fully transparent — making
        # the jaggedness invisible instead of visible.
        gradient_r = r * (1.0 + params.roughness * _ROUGHNESS_JITTER) if params.roughness > 0 else r
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
            painter.drawPath(_jagged_circle_path(center, r, params.roughness))
        else:
            painter.drawEllipse(center, r, r)
        painter.end()

        if params.mask_only:
            self._has_stencil = True

        # Track dirty
        x = max(0, int(cx - r))
        y = max(0, int(cy - r))
        w = min(self._width - x, size + 1)
        h = min(self._height - y, size + 1)
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
        """Snapshot full layer state (mask + stencil + bounds) for undo/redo."""
        return {
            "mask": self._mask.copy(),
            "stencil": self._stencil.copy(),
            "has_stencil": self._has_stencil,
            "width": self._width,
            "height": self._height,
            "pos": self._item.pos(),
        }

    def restore_state(self, state: dict):
        """Restore a previously captured state (undoes/redoes a whole stroke)."""
        self._mask = state["mask"].copy()
        self._stencil = state["stencil"].copy()
        self._has_stencil = state["has_stencil"]
        self._width = state["width"]
        self._height = state["height"]
        self._item.setPos(state["pos"])
        self._result = QImage(self._width, self._height, QImage.Format.Format_ARGB32_Premultiplied)
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
