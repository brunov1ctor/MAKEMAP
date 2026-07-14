"""Compass — rosa dos ventos."""

from PySide6.QtWidgets import QFrame, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors, Typography


class Compass(QFrame):
    """Rosa dos ventos profissional."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 52)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 26px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        lbl = QLabel("N", self)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setGeometry(0, 0, 52, 52)
        lbl.setStyleSheet(f"""
            color: {Colors.ACCENT}; font-size: 18px;
            font-weight: {Typography.WEIGHT_BLACK};
            background: transparent; border: none;
        """)
