"""ÁRVORE DE PROGRESSÃO — as construções da base desenhadas por tier.

Não é um canvas livre como a árvore de habilidades: aqui a posição é
derivada dos dados (o `tier` é a linha, o `parent_id` é a aresta), então
mexer no editor reposiciona o nó sozinho e não existe layout para salvar.
Tudo é pintado num widget só — nós, arestas e rótulos de tier — porque com
dezenas de nós isso desenha e amplia melhor do que dezenas de widgets.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QToolButton,
    QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    BUILD_STATUSES, STATUS_COLORS, tier_name,
    _INPUT_STYLE, _no_wheel, panel_frame_style, sub_header,
)

ROOT_ID = "__root__"


class _TreeCanvas(QWidget):
    """Desenha os nós e liga cada um ao que o destrava."""

    selected = Signal(str)

    NODE_W, NODE_H = 92, 62
    COL_GAP, ROW_GAP = 22, 40
    MARGIN_X, MARGIN_Y = 96, 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)
        self._buildings: list[dict] = []
        self._scale = 1.0
        self._selected_id = ""
        self._hover_id = ""
        self._hitboxes: list[tuple[QRectF, str]] = []
        self._rows: list[tuple[int, list[dict]]] = []

    # ── dados ──

    def set_buildings(self, buildings: list[dict]):
        self._buildings = buildings
        self._relayout()

    def set_selected(self, building_id: str):
        self._selected_id = building_id or ""
        self.update()

    def set_scale(self, scale: float):
        self._scale = max(0.4, min(2.0, scale))
        self._relayout()

    def scale(self) -> float:
        return self._scale

    # ── layout ──

    def _relayout(self):
        """Agrupa por tier e recalcula o tamanho necessário do canvas."""
        by_tier: dict[int, list[dict]] = {}
        for building in self._buildings:
            by_tier.setdefault(int(building.get("tier") or 1), []).append(building)
        for nodes in by_tier.values():
            nodes.sort(key=lambda b: (int(b.get("sort_order") or 0), b.get("name") or ""))
        # A raiz é uma linha sintética: dá um ponto de partida visível mesmo
        # quando nenhuma construção tem parent_id.
        self._rows = [(0, [{"id": ROOT_ID, "name": "Centro da Vila", "icon": "🏰",
                            "level": 1, "status": "concluida"}])]
        self._rows += [(tier, by_tier[tier]) for tier in sorted(by_tier)]

        widest = max((len(nodes) for _t, nodes in self._rows), default=1)
        width = self.MARGIN_X + widest * (self.NODE_W + self.COL_GAP) + self.MARGIN_X // 2
        height = self.MARGIN_Y * 2 + len(self._rows) * (self.NODE_H + self.ROW_GAP)
        self.setMinimumSize(int(width * self._scale), int(height * self._scale))
        self.update()

    def _node_rects(self) -> dict[str, QRectF]:
        """id → retângulo do nó, em coordenadas não escaladas."""
        rects: dict[str, QRectF] = {}
        available = max(self.width() / self._scale, self.minimumWidth() / self._scale)
        for row_index, (_tier, nodes) in enumerate(self._rows):
            span = len(nodes) * self.NODE_W + max(0, len(nodes) - 1) * self.COL_GAP
            start = self.MARGIN_X + max(0.0, (available - self.MARGIN_X - span) / 2)
            y = self.MARGIN_Y + row_index * (self.NODE_H + self.ROW_GAP)
            for col, node in enumerate(nodes):
                x = start + col * (self.NODE_W + self.COL_GAP)
                rects[node["id"]] = QRectF(x, y, self.NODE_W, self.NODE_H)
        return rects

    # ── pintura ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self._scale, self._scale)

        rects = self._node_rects()
        self._hitboxes = [(rects[nid], nid) for nid in rects]
        known = {b["id"] for b in self._buildings}

        # Arestas primeiro, para passarem por baixo dos nós.
        pen = QPen(QColor(255, 255, 255, 45), 1.4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for building in self._buildings:
            child = rects.get(building["id"])
            if child is None:
                continue
            parent_id = building.get("parent_id") or ""
            if parent_id not in known:
                parent_id = ROOT_ID
            parent = rects.get(parent_id)
            if parent is None or parent.top() >= child.top():
                continue
            path = QPainterPath()
            start = QPointF(parent.center().x(), parent.bottom())
            end = QPointF(child.center().x(), child.top())
            mid_y = (start.y() + end.y()) / 2
            path.moveTo(start)
            path.lineTo(start.x(), mid_y)
            path.lineTo(end.x(), mid_y)
            path.lineTo(end)
            p.drawPath(path)

        # Rótulo do tier na margem esquerda + os nós daquela linha.
        for row_index, (tier, nodes) in enumerate(self._rows):
            y = self.MARGIN_Y + row_index * (self.NODE_H + self.ROW_GAP)
            if tier:
                self._draw_tier_label(p, tier, y)
            for node in nodes:
                self._draw_node(p, node, rects[node["id"]])
        p.end()

    def _draw_tier_label(self, p: QPainter, tier: int, y: float):
        font = QFont()
        font.setPointSizeF(7.5)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(Colors.ACCENT))
        p.drawText(QRectF(6, y, self.MARGIN_X - 16, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"TIER {tier}")
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 100))
        p.drawText(QRectF(6, y + 13, self.MARGIN_X - 16, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tier_name(tier))

    def _draw_node(self, p: QPainter, node: dict, rect: QRectF):
        status = node.get("status") or "disponivel"
        color = QColor(STATUS_COLORS.get(status, Colors.ACCENT))
        is_selected = node["id"] == self._selected_id
        is_hover = node["id"] == self._hover_id
        locked = status == "bloqueada"

        fill = QColor(color)
        fill.setAlpha(38 if not is_selected else 70)
        border = QColor(color)
        border.setAlpha(255 if (is_selected or is_hover) else 150)
        p.setBrush(fill)
        p.setPen(QPen(border, 2.0 if is_selected else 1.2))
        p.drawRoundedRect(rect, 8, 8)

        font = QFont()
        font.setPointSizeF(15)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 90 if locked else 230))
        p.drawText(QRectF(rect.x(), rect.y() + 5, rect.width(), 22),
                   Qt.AlignmentFlag.AlignCenter, "🔒" if locked else (node.get("icon") or "🏛"))

        font.setPointSizeF(7.5)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 110 if locked else 235))
        p.drawText(QRectF(rect.x() + 3, rect.y() + 28, rect.width() - 6, 14),
                   Qt.AlignmentFlag.AlignCenter, self._elide(node.get("name") or "—", 13))

        font.setBold(False)
        font.setPointSizeF(7)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 90))
        p.drawText(QRectF(rect.x() + 3, rect.y() + 42, rect.width() - 6, 14),
                   Qt.AlignmentFlag.AlignCenter, f"Nível {node.get('level') or 1}")

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"

    # ── interação ──

    def _hit(self, pos) -> str:
        point = QPointF(pos.x() / self._scale, pos.y() / self._scale)
        for rect, node_id in self._hitboxes:
            if rect.contains(point):
                return node_id
        return ""

    def mousePressEvent(self, event):
        node_id = self._hit(event.position())
        if node_id and node_id != ROOT_ID:
            self.set_selected(node_id)
            self.selected.emit(node_id)

    def mouseMoveEvent(self, event):
        hover = self._hit(event.position())
        if hover != self._hover_id:
            self._hover_id = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover and hover != ROOT_ID
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover_id = ""
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class ProgressionTree(QFrame):
    """Cabeçalho (filtro de ramo + zoom), canvas rolável e legenda."""

    selected = Signal(str)

    def __init__(self, categories_provider=None, parent=None):
        """`categories_provider` devolve as abas de categoria (banco) —
        popula o filtro "Todos os Ramos", que deixou de ser uma lista fixa."""
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(220)
        self._buildings: list[dict] = []
        self._categories_provider = categories_provider or (lambda: [])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(7)
        outer.addWidget(sub_header("Árvore de Progressão"))

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self._branch = QComboBox()
        self._branch.addItem("Todos os Ramos")
        self._branch.setFixedHeight(24)
        _no_wheel(self._branch)
        self._branch.currentIndexChanged.connect(self._refresh_canvas)
        controls.addWidget(self._branch, 1)
        controls.addWidget(self._zoom_btn("−", lambda: self._zoom(-0.1)))
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setFixedWidth(38)
        self._zoom_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        controls.addWidget(self._zoom_lbl)
        controls.addWidget(self._zoom_btn("+", lambda: self._zoom(0.1)))
        controls.addWidget(self._zoom_btn("⛶", self._reset_zoom))
        outer.addLayout(controls)

        self._canvas = _TreeCanvas()
        self._canvas.selected.connect(self.selected.emit)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical, QScrollBar:horizontal { width: 5px; height: 5px; background: transparent; }"
            f"QScrollBar::handle {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; min-width: 20px; }}"
            "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }"
        )
        scroll.setWidget(self._canvas)
        outer.addWidget(scroll, 1)

        # Legenda — os mesmos quatro estados que colorem os nós.
        legend = QHBoxLayout()
        legend.setSpacing(10)
        for _key, label, color in BUILD_STATUSES:
            item = QLabel(f"● {label}")
            item.setStyleSheet(f"color: {color}; font-size: 8px; background: transparent; border: none;")
            legend.addWidget(item)
        legend.addStretch()
        outer.addLayout(legend)

    def _zoom_btn(self, text: str, on_click) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        btn.clicked.connect(on_click)
        return btn

    def _zoom(self, delta: float):
        self._canvas.set_scale(self._canvas.scale() + delta)
        self._zoom_lbl.setText(f"{round(self._canvas.scale() * 100)}%")

    def _reset_zoom(self):
        self._canvas.set_scale(1.0)
        self._zoom_lbl.setText("100%")

    # ── API pública ──

    def set_buildings(self, buildings: list[dict]):
        self._buildings = buildings
        self._refresh_canvas()

    def refresh_branch_options(self):
        """Repopula "Todos os Ramos" com as abas de categoria do banco —
        chamado pelo DungeonsPanel toda vez que a lista de categorias muda."""
        current = self._branch.currentText()
        self._branch.blockSignals(True)
        self._branch.clear()
        self._branch.addItem("Todos os Ramos")
        self._branch.addItems([c["name"] for c in self._categories_provider()])
        index = self._branch.findText(current)
        self._branch.setCurrentIndex(index if index >= 0 else 0)
        self._branch.blockSignals(False)

    def select(self, building_id: str):
        self._canvas.set_selected(building_id)

    def _refresh_canvas(self):
        branch = self._branch.currentText()
        if self._branch.currentIndex() > 0:
            visible = [b for b in self._buildings if (b.get("category") or "") == branch]
        else:
            visible = list(self._buildings)
        self._canvas.set_buildings(visible)
