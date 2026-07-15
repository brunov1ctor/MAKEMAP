"""Blockchain widgets — blocos arrastáveis e canvas de conexões neon."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QMenu, QToolButton,
)
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QPoint
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush, QFont,
)

from src.styles.tokens import Colors, Typography


# ─── Biome Colors ──────────────────────────────────────────────────────────

BIOME_COLORS = {
    "Floresta": "#4CAF50", "Vale": "#8BC34A", "Pântano": "#689F38",
    "Montanhas": "#78909C", "Deserto": "#FFA726", "Vulcão": "#FF5722",
    "Sombras": "#AB47BC", "End Game": "#673AB7", "Tutorial": "#42A5F5",
    "Arena PvP": "#EF5350", "Crafting": "#26A69A", "Costa": "#29B6F6",
    "Abismo": "#5C6BC0",
}


def biome_color(name: str) -> str:
    return BIOME_COLORS.get(name, "#4FC3F7")


# ─── Pipeline Themes ───────────────────────────────────────────────────────

PIPELINE_THEMES = [
    {"name": "Cyan", "color": "#4FC3F7", "glow": "rgba(79,195,247,0.4)"},
    {"name": "Purple", "color": "#AB47BC", "glow": "rgba(171,71,188,0.4)"},
    {"name": "Green", "color": "#66BB6A", "glow": "rgba(102,187,106,0.4)"},
    {"name": "Orange", "color": "#FFA726", "glow": "rgba(255,167,38,0.4)"},
    {"name": "Red", "color": "#EF5350", "glow": "rgba(239,83,80,0.4)"},
    {"name": "Teal", "color": "#26A69A", "glow": "rgba(38,166,154,0.4)"},
]


# ─── Block ─────────────────────────────────────────────────────────────────

class Block(QFrame):
    """Bloco arrastável estilo blockchain."""

    moved = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    connection_started = Signal(object)

    def __init__(self, icon: str, name: str, levels: str, block_color: str,
                 status: str = "○", parent=None):
        super().__init__(parent)
        self._icon = icon
        self._name = name
        self._levels = levels
        self._color = QColor(block_color)
        self._status = status
        self._dragging = False
        self._drag_offset = QPoint(0, 0)

        self.setFixedSize(110, 64)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        self._thumb_lbl = QLabel(icon)
        self._thumb_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        top_row.addWidget(self._thumb_lbl)
        top_row.addStretch()
        self._del_btn = QToolButton()
        self._del_btn.setText("\u2715")
        self._del_btn.setFixedSize(14, 14)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED};
                font-size: 9px; border-radius: 7px; }}
            QToolButton:hover {{ background: rgba(239,83,80,0.3); color: #EF5350; }}
        """)
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        top_row.addWidget(self._del_btn)
        layout.addLayout(top_row)

        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        layout.addWidget(self._name_lbl)

        self._level_lbl = QLabel(levels)
        self._level_lbl.setStyleSheet(f"""
            font-size: 7px; color: {block_color}; font-weight: {Typography.WEIGHT_MEDIUM};
            background: transparent; border: none;
        """)
        layout.addWidget(self._level_lbl)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)

        glow_color = QColor(self._color)
        glow_color.setAlpha(25)
        p.fillPath(path, glow_color)
        p.fillPath(path, QColor(8, 18, 32, 200))

        grad = QLinearGradient(0, 0, 0, h * 0.4)
        highlight = QColor(self._color)
        highlight.setAlpha(20)
        grad.setColorAt(0.0, highlight)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillPath(path, QBrush(grad))

        pen_color = QColor(self._color)
        pen_color.setAlpha(180)
        p.setPen(QPen(pen_color, 1.5))
        p.drawPath(path)

        # Ponto de conexão direita
        p.setPen(Qt.PenStyle.NoPen)
        dot_color = QColor(self._color)
        dot_color.setAlpha(150)
        p.setBrush(dot_color)
        p.drawEllipse(QPointF(w - 5, h / 2), 3, 3)

        p.setPen(QPen(QColor(self._color.red(), self._color.green(), self._color.blue(), 60), 1))
        p.setFont(QFont("Consolas", 6))
        p.drawText(QRectF(6, h - 8, w - 12, 8), Qt.AlignmentFlag.AlignRight, f"#{id(self) % 0xFFFF:04X}")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.pos().x() > self.width() - 15:
                self.connection_started.emit(self)
                return
            self._dragging = True
            self._drag_offset = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            parent = self.parentWidget()
            if parent:
                x = max(0, min(new_pos.x(), parent.width() - self.width()))
                y = max(0, min(new_pos.y(), parent.height() - self.height()))
                # Evita sobrepor zona reservada do botão
                btn = getattr(parent, '_add_rect_btn', None)
                if btn:
                    br = btn.geometry()
                    my_rect = QRectF(x, y, self.width(), self.height())
                    if my_rect.intersects(QRectF(br)):
                        x = br.x() + br.width() + 8
                self.move(int(x), int(y))
            else:
                self.move(new_pos)
            self.moved.emit()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self)

    def right_point(self) -> QPointF:
        return QPointF(self.x() + self.width(), self.y() + self.height() / 2)

    def left_point(self) -> QPointF:
        return QPointF(self.x(), self.y() + self.height() / 2)

    def _show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: rgba(20,32,55,0.95); border: 1px solid {Colors.BORDER};
                     color: {Colors.TEXT_PRIMARY}; font-size: {Typography.SIZE_XS}px; }}
            QMenu::item:selected {{ background: {Colors.PANEL_HOVER}; }}
        """)
        menu.addAction("\u270f Editar", lambda: self.edit_requested.emit(self))
        menu.addAction("\ud83d\uddd1 Remover", lambda: self.delete_requested.emit(self))
        menu.exec(self.mapToGlobal(pos))

    def update_data(self, icon: str, name: str, levels: str):
        self._icon, self._name, self._levels = icon, name, levels
        self._thumb_lbl.setText(icon)
        self._name_lbl.setText(name)
        self._level_lbl.setText(levels)


# ─── RectNode ──────────────────────────────────────────────────────────────

class RectNode(QFrame):
    """Retângulo arrastável — nó visual simples para agrupar/anotar."""

    moved = Signal()
    delete_requested = Signal(object)
    connection_started = Signal(object)

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._color = QColor(color)
        self._dragging = False
        self._drag_offset = QPoint(0, 0)

        self.setFixedSize(140, 48)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)

        self._lbl = QLabel(title)
        self._lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        layout.addWidget(self._lbl, 1)

        self._del_btn = QToolButton()
        self._del_btn.setText("\u2715")
        self._del_btn.setFixedSize(14, 14)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED};
                font-size: 9px; border-radius: 7px; }}
            QToolButton:hover {{ background: rgba(239,83,80,0.3); color: #EF5350; }}
        """)
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        layout.addWidget(self._del_btn)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)

        p.fillPath(path, QColor(8, 18, 32, 180))
        pen_c = QColor(self._color)
        pen_c.setAlpha(160)
        p.setPen(QPen(pen_c, 1.2, Qt.PenStyle.DashLine))
        p.drawPath(path)

        # Ponto de conexão direita
        p.setPen(Qt.PenStyle.NoPen)
        dot = QColor(self._color)
        dot.setAlpha(150)
        p.setBrush(dot)
        p.drawEllipse(QPointF(self.width() - 5, self.height() / 2), 3, 3)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.pos().x() > self.width() - 15:
                self.connection_started.emit(self)
                return
            self._dragging = True
            self._drag_offset = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            parent = self.parentWidget()
            if parent:
                x = max(0, min(new_pos.x(), parent.width() - self.width()))
                y = max(0, min(new_pos.y(), parent.height() - self.height()))
                btn = getattr(parent, '_add_rect_btn', None)
                if btn:
                    br = btn.geometry()
                    my_rect = QRectF(x, y, self.width(), self.height())
                    if my_rect.intersects(QRectF(br)):
                        x = br.x() + br.width() + 8
                self.move(int(x), int(y))
            else:
                self.move(new_pos)
            self.moved.emit()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def right_point(self) -> QPointF:
        return QPointF(self.x() + self.width(), self.y() + self.height() / 2)

    def left_point(self) -> QPointF:
        return QPointF(self.x(), self.y() + self.height() / 2)


# ─── Chain Canvas ──────────────────────────────────────────────────────────

class ChainCanvas(QWidget):
    """Canvas onde os blocos vivem e as conexões neon são desenhadas (grafo livre)."""

    rect_requested = Signal()

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._chain_color = color
        self._blocks: list[Block] = []
        self._rects: list[RectNode] = []
        self._connections: list[tuple] = []
        self._connecting_from = None
        self._connect_end: QPointF | None = None
        self.setMinimumSize(800, 200)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent; border: none;")

        # Botão flutuante para adicionar retângulo
        self._add_rect_btn = QToolButton(self)
        self._add_rect_btn.setText("+ Novo Progresso")
        self._add_rect_btn.setToolTip("Adicionar Retângulo")
        self._add_rect_btn.setFixedSize(110, 28)
        self._add_rect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_rect_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 6px;
                font-size: 9px; font-weight: bold; color: #ffffff;
                background: #2E7D32; }}
            QToolButton:hover {{ background: #388E3C; }}
        """)
        self._add_rect_btn.clicked.connect(self.rect_requested.emit)
        self._add_rect_btn.move(8, 8)
        self._add_rect_btn.raise_()

    def _btn_end_x(self) -> int:
        """Retorna x após o botão com margem."""
        return self._add_rect_btn.x() + self._add_rect_btn.width() + 12

    def _btn_below_y(self) -> int:
        """Retorna y abaixo do botão com margem."""
        return self._add_rect_btn.y() + self._add_rect_btn.height() + 10

    def add_block(self, block: Block):
        block.setParent(self)
        block.moved.connect(self.update)
        block.connection_started.connect(self._start_connection)
        block.show()
        self._blocks.append(block)
        if len(self._blocks) > 1:
            prev = self._blocks[-2]
            block.move(prev.x() + prev.width() + 50, prev.y())
            self._connections.append((prev, block))
        else:
            block.move(self._add_rect_btn.x(), self._btn_below_y())
        self._update_min_size()
        self._add_rect_btn.raise_()
        self.update()

    def add_rect(self, rect: RectNode):
        """Adiciona retângulo ao canvas."""
        rect.setParent(self)
        rect.moved.connect(self.update)
        rect.connection_started.connect(self._start_connection)
        rect.show()
        self._rects.append(rect)
        x_offset = self._btn_end_x() + (len(self._rects) - 1) * 160
        rect.move(x_offset, 10)
        self._update_min_size()
        self._add_rect_btn.raise_()
        self.update()

    def remove_rect(self, rect: RectNode):
        """Remove retângulo e suas conexões."""
        self._connections = [(a, b) for a, b in self._connections if a != rect and b != rect]
        if rect in self._rects:
            self._rects.remove(rect)
        rect.deleteLater()
        self._update_min_size()
        self.update()

    def add_connection(self, source, target):
        """Adiciona conexão arbitrária entre dois nós (grafo)."""
        if source == target:
            return
        if (source, target) not in self._connections:
            self._connections.append((source, target))
            self.update()

    def remove_block(self, block: Block):
        self._connections = [(a, b) for a, b in self._connections if a != block and b != block]
        if block in self._blocks:
            self._blocks.remove(block)
        block.deleteLater()
        self._update_min_size()
        self.update()

    def _start_connection(self, node):
        """Inicia arraste de nova conexão a partir de um bloco ou rect."""
        self._connecting_from = node
        self._connect_end = node.right_point()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseMoveEvent(self, event):
        if self._connecting_from:
            self._connect_end = QPointF(event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if self._connecting_from:
            target = self._node_at(event.pos())
            if target and target != self._connecting_from:
                self.add_connection(self._connecting_from, target)
            self._connecting_from = None
            self._connect_end = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def _node_at(self, pos):
        """Retorna Block ou RectNode na posição."""
        for b in self._blocks:
            if b.geometry().contains(pos):
                return b
        for r in self._rects:
            if r.geometry().contains(pos):
                return r
        return None

    def _update_min_size(self):
        all_nodes = self._blocks + self._rects
        if not all_nodes:
            return
        max_x = max(n.x() + n.width() for n in all_nodes) + 40
        max_y = max(n.y() + n.height() for n in all_nodes) + 40
        self.setMinimumSize(max(800, max_x), max(100, max_y))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._chain_color

        for node_a, node_b in self._connections:
            start, end = node_a.right_point(), node_b.left_point()
            ctrl = abs(end.x() - start.x()) * 0.4
            path = QPainterPath()
            path.moveTo(start)
            path.cubicTo(QPointF(start.x() + ctrl, start.y()),
                         QPointF(end.x() - ctrl, end.y()), end)

            for alpha, width in [(50, 6), (200, 2), (255, 1)]:
                c = QColor(color)
                c.setAlpha(alpha)
                p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(path)

            self._draw_arrow(p, path, color)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color.red(), color.green(), color.blue(), 220))
            p.drawEllipse(start, 3, 3)
            p.drawEllipse(end, 3, 3)

        # Linha temporária durante arraste de conexão
        if self._connecting_from and self._connect_end:
            start = self._connecting_from.right_point()
            end = self._connect_end
            ctrl = abs(end.x() - start.x()) * 0.4
            path = QPainterPath()
            path.moveTo(start)
            path.cubicTo(QPointF(start.x() + ctrl, start.y()),
                         QPointF(end.x() - ctrl, end.y()), end)
            c = QColor(color)
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


# ─── Pipeline ──────────────────────────────────────────────────────────────

class Pipeline:
    """Dados de um pipeline."""

    def __init__(self, name: str, theme: dict, segments: list = None):
        self.name = name
        self.theme = theme
        self.color = QColor(theme["color"])
        self.canvas = ChainCanvas(self.color)

        if segments:
            for icon, bname, levels, status in segments:
                block = Block(icon, bname, levels, biome_color(bname), status)
                self.canvas.add_block(block)
