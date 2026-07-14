"""5. Progressão do Mundo — painel blockchain redimensionável."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QToolButton, QScrollArea, QInputDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter

from src.styles.tokens import Colors, Typography
from src.components.collapsible_panel import CollapsiblePanel
from src.components.blockchain import (
    Block, ChainCanvas, Pipeline, PIPELINE_THEMES, biome_color,
)


class _ResizeHandle(QFrame):
    """Handle de arraste no topo do painel."""

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


class ProgressionBar(CollapsiblePanel):
    """Painel blockchain — blocos arrastáveis com conexões neon, redimensionável."""

    size_changed = Signal()
    MIN_HEIGHT = 80
    MAX_HEIGHT = 500

    def __init__(self, parent=None):
        super().__init__(title="Progressão do Mundo", icon="🗺", parent=parent, radius=10)
        self._current_height = 120
        self.setFixedHeight(self._current_height)

        self._pipelines: list[Pipeline] = []
        self._current_idx = 0

        # Handle de arraste
        self._resize_handle = _ResizeHandle(self)
        self._resize_handle.drag_delta.connect(self._on_drag)
        self._main_layout.insertWidget(0, self._resize_handle)

        # Header controls
        header_layout = self._main_layout.itemAt(1).layout()

        self._tabs_layout = QHBoxLayout()
        self._tabs_layout.setSpacing(2)
        header_layout.insertLayout(header_layout.count() - 1, self._tabs_layout)

        btn_style = f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 10px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """

        for text, tip, slot in [
            ("+", "Novo Pipeline", "_add_pipeline"),
            ("◈+", "Novo Bloco", "_add_block"),
        ]:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.setFixedSize(22 if len(text) > 1 else 18, 18)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style if text != "+" else f"""
                QToolButton {{ border: none; font-size: 11px; color: {Colors.ACCENT}; background: transparent; border-radius: 4px; }}
                QToolButton:hover {{ background: {Colors.ACCENT_DIM}; }}
            """)
            btn.clicked.connect(getattr(self, slot))
            header_layout.insertWidget(header_layout.count() - 1, btn)

        # Scroll area
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
        self.content_layout.addWidget(self._scroll, 1)

        # Pipelines padrão
        self._create_pipeline("Principal", 0, [
            ("🌲", "Floresta", "Lv 1–10", "✓"),
            ("🏔", "Vale", "Lv 10–20", "✓"),
            ("🌿", "Pântano", "Lv 20–30", "◉"),
            ("⛰", "Montanhas", "Lv 30–40", "○"),
            ("🏜", "Deserto", "Lv 40–50", "○"),
            ("🌋", "Vulcão", "Lv 60–70", "○"),
            ("🌑", "Sombras", "Lv 80–90", "○"),
            ("⚔", "End Game", "Lv 90–100", "○"),
        ])
        self._create_pipeline("Side Quests", 1, [
            ("📜", "Tutorial", "Lv 1–5", "✓"),
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
        self._pipelines.append(pipe)
        self._rebuild_tabs()

    def _add_pipeline(self):
        name, ok = QInputDialog.getText(self, "Novo Pipeline", "Nome:")
        if ok and name:
            self._create_pipeline(name, len(self._pipelines) % len(PIPELINE_THEMES))
            self._switch_pipeline(len(self._pipelines) - 1)

    def _add_block(self):
        if not self._pipelines:
            return
        name, ok = QInputDialog.getText(self, "Novo Bloco", "Nome:")
        if not ok or not name:
            return
        levels, ok2 = QInputDialog.getText(self, "Info", "Nível/Info:")
        if not ok2:
            levels = ""
        pipe = self._pipelines[self._current_idx]
        block = Block("🗺", name, levels, biome_color(name), "○")
        block.edit_requested.connect(self._edit_block)
        block.delete_requested.connect(self._delete_block)
        pipe.canvas.add_block(block)

    def _edit_block(self, block: Block):
        name, ok = QInputDialog.getText(self, "Editar Bloco", "Nome:", text=block._name)
        if not ok:
            return
        levels, ok2 = QInputDialog.getText(self, "Info", "Nível:", text=block._levels)
        if not ok2:
            levels = block._levels
        icon, ok3 = QInputDialog.getText(self, "Ícone", "Emoji:", text=block._icon)
        if not ok3:
            icon = block._icon
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
            btn = QToolButton()
            btn.setText(pipe.name)
            btn.setFixedHeight(16)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = (i == self._current_idx)
            c = pipe.theme["color"]
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; border-radius: 4px; padding: 1px 6px;
                    font-size: 8px; font-weight: {Typography.WEIGHT_BOLD};
                    color: {c if is_active else Colors.TEXT_MUTED};
                    background: {pipe.theme['glow'] if is_active else 'transparent'};
                }}
                QToolButton:hover {{ background: {pipe.theme['glow']}; color: {c}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._switch_pipeline(idx))
            self._tabs_layout.addWidget(btn)

    def _on_drag(self, delta: int):
        new_h = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, self._current_height + delta))
        if new_h != self._current_height:
            self._current_height = new_h
            self.setFixedHeight(new_h)
            self.size_changed.emit()

    def toggle(self):
        super().toggle()
        self.setFixedHeight(self._current_height if self.is_expanded() else 28)
        self.size_changed.emit()
