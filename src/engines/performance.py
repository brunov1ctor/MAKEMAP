"""FASE 25 — Performance Engine."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────────────────

class LODLevel(Enum):
    FULL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    PLACEHOLDER = auto()


class WarningType(Enum):
    FRAME_BUDGET = auto()
    MEMORY = auto()
    ITEM_COUNT = auto()
    TEXTURE_SIZE = auto()
    LAYER_COUNT = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class FrameMetrics:
    frame_time_ms: float = 0.0
    render_time_ms: float = 0.0
    update_time_ms: float = 0.0
    items_rendered: int = 0
    items_culled: int = 0
    chunks_loaded: int = 0
    draw_calls: int = 0


@dataclass
class MemoryMetrics:
    texture_cache_mb: float = 0.0
    image_cache_mb: float = 0.0
    total_items: int = 0
    loaded_chunks: int = 0
    total_chunks: int = 0


@dataclass
class PerformanceWarning:
    warning_type: WarningType = WarningType.FRAME_BUDGET
    message: str = ""
    value: float = 0.0
    threshold: float = 0.0
    suggestion: str = ""


@dataclass
class PerformanceConfig:
    target_fps: int = 60
    frame_budget_ms: float = 16.67
    memory_limit_mb: float = 512.0
    max_visible_items: int = 5000
    max_texture_size: int = 4096
    chunk_size: int = 512
    lod_distances: dict[LODLevel, float] = field(default_factory=lambda: {
        LODLevel.FULL: 0,
        LODLevel.HIGH: 500,
        LODLevel.MEDIUM: 1500,
        LODLevel.LOW: 3000,
        LODLevel.PLACEHOLDER: 6000,
    })
    virtualization_distance: float = 8000.0
    cache_size_limit: int = 256  # max cached images


# ─── Performance Engine ──────────────────────────────────────────────────────

class PerformanceEngine:
    def __init__(self, config: PerformanceConfig = None):
        self._config = config or PerformanceConfig()
        self._frame_history: deque[FrameMetrics] = deque(maxlen=120)
        self._memory = MemoryMetrics()
        self._warnings: list[PerformanceWarning] = []
        self._overlay_visible: bool = False
        self._frame_start: float = 0.0
        self._render_start: float = 0.0

    # ─── Frame Tracking ──────────────────────────────────────────────────

    def begin_frame(self):
        self._frame_start = time.perf_counter()

    def begin_render(self):
        self._render_start = time.perf_counter()

    def end_render(self, items_rendered: int = 0, items_culled: int = 0,
                   draw_calls: int = 0):
        render_ms = (time.perf_counter() - self._render_start) * 1000
        frame_ms = (time.perf_counter() - self._frame_start) * 1000
        metrics = FrameMetrics(
            frame_time_ms=frame_ms,
            render_time_ms=render_ms,
            update_time_ms=frame_ms - render_ms,
            items_rendered=items_rendered,
            items_culled=items_culled,
            draw_calls=draw_calls,
            chunks_loaded=self._memory.loaded_chunks,
        )
        self._frame_history.append(metrics)
        self._check_warnings(metrics)

    # ─── Metrics ─────────────────────────────────────────────────────────

    @property
    def fps(self) -> float:
        if not self._frame_history:
            return 0.0
        avg_ms = sum(f.frame_time_ms for f in self._frame_history) / len(self._frame_history)
        return 1000.0 / avg_ms if avg_ms > 0 else 0.0

    @property
    def avg_frame_time(self) -> float:
        if not self._frame_history:
            return 0.0
        return sum(f.frame_time_ms for f in self._frame_history) / len(self._frame_history)

    @property
    def last_frame(self) -> Optional[FrameMetrics]:
        return self._frame_history[-1] if self._frame_history else None

    @property
    def memory(self) -> MemoryMetrics:
        return self._memory

    # ─── LOD ─────────────────────────────────────────────────────────────

    def get_lod_level(self, distance: float) -> LODLevel:
        for level in reversed(LODLevel):
            if distance >= self._config.lod_distances.get(level, 0):
                return level
        return LODLevel.FULL

    def should_virtualize(self, distance: float) -> bool:
        return distance >= self._config.virtualization_distance

    # ─── Chunk Management ────────────────────────────────────────────────

    def update_chunk_stats(self, loaded: int, total: int):
        self._memory.loaded_chunks = loaded
        self._memory.total_chunks = total

    def should_load_chunk(self, chunk_distance: float) -> bool:
        return chunk_distance < self._config.virtualization_distance

    def should_unload_chunk(self, chunk_distance: float) -> bool:
        return chunk_distance > self._config.virtualization_distance * 1.2

    # ─── Memory ──────────────────────────────────────────────────────────

    def update_memory(self, texture_cache_mb: float = None,
                      image_cache_mb: float = None, total_items: int = None):
        if texture_cache_mb is not None:
            self._memory.texture_cache_mb = texture_cache_mb
        if image_cache_mb is not None:
            self._memory.image_cache_mb = image_cache_mb
        if total_items is not None:
            self._memory.total_items = total_items

    @property
    def total_memory_mb(self) -> float:
        return self._memory.texture_cache_mb + self._memory.image_cache_mb

    def is_memory_critical(self) -> bool:
        return self.total_memory_mb > self._config.memory_limit_mb * 0.9

    # ─── Warnings ────────────────────────────────────────────────────────

    def _check_warnings(self, metrics: FrameMetrics):
        self._warnings.clear()
        if metrics.frame_time_ms > self._config.frame_budget_ms:
            self._warnings.append(PerformanceWarning(
                warning_type=WarningType.FRAME_BUDGET,
                message=f"Frame time {metrics.frame_time_ms:.1f}ms exceeds budget {self._config.frame_budget_ms:.1f}ms",
                value=metrics.frame_time_ms, threshold=self._config.frame_budget_ms,
                suggestion="Reduce visible items or enable LOD",
            ))
        if self.total_memory_mb > self._config.memory_limit_mb * 0.8:
            self._warnings.append(PerformanceWarning(
                warning_type=WarningType.MEMORY,
                message=f"Memory usage {self.total_memory_mb:.0f}MB approaching limit {self._config.memory_limit_mb:.0f}MB",
                value=self.total_memory_mb, threshold=self._config.memory_limit_mb,
                suggestion="Clear unused caches or reduce texture resolution",
            ))
        if metrics.items_rendered > self._config.max_visible_items:
            self._warnings.append(PerformanceWarning(
                warning_type=WarningType.ITEM_COUNT,
                message=f"{metrics.items_rendered} items rendered (max: {self._config.max_visible_items})",
                value=metrics.items_rendered, threshold=self._config.max_visible_items,
                suggestion="Use chunking or increase virtualization",
            ))

    @property
    def warnings(self) -> list[PerformanceWarning]:
        return list(self._warnings)

    @property
    def has_warnings(self) -> bool:
        return len(self._warnings) > 0

    # ─── Overlay ─────────────────────────────────────────────────────────

    @property
    def overlay_visible(self) -> bool:
        return self._overlay_visible

    def toggle_overlay(self):
        self._overlay_visible = not self._overlay_visible

    def get_overlay_text(self) -> str:
        last = self.last_frame
        if not last:
            return "No data"
        return (
            f"FPS: {self.fps:.0f} | Frame: {last.frame_time_ms:.1f}ms\n"
            f"Render: {last.render_time_ms:.1f}ms | Items: {last.items_rendered} "
            f"(culled: {last.items_culled})\n"
            f"Memory: {self.total_memory_mb:.0f}MB | "
            f"Chunks: {self._memory.loaded_chunks}/{self._memory.total_chunks}"
        )

    # ─── Config ──────────────────────────────────────────────────────────

    @property
    def config(self) -> PerformanceConfig:
        return self._config

    def set_target_fps(self, fps: int):
        self._config.target_fps = fps
        self._config.frame_budget_ms = 1000.0 / fps
