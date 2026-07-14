"""Input Manager — keyboard/mouse mapping and dispatch."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from src.canvas.tools.base import ToolManager


class InputManager:
    """Maps key events to tool shortcuts and global actions."""

    def __init__(self, tool_manager: ToolManager):
        self._tool_manager = tool_manager
        self._global_shortcuts: dict[str, callable] = {}

    def register_global(self, key: str, callback: callable):
        self._global_shortcuts[key] = callback

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Returns True if the event was consumed."""
        key_text = event.text().upper()

        # Try global shortcuts first
        if key_text in self._global_shortcuts:
            self._global_shortcuts[key_text]()
            return True

        # Try tool shortcuts
        if self._tool_manager.handle_shortcut(key_text):
            return True

        # Forward to active tool
        self._tool_manager.key_press(event)
        return False

    def handle_key_release(self, event: QKeyEvent):
        self._tool_manager.key_release(event)
