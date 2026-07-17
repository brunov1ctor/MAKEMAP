"""5. Progressão do Mundo — painel blockchain redimensionável."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea, QInputDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography
from src.components.blockchain import Block, Pipeline, PIPELINE_THEMES


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
    """Painel blockchain — blocos arrastáveis, redimensionável por arraste."""

    size_changed = Signal()
    MIN_HEIGHT = 80
    MAX_HEIGHT = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_height = 120
        self.setFixedHeight(self._current_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._pipelines: list[Pipeline] = []
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
        header.addStretch()
        self._tabs_layout = QHBoxLayout()
        self._tabs_layout.setSpacing(0)
        header.addLayout(self._tabs_layout)
        main.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:horizontal {{ height: 5px; background: transparent; }}
            QScrollBar::handle:horizontal {{ background: {Colors.BORDER}; border-radius: 2px; }}
            QScrollBar:vertical {{ width: 5px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.BORDER}; border-radius: 2px; }}
        """)
        main.addWidget(self._scroll, 1)

        self._create_pipeline("Principal", 0, [
            ("🌲", "Floresta", "Lv 1-10", "✓"),
            ("🏔", "Vale", "Lv 10-20", "✓"),
            ("🌿", "Pântano", "Lv 20-30", "◉"),
            ("⛰", "Montanhas", "Lv 30-40", "○"),
            ("🏜", "Deserto", "Lv 40-50", "○"),
            ("🌋", "Vulcão", "Lv 60-70", "○"),
            ("🌑", "Sombras", "Lv 80-90", "○"),
            ("⚔", "End Game", "Lv 90-100", "○"),
        ])
        self._create_pipeline("Side Quests", 1, [
            ("📜", "Tutorial", "Lv 1-5", "✓"),
            ("🏴", "Arena PvP", "Lv 20+", "○"),
            ("💎", "Crafting", "Lv 15+", "○"),
        ])
        self._switch_pipeline(0)

    def _create_pipeline(self, name: str, theme_idx: int = 0, segments: list = None):
        theme = PIPELINE_THEMES[theme_idx % len(PIPELINE_THEMES)]
        pipe = Pipeline(name, theme, segments)
        for block in pipe.canvas._blocks:
            block.edit_requested.connect(self._edit_block)
            block.delete_requested.connect(self._delete_block)
        pipe.canvas.rect_requested.connect(self._add_rect)
        self._pipelines.append(pipe)
        self._rebuild_tabs()

    def _add_pipeline(self):
        name = f"Pipeline {len(self._pipelines) + 1}"
        self._create_pipeline(name, len(self._pipelines) % len(PIPELINE_THEMES))
        self._switch_pipeline(len(self._pipelines) - 1)

    def _add_rect(self):
        if not self._pipelines:
            return
        pipe = self._pipelines[self._current_idx]
        block = Block("🗺", "Novo", "", "#4FC3F7", "○")
        block.edit_requested.connect(self._edit_block)
        block.delete_requested.connect(self._delete_block)
        pipe.canvas.add_block(block)

    def _edit_block(self, block: Block):
        name, ok = QInputDialog.getText(self, "Editar Bloco", "Nome:", text=block._name)
        if not ok:
            return
        levels, ok2 = QInputDialog.getText(self, "Info", "Nível:", text=block._levels)
        levels = levels if ok2 else block._levels
        icon, ok3 = QInputDialog.getText(self, "Ícone", "Emoji:", text=block._icon)
        icon = icon if ok3 else block._icon
        block.update_data(icon, name, levels)

    def _delete_block(self, block: Block):
        self._pipelines[self._current_idx].canvas.remove_block(block)

    def _switch_pipeline(self, idx: int):
        self._current_idx = idx
        old = self._scroll.takeWidget()
        if old:
            old.setParent(None)
        self._scroll.setWidget(self._pipelines[idx].canvas)
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
            c = pipe.theme["color"]
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
            lbl = QLabel(pipe.name)
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
