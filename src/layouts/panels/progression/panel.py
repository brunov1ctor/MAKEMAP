"""ProgressionBar — "5. Progressão do Mundo" resizable panel: a guide for
planning routes through the map as a node graph, one tab (pipeline) per
route. Each tab owns its own ProgressionCanvas (QGraphicsScene-based node
graph — see canvas.py), so hover, notes, a per-card map pin, and
drag-to-redirect/delete on connections all come from the same mechanics the
Árvore de Habilidades uses (items/skill_tree/). Persisted per-project via
ProgressionRepository (progression_pipelines table); set_repo() is called
by ProgressionMediator once a project's UnitOfWork exists.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QStackedWidget, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography
from .canvas import ProgressionCanvas

PIPELINE_THEMES = [
    {"name": "Cyan", "color": "#4FC3F7"},
    {"name": "Purple", "color": "#AB47BC"},
    {"name": "Green", "color": "#66BB6A"},
    {"name": "Orange", "color": "#FFA726"},
    {"name": "Red", "color": "#EF5350"},
    {"name": "Teal", "color": "#26A69A"},
]

_DEFAULT_PIPELINES = [
    ("principal", "Principal", 0, [
        ("🌲", "Floresta", "Lv 1-10"),
        ("🏔", "Vale", "Lv 10-20"),
        ("🌿", "Pântano", "Lv 20-30"),
        ("⛰", "Montanhas", "Lv 30-40"),
        ("🏜", "Deserto", "Lv 40-50"),
        ("🌋", "Vulcão", "Lv 60-70"),
        ("🌑", "Sombras", "Lv 80-90"),
        ("⚔", "End Game", "Lv 90-100"),
    ]),
    ("side_quests", "Side Quests", 1, [
        ("📜", "Tutorial", "Lv 1-5"),
        ("🏴", "Arena PvP", "Lv 20+"),
        ("💎", "Crafting", "Lv 15+"),
    ]),
]


class _ResizeHandle(QFrame):
    drag_delta = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self._dragging = False
        self._start_y = 0

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(cx - 16, 2, 32, 2, 1, 1)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_y = event.globalPosition().toPoint().y()

    def mouseMoveEvent(self, event):
        if self._dragging:
            current_y = event.globalPosition().toPoint().y()
            self.drag_delta.emit(self._start_y - current_y)
            self._start_y = current_y

    def mouseReleaseEvent(self, event):
        self._dragging = False


class ProgressionBar(QFrame):
    """Painel de progressão — blocos de rota conectados por setas,
    redimensionável por arraste. Cada aba é um pipeline (rota) independente."""

    size_changed = Signal()
    pin_pick_requested = Signal(object)    # (ProgressionCanvas, _ProgressionNode)
    pin_locate_requested = Signal(object)  # (ProgressionCanvas, _ProgressionNode)
    pipeline_created = Signal(object)      # ProgressionCanvas — so ProgressionMediator can
                                            # mirror it (pins/connections) onto the real map
    MIN_HEIGHT = 6
    MAX_HEIGHT = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_height = 120
        self.setFixedHeight(self._current_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._repo = None
        self._pipelines: list[dict] = []  # {"key","name","theme_idx","canvas"}
        self._current_idx = 0

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self._resize_handle = _ResizeHandle(self)
        self._resize_handle.drag_delta.connect(self._on_drag)
        main.addWidget(self._resize_handle)

        header = QHBoxLayout()
        header.setContentsMargins(10, 2, 10, 2)
        header.setSpacing(6)
        title = QLabel("🗺 Progressão do Mundo")
        title.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_MUTED}; background: transparent; border: none;
        """)
        header.addWidget(title)

        add_node_btn = QToolButton()
        add_node_btn.setText("+ Novo Bloco")
        add_node_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_node_btn.setToolTip("Adicionar bloco de progresso nesta rota")
        add_node_btn.setStyleSheet("""
            QToolButton { border: none; border-radius: 6px; font-size: 9px; font-weight: bold;
                color: #ffffff; background: #2E7D32; padding: 3px 8px; }
            QToolButton:hover { background: #388E3C; }
        """)
        add_node_btn.clicked.connect(self._add_block)
        header.addWidget(add_node_btn)

        header.addStretch()
        self._tabs_layout = QHBoxLayout()
        self._tabs_layout.setSpacing(0)
        header.addLayout(self._tabs_layout)
        main.addLayout(header)

        self._stack = QStackedWidget()
        main.addWidget(self._stack, 1)

        # Sem projeto aberto ainda — set_repo() (via ProgressionMediator)
        # carrega/semeia os pipelines reais assim que houver um uow.

    # ── persistência / carregamento ──

    def set_repo(self, repo):
        self._repo = repo
        self._load_pipelines()

    def _load_pipelines(self):
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._pipelines = []

        rows = self._repo.get_all_ordered() if self._repo else []
        if not rows:
            for order, (key, name, theme_idx, segments) in enumerate(_DEFAULT_PIPELINES):
                self._repo.upsert(key, name=name, theme_idx=theme_idx, sort_order=order,
                                   data=json.dumps({"nodes": [], "edges": []}))
                self._create_pipeline(key, name, theme_idx, seed_segments=segments)
        else:
            for row in rows:
                self._create_pipeline(row["pipeline_key"], row["name"], row.get("theme_idx") or 0)

        self._switch_pipeline(0)

    def _create_pipeline(self, key: str, name: str, theme_idx: int, seed_segments: list = None) -> ProgressionCanvas:
        canvas = ProgressionCanvas(key, pipeline_name=name, repo=self._repo)
        canvas.pin_pick_requested.connect(lambda node, c=canvas: self.pin_pick_requested.emit((c, node)))
        canvas.pin_locate_requested.connect(lambda node, c=canvas: self.pin_locate_requested.emit((c, node)))
        # Emitted before load() so a listener (ProgressionMediator) can
        # subscribe to this canvas's own `changed` signal in time to catch
        # the emission load() fires once the graph is actually populated.
        self.pipeline_created.emit(canvas)
        # Must be appended before load(): load() emits `changed`, which
        # ProgressionMediator handles by rebuilding the map overlay from
        # self._pipelines right then — if this entry weren't in the list
        # yet, its own pins would be silently skipped from that rebuild
        # (only reappearing once some later edit re-triggers a rebuild).
        self._pipelines.append({"key": key, "name": name, "theme_idx": theme_idx, "canvas": canvas})
        canvas.load(seed_segments=seed_segments)
        self._stack.addWidget(canvas)
        self._rebuild_tabs()
        return canvas

    def _add_pipeline(self):
        if self._repo is None:
            return
        idx = len(self._pipelines)
        key = str(uuid.uuid4())
        name = f"Pipeline {idx + 1}"
        theme_idx = idx % len(PIPELINE_THEMES)
        self._repo.upsert(key, name=name, theme_idx=theme_idx, sort_order=idx,
                           data=json.dumps({"nodes": [], "edges": []}))
        self._create_pipeline(key, name, theme_idx)
        self._switch_pipeline(len(self._pipelines) - 1)

    def _add_block(self):
        if not self._pipelines:
            return
        canvas: ProgressionCanvas = self._pipelines[self._current_idx]["canvas"]
        # Nasce onde a view já está centralizada — não empilhado longe à
        # direita do que já existe, o que antes deixava o clique em
        # "+ Novo Bloco" sem efeito visível nenhum (o card ia parar fora da
        # área visível do painel).
        center = canvas.view_center_scene_pos()
        node = canvas.add_node({"icon": "🗺", "name": "Novo", "levels": "",
                                 "x": center.x(), "y": center.y()})
        canvas._view.centerOn(node)

    def _switch_pipeline(self, idx: int):
        if not self._pipelines:
            return
        self._current_idx = idx
        self._stack.setCurrentWidget(self._pipelines[idx]["canvas"])
        self._rebuild_tabs()

    def _rebuild_tabs(self):
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, pipe in enumerate(self._pipelines):
            tab = QFrame()
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setFixedHeight(20)
            is_active = (i == self._current_idx)
            c = PIPELINE_THEMES[pipe["theme_idx"] % len(PIPELINE_THEMES)]["color"]
            tab.setStyleSheet(f"""
                QFrame {{
                    border: none;
                    border-bottom: 2px solid {c if is_active else 'transparent'};
                    background: {'rgba(255,255,255,0.05)' if is_active else 'transparent'};
                    border-top-left-radius: 4px; border-top-right-radius: 4px; padding: 0 8px;
                }}
                QFrame:hover {{
                    background: rgba(255,255,255,0.08); border-bottom: 2px solid {c};
                }}
            """)
            tab_lay = QHBoxLayout(tab)
            tab_lay.setContentsMargins(6, 0, 6, 0)
            tab_lay.setSpacing(0)
            lbl = QLabel(pipe["name"])
            lbl.setStyleSheet(f"""
                font-size: 9px; font-weight: {Typography.WEIGHT_BOLD};
                color: {c if is_active else Colors.TEXT_MUTED};
                background: transparent; border: none;
            """)
            tab_lay.addWidget(lbl)
            tab.mousePressEvent = lambda e, idx=i: self._switch_pipeline(idx)
            self._tabs_layout.addWidget(tab)

        add_tab = QFrame()
        add_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        add_tab.setFixedSize(20, 20)
        add_tab.setStyleSheet("""
            QFrame { border: none; background: transparent;
                border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QFrame:hover { background: rgba(255,255,255,0.08); }
        """)
        add_lay = QHBoxLayout(add_tab)
        add_lay.setContentsMargins(0, 0, 0, 0)
        add_lbl = QLabel("+")
        add_lbl.setStyleSheet(f"font-size: 12px; color: {Colors.ACCENT}; background: transparent; border: none;")
        add_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_lay.addWidget(add_lbl)
        add_tab.mousePressEvent = lambda e: self._add_pipeline()
        self._tabs_layout.addWidget(add_tab)

    def _on_drag(self, delta: int):
        new_h = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, self._current_height + delta))
        if new_h != self._current_height:
            self._current_height = new_h
            self.setFixedHeight(new_h)
            self.size_changed.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 200))
        grad = QLinearGradient(0, 0, 0, h * 0.25)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)
        p.end()
