"""Layer Engine — Photoshop-style layer management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QObject, Signal


class BlendMode(Enum):
    NORMAL = auto()
    MULTIPLY = auto()
    SCREEN = auto()
    OVERLAY = auto()
    DARKEN = auto()
    LIGHTEN = auto()
    COLOR_DODGE = auto()
    COLOR_BURN = auto()
    HARD_LIGHT = auto()
    SOFT_LIGHT = auto()
    DIFFERENCE = auto()
    EXCLUSION = auto()


@dataclass
class LayerNode:
    """A single layer or folder in the layer tree."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Layer"
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    color_tag: str = ""  # visual tag color
    is_folder: bool = False
    parent_id: str | None = None
    order: int = 0
    clip: bool = False  # clip to layer below
    mask_enabled: bool = False


class LayerEngine(QObject):
    """Manages the full layer stack with folders, blend modes, and operations."""

    layer_added = Signal(str)  # layer_id
    layer_removed = Signal(str)
    layer_changed = Signal(str)  # layer_id (property changed)
    layer_reordered = Signal()
    active_layer_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layers: dict[str, LayerNode] = {}
        self._order: list[str] = []  # bottom to top
        self._active_id: str = ""

    # --- Properties ---

    @property
    def active_layer(self) -> LayerNode | None:
        return self._layers.get(self._active_id)

    @property
    def active_id(self) -> str:
        return self._active_id

    @property
    def count(self) -> int:
        return len(self._layers)

    # --- Create ---

    def create_layer(self, name: str = "Layer", parent_id: str | None = None,
                     above: str | None = None) -> LayerNode:
        """Create a new layer."""
        node = LayerNode(name=name, parent_id=parent_id)

        self._layers[node.id] = node

        if above and above in self._order:
            idx = self._order.index(above) + 1
            self._order.insert(idx, node.id)
        else:
            self._order.append(node.id)

        self._reindex()
        self.layer_added.emit(node.id)

        if not self._active_id:
            self.set_active(node.id)

        return node

    def create_folder(self, name: str = "Folder", parent_id: str | None = None) -> LayerNode:
        """Create a layer folder/group."""
        node = LayerNode(name=name, is_folder=True, parent_id=parent_id)
        self._layers[node.id] = node
        self._order.append(node.id)
        self._reindex()
        self.layer_added.emit(node.id)
        return node

    # --- Remove ---

    def remove_layer(self, layer_id: str):
        """Remove a layer and its children (if folder)."""
        if layer_id not in self._layers:
            return

        # Collect children
        to_remove = self._collect_children(layer_id)
        to_remove.append(layer_id)

        for lid in to_remove:
            self._layers.pop(lid, None)
            if lid in self._order:
                self._order.remove(lid)

        self._reindex()

        # Update active
        if self._active_id in to_remove:
            self._active_id = self._order[-1] if self._order else ""
            self.active_layer_changed.emit(self._active_id)

        self.layer_removed.emit(layer_id)

    # --- Duplicate ---

    def duplicate_layer(self, layer_id: str) -> LayerNode | None:
        """Duplicate a layer."""
        source = self._layers.get(layer_id)
        if not source:
            return None

        node = LayerNode(
            name=f"{source.name} (cópia)",
            visible=source.visible,
            locked=source.locked,
            opacity=source.opacity,
            blend_mode=source.blend_mode,
            color_tag=source.color_tag,
            is_folder=False,
            parent_id=source.parent_id,
            clip=source.clip,
        )

        self._layers[node.id] = node
        idx = self._order.index(layer_id) + 1 if layer_id in self._order else len(self._order)
        self._order.insert(idx, node.id)
        self._reindex()
        self.layer_added.emit(node.id)
        return node

    # --- Reorder ---

    def move_layer(self, layer_id: str, target_index: int):
        """Move a layer to a specific position in the stack."""
        if layer_id not in self._order:
            return
        self._order.remove(layer_id)
        target_index = max(0, min(target_index, len(self._order)))
        self._order.insert(target_index, layer_id)
        self._reindex()
        self.layer_reordered.emit()

    def bring_to_front(self, layer_id: str):
        """Move layer to top of stack."""
        self.move_layer(layer_id, len(self._order))

    def send_to_back(self, layer_id: str):
        """Move layer to bottom of stack."""
        self.move_layer(layer_id, 0)

    def bring_forward(self, layer_id: str):
        """Move layer one position up."""
        if layer_id not in self._order:
            return
        idx = self._order.index(layer_id)
        if idx < len(self._order) - 1:
            self.move_layer(layer_id, idx + 1)

    def send_backward(self, layer_id: str):
        """Move layer one position down."""
        if layer_id not in self._order:
            return
        idx = self._order.index(layer_id)
        if idx > 0:
            self.move_layer(layer_id, idx - 1)

    # --- Properties ---

    def set_active(self, layer_id: str):
        if layer_id in self._layers:
            self._active_id = layer_id
            self.active_layer_changed.emit(layer_id)

    def set_visible(self, layer_id: str, visible: bool):
        node = self._layers.get(layer_id)
        if node:
            node.visible = visible
            self.layer_changed.emit(layer_id)

    def set_locked(self, layer_id: str, locked: bool):
        node = self._layers.get(layer_id)
        if node:
            node.locked = locked
            self.layer_changed.emit(layer_id)

    def set_opacity(self, layer_id: str, opacity: float):
        node = self._layers.get(layer_id)
        if node:
            node.opacity = max(0.0, min(1.0, opacity))
            self.layer_changed.emit(layer_id)

    def set_blend_mode(self, layer_id: str, mode: BlendMode):
        node = self._layers.get(layer_id)
        if node:
            node.blend_mode = mode
            self.layer_changed.emit(layer_id)

    def set_name(self, layer_id: str, name: str):
        node = self._layers.get(layer_id)
        if node:
            node.name = name
            self.layer_changed.emit(layer_id)

    def set_color_tag(self, layer_id: str, color: str):
        node = self._layers.get(layer_id)
        if node:
            node.color_tag = color
            self.layer_changed.emit(layer_id)

    def set_clip(self, layer_id: str, clip: bool):
        node = self._layers.get(layer_id)
        if node:
            node.clip = clip
            self.layer_changed.emit(layer_id)

    def toggle_visible(self, layer_id: str):
        node = self._layers.get(layer_id)
        if node:
            node.visible = not node.visible
            self.layer_changed.emit(layer_id)

    def toggle_locked(self, layer_id: str):
        node = self._layers.get(layer_id)
        if node:
            node.locked = not node.locked
            self.layer_changed.emit(layer_id)

    # --- Group/Ungroup ---

    def group_layers(self, layer_ids: list[str], folder_name: str = "Grupo") -> LayerNode:
        """Group layers into a new folder."""
        folder = self.create_folder(folder_name)

        for lid in layer_ids:
            node = self._layers.get(lid)
            if node:
                node.parent_id = folder.id

        self.layer_reordered.emit()
        return folder

    def ungroup(self, folder_id: str):
        """Ungroup: move children out and remove folder."""
        children = self._collect_children(folder_id)
        for cid in children:
            node = self._layers.get(cid)
            if node:
                node.parent_id = self._layers[folder_id].parent_id

        self.remove_layer(folder_id)

    # --- Merge ---

    def merge_down(self, layer_id: str):
        """Merge layer with the one below it."""
        if layer_id not in self._order:
            return
        idx = self._order.index(layer_id)
        if idx == 0:
            return  # nothing below

        below_id = self._order[idx - 1]
        below = self._layers.get(below_id)
        if not below or below.is_folder:
            return

        # Merge: keep below, remove current
        # (actual pixel merge would happen in rendering)
        below.name = f"{below.name} + {self._layers[layer_id].name}"
        self.remove_layer(layer_id)

    def flatten(self):
        """Flatten all layers into one."""
        if len(self._order) <= 1:
            return

        first_id = self._order[0]
        first = self._layers[first_id]
        first.name = "Flattened"
        first.opacity = 1.0
        first.blend_mode = BlendMode.NORMAL

        # Remove all others
        for lid in list(self._order[1:]):
            self._layers.pop(lid, None)
            self._order.remove(lid)

        self._reindex()
        self.set_active(first_id)
        self.layer_reordered.emit()

    # --- Query ---

    def get_layer(self, layer_id: str) -> LayerNode | None:
        return self._layers.get(layer_id)

    def get_all_ordered(self) -> list[LayerNode]:
        """Get all layers in render order (bottom to top)."""
        return [self._layers[lid] for lid in self._order if lid in self._layers]

    def get_visible(self) -> list[LayerNode]:
        """Get only visible layers in order."""
        return [self._layers[lid] for lid in self._order
                if lid in self._layers and self._layers[lid].visible]

    def get_children(self, folder_id: str) -> list[LayerNode]:
        """Get direct children of a folder."""
        return [n for n in self._layers.values() if n.parent_id == folder_id]

    def get_tree(self) -> list[dict]:
        """Get hierarchical tree representation for UI."""
        roots = [n for n in self.get_all_ordered() if n.parent_id is None]
        return [self._node_to_tree(n) for n in reversed(roots)]

    # --- Helpers ---

    def _collect_children(self, folder_id: str) -> list[str]:
        """Recursively collect all children IDs."""
        children = []
        for lid, node in self._layers.items():
            if node.parent_id == folder_id:
                children.append(lid)
                if node.is_folder:
                    children.extend(self._collect_children(lid))
        return children

    def _reindex(self):
        """Update order field on all nodes."""
        for i, lid in enumerate(self._order):
            if lid in self._layers:
                self._layers[lid].order = i

    def _node_to_tree(self, node: LayerNode) -> dict:
        result = {
            "id": node.id,
            "name": node.name,
            "visible": node.visible,
            "locked": node.locked,
            "opacity": node.opacity,
            "blend_mode": node.blend_mode.name,
            "is_folder": node.is_folder,
            "color_tag": node.color_tag,
        }
        if node.is_folder:
            children = self.get_children(node.id)
            result["children"] = [self._node_to_tree(c) for c in children]
        return result
