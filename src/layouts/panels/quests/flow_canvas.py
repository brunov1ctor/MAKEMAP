"""FlowCanvas — o canvas de grafo livre do editor de Fluxo da quest.

Arraste-para-conectar, curva bezier com brilho neon, cada conexão pode ter
um rótulo de texto (o "Sim"/"Não" saindo de um nó Condição), e clicar com o
botão direito no vazio abre um menu pra criar qualquer um dos 5 tipos de nó
ali mesmo — não existe um botão fixo de "+ Novo" único como o de Progressão,
já que o Fluxo tem 5 tipos possíveis.
"""

from __future__ import annotations

import uuid

from PySide6.QtWidgets import QWidget, QMenu, QInputDialog, QLineEdit
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont

from src.styles.tokens import Colors
from src.layouts.panels.quests.flow_node import FlowNode, NODE_TYPES, NODE_TYPE_ORDER

_EDGE_HIT_TOLERANCE = 9.0


class FlowCanvas(QWidget):
    changed = Signal()
    node_edit_requested = Signal(object)
    node_locate_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: list[FlowNode] = []
        self._edges: list[dict] = []  # {"a": FlowNode, "b": FlowNode, "label": str}
        self._connecting_from: FlowNode | None = None
        self._connect_end: QPointF | None = None
        self.setMinimumSize(700, 260)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_canvas_menu)

    # ── nós ──

    def add_node(self, node_type: str, title: str, subtitle: str = "",
                 x: int | None = None, y: int | None = None, node_id: str = "",
                 ref_type: str = "", ref_id: str = "", notify: bool = True) -> FlowNode:
        node_id = node_id or str(uuid.uuid4())
        node = FlowNode(node_id, node_type, title, subtitle, ref_type=ref_type, ref_id=ref_id, parent=self)
        node.moved.connect(self._on_node_moved)
        node.connection_started.connect(self._start_connection)
        node.edit_requested.connect(self.node_edit_requested.emit)
        node.delete_requested.connect(self.remove_node)
        node.locate_requested.connect(self.node_locate_requested.emit)
        if x is None:
            x = 20 + (len(self._nodes) % 4) * 40
        if y is None:
            y = 20 + (len(self._nodes) // 4) * 100
        node.move(int(x), int(y))
        node.show()
        self._nodes.append(node)
        self._update_min_size()
        self.update()
        if notify:
            self.changed.emit()
        return node

    def remove_node(self, node: FlowNode):
        self._edges = [e for e in self._edges if e["a"] != node and e["b"] != node]
        if node in self._nodes:
            self._nodes.remove(node)
        node.deleteLater()
        self._update_min_size()
        self.update()
        self.changed.emit()

    def _on_node_moved(self):
        self.update()
        self.changed.emit()

    def clear(self):
        for node in list(self._nodes):
            node.deleteLater()
        self._nodes = []
        self._edges = []
        self.update()

    def nodes(self) -> list[FlowNode]:
        return list(self._nodes)

    def edges(self) -> list[dict]:
        return list(self._edges)

    # ── conexões ──

    def add_edge(self, source: FlowNode, target: FlowNode, label: str = "", notify: bool = True):
        if source == target:
            return
        if any(e["a"] == source and e["b"] == target for e in self._edges):
            return
        self._edges.append({"a": source, "b": target, "label": label})
        self.update()
        if notify:
            self.changed.emit()

    def _start_connection(self, node):
        self._connecting_from = node
        self._connect_end = node.right_point()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseMoveEvent(self, event):
        if self._connecting_from:
            self._connect_end = QPointF(event.position() if hasattr(event, "position") else event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if self._connecting_from:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            target = self._node_at(pos)
            if target and target != self._connecting_from:
                self.add_edge(self._connecting_from, target)
            self._connecting_from = None
            self._connect_end = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if self._node_at(pos):
            return
        edge = self._edge_at(pos)
        if edge:
            self._prompt_edge_label(edge)

    def _node_at(self, pos) -> FlowNode | None:
        for n in self._nodes:
            if n.geometry().contains(pos):
                return n
        return None

    def _edge_at(self, pos) -> dict | None:
        point = QPointF(pos)
        for edge in self._edges:
            path = self._edge_path(edge)
            for i in range(21):
                t = i / 20
                sample = path.pointAtPercent(t)
                if (sample - point).manhattanLength() < _EDGE_HIT_TOLERANCE:
                    return edge
        return None

    def _prompt_edge_label(self, edge: dict):
        text, ok = QInputDialog.getText(
            self, "Rótulo da conexão", "Texto exibido na seta (ex.: Sim / Não):",
            QLineEdit.EchoMode.Normal, edge.get("label", ""),
        )
        if ok:
            edge["label"] = text.strip()
            self.update()
            self.changed.emit()

    # ── menu de contexto (criar nó) ──

    def _show_canvas_menu(self, pos):
        if self._node_at(pos):
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER};
                     color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        edge = self._edge_at(pos)
        if edge:
            menu.addAction("✏ Editar rótulo da conexão", lambda: self._prompt_edge_label(edge))
            menu.addAction("🗑 Remover conexão", lambda: self._remove_edge(edge))
            menu.addSeparator()
        for key in NODE_TYPE_ORDER:
            meta = NODE_TYPES[key]
            menu.addAction(f"{meta['icon']} Adicionar {meta['label']}",
                            lambda k=key: self.add_node(k, meta_label_default(k), x=pos.x(), y=pos.y()))
        menu.exec(self.mapToGlobal(pos))

    def _remove_edge(self, edge: dict):
        if edge in self._edges:
            self._edges.remove(edge)
            self.update()
            self.changed.emit()

    # ── layout ──

    def _update_min_size(self):
        if not self._nodes:
            return
        max_x = max(n.x() + n.width() for n in self._nodes) + 40
        max_y = max(n.y() + n.height() for n in self._nodes) + 40
        self.setMinimumSize(max(700, max_x), max(260, max_y))

    # ── pintura ──

    def _edge_path(self, edge: dict) -> QPainterPath:
        start, end = edge["a"].right_point(), edge["b"].left_point()
        ctrl = max(abs(end.x() - start.x()) * 0.4, 40)
        path = QPainterPath()
        path.moveTo(start)
        path.cubicTo(QPointF(start.x() + ctrl, start.y()), QPointF(end.x() - ctrl, end.y()), end)
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        for edge in self._edges:
            color = edge["a"].color()
            path = self._edge_path(edge)
            for alpha, width in [(50, 6), (200, 2), (255, 1)]:
                c = QColor(color)
                c.setAlpha(alpha)
                p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(path)
            self._draw_arrow(p, path, color)

            start, end = edge["a"].right_point(), edge["b"].left_point()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color.red(), color.green(), color.blue(), 220))
            p.drawEllipse(start, 3, 3)
            p.drawEllipse(end, 3, 3)

            if edge.get("label"):
                mid = path.pointAtPercent(0.5)
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                metrics = p.fontMetrics()
                text = edge["label"]
                text_w = metrics.horizontalAdvance(text) + 10
                text_h = metrics.height() + 4
                badge = QPainterPath()
                badge.addRoundedRect(mid.x() - text_w / 2, mid.y() - text_h / 2, text_w, text_h, 5, 5)
                p.fillPath(badge, QColor(10, 18, 32, 235))
                p.setPen(QPen(color, 1))
                p.drawPath(badge)
                p.setPen(QColor(Colors.TEXT_PRIMARY))
                p.drawText(
                    int(mid.x() - text_w / 2), int(mid.y() - text_h / 2), int(text_w), int(text_h),
                    Qt.AlignmentFlag.AlignCenter, text,
                )

        if self._connecting_from and self._connect_end:
            start = self._connecting_from.right_point()
            end = self._connect_end
            ctrl = max(abs(end.x() - start.x()) * 0.4, 40)
            path = QPainterPath()
            path.moveTo(start)
            path.cubicTo(QPointF(start.x() + ctrl, start.y()), QPointF(end.x() - ctrl, end.y()), end)
            c = QColor(self._connecting_from.color())
            c.setAlpha(120)
            p.setPen(QPen(c, 2, Qt.PenStyle.DashLine))
            p.drawPath(path)

        p.end()

    def _draw_arrow(self, p: QPainter, path: QPainterPath, color: QColor):
        pt, end = path.pointAtPercent(0.95), path.pointAtPercent(1.0)
        dx, dy = end.x() - pt.x(), end.y() - pt.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 0.1:
            return
        dx /= length
        dy /= length
        s = 8
        p1 = QPointF(end.x() - s * dx + s * 0.4 * dy, end.y() - s * dy - s * 0.4 * dx)
        p2 = QPointF(end.x() - s * dx - s * 0.4 * dy, end.y() - s * dy + s * 0.4 * dx)
        arrow = QPainterPath()
        arrow.moveTo(end)
        arrow.lineTo(p1)
        arrow.lineTo(p2)
        arrow.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 220))
        p.drawPath(arrow)


def meta_label_default(node_type: str) -> str:
    return NODE_TYPES[node_type]["label"]
