"""FASE 21 — Workspace Manager."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────────────────

class DockArea(Enum):
    LEFT = auto()
    RIGHT = auto()
    BOTTOM = auto()
    TOP = auto()
    FLOATING = auto()
    CENTER = auto()


class DisplayMode(Enum):
    NORMAL = auto()
    FULLSCREEN = auto()
    ZEN = auto()           # canvas only
    DISTRACTION_FREE = auto()  # canvas + minimal toolbar


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class PanelState:
    id: str = ""
    name: str = ""
    dock_area: DockArea = DockArea.LEFT
    visible: bool = True
    collapsed: bool = False
    width: int = 250
    height: int = 300
    tab_index: int = 0       # position within dock tab bar
    floating_x: int = 100
    floating_y: int = 100


@dataclass
class WorkspaceLayout:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default"
    panels: list[PanelState] = field(default_factory=list)
    splitter_sizes: list[int] = field(default_factory=lambda: [220, 900, 240])
    display_mode: DisplayMode = DisplayMode.NORMAL
    is_builtin: bool = False


# ─── Workspace Manager ───────────────────────────────────────────────────────

class WorkspaceManager:
    def __init__(self):
        self._panels: dict[str, PanelState] = {}
        self._layouts: dict[str, WorkspaceLayout] = {}
        self._active_layout_id: Optional[str] = None
        self._display_mode: DisplayMode = DisplayMode.NORMAL
        self._init_builtins()

    def _init_builtins(self):
        """Create built-in layout presets."""
        default = WorkspaceLayout(name="Default", is_builtin=True, panels=[
            PanelState(id="explorer", name="Explorer", dock_area=DockArea.LEFT, width=220),
            PanelState(id="inspector", name="Inspector", dock_area=DockArea.RIGHT, width=240),
            PanelState(id="layers", name="Layers", dock_area=DockArea.RIGHT, tab_index=1, width=240),
            PanelState(id="assets", name="Assets", dock_area=DockArea.BOTTOM, height=200),
            PanelState(id="properties", name="Properties", dock_area=DockArea.RIGHT, tab_index=2, width=240),
        ])
        painting = WorkspaceLayout(name="Painting", is_builtin=True, panels=[
            PanelState(id="brushes", name="Brushes", dock_area=DockArea.LEFT, width=200),
            PanelState(id="layers", name="Layers", dock_area=DockArea.LEFT, tab_index=1, width=200),
            PanelState(id="colors", name="Colors", dock_area=DockArea.RIGHT, width=200),
        ], splitter_sizes=[200, 1000, 200])
        mmorpg = WorkspaceLayout(name="MMORPG", is_builtin=True, panels=[
            PanelState(id="explorer", name="Explorer", dock_area=DockArea.LEFT, width=250),
            PanelState(id="entities", name="Entities", dock_area=DockArea.LEFT, tab_index=1, width=250),
            PanelState(id="inspector", name="Inspector", dock_area=DockArea.RIGHT, width=280),
            PanelState(id="quests", name="Quests", dock_area=DockArea.RIGHT, tab_index=1, width=280),
            PanelState(id="connections", name="Connections", dock_area=DockArea.BOTTOM, height=180),
        ], splitter_sizes=[250, 850, 280])
        minimal = WorkspaceLayout(name="Minimal", is_builtin=True, panels=[
            PanelState(id="explorer", name="Explorer", dock_area=DockArea.LEFT, width=180, collapsed=True),
        ], splitter_sizes=[0, 1200, 0])

        for layout in [default, painting, mmorpg, minimal]:
            self._layouts[layout.id] = layout
        self._active_layout_id = default.id
        self._apply_layout(default)

    # ─── Panel Management ────────────────────────────────────────────────

    def register_panel(self, panel_id: str, name: str, dock_area: DockArea = DockArea.LEFT):
        if panel_id not in self._panels:
            self._panels[panel_id] = PanelState(id=panel_id, name=name, dock_area=dock_area)

    def show_panel(self, panel_id: str):
        panel = self._panels.get(panel_id)
        if panel:
            panel.visible = True

    def hide_panel(self, panel_id: str):
        panel = self._panels.get(panel_id)
        if panel:
            panel.visible = False

    def toggle_panel(self, panel_id: str):
        panel = self._panels.get(panel_id)
        if panel:
            panel.visible = not panel.visible

    def collapse_panel(self, panel_id: str):
        panel = self._panels.get(panel_id)
        if panel:
            panel.collapsed = True

    def expand_panel(self, panel_id: str):
        panel = self._panels.get(panel_id)
        if panel:
            panel.collapsed = False

    def move_panel(self, panel_id: str, dock_area: DockArea, tab_index: int = 0):
        panel = self._panels.get(panel_id)
        if panel:
            panel.dock_area = dock_area
            panel.tab_index = tab_index

    def float_panel(self, panel_id: str, x: int = 100, y: int = 100):
        panel = self._panels.get(panel_id)
        if panel:
            panel.dock_area = DockArea.FLOATING
            panel.floating_x = x
            panel.floating_y = y

    def dock_panel(self, panel_id: str, dock_area: DockArea):
        panel = self._panels.get(panel_id)
        if panel:
            panel.dock_area = dock_area

    def resize_panel(self, panel_id: str, width: int = None, height: int = None):
        panel = self._panels.get(panel_id)
        if panel:
            if width is not None:
                panel.width = max(100, width)
            if height is not None:
                panel.height = max(50, height)

    def get_panel(self, panel_id: str) -> Optional[PanelState]:
        return self._panels.get(panel_id)

    def get_visible_panels(self) -> list[PanelState]:
        return [p for p in self._panels.values() if p.visible]

    def get_panels_in_dock(self, dock_area: DockArea) -> list[PanelState]:
        panels = [p for p in self._panels.values()
                  if p.dock_area == dock_area and p.visible]
        return sorted(panels, key=lambda p: p.tab_index)

    # ─── Layout Management ───────────────────────────────────────────────

    def save_layout(self, name: str) -> WorkspaceLayout:
        layout = WorkspaceLayout(
            name=name,
            panels=[PanelState(
                id=p.id, name=p.name, dock_area=p.dock_area,
                visible=p.visible, collapsed=p.collapsed,
                width=p.width, height=p.height, tab_index=p.tab_index,
                floating_x=p.floating_x, floating_y=p.floating_y,
            ) for p in self._panels.values()],
            display_mode=self._display_mode,
        )
        self._layouts[layout.id] = layout
        return layout

    def load_layout(self, layout_id: str) -> bool:
        layout = self._layouts.get(layout_id)
        if not layout:
            return False
        self._apply_layout(layout)
        self._active_layout_id = layout_id
        return True

    def load_layout_by_name(self, name: str) -> bool:
        for layout in self._layouts.values():
            if layout.name == name:
                return self.load_layout(layout.id)
        return False

    def delete_layout(self, layout_id: str) -> bool:
        layout = self._layouts.get(layout_id)
        if layout and not layout.is_builtin:
            self._layouts.pop(layout_id)
            return True
        return False

    def get_all_layouts(self) -> list[WorkspaceLayout]:
        return list(self._layouts.values())

    def get_active_layout(self) -> Optional[WorkspaceLayout]:
        return self._layouts.get(self._active_layout_id) if self._active_layout_id else None

    def reset_to_default(self):
        for layout in self._layouts.values():
            if layout.name == "Default" and layout.is_builtin:
                self.load_layout(layout.id)
                return

    def _apply_layout(self, layout: WorkspaceLayout):
        self._panels.clear()
        for ps in layout.panels:
            self._panels[ps.id] = PanelState(
                id=ps.id, name=ps.name, dock_area=ps.dock_area,
                visible=ps.visible, collapsed=ps.collapsed,
                width=ps.width, height=ps.height, tab_index=ps.tab_index,
                floating_x=ps.floating_x, floating_y=ps.floating_y,
            )
        self._display_mode = layout.display_mode

    # ─── Display Mode ────────────────────────────────────────────────────

    @property
    def display_mode(self) -> DisplayMode:
        return self._display_mode

    def set_display_mode(self, mode: DisplayMode):
        self._display_mode = mode

    def toggle_fullscreen(self):
        if self._display_mode == DisplayMode.FULLSCREEN:
            self._display_mode = DisplayMode.NORMAL
        else:
            self._display_mode = DisplayMode.FULLSCREEN

    def toggle_zen(self):
        if self._display_mode == DisplayMode.ZEN:
            self._display_mode = DisplayMode.NORMAL
        else:
            self._display_mode = DisplayMode.ZEN

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def panel_count(self) -> int:
        return len(self._panels)

    @property
    def layout_count(self) -> int:
        return len(self._layouts)
