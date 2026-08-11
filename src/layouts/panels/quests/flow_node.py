"""FlowNode — bloco arrastável do editor de Fluxo da quest.

Ponto de conexão na borda direita, arraste solto, botão ✕, com um
vocabulário próprio de tipos (Início/Objetivo/Condição/Evento/Fim) em vez de
um único tipo genérico — cada tipo tem ícone e cor fixos, e o nó mostra um
selo com o tipo além do título/subtítulo. Vive num arquivo próprio porque o
Fluxo da quest e a Progressão de bioma divergem demais no que cada nó
precisa representar para valer a pena forçar um widget genérico único entre
os dois.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QPoint
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient, QFont

from src.styles.tokens import Colors

NODE_TYPES: dict[str, dict] = {
    "inicio": {"label": "Início", "icon": "🚩", "color": Colors.SUCCESS},
    "objetivo": {"label": "Objetivo", "icon": "🎯", "color": Colors.ACCENT},
    "condicao": {"label": "Condição", "icon": "🔀", "color": "#AB47BC"},
    "evento": {"label": "Evento", "icon": "🚩", "color": "#7E57C2"},
    "fim": {"label": "Fim", "icon": "🏁", "color": Colors.ERROR},
}
NODE_TYPE_ORDER = ["inicio", "objetivo", "condicao", "evento", "fim"]


class FlowNode(QFrame):
    moved = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    connection_started = Signal(object)
    locate_requested = Signal(object)
    edit_on_map_requested = Signal(object)
    pin_pick_requested = Signal(object)
    pin_locate_requested = Signal(object)
    pin_clear_requested = Signal(object)

    WIDTH, HEIGHT = 172, 74
    HANDLE_R = 9
    HANDLE_HIT_R = 13
    CONNECT_ICON = "🔗"

    def __init__(self, node_id: str, node_type: str, title: str, subtitle: str = "",
                 ref_type: str = "", ref_id: str = "", pin: dict | None = None, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self._type = node_type if node_type in NODE_TYPES else "objetivo"
        self._title = title
        self._subtitle = subtitle
        self._ref_type = ref_type
        self._ref_id = ref_id
        self.pin = dict(pin) if pin else None
        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self._handle_hovering = False

        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        self._type_lbl = QLabel()
        self._type_lbl.setStyleSheet("font-size: 8px; font-weight: bold; background: transparent; border: none;")
        top_row.addWidget(self._type_lbl)
        top_row.addStretch()
        self._locate_btn = QToolButton()
        self._locate_btn.setText("📍")
        self._locate_btn.setFixedSize(14, 14)
        self._locate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._locate_btn.setToolTip("Ver no mapa")
        self._locate_btn.setStyleSheet("""
            QToolButton { border: none; background: transparent; font-size: 9px; }
            QToolButton:hover { background: rgba(255,255,255,0.15); border-radius: 7px; }
        """)
        self._locate_btn.clicked.connect(lambda: self.locate_requested.emit(self))
        top_row.addWidget(self._locate_btn)
        self._edit_map_btn = QToolButton()
        self._edit_map_btn.setText("🖊")
        self._edit_map_btn.setFixedSize(14, 14)
        self._edit_map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_map_btn.setToolTip("Colocar/editar no mapa")
        self._edit_map_btn.setStyleSheet("""
            QToolButton { border: none; background: transparent; font-size: 9px; }
            QToolButton:hover { background: rgba(255,255,255,0.15); border-radius: 7px; }
        """)
        self._edit_map_btn.clicked.connect(lambda: self.edit_on_map_requested.emit(self))
        top_row.addWidget(self._edit_map_btn)
        self._pin_btn = QToolButton()
        self._pin_btn.setFixedSize(14, 14)
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setStyleSheet("""
            QToolButton { border: none; background: transparent; font-size: 9px; }
            QToolButton:hover { background: rgba(255,255,255,0.15); border-radius: 7px; }
        """)
        self._pin_btn.clicked.connect(self._on_pin_button_clicked)
        self._pin_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._pin_btn.customContextMenuRequested.connect(self._on_pin_button_right_click)
        top_row.addWidget(self._pin_btn)
        del_btn = QToolButton()
        del_btn.setText("✕")
        del_btn.setFixedSize(14, 14)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED};
                font-size: 9px; border-radius: 7px; }}
            QToolButton:hover {{ background: rgba(239,83,80,0.3); color: #EF5350; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        top_row.addWidget(del_btn)
        layout.addLayout(top_row)

        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._title_lbl)

        self._subtitle_lbl = QLabel()
        self._subtitle_lbl.setStyleSheet(
            f"font-size: 8px; color: {Colors.TEXT_MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._subtitle_lbl)

        self._refresh_labels()

    # ── API pública ──

    def node_type(self) -> str:
        return self._type

    def title(self) -> str:
        return self._title

    @property
    def name(self) -> str:
        """Alias for title() — lets this node be fed directly into
        progression/map_overlay.py's _MapMarkerItem, which is written
        against _ProgressionNode's `.name` attribute (see its tooltip)."""
        return self._title

    def subtitle(self) -> str:
        return self._subtitle

    def color(self) -> QColor:
        return QColor(NODE_TYPES[self._type]["color"])

    def ref_type(self) -> str:
        return self._ref_type

    def ref_id(self) -> str:
        return self._ref_id

    def set_data(self, node_type: str, title: str, subtitle: str, ref_type: str = "", ref_id: str = ""):
        self._type = node_type if node_type in NODE_TYPES else self._type
        self._title = title
        self._subtitle = subtitle
        self._ref_type = ref_type
        self._ref_id = ref_id
        self._refresh_labels()
        self.update()

    # ── pino decorativo (independente do ref_type/ref_id) ──

    def set_pin(self, x: float, y: float):
        self.pin = {"x": x, "y": y}
        self._refresh_pin_button()

    def clear_pin(self):
        self.pin = None
        self._refresh_pin_button()

    def _on_pin_button_clicked(self):
        if self.pin:
            self.pin_locate_requested.emit(self)
        else:
            self.pin_pick_requested.emit(self)

    def _on_pin_button_right_click(self, _pos):
        if self.pin:
            self.pin_clear_requested.emit(self)

    def _refresh_pin_button(self):
        if self.pin:
            self._pin_btn.setText("🎯")
            self._pin_btn.setToolTip("Ver marcador no mapa • clique direito remove")
        else:
            self._pin_btn.setText("📌")
            self._pin_btn.setToolTip("Colocar marcador no mapa (mini-mapa acima)")

    def _refresh_labels(self):
        self._locate_btn.setVisible(bool(self._ref_id))
        self._edit_map_btn.setVisible(bool(self._ref_id))
        self._refresh_pin_button()
        meta = NODE_TYPES[self._type]
        self._type_lbl.setText(f"{meta['icon']} {meta['label'].upper()}")
        self._type_lbl.setStyleSheet(
            f"font-size: 8px; font-weight: bold; color: {meta['color']}; background: transparent; border: none;"
        )
        metrics_title = self._title_lbl.fontMetrics()
        elided = metrics_title.elidedText(self._title or "—", Qt.TextElideMode.ElideRight, self.WIDTH - 20)
        self._title_lbl.setText(elided)
        self._title_lbl.setToolTip(self._title)
        metrics_sub = self._subtitle_lbl.fontMetrics()
        elided_sub = metrics_sub.elidedText(self._subtitle or "", Qt.TextElideMode.ElideRight, self.WIDTH - 20)
        self._subtitle_lbl.setText(elided_sub)
        self._subtitle_lbl.setToolTip(self._subtitle)

    # ── pintura (estilo neon) ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(1, 1, w - 2, h - 2)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)

        color = self.color()
        glow = QColor(color)
        glow.setAlpha(25)
        p.fillPath(path, glow)
        p.fillPath(path, QColor(8, 18, 32, 200))

        grad = QLinearGradient(0, 0, 0, h * 0.4)
        highlight = QColor(color)
        highlight.setAlpha(20)
        grad.setColorAt(0.0, highlight)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillPath(path, QBrush(grad))

        pen_color = QColor(color)
        pen_color.setAlpha(180)
        p.setPen(QPen(pen_color, 1.5))
        p.drawPath(path)

        # Ponto de entrada (esquerda)
        p.setPen(Qt.PenStyle.NoPen)
        dot_color = QColor(color)
        dot_color.setAlpha(150)
        p.setBrush(dot_color)
        p.drawEllipse(QPointF(5, h / 2), 3, 3)

        # Alça 🔗 de conexão (canto inferior direito)
        hc = self._handle_center_local()
        hr = self.HANDLE_R
        handle_rect = QRectF(hc.x() - hr, hc.y() - hr, 2 * hr, 2 * hr)
        if self._handle_hovering:
            glow_rect = QRectF(hc.x() - hr - 4, hc.y() - hr - 4, 2 * (hr + 4), 2 * (hr + 4))
            glow_color = QColor(color)
            glow_color.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow_color)
            p.drawEllipse(glow_rect)
            handle_rect = QRectF(hc.x() - hr - 1.5, hc.y() - hr - 1.5, 2 * (hr + 1.5), 2 * (hr + 1.5))
        p.setPen(QPen(QColor(color), 1.5))
        p.setBrush(QBrush(QColor(20, 26, 40, 230)))
        p.drawEllipse(handle_rect)
        p.setFont(QFont("Segoe UI Emoji", 7))
        p.setPen(QColor(color))
        p.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, self.CONNECT_ICON)
        p.end()

    def _handle_center_local(self) -> QPointF:
        return QPointF(self.WIDTH - self.HANDLE_R - 2, self.HEIGHT - self.HANDLE_R - 2)

    def _is_over_handle(self, pos: QPoint) -> bool:
        hc = self._handle_center_local()
        dx, dy = pos.x() - hc.x(), pos.y() - hc.y()
        return dx * dx + dy * dy <= self.HANDLE_HIT_R * self.HANDLE_HIT_R

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_over_handle(event.pos()):
                self.connection_started.emit(self)
                return
            self._dragging = True
            self._drag_offset = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()

    def mouseMoveEvent(self, event):
        over = self._is_over_handle(event.pos())
        if over != self._handle_hovering:
            self._handle_hovering = over
            self.update()
        self.setCursor(Qt.CursorShape.CrossCursor if over else (Qt.CursorShape.ClosedHandCursor if self._dragging else Qt.CursorShape.OpenHandCursor))
        if self._dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            parent = self.parentWidget()
            if parent:
                x = max(0, min(new_pos.x(), max(0, parent.width() - self.width())))
                y = max(0, min(new_pos.y(), max(0, parent.height() - self.height())))
                self.move(int(x), int(y))
            else:
                self.move(new_pos)
            self.moved.emit()

    def leaveEvent(self, event):
        if self._handle_hovering:
            self._handle_hovering = False
            self.update()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self)

    def right_point(self) -> QPointF:
        """Ponto de saída da seta — centro da alça 🔗 em coordenadas do canvas."""
        hc = self._handle_center_local()
        return QPointF(self.x() + hc.x(), self.y() + hc.y())

    def left_point(self) -> QPointF:
        return QPointF(self.x(), self.y() + self.height() / 2)
