"""Reusable glass panel widget with blur and translucency."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from src.styles.tokens import Metrics


class GlassPanel(QFrame):
    """Translucent panel with drop shadow — base building block."""

    def __init__(self, parent=None, object_name: str = "glass_panel"):
        super().__init__(parent)
        self.setObjectName(object_name)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            Metrics.SPACING_MD, Metrics.SPACING_MD,
            Metrics.SPACING_MD, Metrics.SPACING_MD,
        )
        self._layout.setSpacing(Metrics.SPACING_SM)

    @property
    def inner_layout(self) -> QVBoxLayout:
        return self._layout
