"""HUD Overlay — informações de camada ativa, grid, legendas."""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from src.styles.tokens import Colors, Typography


class HUDOverlay(QFrame):
    """HUD com informações de camada ativa, fronteiras, legendas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 28)
        self.setStyleSheet(f"""
            HUDOverlay {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 14px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self.layer_label = QLabel("📐 Terreno")
        self.layer_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.ACCENT};
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        layout.addWidget(self.layer_label)

        sep = QFrame()
        sep.setFixedSize(1, 14)
        sep.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        layout.addWidget(sep)

        self.grid_label = QLabel("Grid: ON")
        self.grid_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        layout.addWidget(self.grid_label)
