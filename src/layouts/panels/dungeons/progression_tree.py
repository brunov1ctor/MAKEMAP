"""ÁRVORE DE PROGRESSÃO — as construções da base desenhadas por tier.

Não é um canvas livre como a árvore de habilidades: aqui a posição é
derivada dos dados (o `tier` é a linha, o `parent_id` é a aresta), então
mexer no editor reposiciona o nó sozinho e não existe layout para salvar.
Tudo é pintado num widget só — nós, arestas e rótulos de tier — porque com
dezenas de nós isso desenha e amplia melhor do que dezenas de widgets.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    BUILD_STATUSES, STATUS_COLORS, tier_name,
    _INPUT_STYLE, panel_frame_style, sub_header,
)


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
        # path -> QPixmap, para não reler do disco a cada paintEvent (que
        # dispara bastante — hover, zoom, resize).
        self._pixmap_cache: dict[str, QPixmap] = {}

    # ── dados ──

    def set_buildings(self, buildings: list[dict]):
        self._buildings = buildings
        # Descarta imagens de construções que não estão mais na lista —
        # evita crescer pra sempre trocando de categoria repetidamente.
        paths = {b["image"] for b in buildings if b.get("image")}
        for stale in set(self._pixmap_cache) - paths:
            del self._pixmap_cache[stale]
        self._relayout()

    def _pixmap_for(self, path: str) -> QPixmap | None:
        if not path:
            return None
        cached = self._pixmap_cache.get(path)
        if cached is not None:
            return cached if not cached.isNull() else None
        pix = QPixmap(path)
        self._pixmap_cache[path] = pix
        return pix if not pix.isNull() else None

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
        # Sem raiz sintética — cada categoria mostra só as construções que
        # de fato pertencem a ela (um "Centro da Vila" fixo aparecia em toda
        # aba/ramo, mesmo nas que não tinham nenhuma construção real).
        # Construções de tier 1 (sem parent_id real) já leem como raiz por
        # não terem aresta de entrada — ver paintEvent.
        self._rows = [(tier, by_tier[tier]) for tier in sorted(by_tier)]

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
                continue  # sem pai conhecido nesta categoria — lê como raiz, sem aresta
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
        border = QColor(color)
        border.setAlpha(255 if (is_selected or is_hover) else 150)
        pixmap = self._pixmap_for(node.get("image") or "")

        card_path = QPainterPath()
        card_path.addRoundedRect(rect, 8, 8)

        if pixmap is not None:
            # Preenche o card com a imagem da construção (cover-fit,
            # recortada nos cantos arredondados) em vez do retângulo sólido
            # de cor — só cai pro preenchimento de cor quando não há
            # imagem (ver ramo abaixo).
            p.save()
            p.setClipPath(card_path)
            scaled = pixmap.scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    Qt.TransformationMode.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) / 2
            y = rect.y() + (rect.height() - scaled.height()) / 2
            p.drawPixmap(QPointF(x, y), scaled)
            # Véu escuro gradual (mais forte embaixo, onde fica o texto) —
            # sem isso o nome/nível somem contra imagens claras.
            grad_top = QColor(0, 0, 0, 90 if not locked else 150)
            grad_bottom = QColor(0, 0, 0, 175 if not locked else 205)
            p.fillRect(rect, grad_top)
            p.fillRect(QRectF(rect.x(), rect.bottom() - 36, rect.width(), 36), grad_bottom)
            p.restore()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(border, 2.0 if is_selected else 1.2))
            p.drawPath(card_path)
        else:
            fill = QColor(color)
            fill.setAlpha(38 if not is_selected else 70)
            p.setBrush(fill)
            p.setPen(QPen(border, 2.0 if is_selected else 1.2))
            p.drawRoundedRect(rect, 8, 8)

            font = QFont()
            font.setPointSizeF(15)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 90 if locked else 230))
            p.drawText(QRectF(rect.x(), rect.y() + 5, rect.width(), 22),
                       Qt.AlignmentFlag.AlignCenter, node.get("icon") or "🏛")

        if locked and pixmap is not None:
            font = QFont()
            font.setPointSizeF(13)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 210))
            p.drawText(QRectF(rect.x(), rect.y() + 4, rect.width(), 20),
                       Qt.AlignmentFlag.AlignCenter, "🔒")

        font = QFont()
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
        if node_id:
            self.set_selected(node_id)
            self.selected.emit(node_id)

    def mouseMoveEvent(self, event):
        hover = self._hit(event.position())
        if hover != self._hover_id:
            self._hover_id = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(220)
        self._buildings: list[dict] = []
        # "" = Todas — segue a MESMA aba de categoria que já filtra a lista
        # (CategoryTabBar em panel.py), em vez de um combo próprio e
        # desincronizado só desta árvore.
        self._active_category = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(7)
        outer.addWidget(sub_header("Árvore de Progressão"))

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self._branch_lbl = QLabel("Todas as categorias")
        self._branch_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        controls.addWidget(self._branch_lbl, 1)
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

    def set_active_category(self, category: str):
        """Chamado pelo DungeonsPanel quando a aba de categoria da lista
        muda (CategoryTabBar.selected) — mantém a árvore sempre mostrando
        o mesmo ramo que a lista, em vez de um filtro próprio e
        desincronizado."""
        self._active_category = category or ""
        self._branch_lbl.setText(f"Ramo: {self._active_category}" if self._active_category else "Todas as categorias")
        self._refresh_canvas()

    def select(self, building_id: str):
        self._canvas.set_selected(building_id)

    def _refresh_canvas(self):
        if self._active_category:
            visible = [b for b in self._buildings if (b.get("category") or "") == self._active_category]
        else:
            visible = list(self._buildings)
        self._canvas.set_buildings(visible)
