"""FASE 28 — Polimento (Onboarding, Tooltips, Shortcuts, Stress Test)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────────────────

class TutorialStep(Enum):
    WELCOME = auto()
    CREATE_PROJECT = auto()
    NAVIGATE_CANVAS = auto()
    PLACE_ASSET = auto()
    USE_BRUSH = auto()
    ADD_ENTITY = auto()
    SAVE_EXPORT = auto()
    COMPLETE = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class Tooltip:
    widget_id: str = ""
    text: str = ""
    shortcut: str = ""
    position: str = "bottom"  # top, bottom, left, right


@dataclass
class Shortcut:
    key: str = ""
    action: str = ""
    context: str = "global"  # global, canvas, explorer, inspector
    description: str = ""


@dataclass
class OnboardingState:
    current_step: TutorialStep = TutorialStep.WELCOME
    completed_steps: list[TutorialStep] = field(default_factory=list)
    skipped: bool = False
    first_run: bool = True


@dataclass
class StressTestResult:
    name: str = ""
    items_created: int = 0
    time_ms: float = 0.0
    fps_avg: float = 0.0
    memory_mb: float = 0.0
    passed: bool = True
    notes: str = ""


# ─── Polishing Engine ────────────────────────────────────────────────────────

class PolishEngine:
    def __init__(self):
        self._onboarding = OnboardingState()
        self._tooltips: dict[str, Tooltip] = {}
        self._shortcuts: list[Shortcut] = []
        self._stress_results: list[StressTestResult] = []
        self._init_shortcuts()
        self._init_tooltips()

    # ─── Onboarding ──────────────────────────────────────────────────────

    @property
    def onboarding(self) -> OnboardingState:
        return self._onboarding

    def start_tutorial(self):
        self._onboarding.current_step = TutorialStep.WELCOME
        self._onboarding.completed_steps.clear()
        self._onboarding.skipped = False

    def advance_step(self) -> TutorialStep:
        steps = list(TutorialStep)
        idx = steps.index(self._onboarding.current_step)
        if self._onboarding.current_step not in self._onboarding.completed_steps:
            self._onboarding.completed_steps.append(self._onboarding.current_step)
        if idx < len(steps) - 1:
            self._onboarding.current_step = steps[idx + 1]
        return self._onboarding.current_step

    def skip_tutorial(self):
        self._onboarding.skipped = True
        self._onboarding.current_step = TutorialStep.COMPLETE
        self._onboarding.first_run = False

    @property
    def tutorial_complete(self) -> bool:
        return self._onboarding.current_step == TutorialStep.COMPLETE

    @property
    def tutorial_progress(self) -> float:
        total = len(TutorialStep) - 1  # exclude COMPLETE
        done = len(self._onboarding.completed_steps)
        return min(1.0, done / total) if total > 0 else 1.0

    # ─── Tooltips ────────────────────────────────────────────────────────

    def get_tooltip(self, widget_id: str) -> Optional[Tooltip]:
        return self._tooltips.get(widget_id)

    def set_tooltip(self, widget_id: str, text: str, shortcut: str = "", position: str = "bottom"):
        self._tooltips[widget_id] = Tooltip(
            widget_id=widget_id, text=text, shortcut=shortcut, position=position)

    def _init_tooltips(self):
        tips = [
            ("btn_select", "Select Tool", "V"),
            ("btn_move", "Move Tool", "M"),
            ("btn_brush", "Brush Tool", "B"),
            ("btn_eraser", "Eraser", "E"),
            ("btn_text", "Text Tool", "T"),
            ("btn_polygon", "Polygon Tool", "P"),
            ("btn_road", "Road Tool", "R"),
            ("btn_river", "River Tool", "W"),
            ("btn_entity", "Place Entity", "N"),
            ("btn_zoom_in", "Zoom In", "Ctrl++"),
            ("btn_zoom_out", "Zoom Out", "Ctrl+-"),
            ("btn_fit", "Fit to View", "Ctrl+0"),
            ("btn_undo", "Undo", "Ctrl+Z"),
            ("btn_redo", "Redo", "Ctrl+Y"),
            ("btn_save", "Save Project", "Ctrl+S"),
            ("btn_export", "Export Map", "Ctrl+E"),
        ]
        for wid, text, shortcut in tips:
            self._tooltips[wid] = Tooltip(widget_id=wid, text=text, shortcut=shortcut)

    # ─── Shortcuts ───────────────────────────────────────────────────────

    @property
    def shortcuts(self) -> list[Shortcut]:
        return self._shortcuts

    def get_shortcuts_by_context(self, context: str) -> list[Shortcut]:
        return [s for s in self._shortcuts if s.context == context]

    def add_shortcut(self, key: str, action: str, context: str = "global", description: str = ""):
        self._shortcuts.append(Shortcut(key=key, action=action, context=context, description=description))

    def get_shortcut_for(self, action: str) -> Optional[Shortcut]:
        return next((s for s in self._shortcuts if s.action == action), None)

    def _init_shortcuts(self):
        shortcuts = [
            ("Ctrl+N", "new_project", "global", "Create new project"),
            ("Ctrl+O", "open_project", "global", "Open project"),
            ("Ctrl+S", "save", "global", "Save project"),
            ("Ctrl+Shift+S", "save_as", "global", "Save as"),
            ("Ctrl+Z", "undo", "global", "Undo"),
            ("Ctrl+Y", "redo", "global", "Redo"),
            ("Ctrl+C", "copy", "canvas", "Copy selection"),
            ("Ctrl+X", "cut", "canvas", "Cut selection"),
            ("Ctrl+V", "paste", "canvas", "Paste"),
            ("Ctrl+D", "duplicate", "canvas", "Duplicate selection"),
            ("Delete", "delete", "canvas", "Delete selection"),
            ("Ctrl+A", "select_all", "canvas", "Select all"),
            ("Escape", "deselect", "canvas", "Deselect all"),
            ("V", "tool_select", "canvas", "Select tool"),
            ("M", "tool_move", "canvas", "Move tool"),
            ("B", "tool_brush", "canvas", "Brush tool"),
            ("E", "tool_eraser", "canvas", "Eraser tool"),
            ("T", "tool_text", "canvas", "Text tool"),
            ("P", "tool_polygon", "canvas", "Polygon tool"),
            ("R", "tool_road", "canvas", "Road tool"),
            ("W", "tool_river", "canvas", "River tool"),
            ("N", "tool_entity", "canvas", "Entity tool"),
            ("Space", "pan", "canvas", "Pan canvas (hold)"),
            ("Ctrl++", "zoom_in", "canvas", "Zoom in"),
            ("Ctrl+-", "zoom_out", "canvas", "Zoom out"),
            ("Ctrl+0", "fit_view", "canvas", "Fit to view"),
            ("F11", "fullscreen", "global", "Toggle fullscreen"),
            ("Ctrl+E", "export", "global", "Export map"),
            ("Ctrl+K", "search", "global", "Quick search"),
            ("Tab", "cycle_mode", "global", "Cycle view mode"),
            ("F1", "help", "global", "Show shortcuts"),
        ]
        for key, action, ctx, desc in shortcuts:
            self._shortcuts.append(Shortcut(key=key, action=action, context=ctx, description=desc))

    # ─── Stress Test ─────────────────────────────────────────────────────

    def run_stress_test(self, name: str, item_count: int,
                        test_fn=None) -> StressTestResult:
        """Run a stress test. test_fn(item_count) -> (time_ms, fps, memory_mb)."""
        import time
        result = StressTestResult(name=name, items_created=item_count)
        if test_fn:
            start = time.perf_counter()
            try:
                time_ms, fps, mem = test_fn(item_count)
                result.time_ms = time_ms
                result.fps_avg = fps
                result.memory_mb = mem
                result.passed = fps >= 30
            except Exception as ex:
                result.passed = False
                result.notes = str(ex)
                result.time_ms = (time.perf_counter() - start) * 1000
        else:
            # Simulate
            result.time_ms = item_count * 0.01
            result.fps_avg = max(10, 60 - item_count / 1000)
            result.memory_mb = item_count * 0.05
            result.passed = result.fps_avg >= 30
        self._stress_results.append(result)
        return result

    def get_stress_results(self) -> list[StressTestResult]:
        return list(self._stress_results)

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def tooltip_count(self) -> int:
        return len(self._tooltips)

    @property
    def shortcut_count(self) -> int:
        return len(self._shortcuts)
