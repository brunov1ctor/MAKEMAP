"""MarkerToolPanel — "Marcador" toolbar panel: shown while the Marcador
tool is armed, before anything's been placed. Just an icon picker — every
other property (nome, categoria, descrição, efeitos...) is edited
afterward, on the placed marker, via MarkerEditPanel."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.marker.icon_picker import IconPicker
from src.engines.marker import ICONS


class MarkerToolPanel(QFrame):
    PANEL_WIDTH = 260

    icon_changed = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self._icon = ICONS[0]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("📍 MARCADOR")
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

        hint = QLabel("Clique no mapa para posicionar um novo marcador")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 10pt;
            background: transparent; border: none;
        """)
        layout.addWidget(hint)

        icons_label = QLabel("Ícones")
        icons_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10pt;
            background: transparent; border: none;
        """)
        layout.addWidget(icons_label)

        self._icon_picker = IconPicker(ICONS, button_size=34, max_height=170)
        self._icon_picker.set_checked(self._icon)
        self._icon_picker.icon_picked.connect(self._on_icon_clicked)
        layout.addWidget(self._icon_picker)

    def _on_icon_clicked(self, icon: str):
        self._icon = icon
        self.icon_changed.emit(icon)

    def current_icon(self) -> str:
        return self._icon

    def paintEvent(self, event):
        paint_glass_panel(self)
