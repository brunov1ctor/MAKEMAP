"""LightPanel — "Iluminação" toolbar panel: opened by the 💡 toggle button
(main_layout._toggle_light_panel). Lists the light types as clickable
cards; picking one arms LightTool (see LightMediator) so the next map
click plants a light of that type — same "toggle opens a picker, picking
an option arms the actual placement tool" flow RegionSettingsPanel already
uses for painting a região."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.engines.light import LIGHT_TYPES


class _TypeRow(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
            QFrame:hover {{ background: rgba(255,255,255,0.08); border-color: {Colors.BORDER_HOVER}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(name_lbl, 1)
        arrow = QLabel("›")
        arrow.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        lay.addWidget(arrow)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class LightPanel(QFrame):
    PANEL_WIDTH = 260

    type_picked = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("💡 ILUMINAÇÃO")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        hint = QLabel("Clique num tipo e depois no mapa para posicionar")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10pt; background: transparent; border: none;")
        layout.addWidget(hint)

        for key, icon, label in LIGHT_TYPES:
            row = _TypeRow(key, icon, label)
            row.clicked.connect(self.type_picked.emit)
            layout.addWidget(row)

    def paintEvent(self, event):
        paint_glass_panel(self)
