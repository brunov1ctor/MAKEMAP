"""BrushEffectsOverlay — a single whole-scene QGraphicsItem that paints
every brush-painted animated effect (see brush_effects.ANIMATED_EFFECTS,
e.g. "Névoa") on top of the map. An effect stroke's own TerrainLayer is
mask-only (no visible texture — see BrushTool's effects routing), so the
animated look is entirely painted here, per-frame, by BrushMediator's own
refresh timer, clipped per-stroke to TerrainLayer.effect_geometry()'s
traced silhouette.

BrushMediator owns creating/ticking this (mirrors LightMediator's analogous
ownership of GlobalLightingOverlay); it finds active effect strokes itself
by scanning the scene rather than BrushMediator handing it a list, so it
stays correct across stroke add/remove/erase without extra wiring.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsItem

from src.canvas.z_order import ZOrder
from src.canvas.item_utils import make_non_interactive
from src.engines.map.brush_effects import ANIMATED_EFFECTS, effect_color
from src.engines.map.terrain_layer import TerrainLayer

# Extra margin (scene units) added around each stroke's own effect bounds
# to cover glow/blur overdraw (e.g. particle glow halos) that paints
# slightly outside effect_geometry()'s own reported bounds.
_MARGIN = 16.0


class BrushEffectsOverlay(QGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(ZOrder.ANIMATED_EFFECTS)
        make_non_interactive(self)
        # Per-layer FBM/mask cache, id(layer) -> dict — see
        # brush_effects._fog_textures. Regenerating the noise textures
        # every repaint tick would be wasteful; this only regenerates when
        # a stroke's size bucket actually changes.
        self._cache: dict[int, dict] = {}
        # Cached (layer, effect_key) list — rescanning the whole scene
        # every 150ms tick regardless of whether anything changed was a
        # real cost at scale; see BrushMediator.mark_dirty callers for
        # every point that invalidates this.
        self._active_cache: list[tuple[TerrainLayer, str]] | None = None

    def mark_dirty(self):
        """Call whenever which effect strokes are active (or their painted
        bounds) may have changed — add/remove/visibility/paint/erase."""
        self._active_cache = None
        self.prepareGeometryChange()

    def has_active(self) -> bool:
        return bool(self._active_layers())

    def _active_layers(self) -> list[tuple[TerrainLayer, str]]:
        """(layer, effect_key) for every visible, painted brush-effect
        stroke — discovered by scanning the scene for items tagged with an
        "effect_key" (see BrushTool's effects routing, which sets
        item.data(0)["effect_key"] and item.data(3) = the backing
        TerrainLayer instance). Cached until mark_dirty() is called, so
        strokes being added/removed/reloaded must call mark_dirty() to
        stay in sync (see BrushMediator)."""
        if self._active_cache is not None:
            return self._active_cache
        if self.scene() is None:
            return []
        out = []
        for item in self.scene().items():
            data = item.data(0)
            if not isinstance(data, dict):
                continue
            effect_key = data.get("effect_key")
            if not effect_key or effect_key not in ANIMATED_EFFECTS:
                continue
            if not item.isVisible():
                continue
            layer = item.data(3)
            if isinstance(layer, TerrainLayer):
                out.append((layer, effect_key))
        self._active_cache = out
        return out

    def _union_active_bounds(self) -> QRectF:
        """Union of every active stroke's own mapped effect bounds (not
        the whole scene) — each stroke's effect only ever paints within
        its own geometry, so the overlay's dirty region can stay bounded
        to that instead of forcing Qt to recomposite the entire canvas."""
        union = QRectF()
        for layer, _effect_key in self._active_layers():
            geometry = layer.effect_geometry()
            if geometry is None:
                continue
            _local_path, local_bounds = geometry
            scene_bounds = layer.item.sceneTransform().mapRect(local_bounds)
            scene_bounds = scene_bounds.adjusted(-_MARGIN, -_MARGIN, _MARGIN, _MARGIN)
            union = scene_bounds if union.isNull() else union.united(scene_bounds)
        return union

    def boundingRect(self) -> QRectF:
        if self.scene() is None or not self._active_layers():
            return QRectF()
        return self._union_active_bounds()

    def paint(self, painter: QPainter, option, widget=None):
        active = self._active_layers()
        if not active:
            return
        self._prune_cache(active)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Collected once per paint (not once per stroke) and stashed under
        # a key that isn't a layer id, so it never collides with
        # _particle_seeds' per-layer cache entries (see brush_effects.
        # _nearest_light_bias, which reads this instead of scanning the
        # scene itself).
        self._cache["_lights"] = self._nearby_lights()
        for layer, effect_key in active:
            geometry = layer.effect_geometry()
            if geometry is None:
                continue
            local_path, local_bounds = geometry
            transform = layer.item.sceneTransform()
            scene_path = transform.map(local_path)
            scene_bounds = transform.mapRect(local_bounds)
            if not scene_bounds.intersects(option.exposedRect):
                continue
            effect = ANIMATED_EFFECTS[effect_key]
            effect(painter, self._cache, layer, scene_path, scene_bounds, effect_color(effect_key))

    def _nearby_lights(self):
        """Visible LightItems in the scene, collected once per paint (not
        once per stroke) — feeds brush_effects._nearest_light_bias (used
        by the insect effect) via cache["_lights"] instead of it doing its
        own separate full-scene scan."""
        from src.canvas.light_item import LightItem

        if self.scene() is None:
            return []
        return [it for it in self.scene().items() if isinstance(it, LightItem) and it.isVisible()]

    def _prune_cache(self, active: list[tuple[TerrainLayer, str]]):
        live_ids = {id(layer) for layer, _ in active}
        for stale_id in set(self._cache) - live_ids:
            del self._cache[stale_id]
