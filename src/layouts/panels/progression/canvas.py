"""ProgressionCanvas — one pipeline's (aba's) node graph: a QGraphicsScene
of _ProgressionNode cards connected by _ProgressionEdge arrows, wrapped in a
_ProgressionView. Mirrors items/skill_tree/canvas.py's SkillTreeCanvas
architecture (undo/redo Commands + HistoryEngine, JSON blob persisted per
tab) trimmed to what a biome/step pipeline needs — no rank/image, but adds
notes and an optional map pin per card (see items.py).

ProgressionBar (progression.py) owns one ProgressionCanvas per pipeline tab
and swaps which one is visible; each canvas keeps its own scene/history so
switching tabs doesn't lose in-flight state.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsScene, QSizePolicy
from PySide6.QtCore import Signal, QPointF, QTimer

from src.engines.core.history import Command, HistoryEngine
from .items import _ProgressionNode, _ProgressionEdge, _ProgressionConnectPreview, biome_color
from .view import _ProgressionView


# ── undo/redo commands (connection create/delete/redirect, node delete) ──

class _AddEdgeCommand(Command):
    def __init__(self, canvas: "ProgressionCanvas", src: _ProgressionNode, dst: _ProgressionNode):
        self.canvas = canvas
        self.src = src
        self.dst = dst
        self.edge: _ProgressionEdge | None = None
        self.description = "Criar conexão"

    def redo(self):
        if self.edge is None:
            self.edge = self.canvas._add_edge_item(self.src, self.dst)
        else:
            self.canvas._scene.addItem(self.edge)
            self.canvas._edges.append(self.edge)
        self.canvas._persist()

    def undo(self):
        self.canvas._scene.removeItem(self.edge)
        self.canvas._edges.remove(self.edge)
        self.canvas._persist()


class _DeleteEdgesCommand(Command):
    def __init__(self, canvas: "ProgressionCanvas", edges: list[_ProgressionEdge]):
        self.canvas = canvas
        self.edges = edges
        self.description = "Remover conexão" if len(edges) == 1 else f"Remover {len(edges)} conexões"

    def redo(self):
        for e in self.edges:
            self.canvas._scene.removeItem(e)
            self.canvas._edges.remove(e)
        self.canvas._persist()

    def undo(self):
        for e in self.edges:
            self.canvas._scene.addItem(e)
            self.canvas._edges.append(e)
        self.canvas._persist()


class _RedirectEdgeCommand(Command):
    def __init__(self, canvas: "ProgressionCanvas", edge: _ProgressionEdge, end: str,
                 old_node: _ProgressionNode, new_node: _ProgressionNode):
        self.canvas = canvas
        self.edge = edge
        self.end = end
        self.old_node = old_node
        self.new_node = new_node
        self.description = "Redirecionar conexão"

    def _apply(self, node: _ProgressionNode):
        setattr(self.edge, self.end, node)
        self.edge.update_path()
        self.canvas._persist()

    def redo(self):
        self._apply(self.new_node)

    def undo(self):
        self._apply(self.old_node)


class _DeleteNodeCommand(Command):
    def __init__(self, canvas: "ProgressionCanvas", node: _ProgressionNode, edges: list[_ProgressionEdge]):
        self.canvas = canvas
        self.node = node
        self.edges = edges
        self.description = "Remover bloco"

    def redo(self):
        for e in self.edges:
            self.canvas._scene.removeItem(e)
            self.canvas._edges.remove(e)
        self.canvas._scene.removeItem(self.node)
        self.canvas._nodes.pop(self.node.node_id, None)
        if self.canvas._selected_node is self.node:
            self.canvas._selected_node = None
        self.canvas._persist()

    def undo(self):
        self.canvas._scene.addItem(self.node)
        self.canvas._nodes[self.node.node_id] = self.node
        for e in self.edges:
            self.canvas._scene.addItem(e)
            self.canvas._edges.append(e)
        self.canvas._persist()


class ProgressionCanvas(QWidget):
    changed = Signal()
    pin_pick_requested = Signal(object)   # _ProgressionNode
    pin_locate_requested = Signal(object)  # _ProgressionNode

    def __init__(self, pipeline_key: str, repo=None, parent=None):
        super().__init__(parent)
        self.pipeline_key = pipeline_key
        self._repo = repo
        self._nodes: dict[str, _ProgressionNode] = {}
        self._edges: list[_ProgressionEdge] = []
        self._selected_node: _ProgressionNode | None = None
        self._drop_target_node: _ProgressionNode | None = None
        self._connecting_from: _ProgressionNode | None = None
        self._redirecting_edge: _ProgressionEdge | None = None
        self._redirecting_end: str | None = None
        self._temp_edge_line: "_ProgressionConnectPreview | None" = None
        self._history = HistoryEngine(self)
        self._zoom = 1.0

        # Drives the small light travelling along each edge (see
        # _ProgressionEdge._draw_flow_light) — only runs while this
        # pipeline's tab is actually visible (see showEvent/hideEvent).
        self._flow_phase = 0.0
        self._flow_timer = QTimer(self)
        self._flow_timer.timeout.connect(self._advance_flow)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-1000, -1000, 3000, 1000)
        self._view = _ProgressionView(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._view)

    def showEvent(self, event):
        super().showEvent(event)
        self._flow_timer.start(40)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._flow_timer.stop()

    def _advance_flow(self):
        self._flow_phase = (self._flow_phase + 0.012) % 1.0
        for e in self._edges:
            e.update()

    # ── public entry ──

    def set_repo(self, repo):
        self._repo = repo

    def load(self, data: dict | None = None, seed_segments: list | None = None):
        """Loads this pipeline's saved graph, or seeds it from
        `seed_segments` (icon, name, levels tuples) the first time a fresh
        project has no row for this pipeline_key yet."""
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._selected_node = None
        self._history.clear()

        if data is None and self._repo is not None:
            row = self._repo.get_pipeline(self.pipeline_key)
            data = self._parse_data(row.get("data")) if row else None
        if data is None:
            data = {"nodes": [], "edges": []}

        nodes = data.get("nodes", [])
        if not nodes and seed_segments:
            x = 20
            prev = None
            for icon, name, levels in seed_segments:
                node = self.add_node({"icon": icon, "name": name, "levels": levels,
                                       "x": x, "y": 20}, notify=False)
                if prev is not None:
                    self.add_edge(prev, node, notify=False)
                prev = node
                x += 160
            self._persist()
            return

        for nd in nodes:
            self._add_node_item(nd)
        for edge in data.get("edges", []):
            src = self._nodes.get(edge[0])
            dst = self._nodes.get(edge[1])
            if src and dst:
                self._add_edge_item(src, dst)
        # Loading existing data doesn't otherwise call _persist() (nothing
        # actually changed), but listeners that mirror this pipeline
        # elsewhere — the map pin overlay (see ProgressionMediator) — still
        # need to know a full graph just became available.
        self.changed.emit()

    def view_center_scene_pos(self) -> QPointF:
        """Where the user is actually looking right now, in scene
        coordinates — used to place a freshly added card somewhere visible
        instead of always appending far to the right of whatever's already
        on screen (which used to land clicks on "+ Novo Bloco" outside the
        visible area, reading as if nothing happened)."""
        return self._view.mapToScene(self._view.viewport().rect().center())

    def add_node(self, data: dict | None = None, notify: bool = True) -> _ProgressionNode:
        data = dict(data or {})
        data.setdefault("id", str(uuid.uuid4()))
        node = self._add_node_item(data)
        if notify:
            self._persist()
        return node

    def add_edge(self, src: _ProgressionNode, dst: _ProgressionNode, notify: bool = True):
        if src == dst or self._edge_exists(src, dst):
            return
        self._add_edge_item(src, dst)
        if notify:
            self._persist()

    def nodes(self) -> list[_ProgressionNode]:
        return list(self._nodes.values())

    # ── scene <-> data ──

    def _add_node_item(self, data: dict) -> _ProgressionNode:
        node = _ProgressionNode(data, self)
        node.clicked.connect(self._on_node_clicked)
        node.moved.connect(lambda n: self._persist())
        node.edit_requested.connect(self._edit_node)
        node.pin_pick_requested.connect(self.pin_pick_requested.emit)
        node.pin_locate_requested.connect(self.pin_locate_requested.emit)
        node.pin_clear_requested.connect(self._on_pin_clear)
        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        return node

    def _add_edge_item(self, src: _ProgressionNode, dst: _ProgressionNode) -> _ProgressionEdge:
        edge = _ProgressionEdge(src, dst, self)
        self._scene.addItem(edge)
        self._edges.append(edge)
        return edge

    def set_node_pin(self, node: _ProgressionNode, x: float, y: float):
        node.set_pin(x, y)
        self._persist()

    def _on_pin_clear(self, node: _ProgressionNode):
        node.clear_pin()
        self._persist()

    def _edit_node(self, node: _ProgressionNode):
        from .node_dialog import ProgressionNodeDialog
        # Scoped to the whole app window, not just this canvas — the
        # Progressão panel itself is a short strip, so sizing the popup's
        # backdrop to `self` (see _PopupOverlay._run) clipped the card
        # against the panel's own small height instead of centering it
        # over the full screen.
        dlg = ProgressionNodeDialog(
            node.icon, node.name, node.levels, node.notes,
            node.border_color, biome_color(node.name), parent=self.window(),
        )
        if not dlg.exec():
            return
        icon, name, levels, notes, border_color = dlg.values()
        node.set_data(icon, name, levels, notes)
        node.set_border_color(border_color)  # triggers its own + connected edges' repaint
        self._persist()

    def _on_node_color_changed(self, node: _ProgressionNode):
        for e in self._edges:
            if e.src is node or e.dst is node:
                e.update()

    # ── connecting cards: drag from the 🔗 handle, or drop one onto another ──

    def _node_at(self, scene_pos: QPointF, exclude: _ProgressionNode = None) -> _ProgressionNode | None:
        for n in self._nodes.values():
            if n is not exclude and n.sceneBoundingRect().contains(scene_pos):
                return n
        return None

    def request_connection(self, src: _ProgressionNode, dst: _ProgressionNode):
        """Called either when a card is dropped on top of another one (see
        _ProgressionNode.mouseReleaseEvent) or when a 🔗-handle drag is
        released over a target (see _finish_connect below) — both gestures
        end up here."""
        if src is dst or self._edge_exists(src, dst):
            return
        self._history.push(_AddEdgeCommand(self, src, dst))

    def _begin_connect(self, node: _ProgressionNode, scene_pos: QPointF):
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        self._connecting_from = node
        preview = _ProgressionConnectPreview(node, scene_pos, node.color)
        self._scene.addItem(preview)
        self._temp_edge_line = preview

    def _finish_connect(self, scene_pos: QPointF):
        src = self._connecting_from
        self._connecting_from = None
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        if not src:
            return
        dst = self._node_at(scene_pos, exclude=src)
        if dst is not None:
            self.request_connection(src, dst)

    def _update_drop_highlight(self, dragging_node: _ProgressionNode):
        """Rings whichever card `dragging_node` currently overlaps, so
        dropping it there to connect (instead of just repositioning it) is
        obvious before the user lets go — see _ProgressionNode.paint's
        _drop_highlighted ring."""
        target = self._node_at(dragging_node.pos(), exclude=dragging_node)
        if target is self._drop_target_node:
            return
        if self._drop_target_node is not None:
            self._drop_target_node.set_drop_highlight(False)
        self._drop_target_node = target
        if target is not None:
            target.set_drop_highlight(True)

    def _clear_drop_highlight(self):
        if self._drop_target_node is not None:
            self._drop_target_node.set_drop_highlight(False)
            self._drop_target_node = None

    def _update_connect(self, scene_pos: QPointF):
        """Shared by the redirect-an-existing-edge drag below — moves the
        dashed preview/badge toward the cursor."""
        if self._temp_edge_line:
            self._temp_edge_line.set_end(scene_pos)

    def _delete_selected_edges(self):
        selected = [e for e in self._edges if e.isSelected()]
        if not selected:
            return
        self._history.push(_DeleteEdgesCommand(self, selected))

    def _delete_edge(self, edge: _ProgressionEdge):
        if edge not in self._edges:
            return
        self._history.push(_DeleteEdgesCommand(self, [edge]))

    def _delete_node(self, node: "_ProgressionNode | None"):
        if node is None or node.node_id not in self._nodes:
            return
        edges = [e for e in self._edges if e.src is node or e.dst is node]
        self._history.push(_DeleteNodeCommand(self, node, edges))

    # ── redirecting an existing connection's endpoint ──

    def _begin_redirect(self, edge: _ProgressionEdge, end: str, scene_pos: QPointF):
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        self._redirecting_edge = edge
        self._redirecting_end = end
        anchor = edge.dst if end == "src" else edge.src
        preview = _ProgressionConnectPreview(anchor, scene_pos, edge.src.color)
        self._scene.addItem(preview)
        self._temp_edge_line = preview

    def _finish_redirect(self, scene_pos: QPointF):
        edge = self._redirecting_edge
        end = self._redirecting_end
        self._redirecting_edge = None
        self._redirecting_end = None
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        if not edge:
            return
        fixed_node = edge.dst if end == "src" else edge.src
        old_node = getattr(edge, end)
        target = next(
            (n for n in self._nodes.values() if n is not fixed_node and n.sceneBoundingRect().contains(scene_pos)),
            None,
        )
        if not target or target is old_node:
            return
        prospective_src = target if end == "src" else edge.src
        prospective_dst = target if end == "dst" else edge.dst
        if self._edge_exists_excluding(edge, prospective_src, prospective_dst):
            return
        self._history.push(_RedirectEdgeCommand(self, edge, end, old_node, target))

    # ── interaction ──

    def _on_node_clicked(self, node: _ProgressionNode, modifiers):
        self._select_node(node)

    def _select_node(self, node: _ProgressionNode | None):
        for e in self._edges:
            e.setSelected(False)
        if self._selected_node and self._selected_node is not node:
            self._selected_node.set_selected(False)
        self._selected_node = node
        if node:
            node.set_selected(True)

    def _edge_exists(self, a: _ProgressionNode, b: _ProgressionNode) -> bool:
        return any((e.src is a and e.dst is b) or (e.src is b and e.dst is a) for e in self._edges)

    def _edge_exists_excluding(self, exclude: _ProgressionEdge, a: _ProgressionNode, b: _ProgressionNode) -> bool:
        return any(
            e is not exclude and ((e.src is a and e.dst is b) or (e.src is b and e.dst is a))
            for e in self._edges
        )

    def _on_node_moving(self, node: _ProgressionNode):
        for e in self._edges:
            if e.src is node or e.dst is node:
                e.update_path()

    # ── zoom ──

    def zoom_by(self, factor: float):
        new_zoom = self._zoom * factor
        if not (0.3 <= new_zoom <= 3.0):
            return
        self._zoom = new_zoom
        self._view.scale(factor, factor)

    # ── persistence ──

    def _persist(self):
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [[e.src.node_id, e.dst.node_id] for e in self._edges],
        }
        if self._repo is not None:
            self._repo.upsert(self.pipeline_key, data=json.dumps(data, ensure_ascii=False))
        self.changed.emit()

    @staticmethod
    def _parse_data(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {"nodes": [], "edges": []}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"nodes": [], "edges": []}
        except (json.JSONDecodeError, TypeError):
            return {"nodes": [], "edges": []}
