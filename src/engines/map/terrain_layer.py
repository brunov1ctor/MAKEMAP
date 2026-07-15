"""TerrainLayer — rasterized terrain painting with mask + tiled texture."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QBrush, QTransform,
    QRadialGradient, QPen,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene


@dataclass
class TerrainBrushParams:
    """Parameters for a single terrain brush stroke."""
    size: float = 100.0
    opacity: float = 1.0
    softness: float = 0.5  # 0=hard edge, 1=fully soft
    texture_scale: float = 1.0
    texture_rotation: float = 0.0
    erase: bool = False
    mask_only: bool = False  # paint mask without showing texture


class TerrainLayer:
    """A single terrain layer: mask + tiled texture → composited pixmap item.

    Supports stencil mask: paint_at writes to the mask, and texture is only
    visible where the mask exists. In mask-only mode, a preview color shows
    the masked area without texture.
    """

    MASK_PREVIEW_COLOR = QColor(255, 255, 255, 80)

    def __init__(self, scene: QGraphicsScene, map_width: int = 4096, map_height: int = 4096):
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

        # Scene item
        self._item = QGraphicsPixmapItem()
        self._item.setZValue(1)
        self._item.setPos(0, 0)
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
        if cx + r < 0 or cy + r < 0 or cx - r > self._width or cy - r > self._height:
            return

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
        gradient = QRadialGradient(center, r)
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
        """Recomposite only the given rect region."""
        painter = QPainter(self._result)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(rect, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setClipRect(rect)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Layer 1: existing texture (paint mask clipped by stencil if exists)
        if self._texture and not self._texture.isNull():
            painter.save()
            painter.setBrush(self._create_texture_brush())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawImage(rect, self._mask, rect)
            if self._has_stencil:
                painter.drawImage(rect, self._stencil, rect)
            painter.restore()

        # Layer 2: stencil preview overlay (only in mask mode)
        if self._mask_only and self._has_stencil:
            # Draw semi-transparent preview of stencil area on top
            stencil_preview = QImage(rect.size(), QImage.Format.Format_ARGB32_Premultiplied)
            stencil_preview.fill(QColor(0, 0, 0, 0))
            sp = QPainter(stencil_preview)
            sp.setBrush(QBrush(self.MASK_PREVIEW_COLOR))
            sp.setPen(Qt.PenStyle.NoPen)
            sp.drawRect(stencil_preview.rect())
            sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            sp.drawImage(0, 0, self._stencil, rect.x(), rect.y(), rect.width(), rect.height())
            sp.end()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawImage(rect.topLeft(), stencil_preview)

        painter.end()

    def _recomposite_full(self):
        """Full recomposite."""
        self._result.fill(QColor(0, 0, 0, 0))
        full_rect = QRect(0, 0, self._width, self._height)
        self._recomposite_rect(full_rect)
        self._item.setPixmap(QPixmap.fromImage(self._result))

    def _create_texture_brush(self) -> QBrush:
        brush = QBrush(self._texture)
        transform = QTransform()
        if self._texture_rotation != 0.0:
            transform.rotate(self._texture_rotation)
        if self._texture_scale != 1.0:
            s = 1.0 / self._texture_scale
            transform.scale(s, s)
        brush.setTransform(transform)
        return brush

    # ─── Undo ────────────────────────────────────────────────────────────

    def save_mask_region(self, rect: QRect) -> QImage:
        return self._mask.copy(rect)

    def restore_mask_region(self, rect: QRect, saved: QImage):
        painter = QPainter(self._mask)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(rect.topLeft(), saved)
        painter.end()
        self._recomposite_rect(rect)
        self._item.setPixmap(QPixmap.fromImage(self._result))

    def get_stroke_rect(self) -> QRect | None:
        return self._stroke_dirty

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
