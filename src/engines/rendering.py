"""Rendering Engine — render queue, item effects, ambient effects, cache, config."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time

from PySide6.QtCore import QRectF, QPointF, Qt
from PySide6.QtGui import (
    QPainter, QColor, QImage, QPixmap, QPen, QBrush,
    QRadialGradient, QLinearGradient, QPainterPath,
)
from PySide6.QtWidgets import QGraphicsItem


# ─── Item Effects ───────────────────────────────────────────────────────────

class EffectType(Enum):
    DROP_SHADOW = auto()
    GLOW = auto()
    COLOR_OVERLAY = auto()
    GRADIENT_OVERLAY = auto()
    OUTLINE = auto()


@dataclass
class ItemEffect:
    type: EffectType
    enabled: bool = True
    opacity: float = 1.0
    # Drop Shadow / Glow
    color: str = "#000000"
    blur: float = 10.0
    offset_x: float = 0.0
    offset_y: float = 4.0
    # Color Overlay
    overlay_color: str = "#FF0000"
    # Gradient Overlay
    gradient_start: str = "#000000"
    gradient_end: str = "#FFFFFF"
    gradient_angle: float = 0.0
    # Outline
    stroke_width: float = 2.0
    stroke_color: str = "#FFFFFF"


# ─── Ambient Effects ────────────────────────────────────────────────────────

class AmbientType(Enum):
    FOG = auto()
    CLOUDS = auto()
    MIST = auto()
    WATER_REFLECTION = auto()
    AMBIENT_LIGHT = auto()
    NOISE_GRAIN = auto()


@dataclass
class AmbientEffect:
    type: AmbientType
    enabled: bool = True
    opacity: float = 0.5
    color: str = "#FFFFFF"
    intensity: float = 1.0
    speed: float = 1.0  # for animated effects
    scale: float = 1.0


# ─── Render Item ────────────────────────────────────────────────────────────

@dataclass
class RenderItem:
    """Item na render queue com z-index e efeitos."""
    item: QGraphicsItem
    z_index: int = 0
    effects: list[ItemEffect] = field(default_factory=list)
    visible: bool = True
    cached_pixmap: Optional[QPixmap] = None
    dirty: bool = True

    def add_effect(self, effect: ItemEffect):
        self.effects.append(effect)
        self.dirty = True

    def remove_effect(self, effect_type: EffectType):
        self.effects = [e for e in self.effects if e.type != effect_type]
        self.dirty = True

    def toggle_effect(self, effect_type: EffectType, enabled: bool):
        for e in self.effects:
            if e.type == effect_type:
                e.enabled = enabled
        self.dirty = True


# ─── Chunk Manager (LOD) ───────────────────────────────────────────────────

@dataclass
class Chunk:
    """Tile do mapa para culling e LOD."""
    rect: QRectF
    items: list[RenderItem] = field(default_factory=list)
    lod_level: int = 0  # 0=full, 1=medium, 2=low
    cached: Optional[QPixmap] = None
    dirty: bool = True


class ChunkManager:
    """Divide o mundo em chunks para culling e batch rendering."""

    def __init__(self, chunk_size: float = 512.0):
        self._chunk_size = chunk_size
        self._chunks: dict[tuple[int, int], Chunk] = {}

    @property
    def chunk_size(self) -> float:
        return self._chunk_size

    def get_chunk(self, cx: int, cy: int) -> Chunk:
        key = (cx, cy)
        if key not in self._chunks:
            rect = QRectF(
                cx * self._chunk_size, cy * self._chunk_size,
                self._chunk_size, self._chunk_size,
            )
            self._chunks[key] = Chunk(rect=rect)
        return self._chunks[key]

    def chunk_at(self, pos: QPointF) -> tuple[int, int]:
        cx = int(pos.x() // self._chunk_size)
        cy = int(pos.y() // self._chunk_size)
        return cx, cy

    def visible_chunks(self, viewport: QRectF) -> list[Chunk]:
        """Retorna chunks visíveis no viewport (culling)."""
        x0 = int(viewport.left() // self._chunk_size)
        y0 = int(viewport.top() // self._chunk_size)
        x1 = int(viewport.right() // self._chunk_size) + 1
        y1 = int(viewport.bottom() // self._chunk_size) + 1

        result = []
        for cx in range(x0, x1):
            for cy in range(y0, y1):
                result.append(self.get_chunk(cx, cy))
        return result

    def add_item(self, item: RenderItem, pos: QPointF):
        cx, cy = self.chunk_at(pos)
        chunk = self.get_chunk(cx, cy)
        chunk.items.append(item)
        chunk.dirty = True

    def remove_item(self, item: RenderItem):
        for chunk in self._chunks.values():
            if item in chunk.items:
                chunk.items.remove(item)
                chunk.dirty = True
                return

    def invalidate_all(self):
        for chunk in self._chunks.values():
            chunk.dirty = True
            chunk.cached = None

    def lod_for_zoom(self, zoom: float) -> int:
        if zoom >= 0.5:
            return 0
        elif zoom >= 0.2:
            return 1
        return 2


# ─── Image Cache ───────────────────────────────────────────────────────────

class ImageCache:
    """Cache LRU compartilhado para pixmaps renderizados."""

    def __init__(self, max_size: int = 128):
        self._max = max_size
        self._cache: dict[str, QPixmap] = {}
        self._order: list[str] = []

    def get(self, key: str) -> Optional[QPixmap]:
        if key in self._cache:
            self._order.remove(key)
            self._order.append(key)
            return self._cache[key]
        return None

    def put(self, key: str, pixmap: QPixmap):
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self._max:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = pixmap
        self._order.append(key)

    def invalidate(self, key: str):
        if key in self._cache:
            del self._cache[key]
            self._order.remove(key)

    def clear(self):
        self._cache.clear()
        self._order.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# ─── Effect Renderer ───────────────────────────────────────────────────────

class EffectRenderer:
    """Renderiza efeitos individuais sobre items."""

    @staticmethod
    def render_drop_shadow(painter: QPainter, rect: QRectF, effect: ItemEffect):
        if not effect.enabled:
            return
        color = QColor(effect.color)
        color.setAlphaF(effect.opacity * 0.6)
        shadow_rect = rect.translated(effect.offset_x, effect.offset_y)
        shadow_rect.adjust(-effect.blur, -effect.blur, effect.blur, effect.blur)
        path = QPainterPath()
        path.addRoundedRect(shadow_rect, 4, 4)
        painter.fillPath(path, color)

    @staticmethod
    def render_glow(painter: QPainter, rect: QRectF, effect: ItemEffect):
        if not effect.enabled:
            return
        center = rect.center()
        radius = max(rect.width(), rect.height()) / 2 + effect.blur
        grad = QRadialGradient(center, radius)
        color = QColor(effect.color)
        color.setAlphaF(effect.opacity * 0.4)
        grad.setColorAt(0.0, color)
        grad.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), int(color.alpha() * 0.3)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect.adjusted(-effect.blur * 2, -effect.blur * 2,
                                        effect.blur * 2, effect.blur * 2), QBrush(grad))

    @staticmethod
    def render_color_overlay(painter: QPainter, rect: QRectF, effect: ItemEffect):
        if not effect.enabled:
            return
        color = QColor(effect.overlay_color)
        color.setAlphaF(effect.opacity * 0.5)
        painter.fillRect(rect, color)

    @staticmethod
    def render_gradient_overlay(painter: QPainter, rect: QRectF, effect: ItemEffect):
        if not effect.enabled:
            return
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        c1 = QColor(effect.gradient_start)
        c2 = QColor(effect.gradient_end)
        c1.setAlphaF(effect.opacity * 0.5)
        c2.setAlphaF(effect.opacity * 0.5)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        painter.fillRect(rect, QBrush(grad))

    @staticmethod
    def render_outline(painter: QPainter, rect: QRectF, effect: ItemEffect):
        if not effect.enabled:
            return
        color = QColor(effect.stroke_color)
        color.setAlphaF(effect.opacity)
        pen = QPen(color, effect.stroke_width)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.setPen(Qt.PenStyle.NoPen)

    @classmethod
    def render_effects(cls, painter: QPainter, rect: QRectF, effects: list[ItemEffect]):
        for effect in effects:
            if not effect.enabled:
                continue
            if effect.type == EffectType.DROP_SHADOW:
                cls.render_drop_shadow(painter, rect, effect)
            elif effect.type == EffectType.GLOW:
                cls.render_glow(painter, rect, effect)
            elif effect.type == EffectType.COLOR_OVERLAY:
                cls.render_color_overlay(painter, rect, effect)
            elif effect.type == EffectType.GRADIENT_OVERLAY:
                cls.render_gradient_overlay(painter, rect, effect)
            elif effect.type == EffectType.OUTLINE:
                cls.render_outline(painter, rect, effect)


# ─── Ambient Renderer ──────────────────────────────────────────────────────

class AmbientRenderer:
    """Renderiza efeitos ambientais sobre o mapa/layer."""

    @staticmethod
    def render_fog(painter: QPainter, viewport: QRectF, effect: AmbientEffect):
        if not effect.enabled:
            return
        color = QColor(effect.color)
        color.setAlphaF(effect.opacity * 0.3 * effect.intensity)
        grad = QLinearGradient(viewport.topLeft(), viewport.bottomLeft())
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.6, color)
        grad.setColorAt(1.0, color)
        painter.fillRect(viewport, QBrush(grad))

    @staticmethod
    def render_ambient_light(painter: QPainter, viewport: QRectF, effect: AmbientEffect):
        if not effect.enabled:
            return
        color = QColor(effect.color)
        color.setAlphaF(effect.opacity * 0.15 * effect.intensity)
        painter.fillRect(viewport, color)

    @staticmethod
    def render_mist(painter: QPainter, viewport: QRectF, effect: AmbientEffect):
        if not effect.enabled:
            return
        color = QColor(effect.color)
        color.setAlphaF(effect.opacity * 0.2 * effect.intensity)
        center = viewport.center()
        radius = max(viewport.width(), viewport.height()) * 0.6 * effect.scale
        grad = QRadialGradient(center, radius)
        grad.setColorAt(0.0, color)
        grad.setColorAt(0.7, QColor(color.red(), color.green(), color.blue(), int(color.alpha() * 0.3)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(viewport, QBrush(grad))

    @classmethod
    def render(cls, painter: QPainter, viewport: QRectF, effects: list[AmbientEffect]):
        for effect in effects:
            if not effect.enabled:
                continue
            if effect.type == AmbientType.FOG:
                cls.render_fog(painter, viewport, effect)
            elif effect.type == AmbientType.AMBIENT_LIGHT:
                cls.render_ambient_light(painter, viewport, effect)
            elif effect.type == AmbientType.MIST:
                cls.render_mist(painter, viewport, effect)


# ─── Render Queue ──────────────────────────────────────────────────────────

@dataclass
class FrameStats:
    """Estatísticas de frame para profiling."""
    frame_time_ms: float = 0.0
    items_rendered: int = 0
    items_culled: int = 0
    chunks_visible: int = 0
    cache_hits: int = 0


class RenderQueue:
    """Fila de renderização com z-ordering, culling e batching."""

    def __init__(self):
        self._items: list[RenderItem] = []
        self._sorted = False
        self._stats = FrameStats()

    @property
    def stats(self) -> FrameStats:
        return self._stats

    def add(self, item: RenderItem):
        self._items.append(item)
        self._sorted = False

    def remove(self, item: RenderItem):
        if item in self._items:
            self._items.remove(item)

    def clear(self):
        self._items.clear()

    def sort(self):
        """Ordena por z-index."""
        self._items.sort(key=lambda ri: ri.z_index)
        self._sorted = True

    def visible_items(self, viewport: QRectF) -> list[RenderItem]:
        """Retorna items visíveis no viewport (culling)."""
        if not self._sorted:
            self.sort()

        visible = []
        culled = 0
        for ri in self._items:
            if not ri.visible:
                culled += 1
                continue
            item_rect = ri.item.sceneBoundingRect()
            if viewport.intersects(item_rect):
                visible.append(ri)
            else:
                culled += 1

        self._stats.items_culled = culled
        return visible

    @property
    def count(self) -> int:
        return len(self._items)


# ─── Rendering Engine ──────────────────────────────────────────────────────

class RenderingEngine:
    """Engine principal de renderização — orquestra queue, effects, cache, chunks."""

    def __init__(self):
        self.queue = RenderQueue()
        self.chunks = ChunkManager()
        self.cache = ImageCache()
        self.effect_renderer = EffectRenderer()
        self.ambient_renderer = AmbientRenderer()
        self.ambient_effects: list[AmbientEffect] = []
        self._zoom = 1.0
        self._stats = FrameStats()

    @property
    def stats(self) -> FrameStats:
        return self._stats

    def set_zoom(self, zoom: float):
        self._zoom = zoom

    # ── Item management ──

    def add_item(self, graphics_item: QGraphicsItem, z_index: int = 0,
                 effects: list[ItemEffect] | None = None) -> RenderItem:
        ri = RenderItem(item=graphics_item, z_index=z_index, effects=effects or [])
        self.queue.add(ri)
        pos = graphics_item.pos()
        self.chunks.add_item(ri, pos)
        return ri

    def remove_item(self, render_item: RenderItem):
        self.queue.remove(render_item)
        self.chunks.remove_item(render_item)

    # ── Ambient effects ──

    def add_ambient(self, effect: AmbientEffect):
        self.ambient_effects.append(effect)

    def remove_ambient(self, effect_type: AmbientType):
        self.ambient_effects = [e for e in self.ambient_effects if e.type != effect_type]

    def toggle_ambient(self, effect_type: AmbientType, enabled: bool):
        for e in self.ambient_effects:
            if e.type == effect_type:
                e.enabled = enabled

    # ── Rendering ──

    def render_frame(self, painter: QPainter, viewport: QRectF):
        """Renderiza um frame completo."""
        start = time.perf_counter()

        lod = self.chunks.lod_for_zoom(self._zoom)

        # 1. Get visible items (culling)
        visible = self.queue.visible_items(viewport)
        visible_chunks = self.chunks.visible_chunks(viewport)

        # 2. Render item effects (pre-pass: shadows/glow behind items)
        for ri in visible:
            pre_effects = [e for e in ri.effects if e.type in (EffectType.DROP_SHADOW, EffectType.GLOW)]
            if pre_effects:
                rect = ri.item.sceneBoundingRect()
                self.effect_renderer.render_effects(painter, rect, pre_effects)

        # 3. Items are rendered by QGraphicsScene (we don't paint them manually)
        # This engine provides the effects layer

        # 4. Render item effects (post-pass: overlays/outline on top)
        for ri in visible:
            post_effects = [e for e in ri.effects
                           if e.type in (EffectType.COLOR_OVERLAY, EffectType.GRADIENT_OVERLAY, EffectType.OUTLINE)]
            if post_effects:
                rect = ri.item.sceneBoundingRect()
                self.effect_renderer.render_effects(painter, rect, post_effects)

        # 5. Ambient effects (on top of everything)
        if self.ambient_effects:
            self.ambient_renderer.render(painter, viewport, self.ambient_effects)

        # Stats
        elapsed = (time.perf_counter() - start) * 1000
        self._stats = FrameStats(
            frame_time_ms=elapsed,
            items_rendered=len(visible),
            items_culled=self.queue.stats.items_culled,
            chunks_visible=len(visible_chunks),
            cache_hits=0,
        )

    def invalidate(self):
        """Invalida todo o cache."""
        self.cache.clear()
        self.chunks.invalidate_all()
        for ri in self.queue._items:
            ri.dirty = True
