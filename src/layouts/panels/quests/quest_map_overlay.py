"""QuestMapOverlay — mirrors every Flow node's decorative pin (see FlowNode.
pin/set_pin, flow_node.py) onto the real map scene, the same idea as
ProgressionMapOverlay (progression/map_overlay.py) but markers only — a
Quest's Fluxo has no equivalent to Progressão's connector lines between
cards, so there's nothing here to draw between two pins.

Reuses _MapMarkerItem itself rather than a quest-local copy: it's already
written against a duck-typed node (.node_id, .pin, .name) plus explicit
color/icon args, so a FlowNode (which exposes the same shape — see its
`name` property) drops in unchanged, including drag-to-reposition, hover,
and the ✕ remove badge (see canvas/engine.py's try_close duck-typing).

Owned by FlowTab, which calls rebuild() whenever FlowCanvas.changed fires.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF

from src.layouts.panels.progression.map_overlay import _MapMarkerItem
from src.layouts.panels.quests.flow_node import NODE_TYPES


class QuestMapOverlay:
    """Owns every pin item mirrored onto the real map scene for one Quest's
    Flow — matched to its FlowNode by node_id and updated in place rather
    than torn down/recreated (see ProgressionMapOverlay.rebuild()'s
    docstring for why: a marker is a real selectable/movable item, and
    swapping its identity out from under an active Selecionar-tool
    interaction is not safe)."""

    def __init__(self, scene_provider):
        self._scene_provider = scene_provider
        self._markers: dict[str, _MapMarkerItem] = {}  # node_id -> item

    def items(self) -> list:
        return list(self._markers.values())

    def clear(self):
        for item in self._markers.values():
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
        self._markers = {}

    def rebuild(self, nodes: list, on_marker_moved=None, on_marker_remove=None):
        """`nodes`: this quest's FlowNode list (see FlowCanvas.nodes()).
        `on_marker_moved(node, QPointF)` connects to every marker's
        drag-release; `on_marker_remove(node)` connects to every marker's
        ✕ badge — both mirror ProgressionMediator's equivalents."""
        scene = self._scene_provider()
        if scene is None:
            self.clear()
            return

        seen_ids = set()
        for node in nodes:
            if not node.pin:
                continue
            seen_ids.add(node.node_id)
            pos = QPointF(node.pin["x"], node.pin["y"])
            color = node.color().name()
            icon = NODE_TYPES[node.node_type()]["icon"]
            marker = self._markers.get(node.node_id)
            if marker is None:
                marker = _MapMarkerItem(node, pos, color, icon)
                if on_marker_moved is not None:
                    marker.moved.connect(on_marker_moved)
                if on_marker_remove is not None:
                    marker.remove_requested.connect(on_marker_remove)
                scene.addItem(marker)
                self._markers[node.node_id] = marker
            else:
                if marker.pos() != pos:
                    marker.setPos(pos)
                marker.set_appearance(color, icon)

        for node_id in list(self._markers):
            if node_id not in seen_ids:
                item = self._markers.pop(node_id)
                stale_scene = item.scene()
                if stale_scene is not None:
                    stale_scene.removeItem(item)
