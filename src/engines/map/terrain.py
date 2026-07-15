"""Terrain Engine — terrain painting with layers and blending."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient, QBrush, QPixmap

from src.engines.map.brush import BrushEngine, BrushConfig, BrushMode

if TYPE_CHECKING:
    pass


class TerrainType(Enum):
    GRASS = auto()
    SAND = auto()
    SNOW = auto()
    ROCK = auto()
    MUD = auto()
    WATER = auto()
    LAVA = auto()
    ASH = auto()
    DIRT = auto()
    CUSTOM = auto()


@dataclass
class TerrainDef:
    """Definition of a terrain type with visual properties."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    terrain_type: TerrainType = TerrainType.GRASS
    color: QColor = field(default_factory=lambda: QColor(34, 139, 34))
    texture_path: str = ""
    blend_priority: int = 0  # higher = painted on top
    texture_asset_id: str = ""  # asset registrado no AssetEngine
    texture_scale: float = 1.0


# Default terrain palette
DEFAULT_TERRAINS: list[TerrainDef] = [
    TerrainDef(name="Grass", terrain_type=TerrainType.GRASS, color=QColor(34, 139, 34), blend_priority=0),
    TerrainDef(name="Sand", terrain_type=TerrainType.SAND, color=QColor(210, 180, 100), blend_priority=1),
    TerrainDef(name="Snow", terrain_type=TerrainType.SNOW, color=QColor(240, 248, 255), blend_priority=2),
    TerrainDef(name="Rock", terrain_type=TerrainType.ROCK, color=QColor(128, 128, 128), blend_priority=3),
    TerrainDef(name="Mud", terrain_type=TerrainType.MUD, color=QColor(101, 67, 33), blend_priority=1),
    TerrainDef(name="Water", terrain_type=TerrainType.WATER, color=QColor(30, 100, 180), blend_priority=4),
    TerrainDef(name="Lava", terrain_type=TerrainType.LAVA, color=QColor(207, 16, 32), blend_priority=5),
    TerrainDef(name="Ash", terrain_type=TerrainType.ASH, color=QColor(80, 80, 80), blend_priority=2),
    TerrainDef(name="Dirt", terrain_type=TerrainType.DIRT, color=QColor(139, 90, 43), blend_priority=0),
]


@dataclass
class TerrainStroke:
    """A single paint stroke on a terrain layer."""
    position: QPointF
    radius: float
    hardness: float
    opacity: float
    terrain_id: str


class TerrainLayer:
    """A single terrain layer with alpha mask for blending."""

    def __init__(self, terrain_def: TerrainDef, width: int, height: int):
        self.terrain_def = terrain_def
        self.width = width
        self.height = height
        # Alpha mask: 0=transparent, 255=fully painted
        self._mask = QImage(width, height, QImage.Format.Format_Grayscale8)
        self._mask.fill(0)

    @property
    def mask(self) -> QImage:
        return self._mask

    def paint_circle(self, center: QPointF, radius: float, hardness: float, opacity: float):
        """Paint a circle on the alpha mask with soft edges."""
        painter = QPainter(self._mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Create radial gradient for soft edges
        gradient = QRadialGradient(center, radius)
        inner_radius = hardness  # 0-1
        alpha = int(255 * opacity)

        gradient.setColorAt(0, QColor(alpha, alpha, alpha))
        gradient.setColorAt(inner_radius, QColor(alpha, alpha, alpha))
        gradient.setColorAt(1.0, QColor(0, 0, 0))

        painter.setPen(QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Lighten)
        painter.drawEllipse(center, radius, radius)
        painter.end()

    def erase_circle(self, center: QPointF, radius: float, hardness: float, opacity: float):
        """Erase a circle from the alpha mask."""
        painter = QPainter(self._mask)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QRadialGradient(center, radius)
        alpha = int(255 * opacity)

        gradient.setColorAt(0, QColor(alpha, alpha, alpha))
        gradient.setColorAt(hardness, QColor(alpha, alpha, alpha))
        gradient.setColorAt(1.0, QColor(0, 0, 0))

        painter.setPen(QColor(0, 0, 0, 0))
        painter.setBrush(gradient)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter.drawEllipse(center, radius, radius)
        painter.end()

    def clear(self):
        """Clear the entire mask."""
        self._mask.fill(0)

    def fill(self):
        """Fill the entire mask."""
        self._mask.fill(255)


class TerrainEngine(QObject):
    """Manages terrain layers, painting, and blending."""

    terrain_painted = Signal(str, object)  # terrain_id, TerrainStroke
    terrain_erased = Signal(str, object)
    layer_added = Signal(str)  # terrain_id
    layer_removed = Signal(str)

    def __init__(self, width: int = 4096, height: int = 4096, asset_engine=None, parent=None):
        super().__init__(parent)
        self._width = width
        self._height = height
        self._asset_engine = asset_engine
        self._layers: dict[str, TerrainLayer] = {}
        self._terrain_defs: dict[str, TerrainDef] = {}
        self._active_terrain_id: str = ""
        self._brush = BrushEngine(self)

        # Register default terrains
        for td in DEFAULT_TERRAINS:
            self.register_terrain(td)

    def set_asset_engine(self, asset_engine):
        """Injeta o AssetEngine para renderizar texturas."""
        self._asset_engine = asset_engine

    # --- Terrain Definitions ---

    def register_terrain(self, terrain_def: TerrainDef):
        """Register a terrain type."""
        self._terrain_defs[terrain_def.id] = terrain_def

    def get_terrain(self, terrain_id: str) -> TerrainDef | None:
        return self._terrain_defs.get(terrain_id)

    @property
    def terrains(self) -> list[TerrainDef]:
        return sorted(self._terrain_defs.values(), key=lambda t: t.blend_priority)

    def set_active_terrain(self, terrain_id: str):
        self._active_terrain_id = terrain_id

    @property
    def active_terrain_id(self) -> str:
        return self._active_terrain_id

    # --- Layer Management ---

    def add_layer(self, terrain_id: str) -> TerrainLayer:
        """Create a terrain layer for a terrain type."""
        td = self._terrain_defs.get(terrain_id)
        if not td:
            raise ValueError(f"Terrain não registrado: {terrain_id}")

        layer = TerrainLayer(td, self._width, self._height)
        self._layers[terrain_id] = layer
        self.layer_added.emit(terrain_id)
        return layer

    def get_layer(self, terrain_id: str) -> TerrainLayer | None:
        return self._layers.get(terrain_id)

    def remove_layer(self, terrain_id: str):
        if terrain_id in self._layers:
            del self._layers[terrain_id]
            self.layer_removed.emit(terrain_id)

    @property
    def layers(self) -> list[TerrainLayer]:
        """Layers sorted by blend priority."""
        return sorted(
            self._layers.values(),
            key=lambda l: l.terrain_def.blend_priority,
        )

    # --- Painting ---

    def paint(self, pos: QPointF, radius: float | None = None,
              hardness: float | None = None, opacity: float | None = None):
        """Paint active terrain at position."""
        if not self._active_terrain_id:
            return

        layer = self._layers.get(self._active_terrain_id)
        if not layer:
            layer = self.add_layer(self._active_terrain_id)

        r = radius or self._brush.config.size * 0.5
        h = hardness or self._brush.config.hardness
        o = opacity or self._brush.config.opacity

        layer.paint_circle(pos, r, h, o)

        stroke = TerrainStroke(
            position=pos, radius=r, hardness=h,
            opacity=o, terrain_id=self._active_terrain_id,
        )
        self.terrain_painted.emit(self._active_terrain_id, stroke)

    def erase(self, pos: QPointF, radius: float | None = None,
              hardness: float | None = None, opacity: float | None = None):
        """Erase active terrain at position."""
        if not self._active_terrain_id:
            return

        layer = self._layers.get(self._active_terrain_id)
        if not layer:
            return

        r = radius or self._brush.config.size * 0.5
        h = hardness or self._brush.config.hardness
        o = opacity or self._brush.config.opacity

        layer.erase_circle(pos, r, h, o)

        stroke = TerrainStroke(
            position=pos, radius=r, hardness=h,
            opacity=o, terrain_id=self._active_terrain_id,
        )
        self.terrain_erased.emit(self._active_terrain_id, stroke)

    # --- Brush Config ---

    @property
    def brush(self) -> BrushEngine:
        return self._brush

    def set_brush_size(self, size: float):
        self._brush.set_size(size)

    def set_brush_hardness(self, hardness: float):
        self._brush.config.hardness = max(0.0, min(1.0, hardness))

    def set_brush_opacity(self, opacity: float):
        self._brush.set_opacity(opacity)

    # --- Rendering ---

    def render_composite(self) -> QImage:
        """Render all terrain layers into a single composite image."""
        composite = QImage(self._width, self._height, QImage.Format.Format_ARGB32)
        composite.fill(QColor(0, 0, 0, 0))

        painter = QPainter(composite)
        for layer in self.layers:
            # Create colored/textured image
            colored = QImage(self._width, self._height, QImage.Format.Format_ARGB32)
            colored.fill(QColor(0, 0, 0, 0))

            texture_pixmap = None
            if self._asset_engine and layer.terrain_def.texture_asset_id:
                texture_pixmap = self._asset_engine.get_pixmap(layer.terrain_def.texture_asset_id)

            tile_painter = QPainter(colored)
            if texture_pixmap and not texture_pixmap.isNull():
                # Tile texture across the image
                tile_painter.fillRect(colored.rect(), QBrush(texture_pixmap))
            else:
                tile_painter.fillRect(colored.rect(), layer.terrain_def.color)
            tile_painter.end()

            # Apply mask as alpha
            for y in range(self._height):
                for x in range(self._width):
                    alpha = layer.mask.pixelColor(x, y).red()
                    c = colored.pixelColor(x, y)
                    c.setAlpha(alpha)
                    colored.setPixelColor(x, y, c)

            painter.drawImage(0, 0, colored)

        painter.end()
        return composite

    def render_region(self, rect: QRectF) -> QImage:
        """Render only a region (for performance)."""
        x = int(rect.x())
        y = int(rect.y())
        w = int(rect.width())
        h = int(rect.height())

        region = QImage(w, h, QImage.Format.Format_ARGB32)
        region.fill(QColor(0, 0, 0, 0))

        painter = QPainter(region)
        for layer in self.layers:
            cropped_mask = layer.mask.copy(x, y, w, h)
            colored = QImage(w, h, QImage.Format.Format_ARGB32)
            colored.fill(layer.terrain_def.color)

            # Fast alpha application using scanlines would be ideal,
            # but for now use composition
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setOpacity(1.0)
            painter.drawImage(0, 0, colored)

        painter.end()
        return region

    # --- Resize ---

    def resize(self, width: int, height: int):
        """Resize all terrain layers."""
        self._width = width
        self._height = height
        for terrain_id, layer in list(self._layers.items()):
            td = layer.terrain_def
            self._layers[terrain_id] = TerrainLayer(td, width, height)
