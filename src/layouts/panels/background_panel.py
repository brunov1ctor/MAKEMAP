"""Background Panel — floating toolbar panel for the map's background
(cor fixa / imagem estática / parallax). Opened from the canvas toolbar's
"Plano de Fundo" toggle (right after the View dropdown), same PanelManager-
registered pattern as Grid/Terrain/Region/Light — not a top-bar menu, not a
section nested inside the Terrain panel.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.terrain.background import BackgroundSection


class BackgroundPanel(QFrame):
    """Side panel wrapping BackgroundSection with the same header/close/
    glass-frame shell every other toolbar panel (Grid/Terrain/Region/Light)
    already has — BackgroundSection itself has no header of its own (see
    its own docstring), it just gets embedded, same as it used to be inside
    TerrainSettingsPanel."""

    PANEL_WIDTH = 300

    background_changed = Signal(str, str)  # type, value — re-exposes BackgroundSection's own
    close_requested = Signal()
    content_changed = Signal()  # emitted when visible content changes size

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._container = container
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("🖼")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Plano de Fundo")
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
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        layout.addWidget(sep)

        bg_dir = str(Path(__file__).resolve().parents[3] / "library" / "backgrounds")
        self._section = BackgroundSection(bg_dir)
        self._section.background_changed.connect(self.background_changed.emit)
        self._section.close_requested.connect(self.close_requested.emit)
        self._section.content_changed.connect(self._on_content_changed)
        layout.addWidget(self._section)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _on_content_changed(self):
        self.content_changed.emit()

    def content_height(self) -> int:
        """Same reasoning as TerrainSettingsPanel's own override — this
        panel nests QScrollAreas two levels deep (whole-panel ->
        BackgroundSection's own image-browser grid), so PanelManager's
        generic _content_height() (which only measures the first
        QScrollArea it finds) can't be trusted to size this correctly."""
        self._container.adjustSize()
        return self._container.sizeHint().height() + 20

    def paintEvent(self, event):
        paint_glass_panel(self)
