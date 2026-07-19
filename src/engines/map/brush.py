"""Brush Engine — independent painting system for assets, terrain, and effects."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF

if TYPE_CHECKING:
    from PySide6.QtWidgets import QGraphicsScene


class BrushMode(Enum):
    PAINT = auto()
    ERASE = auto()
    MASK = auto()
    ALPHA = auto()


@dataclass
class BrushAssetEntry:
    """A single asset in a brush with weight and constraints."""
    asset_id: str
    weight: float = 1.0
    scale_min: float = 0.8
    scale_max: float = 1.2
    rotation_min: float = 0.0
    rotation_max: float = 360.0


@dataclass
class BrushConfig:
    """Full brush configuration."""
    name: str = "Default Brush"
    size: float = 64.0
    spacing: float = 0.3  # fraction of size
    scatter: float = 0.5  # dispersion amount (0-1)
    density: float = 1.0  # items per stamp
    flow: float = 1.0  # opacity per stamp
    opacity: float = 1.0
    hardness: float = 0.8  # edge softness (0=soft, 1=hard)
    random_rotation: bool = True
    random_scale: bool = True
    random_color_variation: float = 0.0  # 0-1
    # Stamped images have no soft edge to jitter (unlike terrain's radial-
    # gradient mask), so roughness here means extra placement irregularity —
    # widens rotation/scale jitter on top of each entry's own min/max range.
    roughness: float = 0.0  # 0-1
    # When the picked asset differs from the previous stamp's, ramp opacity
    # in over a few stamps instead of popping in at full opacity — a smooth
    # visual hand-off between different shapes mid-stroke.
    smoothness: float = 0.0  # 0-1
    assets: list[BrushAssetEntry] = field(default_factory=list)


@dataclass
class BrushStamp:
    """A single stamp placed by the brush."""
    position: QPointF
    asset_id: str
    scale: float
    rotation: float
    opacity: float


class BrushEngine(QObject):
    """Core brush system used by terrain, painting, and procedural engines."""

    stroke_started = Signal()
    stamp_placed = Signal(object)  # BrushStamp
    stroke_finished = Signal(list)  # list[BrushStamp]

    # Smoothness=1.0 fade-in duration, in real seconds — long enough to
    # actually be seen regardless of stroke speed/density (see _generate_stamps).
    MAX_FADE_SECONDS = 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = BrushConfig()
        self.config.scatter = 0.0  # default no scatter so stamps stay inside cursor
        self.mode = BrushMode.PAINT
        self._active = False
        self._last_pos: QPointF | None = None
        self._current_stroke: list[BrushStamp] = []
        self._distance_acc = 0.0
        # Smoothness cross-fade: per-asset wall-clock time.monotonic() of
        # when that asset was last picked with a *different* asset
        # immediately before it — reset whenever a stroke ends, so every new
        # stroke starts each asset's ramp fresh (an asset that was already
        # "warmed up" earlier in the same stroke doesn't need to fade in again).
        self._last_stamp_asset_id: str = ""
        self._fade_start: dict[str, float] = {}

    # --- Configuration ---

    def set_config(self, config: BrushConfig):
        self.config = config

    def set_size(self, size: float):
        self.config.size = max(1.0, min(2048.0, size))

    def set_spacing(self, spacing: float):
        self.config.spacing = max(0.01, min(2.0, spacing))

    def set_scatter(self, scatter: float):
        self.config.scatter = max(0.0, min(1.0, scatter))

    def set_density(self, density: float):
        self.config.density = max(0.1, min(10.0, density))

    def set_opacity(self, opacity: float):
        self.config.opacity = max(0.0, min(1.0, opacity))

    def set_mode(self, mode: BrushMode):
        self.mode = mode

    def add_asset(self, asset_id: str, weight: float = 1.0,
                  scale_min: float = 0.8, scale_max: float = 1.2,
                  rotation_min: float = 0.0, rotation_max: float = 360.0):
        self.config.assets.append(BrushAssetEntry(
            asset_id=asset_id, weight=weight,
            scale_min=scale_min, scale_max=scale_max,
            rotation_min=rotation_min, rotation_max=rotation_max,
        ))

    def clear_assets(self):
        self.config.assets.clear()

    # --- Stroke Lifecycle ---

    def begin_stroke(self, pos: QPointF):
        """Start a new brush stroke."""
        self._active = True
        self._last_pos = pos
        self._current_stroke.clear()
        self._distance_acc = 0.0
        self._last_stamp_asset_id = ""
        self._fade_start = {}
        self.stroke_started.emit()

        # Place initial stamp
        stamps = self._generate_stamps(pos)
        for s in stamps:
            self._current_stroke.append(s)
            self.stamp_placed.emit(s)

    def continue_stroke(self, pos: QPointF):
        """Continue stroke — places stamps along the path based on spacing."""
        if not self._active or not self._last_pos:
            return

        dx = pos.x() - self._last_pos.x()
        dy = pos.y() - self._last_pos.y()
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 0.1:
            return

        step = max(1.0, self.config.size * self.config.spacing)
        self._distance_acc += distance

        while self._distance_acc >= step:
            self._distance_acc -= step
            # Interpolate position
            t = 1.0 - (self._distance_acc / distance) if distance > 0 else 1.0
            stamp_x = self._last_pos.x() + dx * t
            stamp_y = self._last_pos.y() + dy * t
            stamp_pos = QPointF(stamp_x, stamp_y)

            stamps = self._generate_stamps(stamp_pos)
            for s in stamps:
                self._current_stroke.append(s)
                self.stamp_placed.emit(s)

        self._last_pos = pos

    def end_stroke(self) -> list[BrushStamp]:
        """End the current stroke. Returns all stamps placed."""
        self._active = False
        result = list(self._current_stroke)
        self.stroke_finished.emit(result)
        self._current_stroke.clear()
        self._last_pos = None
        return result

    def cancel_stroke(self):
        """Cancel without emitting finished."""
        self._active = False
        self._current_stroke.clear()
        self._last_pos = None

    @property
    def is_active(self) -> bool:
        return self._active

    # --- Stamp Generation ---

    def _generate_stamps(self, center: QPointF) -> list[BrushStamp]:
        """Generate stamps at a position based on density and scatter."""
        stamps = []
        count = max(1, int(self.config.density))

        for _ in range(count):
            # Scatter offset
            if self.config.scatter > 0:
                angle = random.uniform(0, 2 * math.pi)
                radius = random.uniform(0, self.config.size * 0.5 * self.config.scatter)
                offset_x = math.cos(angle) * radius
                offset_y = math.sin(angle) * radius
                pos = QPointF(center.x() + offset_x, center.y() + offset_y)
            else:
                pos = QPointF(center.x(), center.y())

            # Pick asset
            asset_id = self._pick_asset()
            if not asset_id:
                continue

            # Get asset entry for constraints
            entry = self._get_entry(asset_id)

            # Random scale
            if self.config.random_scale and entry:
                scale = random.uniform(entry.scale_min, entry.scale_max)
            else:
                scale = 1.0

            # Random rotation
            if self.config.random_rotation and entry:
                rotation = random.uniform(entry.rotation_min, entry.rotation_max)
            else:
                rotation = 0.0

            # Roughness: extra placement irregularity on top of whatever
            # random_rotation/random_scale already produced — no soft edge
            # to jitter on a stamped image, so this is the closest analog.
            # Needs to actually read as "rough" at a glance (Incarnate-style),
            # not a barely-there wobble — rotation, scale, AND position all
            # get pushed hard at roughness=1.
            if self.config.roughness > 0:
                rotation += random.uniform(-1, 1) * self.config.roughness * 45.0
                scale *= 1.0 + random.uniform(-1, 1) * self.config.roughness * 0.35
                jitter_radius = self.config.roughness * self.config.size * 0.3
                pos = QPointF(
                    pos.x() + random.uniform(-1, 1) * jitter_radius,
                    pos.y() + random.uniform(-1, 1) * jitter_radius,
                )

            # Opacity
            opacity = self.config.opacity * self.config.flow

            # Smoothness: when this stamp's asset differs from the previous
            # stamp's, ramp its opacity in over real elapsed time (not stamp
            # count) — at high density/fast drag speed, 8 *stamps* can pass
            # in well under a tenth of a second, so a stamp-count ramp was
            # effectively invisible. Time keeps the fade perceptible
            # regardless of how fast/dense the stroke is.
            if self.config.smoothness > 0:
                now = time.monotonic()
                if asset_id != self._last_stamp_asset_id:
                    self._fade_start[asset_id] = now
                duration = self.config.smoothness * self.MAX_FADE_SECONDS
                start = self._fade_start.get(asset_id)
                if start is not None and duration > 0:
                    elapsed = now - start
                    if elapsed < duration:
                        opacity *= max(0.05, elapsed / duration)
            self._last_stamp_asset_id = asset_id

            stamps.append(BrushStamp(
                position=pos,
                asset_id=asset_id,
                scale=scale,
                rotation=rotation,
                opacity=opacity,
            ))

        return stamps

    def _pick_asset(self) -> str:
        """Weighted random pick from brush assets."""
        if not self.config.assets:
            return ""

        total = sum(a.weight for a in self.config.assets)
        if total <= 0:
            return self.config.assets[0].asset_id

        r = random.uniform(0, total)
        cumulative = 0.0
        for entry in self.config.assets:
            cumulative += entry.weight
            if r <= cumulative:
                return entry.asset_id

        return self.config.assets[-1].asset_id

    def _get_entry(self, asset_id: str) -> BrushAssetEntry | None:
        for entry in self.config.assets:
            if entry.asset_id == asset_id:
                return entry
        return None


# --- Preset Brushes ---

def create_forest_brush(tree_ids: list[str]) -> BrushConfig:
    """Preset: dense forest brush."""
    config = BrushConfig(
        name="Forest Brush",
        size=200,
        spacing=0.2,
        scatter=0.8,
        density=3,
        random_rotation=True,
        random_scale=True,
    )
    for tid in tree_ids:
        config.assets.append(BrushAssetEntry(
            asset_id=tid, weight=1.0,
            scale_min=0.7, scale_max=1.3,
        ))
    return config


def create_rock_brush(rock_ids: list[str]) -> BrushConfig:
    """Preset: scattered rocks."""
    config = BrushConfig(
        name="Rock Brush",
        size=150,
        spacing=0.4,
        scatter=0.6,
        density=2,
        random_rotation=True,
        random_scale=True,
    )
    for rid in rock_ids:
        config.assets.append(BrushAssetEntry(
            asset_id=rid, weight=1.0,
            scale_min=0.5, scale_max=1.5,
        ))
    return config


def create_vegetation_brush(plant_ids: list[str]) -> BrushConfig:
    """Preset: bushes and vegetation."""
    config = BrushConfig(
        name="Vegetation Brush",
        size=120,
        spacing=0.25,
        scatter=0.7,
        density=4,
        random_rotation=True,
        random_scale=True,
    )
    for pid in plant_ids:
        config.assets.append(BrushAssetEntry(
            asset_id=pid, weight=1.0,
            scale_min=0.6, scale_max=1.1,
        ))
    return config
