"""History Engine — independent Undo/Redo system with command pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from PySide6.QtCore import QObject, Signal, QPointF
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QTransform


# --- Base Command ---

class Command(ABC):
    """Abstract command for undo/redo."""

    description: str = ""

    @abstractmethod
    def redo(self):
        pass

    @abstractmethod
    def undo(self):
        pass

    def merge_with(self, other: Command) -> bool:
        """Try to merge with another command. Returns True if merged."""
        return False


# --- Concrete Commands ---

class MoveItemsCommand(Command):
    """Move items by delta."""

    def __init__(self, items: list[QGraphicsItem], dx: float, dy: float):
        self.items = items
        self.dx = dx
        self.dy = dy
        self.description = f"Mover {len(items)} item(s)"

    def redo(self):
        for item in self.items:
            item.moveBy(self.dx, self.dy)

    def undo(self):
        for item in self.items:
            item.moveBy(-self.dx, -self.dy)

    def merge_with(self, other: Command) -> bool:
        if isinstance(other, MoveItemsCommand) and set(other.items) == set(self.items):
            self.dx += other.dx
            self.dy += other.dy
            return True
        return False


class TransformItemCommand(Command):
    """Store before/after transform state."""

    def __init__(self, item: QGraphicsItem, old_pos: QPointF, new_pos: QPointF,
                 old_transform: QTransform, new_transform: QTransform,
                 old_rotation: float, new_rotation: float):
        self.item = item
        self.old_pos = old_pos
        self.new_pos = new_pos
        self.old_transform = old_transform
        self.new_transform = new_transform
        self.old_rotation = old_rotation
        self.new_rotation = new_rotation
        self.description = "Transformar item"

    def redo(self):
        self.item.setPos(self.new_pos)
        self.item.setTransform(self.new_transform)
        self.item.setRotation(self.new_rotation)

    def undo(self):
        self.item.setPos(self.old_pos)
        self.item.setTransform(self.old_transform)
        self.item.setRotation(self.old_rotation)


class CreateItemCommand(Command):
    """Add an item to the scene."""

    def __init__(self, scene, item: QGraphicsItem):
        self.scene = scene
        self.item = item
        self.description = "Criar item"

    def redo(self):
        self.scene.addItem(self.item)

    def undo(self):
        self.scene.removeItem(self.item)


class DeleteItemCommand(Command):
    """Remove an item from the scene."""

    def __init__(self, scene, item: QGraphicsItem):
        self.scene = scene
        self.item = item
        self.description = "Deletar item"

    def redo(self):
        self.scene.removeItem(self.item)

    def undo(self):
        self.scene.addItem(self.item)


class PaintStrokeCommand(Command):
    """Undo/redo a single terrain paint stroke via whole-layer snapshots."""

    def __init__(self, layer, before_state: dict, after_state: dict):
        self.layer = layer
        self.before_state = before_state
        self.after_state = after_state
        self.description = "Pintura de terreno"

    def redo(self):
        self.layer.restore_state(self.after_state)

    def undo(self):
        self.layer.restore_state(self.before_state)


class PlaceObjectCommand(Command):
    """Undo/redo placing a single brush-stamped object via visibility toggle.

    Stamped items may be parented to a boundary item rather than added
    directly to the scene, so toggling visibility is used instead of
    add/removeItem (which assumes a scene-level item).
    """

    def __init__(self, item: QGraphicsItem):
        self.item = item
        self.description = "Colocar objeto"

    def redo(self):
        self.item.setVisible(True)

    def undo(self):
        self.item.setVisible(False)


class ChangePropertyCommand(Command):
    """Change a property on an item's data dict."""

    def __init__(self, item: QGraphicsItem, key: str, old_value: Any, new_value: Any):
        self.item = item
        self.key = key
        self.old_value = old_value
        self.new_value = new_value
        self.description = f"Alterar {key}"

    def redo(self):
        data = self.item.data(0) or {}
        data[self.key] = self.new_value
        self.item.setData(0, data)

    def undo(self):
        data = self.item.data(0) or {}
        data[self.key] = self.old_value
        self.item.setData(0, data)


class ChangeLayerCommand(Command):
    """Move item between layers."""

    def __init__(self, item: QGraphicsItem, old_layer_id: str, new_layer_id: str):
        self.item = item
        self.old_layer_id = old_layer_id
        self.new_layer_id = new_layer_id
        self.description = "Mudar camada"

    def redo(self):
        data = self.item.data(0) or {}
        data["layer_id"] = self.new_layer_id
        self.item.setData(0, data)

    def undo(self):
        data = self.item.data(0) or {}
        data["layer_id"] = self.old_layer_id
        self.item.setData(0, data)


class CompositeCommand(Command):
    """Groups multiple commands into a single undo/redo step."""

    def __init__(self, commands: list[Command], description: str = ""):
        self.commands = commands
        self.description = description or f"Grupo ({len(commands)} ações)"

    def redo(self):
        for cmd in self.commands:
            cmd.redo()

    def undo(self):
        for cmd in reversed(self.commands):
            cmd.undo()


# --- History Engine ---

class HistoryEngine(QObject):
    """Manages the undo/redo stack."""

    history_changed = Signal()  # emitted on push/undo/redo
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)

    DEFAULT_LIMIT = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._limit = self.DEFAULT_LIMIT
        self._group: list[Command] | None = None  # for grouping

    # --- Properties ---

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_description(self) -> str:
        if self._undo_stack:
            return self._undo_stack[-1].description
        return ""

    @property
    def redo_description(self) -> str:
        if self._redo_stack:
            return self._redo_stack[-1].description
        return ""

    @property
    def history(self) -> list[str]:
        """Return descriptions of all commands in undo stack."""
        return [cmd.description for cmd in self._undo_stack]

    @property
    def limit(self) -> int:
        return self._limit

    @limit.setter
    def limit(self, value: int):
        self._limit = max(10, value)
        self._trim()

    # --- Core Operations ---

    def push(self, command: Command):
        """Execute a command and push to undo stack."""
        if self._group is not None:
            # Collecting commands for a group
            command.redo()
            self._group.append(command)
            return

        # Try to merge with last command
        if self._undo_stack and self._undo_stack[-1].merge_with(command):
            self._emit()
            return

        command.redo()
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._trim()
        self._emit()

    def undo(self):
        """Undo the last command."""
        if not self._undo_stack:
            return
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._emit()

    def redo(self):
        """Redo the last undone command."""
        if not self._redo_stack:
            return
        cmd = self._redo_stack.pop()
        cmd.redo()
        self._undo_stack.append(cmd)
        self._emit()

    def clear(self):
        """Clear all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._emit()

    # --- Grouping ---

    def begin_group(self, description: str = ""):
        """Start collecting commands into a single composite command."""
        self._group = []
        self._group_description = description

    def end_group(self):
        """Finish group and push as a single composite command."""
        if self._group is None:
            return

        commands = self._group
        description = self._group_description
        self._group = None

        if commands:
            composite = CompositeCommand(commands, description)
            self._undo_stack.append(composite)
            self._redo_stack.clear()
            self._trim()
            self._emit()

    def cancel_group(self):
        """Cancel group and undo all commands in it."""
        if self._group is None:
            return

        for cmd in reversed(self._group):
            cmd.undo()
        self._group = None

    # --- Helpers ---

    def _trim(self):
        while len(self._undo_stack) > self._limit:
            self._undo_stack.pop(0)

    def _emit(self):
        self.can_undo_changed.emit(self.can_undo)
        self.can_redo_changed.emit(self.can_redo)
        self.history_changed.emit()
