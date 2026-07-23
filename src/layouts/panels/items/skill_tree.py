"""SkillTreeCanvas — the ÁRVORE DE HABILIDADES right column of the
Habilidades row.

A read-only-ish node graph on a QGraphicsView: element tabs across the top
(Fogo / Terra / Água / +, each closable), circular nodes each showing an
icon + name + rank (3/5), connections drawn between them, zoom controls
bottom-right, and a drag-to-reposition-only interaction (dragging just
saves the node's x/y — it never creates or removes anything).

Nodes/edges are no longer placed by hand here (no more double-click menu,
drag-from-list, or a "+ Nó" search combo) — they're derived straight from
SkillEditor's "Evoluir de:" field (see `sync_skill_node`), the same idea as
BuildingEditor's "Desbloqueada por": the record itself carries its
prerequisite, and the visualization follows.

The whole graph for the active tab is persisted as one JSON document per
element in the skill_trees table (see migration 12). uow may be None (no
project open) — then it degrades to in-memory only.
"""

from __future__ import annotations

import json
import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsPathItem,
    QSizePolicy, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.items.constants import panel_frame_style, sub_header

logger = logging.getLogger("MAKEMAP")


class _NodeItem(QGraphicsObject):
    """One circular skill node. Draggable; reports clicks (with modifiers)
    and drag-release back to the canvas so it can connect/persist."""

    NODE_R = 30  # icon circle radius

    clicked = Signal(object, object)     # (self, Qt.KeyboardModifiers)
    moved = Signal(object)               # self (on drag release)

    def __init__(self, data: dict, canvas: "SkillTreeCanvas"):
        super().__init__()
        self._canvas = canvas
        self.node_id = data.get("id") or str(uuid.uuid4())
        self.name = data.get("name", "Nó")
        self.icon = data.get("icon", "✨")
        self.rank_current = int(data.get("rank_current", 0))
        self.rank_max = int(data.get("rank_max", 1))
        self.color = data.get("color") or Colors.ACCENT
        self.setPos(QPointF(float(data.get("x", 0)), float(data.get("y", 0))))
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(2)
        self._selected = False

    def boundingRect(self) -> QRectF:
        r = self.NODE_R
        # circle + label strip below
        return QRectF(-r - 4, -r - 4, 2 * r + 8, 2 * r + 34)

    def center(self) -> QPointF:
        return self.pos()

    def set_selected(self, value: bool):
        self._selected = value
        self.update()

    def to_dict(self) -> dict:
        return {
            "id": self.node_id, "name": self.name, "icon": self.icon,
            "rank_current": self.rank_current, "rank_max": self.rank_max,
            "color": self.color, "x": self.pos().x(), "y": self.pos().y(),
        }

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.NODE_R
        color = QColor(self.color)

        # Selection / ring
        if self._selected:
            p.setPen(QPen(QColor(Colors.ACCENT), 3))
        else:
            ring = QColor(color)
            ring.setAlpha(200)
            p.setPen(QPen(ring, 2))
        grad = QColor(color)
        grad.setAlpha(60)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

        # Icon
        p.setPen(QColor("#FFFFFF"))
        icon_font = QFont("Segoe UI Emoji", 20)
        p.setFont(icon_font)
        p.drawText(QRectF(-r, -r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, self.icon)

        # Name
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        name_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(name_font)
        p.drawText(QRectF(-r - 4, r + 2, 2 * r + 8, 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.name)

        # Rank
        p.setPen(QColor(Colors.TEXT_MUTED))
        rank_font = QFont("Segoe UI", 8)
        p.setFont(rank_font)
        p.drawText(QRectF(-r - 4, r + 16, 2 * r + 8, 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   f"{self.rank_current}/{self.rank_max}")

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged:
            self._canvas._on_node_moving(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.clicked.emit(self, event.modifiers())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
        self.moved.emit(self)


class _EdgeItem(QGraphicsPathItem):
    """A connection between two nodes. Selectable (click) so Del can remove
    it; redraws itself whenever either endpoint moves."""

    def __init__(self, src: _NodeItem, dst: _NodeItem):
        super().__init__()
        self.src = src
        self.dst = dst
        self.setZValue(1)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor(Colors.ACCENT), 2))
        self.update_path()

    def update_path(self):
        a = self.src.center()
        b = self.dst.center()
        path = QPainterPath(a)
        # slight vertical S-curve, like the reference's elbow connectors
        mid_y = (a.y() + b.y()) / 2
        path.cubicTo(QPointF(a.x(), mid_y), QPointF(b.x(), mid_y), b)
        self.setPath(path)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isSelected():
            p.setPen(QPen(QColor(Colors.ACCENT_HOVER), 3, Qt.PenStyle.DashLine))
        else:
            pen_color = QColor(Colors.ACCENT)
            pen_color.setAlpha(150)
            p.setPen(QPen(pen_color, 2))
        p.drawPath(self.path())


class _TreeView(QGraphicsView):
    """QGraphicsView with wheel-zoom, delegating the real work to the
    canvas. Nodes only get created via `sync_skill_node` now (driven by
    SkillEditor's "Evoluir de:"), so this no longer accepts a double-click
    or a drag from the Habilidades list to spawn one."""

    def __init__(self, canvas: "SkillTreeCanvas"):
        super().__init__(canvas._scene)
        self._canvas = canvas
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background: transparent; border: none;")

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._canvas.zoom_by(factor)


class SkillTreeCanvas(QWidget):
    """The whole right column: element tabs, the node view and zoom controls."""

    def __init__(self, uow=None, skills_provider=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._skills_provider = skills_provider or (lambda: [])
        self._trees: list[dict] = []
        self._active_key: str = ""
        self._nodes: dict[str, _NodeItem] = {}
        self._edges: list[_EdgeItem] = []
        self._selected_node: _NodeItem | None = None
        self._zoom = 1.0

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        outer_wrap = QVBoxLayout(self)
        outer_wrap.setContentsMargins(0, 0, 0, 0)
        outer_wrap.addWidget(frame)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # ── Header: title + guia ativa (sem botões — criar/trocar de guia
        # agora acontece a partir do Editor de Habilidade: "Evoluir de:" →
        # "— Nenhuma (raiz) —" pede o nome da guia; ver o nó de uma
        # habilidade troca de guia sozinho, sem precisar clicar em nada
        # aqui). Só um "✕" pra apagar a guia mostrada no momento. ──
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(sub_header("Árvore de Habilidades"))
        head.addStretch()
        self._tab_label = QLabel("")
        self._tab_label.setStyleSheet(f"""
            color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM};
            border: 1px solid {Colors.ACCENT}; border-radius: 5px;
            padding: 3px 9px; font-size: 9px; font-weight: bold;
        """)
        head.addWidget(self._tab_label)
        self._tab_delete_btn = QToolButton()
        self._tab_delete_btn.setText("✕")
        self._tab_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_delete_btn.setFixedSize(16, 16)
        self._tab_delete_btn.setToolTip("Excluir esta guia")
        self._tab_delete_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        self._tab_delete_btn.clicked.connect(self._on_delete_active_tree)
        head.addWidget(self._tab_delete_btn)
        outer.addLayout(head)

        # ── Graphics view ──
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-1000, -1000, 2000, 2000)
        self._view = _TreeView(self)
        outer.addWidget(self._view, 1)

        # ── Footer overlay: hints (left) + zoom (right) ──
        footer = QHBoxLayout()
        hints = QLabel("Arraste para reposicionar • Nós/conexões vêm do \"Evoluir de:\" do editor")
        hints.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        # Don't let this long line dictate the column's minimum width (it would
        # break the 2×3 grid alignment) — it can clip if the column is narrow.
        hints.setMinimumWidth(1)
        hints.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(hints)
        footer.addStretch()
        for text, cb in [("－", lambda: self.zoom_by(1 / 1.15)),
                         (None, None),
                         ("＋", lambda: self.zoom_by(1.15)),
                         ("⤢", self._reset_zoom)]:
            if text is None:
                self._zoom_lbl = QLabel("100%")
                self._zoom_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
                self._zoom_lbl.setFixedWidth(38)
                self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                footer.addWidget(self._zoom_lbl)
                continue
            b = QToolButton()
            b.setText(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; font-size: 11px;
                    min-width: 22px; min-height: 20px; }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            """)
            b.clicked.connect(cb)
            footer.addWidget(b)
        outer.addLayout(footer)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ── tab styling ──

    # ── public entry ──

    def reload(self):
        """(Re)load every guia + the active one's nodes from the DB. No
        auto-seed anymore — a guia only exists once some habilidade raiz
        names one via "Evoluir de:" no editor."""
        self._trees = self._load_trees()
        if not self._active_key or self._active_key not in {t["tree_key"] for t in self._trees}:
            self._active_key = self._trees[0]["tree_key"] if self._trees else ""
        self._refresh_tab_label()
        self._load_active_tree()

    def create_tab_for_skill(self, skill: dict, tab_name: str) -> str:
        """Chamado pelo painel quando "Evoluir de:" = "— Nenhuma (raiz) —"
        e um nome de guia foi digitado — cria (ou reaproveita, se o nome já
        existir) a guia e a deixa ativa. O ícone vem do próprio ícone da
        habilidade no editor."""
        tab_name = tab_name.strip() or "Nova Guia"
        key = tab_name.lower().replace(" ", "_")
        if self._uow:
            existing = self._uow.skill_trees.get_all_ordered()
            if not any(t["tree_key"] == key for t in existing):
                self._uow.skill_trees.upsert(
                    key, name=tab_name, icon=skill.get("icon") or "✨",
                    sort_order=len(existing), data='{"nodes": [], "edges": []}')
        self._active_key = key
        self.reload()
        return key

    def show_tab_for_skill(self, skill_id: str):
        """Troca pra guia onde a habilidade já tem nó — chamado sempre que
        ela é selecionada na lista, pra árvore "seguir" o que está sendo
        editado em vez de exigir um clique numa aba pra ver."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            if any(n.get("id") == skill_id for n in data.get("nodes", [])):
                if tree["tree_key"] != self._active_key:
                    self._active_key = tree["tree_key"]
                    self.reload()
                return

    def sync_skill_node(self, skill_id: str, evolves_from: str | None):
        """Chamado pelo painel logo depois de salvar uma habilidade —
        garante que ela (e, se houver, sua pré-requisito) tenham um nó na
        guia ativa, com a conexão entre os dois. É a única forma de um nó
        aparecer agora: nada aqui cria nós por conta própria."""
        skills_by_id = {sk.get("id"): sk for sk in (self._skills_provider() or [])}
        skill = skills_by_id.get(skill_id)
        if not skill or not self._active_tree():
            return
        node = self._ensure_node(skill)
        if evolves_from:
            parent = skills_by_id.get(evolves_from)
            if parent:
                parent_node = self._ensure_node(parent)
                if not self._edge_exists(parent_node, node):
                    self._add_edge_item(parent_node, node)
        self._persist()

    def remove_skill_node(self, skill_id: str):
        """Chamado pelo painel ao excluir uma habilidade — tira o nó dela
        (e qualquer conexão que o referencie) de qualquer guia onde exista,
        pra não sobrar um nó órfão apontando pra um id que já era."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            if not any(n.get("id") == skill_id for n in nodes):
                continue
            data["nodes"] = [n for n in nodes if n.get("id") != skill_id]
            data["edges"] = [e for e in data.get("edges", []) if skill_id not in e]
            self._uow.skill_trees.upsert(tree["tree_key"], data=json.dumps(data, ensure_ascii=False))
            if tree["tree_key"] == self._active_key:
                self._load_active_tree()

    def _ensure_node(self, skill: dict) -> _NodeItem:
        """Nó existente pro id, ou um novo posicionado perto do centro da
        vista (deslocado a cada novo nó pra não empilhar em cima)."""
        existing = self._nodes.get(skill.get("id"))
        if existing:
            existing.name = skill.get("name", existing.name)
            existing.icon = skill.get("icon") or existing.icon
            existing.update()
            return existing
        center = self._view.mapToScene(self._view.viewport().rect().center())
        offset = (len(self._nodes) % 5) * 24
        data = {
            "id": skill["id"],
            "name": skill.get("name", "Habilidade"),
            "icon": skill.get("icon") or "✨",
            "color": item_rarity_color(skill.get("rarity", "common")),
            "x": center.x() + offset, "y": center.y() + offset,
            "rank_current": 0, "rank_max": 5,
        }
        return self._add_node_item(data)

    def _load_trees(self) -> list[dict]:
        if not self._uow:
            return []
        return self._uow.skill_trees.get_all_ordered()

    def _refresh_tab_label(self):
        tree = self._active_tree()
        if tree:
            self._tab_label.setText(f"{tree.get('icon', '')} {tree['name']}".strip())
            self._tab_label.setVisible(True)
            self._tab_delete_btn.setVisible(True)
        else:
            self._tab_label.setText("Nenhuma guia ainda — nomeie uma em \"Evoluir de:\"")
            self._tab_delete_btn.setVisible(False)

    def _on_delete_active_tree(self):
        tree = self._active_tree()
        if not tree:
            return
        reply = QMessageBox.question(
            self, "Excluir guia",
            f'Excluir a guia "{tree["name"]}"? Todos os nós e conexões dela se perdem.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._uow:
            self._uow.skill_trees.delete_tree(tree["tree_key"])
        self._active_key = ""
        self.reload()
        logger.info("Guia da árvore de habilidades excluída: %s", tree["tree_key"])

    # ── scene <-> data ──

    def _active_tree(self) -> dict | None:
        for t in self._trees:
            if t["tree_key"] == self._active_key:
                return t
        return None

    def _load_active_tree(self):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._selected_node = None
        tree = self._active_tree()
        if not tree:
            return
        data = self._parse_data(tree.get("data"))
        for nd in data.get("nodes", []):
            self._add_node_item(nd)
        for edge in data.get("edges", []):
            src = self._nodes.get(edge[0])
            dst = self._nodes.get(edge[1])
            if src and dst:
                self._add_edge_item(src, dst)

    def _add_node_item(self, data: dict) -> _NodeItem:
        node = _NodeItem(data, self)
        node.clicked.connect(self._on_node_clicked)
        node.moved.connect(lambda n: self._persist())
        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        return node

    def _add_edge_item(self, src: _NodeItem, dst: _NodeItem) -> _EdgeItem:
        edge = _EdgeItem(src, dst)
        self._scene.addItem(edge)
        self._edges.append(edge)
        return edge

    # ── new guia (inline text box) ──

    def _begin_new_tree(self):
        self._add_tab_btn.hide()
        self._new_tab_edit.clear()
        self._new_tab_edit.show()
        self._new_tab_edit.setFocus()

    def _cancel_new_tree(self):
        # editingFinished also fires right after returnPressed commits — the
        # hidden state makes this a no-op in that case.
        if self._new_tab_edit.isVisible() and not self._new_tab_edit.text().strip():
            self._new_tab_edit.hide()
            self._add_tab_btn.show()

    def _commit_new_tree(self):
        name = self._new_tab_edit.text().strip()
        self._new_tab_edit.hide()
        self._add_tab_btn.show()
        if not name:
            return
        key = name.lower().replace(" ", "_")
        if any(t["tree_key"] == key for t in self._trees):
            self._switch_tree(key)
            return
        order = len(self._trees)
        if self._uow:
            self._uow.skill_trees.upsert(key, name=name, icon="✨", sort_order=order,
                                         data='{"nodes": [], "edges": []}')
        else:
            self._trees.append({"tree_key": key, "name": name, "icon": "✨",
                                "data": '{"nodes": [], "edges": []}'})
        self._active_key = key
        self.reload()

    # ── interaction ──

    def _on_node_clicked(self, node: _NodeItem, modifiers):
        self._select_node(node)

    def _select_node(self, node: _NodeItem | None):
        for e in self._edges:
            e.setSelected(False)
        if self._selected_node and self._selected_node is not node:
            self._selected_node.set_selected(False)
        self._selected_node = node
        if node:
            node.set_selected(True)

    def _edge_exists(self, a: _NodeItem, b: _NodeItem) -> bool:
        return any((e.src is a and e.dst is b) or (e.src is b and e.dst is a) for e in self._edges)

    def _on_node_moving(self, node: _NodeItem):
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
        self._zoom_lbl.setText(f"{int(self._zoom * 100)}%")

    def _reset_zoom(self):
        if self._zoom != 1.0:
            self._view.scale(1 / self._zoom, 1 / self._zoom)
            self._zoom = 1.0
            self._zoom_lbl.setText("100%")
        self._view.centerOn(0, 0)

    # ── persistence ──

    def _persist(self):
        tree = self._active_tree()
        if not tree:
            return
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [[e.src.node_id, e.dst.node_id] for e in self._edges],
        }
        tree["data"] = json.dumps(data, ensure_ascii=False)
        if self._uow:
            self._uow.skill_trees.upsert(self._active_key, data=tree["data"])

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
