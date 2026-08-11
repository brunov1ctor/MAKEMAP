"""Canvas Area — widget principal do editor que contém o engine."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget, QSizePolicy
from PySide6.QtCore import Qt

from src.canvas.engine import CanvasEngine
from src.styles.tokens import Colors

# A widget with its own local setStyleSheet doesn't reliably inherit the
# global QToolTip rule from the app's QSS (same bug already fixed in
# top_bar.py/view_dropdown.py) — without repeating it here, any tooltip
# shown over the canvas (e.g. a map marker's) renders as a native opaque
# box on Windows instead of the app's glass style.
_TOOLTIP_QSS = f"""
    QToolTip {{
        background-color: {Colors.BG_ELEVATED};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 11px;
    }}
"""


class CanvasArea(QFrame):
    """Editor principal — canvas engine fullscreen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet(f"QFrame {{ background: transparent; border: none; }}{_TOOLTIP_QSS}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        canvas_container = QWidget()
        canvas_container.setStyleSheet(f"QWidget {{ background: transparent; }}{_TOOLTIP_QSS}")
        container_layout = QVBoxLayout(canvas_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.engine = CanvasEngine(canvas_container)
        container_layout.addWidget(self.engine)

        layout.addWidget(canvas_container, 1)
