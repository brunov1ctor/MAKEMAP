"""ZoomControl — controle de zoom vertical com slider."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QToolButton, QSlider
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors


class ZoomControl(QFrame):
    """Controle de zoom vertical — slider + botões."""

    zoom_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 140)
        self.setStyleSheet(f"""
            ZoomControl {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 18px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)

        btn_style = f"""
            QToolButton {{
                border: none; border-radius: 12px;
                font-size: 14px; color: {Colors.TEXT_MUTED};
                background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """

        self.btn_in = QToolButton()
        self.btn_in.setText("+")
        self.btn_in.setFixedSize(24, 24)
        self.btn_in.setStyleSheet(btn_style)
        layout.addWidget(self.btn_in, 0, Qt.AlignmentFlag.AlignCenter)

        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setRange(5, 500)
        self.slider.setValue(100)
        self.slider.setFixedWidth(20)
        self.slider.setStyleSheet(f"""
            QSlider::groove:vertical {{
                background: {Colors.BG_TERTIARY};
                width: 4px; border-radius: 2px;
            }}
            QSlider::handle:vertical {{
                background: {Colors.ACCENT};
                width: 12px; height: 12px;
                margin: -4px -4px;
                border-radius: 6px;
            }}
            QSlider::handle:vertical:hover {{
                background: {Colors.ACCENT_HOVER};
            }}
        """)
        layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignCenter)

        self.btn_out = QToolButton()
        self.btn_out.setText("−")
        self.btn_out.setFixedSize(24, 24)
        self.btn_out.setStyleSheet(btn_style)
        layout.addWidget(self.btn_out, 0, Qt.AlignmentFlag.AlignCenter)
