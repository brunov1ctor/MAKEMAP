"""MiniMap — minimapa com viewport indicator e zoom, ocultável."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
    QToolButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors, Typography


class MiniMap(QFrame):
    """Minimapa com viewport indicator e zoom, ocultável."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._full_size = (170, 130)
        self._collapsed_size = (170, 30)
        self.setFixedSize(*self._full_size)
        self.setStyleSheet(f"""
            MiniMap {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 10px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("🗺 Minimap")
        header.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        header_row.addWidget(header)
        header_row.addStretch()

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("▼")
        self._toggle_btn.setFixedSize(16, 16)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 8px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._toggle_btn.clicked.connect(self.toggle_visibility)
        header_row.addWidget(self._toggle_btn)
        layout.addLayout(header_row)

        # Viewport area
        self._viewport_area = QFrame()
        self._viewport_area.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)
        layout.addWidget(self._viewport_area, 1)

        # Zoom bar
        self._zoom_row = QFrame()
        self._zoom_row.setStyleSheet("background: transparent; border: none;")
        zoom_lay = QHBoxLayout(self._zoom_row)
        zoom_lay.setContentsMargins(0, 0, 0, 0)
        zoom_lay.setSpacing(4)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_lay.addStretch()
        zoom_lay.addWidget(self.zoom_label)
        zoom_lay.addStretch()
        layout.addWidget(self._zoom_row)

    def toggle_visibility(self):
        self._expanded = not self._expanded
        self._viewport_area.setVisible(self._expanded)
        self._zoom_row.setVisible(self._expanded)
        if self._expanded:
            self.setFixedSize(*self._full_size)
            self._toggle_btn.setText("▼")
        else:
            self.setFixedSize(*self._collapsed_size)
            self._toggle_btn.setText("▶")
