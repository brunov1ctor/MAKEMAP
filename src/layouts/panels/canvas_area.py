"""Canvas Area — widget principal do editor que contém o engine."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget, QSizePolicy
from PySide6.QtCore import Qt

from src.canvas.engine import CanvasEngine


class CanvasArea(QFrame):
    """Editor principal — canvas engine fullscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        canvas_container = QWidget()
        canvas_container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(canvas_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.engine = CanvasEngine(canvas_container)
        container_layout.addWidget(self.engine)

        layout.addWidget(canvas_container, 1)
