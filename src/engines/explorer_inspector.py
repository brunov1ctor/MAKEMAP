"""FASE 26 — Explorer & Inspector Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any


# ─── Enums ───────────────────────────────────────────────────────────────────

class NodeType(Enum):
    WORLD = auto()
    CONTINENT = auto()
    KINGDOM = auto()
    REGION = auto()
    CITY = auto()
    DUNGEON = auto()
    MAP = auto()
    LAYER = auto()
    GROUP = auto()
    ITEM = auto()
    ENTITY = auto()


class PropertyType(Enum):
    STRING = auto()
    INT = auto()
    FLOAT = auto()
    BOOL = auto()
    COLOR = auto()
    ENUM = auto()
    POINT = auto()
    RECT = auto()
    LIST = auto()
    REFERENCE = auto()


# ─── Explorer ────────────────────────────────────────────────────────────────

@dataclass
class TreeNode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    node_type: NodeType = NodeType.ITEM
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    icon: str = ""
    expanded: bool = False
    visible: bool = True
    locked: bool = False
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class ExplorerEngine:
    def __init__(self):
        self._nodes: dict[str, TreeNode] = {}
        self._root_ids: list[str] = []
        self._selection: list[str] = []
        self._filter_type: Optional[NodeType] = None
        self._search_query: str = ""

    # ─── Node CRUD ───────────────────────────────────────────────────────

    def add_node(self, node: TreeNode) -> TreeNode:
        self._nodes[node.id] = node
        if node.parent_id:
            parent = self._nodes.get(node.parent_id)
            if parent and node.id not in parent.children_ids:
                parent.children_ids.append(node.id)
        else:
            if node.id not in self._root_ids:
                self._root_ids.append(node.id)
        return node

    def remove_node(self, node_id: str) -> Optional[TreeNode]:
        node = self._nodes.get(node_id)
        if not node:
            return None
        # Remove children recursively
        for child_id in list(node.children_ids):
            self.remove_node(child_id)
        # Remove from parent
        if node.parent_id:
            parent = self._nodes.get(node.parent_id)
            if parent and node_id in parent.children_ids:
                parent.children_ids.remove(node_id)
        else:
            if node_id in self._root_ids:
                self._root_ids.remove(node_id)
        if node_id in self._selection:
            self._selection.remove(node_id)
        return self._nodes.pop(node_id, None)

    def rename_node(self, node_id: str, name: str):
        node = self._nodes.get(node_id)
        if node:
            node.name = name

    def move_node(self, node_id: str, new_parent_id: Optional[str], index: int = -1):
        node = self._nodes.get(node_id)
        if not node:
            return
        # Remove from old parent
        if node.parent_id:
            old_parent = self._nodes.get(node.parent_id)
            if old_parent and node_id in old_parent.children_ids:
                old_parent.children_ids.remove(node_id)
        elif node_id in self._root_ids:
            self._root_ids.remove(node_id)
        # Add to new parent
        node.parent_id = new_parent_id
        if new_parent_id:
            new_parent = self._nodes.get(new_parent_id)
            if new_parent:
                if index < 0:
                    new_parent.children_ids.append(node_id)
                else:
                    new_parent.children_ids.insert(index, node_id)
        else:
            if index < 0:
                self._root_ids.append(node_id)
            else:
                self._root_ids.insert(index, node_id)

    def duplicate_node(self, node_id: str) -> Optional[TreeNode]:
        node = self._nodes.get(node_id)
        if not node:
            return None
        new_node = TreeNode(
            name=f"{node.name} (copy)", node_type=node.node_type,
            parent_id=node.parent_id, icon=node.icon, tags=list(node.tags),
        )
        return self.add_node(new_node)

    def get_node(self, node_id: str) -> Optional[TreeNode]:
        return self._nodes.get(node_id)

    def get_children(self, node_id: str) -> list[TreeNode]:
        node = self._nodes.get(node_id)
        if not node:
            return []
        return [self._nodes[cid] for cid in node.children_ids if cid in self._nodes]

    def get_roots(self) -> list[TreeNode]:
        return [self._nodes[rid] for rid in self._root_ids if rid in self._nodes]

    # ─── Selection ───────────────────────────────────────────────────────

    def select(self, node_id: str, multi: bool = False):
        if not multi:
            self._selection.clear()
        if node_id in self._nodes and node_id not in self._selection:
            self._selection.append(node_id)

    def deselect(self, node_id: str):
        if node_id in self._selection:
            self._selection.remove(node_id)

    def clear_selection(self):
        self._selection.clear()

    @property
    def selection(self) -> list[str]:
        return list(self._selection)

    @property
    def selected_nodes(self) -> list[TreeNode]:
        return [self._nodes[nid] for nid in self._selection if nid in self._nodes]

    # ─── Filter & Search ─────────────────────────────────────────────────

    def set_filter(self, node_type: Optional[NodeType]):
        self._filter_type = node_type

    def search(self, query: str):
        self._search_query = query.lower()

    def get_filtered_nodes(self) -> list[TreeNode]:
        nodes = list(self._nodes.values())
        if self._filter_type:
            nodes = [n for n in nodes if n.node_type == self._filter_type]
        if self._search_query:
            nodes = [n for n in nodes if self._search_query in n.name.lower()
                     or any(self._search_query in t.lower() for t in n.tags)]
        return nodes

    # ─── Expand/Collapse ─────────────────────────────────────────────────

    def toggle_expand(self, node_id: str):
        node = self._nodes.get(node_id)
        if node:
            node.expanded = not node.expanded

    def expand_all(self):
        for node in self._nodes.values():
            node.expanded = True

    def collapse_all(self):
        for node in self._nodes.values():
            node.expanded = False

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return len(self._nodes)


# ─── Inspector ───────────────────────────────────────────────────────────────

@dataclass
class PropertyDef:
    key: str = ""
    label: str = ""
    prop_type: PropertyType = PropertyType.STRING
    value: Any = None
    default: Any = None
    editable: bool = True
    section: str = "General"
    options: list[str] = field(default_factory=list)  # for ENUM type
    min_val: Optional[float] = None
    max_val: Optional[float] = None


@dataclass
class InspectorSection:
    name: str = ""
    collapsed: bool = False
    properties: list[PropertyDef] = field(default_factory=list)


class InspectorEngine:
    def __init__(self):
        self._sections: list[InspectorSection] = []
        self._target_id: Optional[str] = None
        self._change_callbacks: list = []

    # ─── Target ──────────────────────────────────────────────────────────

    def inspect(self, target_id: str, properties: list[PropertyDef]):
        """Set current inspection target and its properties."""
        self._target_id = target_id
        self._sections.clear()
        # Group by section
        sections_map: dict[str, list[PropertyDef]] = {}
        for prop in properties:
            sections_map.setdefault(prop.section, []).append(prop)
        for name, props in sections_map.items():
            self._sections.append(InspectorSection(name=name, properties=props))

    def clear(self):
        self._target_id = None
        self._sections.clear()

    @property
    def target_id(self) -> Optional[str]:
        return self._target_id

    @property
    def sections(self) -> list[InspectorSection]:
        return self._sections

    # ─── Property Access ─────────────────────────────────────────────────

    def get_property(self, key: str) -> Optional[PropertyDef]:
        for section in self._sections:
            for prop in section.properties:
                if prop.key == key:
                    return prop
        return None

    def set_property(self, key: str, value: Any) -> bool:
        prop = self.get_property(key)
        if not prop or not prop.editable:
            return False
        prop.value = value
        for cb in self._change_callbacks:
            cb(self._target_id, key, value)
        return True

    def get_all_values(self) -> dict[str, Any]:
        result = {}
        for section in self._sections:
            for prop in section.properties:
                result[prop.key] = prop.value
        return result

    # ─── Sections ────────────────────────────────────────────────────────

    def toggle_section(self, name: str):
        for section in self._sections:
            if section.name == name:
                section.collapsed = not section.collapsed
                return

    def collapse_all(self):
        for section in self._sections:
            section.collapsed = True

    def expand_all(self):
        for section in self._sections:
            section.collapsed = False

    # ─── Callbacks ───────────────────────────────────────────────────────

    def on_change(self, callback):
        """Register callback(target_id, key, value) for property changes."""
        self._change_callbacks.append(callback)

    # ─── Presets ─────────────────────────────────────────────────────────

    @staticmethod
    def properties_for_item(item: dict) -> list[PropertyDef]:
        """Generate property definitions for a generic canvas item."""
        return [
            PropertyDef(key="name", label="Name", value=item.get("name", ""), section="General"),
            PropertyDef(key="x", label="X", prop_type=PropertyType.FLOAT, value=item.get("x", 0), section="Transform"),
            PropertyDef(key="y", label="Y", prop_type=PropertyType.FLOAT, value=item.get("y", 0), section="Transform"),
            PropertyDef(key="rotation", label="Rotation", prop_type=PropertyType.FLOAT, value=item.get("rotation", 0), min_val=0, max_val=360, section="Transform"),
            PropertyDef(key="scale_x", label="Scale X", prop_type=PropertyType.FLOAT, value=item.get("scale_x", 1.0), section="Transform"),
            PropertyDef(key="scale_y", label="Scale Y", prop_type=PropertyType.FLOAT, value=item.get("scale_y", 1.0), section="Transform"),
            PropertyDef(key="opacity", label="Opacity", prop_type=PropertyType.FLOAT, value=item.get("opacity", 1.0), min_val=0, max_val=1, section="Appearance"),
            PropertyDef(key="visible", label="Visible", prop_type=PropertyType.BOOL, value=item.get("visible", True), section="Appearance"),
            PropertyDef(key="locked", label="Locked", prop_type=PropertyType.BOOL, value=item.get("locked", False), section="Appearance"),
        ]

    @staticmethod
    def properties_for_entity(entity: dict) -> list[PropertyDef]:
        """Generate property definitions for a game entity."""
        props = [
            PropertyDef(key="name", label="Name", value=entity.get("name", ""), section="General"),
            PropertyDef(key="level", label="Level", prop_type=PropertyType.INT, value=entity.get("level", 1), min_val=1, max_val=100, section="General"),
            PropertyDef(key="type", label="Type", prop_type=PropertyType.ENUM, value=entity.get("type", ""), options=["NPC", "Mob", "Boss", "Quest", "Dungeon"], section="General"),
            PropertyDef(key="faction", label="Faction", prop_type=PropertyType.ENUM, value=entity.get("faction", "Neutral"), options=["Neutral", "Friendly", "Hostile"], section="General"),
            PropertyDef(key="hp", label="HP", prop_type=PropertyType.INT, value=entity.get("hp", 100), min_val=1, section="Stats"),
            PropertyDef(key="damage", label="Damage", prop_type=PropertyType.INT, value=entity.get("damage", 10), min_val=0, section="Stats"),
        ]
        return props
