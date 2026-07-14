"""MiniMap — minimapa com viewport indicator e zoom."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors, Typography


class MiniMap(QFrame):
    """Minimapa com viewport indicator e zoom."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(170, 130)
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
        layout.addLayout(header_row)

        # Viewport area
        viewport_area = QFrame()
        viewport_area.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_TERTIARY};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)
        layout.addWidget(viewport_area, 1)

        # Zoom bar
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_row.addStretch()
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)
