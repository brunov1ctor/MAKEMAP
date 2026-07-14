"""Tool system — base tool class and tool manager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, Signal, QObject
from PySide6.QtGui import QMouseEvent, QKeyEvent, QCursor

if TYPE_CHECKING:
    from src.canvas.viewport import Viewport


class BaseTool(ABC):
    """Abstract base for all canvas tools."""

    name: str = "Tool"
    icon: str = ""
    shortcut: str = ""
    cursor: Qt.CursorShape = Qt.CursorShape.ArrowCursor

    def __init__(self, viewport: Viewport):
        self.viewport = viewport
        self.active = False

    def activate(self):
        self.active = True
        self.viewport.setCursor(self.cursor)

    def deactivate(self):
        self.active = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        pass

    def key_press(self, event: QKeyEvent):
        pass

    def key_release(self, event: QKeyEvent):
        pass


class ToolManager(QObject):
    """Registers and manages canvas tools."""

    tool_changed = Signal(str)  # emits tool name

    def __init__(self, viewport: Viewport, parent=None):
        super().__init__(parent)
        self._viewport = viewport
        self._tools: dict[str, BaseTool] = {}
        self._active: BaseTool | None = None
        self._shortcuts: dict[str, str] = {}  # key -> tool_name

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        if tool.shortcut:
            self._shortcuts[tool.shortcut] = tool.name

    def activate(self, name: str):
        if self._active:
            self._active.deactivate()

        tool = self._tools.get(name)
        if tool:
            tool.activate()
            self._active = tool
            self.tool_changed.emit(name)

    @property
    def active_tool(self) -> BaseTool | None:
        return self._active

    @property
    def active_name(self) -> str:
        return self._active.name if self._active else ""

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def handle_shortcut(self, key: str) -> bool:
        """Try to activate a tool by shortcut key. Returns True if handled."""
        name = self._shortcuts.get(key)
        if name:
            self.activate(name)
            return True
        return False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if self._active:
            self._active.mouse_press(event, scene_pos)

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._active:
            self._active.mouse_move(event, scene_pos)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        if self._active:
            self._active.mouse_release(event, scene_pos)

    def key_press(self, event: QKeyEvent):
        if self._active:
            self._active.key_press(event)

    def key_release(self, event: QKeyEvent):
        if self._active:
            self._active.key_release(event)
