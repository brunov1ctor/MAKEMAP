"""FASE 22 — View Modes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────────────────

class ViewMode(Enum):
    ILLUSTRATION = auto()
    TERRAIN = auto()
    BRUSH = auto()
    ENTITY = auto()
    GRID = auto()
    GAME = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class ModeConfig:
    mode: ViewMode = ViewMode.ILLUSTRATION
    toolbar_items: list[str] = field(default_factory=list)
    visible_panels: list[str] = field(default_factory=list)
    visible_layers: list[str] = field(default_factory=list)  # empty = all
    shortcuts: dict[str, str] = field(default_factory=dict)
    cursor: str = "default"
    grid_visible: bool = False
    snap_enabled: bool = False


@dataclass
class ModeState:
    """Persisted state per mode (camera, tool, etc.)."""
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    active_tool: str = ""
    extra: dict = field(default_factory=dict)


# ─── View Mode Engine ────────────────────────────────────────────────────────

class ViewModeEngine:
    def __init__(self):
        self._active_mode: ViewMode = ViewMode.ILLUSTRATION
        self._configs: dict[ViewMode, ModeConfig] = {}
        self._states: dict[ViewMode, ModeState] = {}
        self._init_configs()

    def _init_configs(self):
        self._configs[ViewMode.ILLUSTRATION] = ModeConfig(
            mode=ViewMode.ILLUSTRATION,
            toolbar_items=["select", "move", "pen", "brush", "eraser", "text",
                           "shape", "asset", "eyedropper"],
            visible_panels=["explorer", "inspector", "layers", "assets"],
            cursor="crosshair",
            shortcuts={"B": "brush", "E": "eraser", "T": "text", "V": "select"},
        )
        self._configs[ViewMode.TERRAIN] = ModeConfig(
            mode=ViewMode.TERRAIN,
            toolbar_items=["terrain_paint", "terrain_erase", "elevation",
                           "biome", "blend", "flatten"],
            visible_panels=["explorer", "terrain", "layers"],
            cursor="circle",
            grid_visible=True,
            shortcuts={"P": "terrain_paint", "E": "terrain_erase", "F": "flatten"},
        )
        self._configs[ViewMode.BRUSH] = ModeConfig(
            mode=ViewMode.BRUSH,
            toolbar_items=["brush", "eraser", "scatter", "spray",
                           "smudge", "mask", "alpha"],
            visible_panels=["brushes", "layers", "colors"],
            cursor="circle",
            shortcuts={"B": "brush", "E": "eraser", "S": "scatter", "M": "mask"},
        )
        self._configs[ViewMode.ENTITY] = ModeConfig(
            mode=ViewMode.ENTITY,
            toolbar_items=["select", "place_npc", "place_mob", "place_boss",
                           "place_quest", "place_dungeon", "place_spawn",
                           "place_portal", "connect", "path"],
            visible_panels=["explorer", "entities", "inspector", "quests", "connections"],
            cursor="default",
            shortcuts={"N": "place_npc", "M": "place_mob", "Q": "place_quest",
                       "C": "connect", "V": "select"},
        )
        self._configs[ViewMode.GRID] = ModeConfig(
            mode=ViewMode.GRID,
            toolbar_items=["select", "move", "align", "distribute",
                           "measure", "guide"],
            visible_panels=["explorer", "inspector", "grid_settings"],
            cursor="default",
            grid_visible=True,
            snap_enabled=True,
            shortcuts={"G": "guide", "A": "align", "D": "distribute"},
        )
        self._configs[ViewMode.GAME] = ModeConfig(
            mode=ViewMode.GAME,
            toolbar_items=["pan", "zoom", "inspect"],
            visible_panels=[],
            cursor="hand",
            shortcuts={"Escape": "exit_game_mode"},
        )
        # Init empty states
        for mode in ViewMode:
            self._states[mode] = ModeState()

    # ─── Mode Switching ──────────────────────────────────────────────────

    @property
    def active_mode(self) -> ViewMode:
        return self._active_mode

    def set_mode(self, mode: ViewMode):
        self._active_mode = mode

    def cycle_next(self):
        modes = list(ViewMode)
        idx = (modes.index(self._active_mode) + 1) % len(modes)
        self._active_mode = modes[idx]

    def cycle_prev(self):
        modes = list(ViewMode)
        idx = (modes.index(self._active_mode) - 1) % len(modes)
        self._active_mode = modes[idx]

    # ─── Config Access ───────────────────────────────────────────────────

    def get_config(self, mode: ViewMode = None) -> ModeConfig:
        return self._configs[mode or self._active_mode]

    def get_toolbar_items(self) -> list[str]:
        return self._configs[self._active_mode].toolbar_items

    def get_visible_panels(self) -> list[str]:
        return self._configs[self._active_mode].visible_panels

    def get_visible_layers(self) -> list[str]:
        return self._configs[self._active_mode].visible_layers

    def get_shortcuts(self) -> dict[str, str]:
        return self._configs[self._active_mode].shortcuts

    def get_cursor(self) -> str:
        return self._configs[self._active_mode].cursor

    def is_grid_visible(self) -> bool:
        return self._configs[self._active_mode].grid_visible

    def is_snap_enabled(self) -> bool:
        return self._configs[self._active_mode].snap_enabled

    # ─── State Persistence ───────────────────────────────────────────────

    def save_state(self, zoom: float = None, pan_x: float = None,
                   pan_y: float = None, active_tool: str = None, **extra):
        state = self._states[self._active_mode]
        if zoom is not None:
            state.zoom = zoom
        if pan_x is not None:
            state.pan_x = pan_x
        if pan_y is not None:
            state.pan_y = pan_y
        if active_tool is not None:
            state.active_tool = active_tool
        state.extra.update(extra)

    def get_state(self, mode: ViewMode = None) -> ModeState:
        return self._states[mode or self._active_mode]

    # ─── Customization ───────────────────────────────────────────────────

    def set_toolbar_items(self, mode: ViewMode, items: list[str]):
        self._configs[mode].toolbar_items = items

    def set_visible_panels(self, mode: ViewMode, panels: list[str]):
        self._configs[mode].visible_panels = panels

    def set_shortcut(self, mode: ViewMode, key: str, action: str):
        self._configs[mode].shortcuts[key] = action

    def set_cursor(self, mode: ViewMode, cursor: str):
        self._configs[mode].cursor = cursor
