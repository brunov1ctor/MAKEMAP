"""CollapsiblePanel — painel glass com header fixo e conteúdo recolhível."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QWidget, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QRectF, QPropertyAnimation, QEasingCurve, Property, Signal,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush,
)

from src.styles.tokens import Colors, Typography


class CollapsiblePanel(QFrame):
    """Painel glass com header visível e conteúdo colapsável via seta."""

    collapsed_changed = Signal(bool)

    def __init__(self, title: str, icon: str = "", parent=None, radius: int = 10, expanded: bool = True):
        super().__init__(parent)
        self._radius = radius
        self._expanded = expanded
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(10, 6, 10, 6)
        self._main_layout.setSpacing(4)

        # ─── Header ───
        header_row = QHBoxLayout()
        header_row.setSpacing(4)

        header_text = f"{icon} {title}".strip() if icon else title
        self._title_label = QLabel(header_text)
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_MUTED}; background: transparent; border: none;
        """)
        header_row.addWidget(self._title_label)
        header_row.addStretch()

        self._arrow_btn = QToolButton()
        self._arrow_btn.setFixedSize(18, 18)
        self._arrow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 9px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._arrow_btn.clicked.connect(self.toggle)
        header_row.addWidget(self._arrow_btn)

        self._main_layout.addLayout(header_row)

        # ─── Content container ───
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent; border: none;")
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._main_layout.addWidget(self._content)

        self._update_arrow()
        if not self._expanded:
            self._content.setVisible(False)

    @property
    def content_layout(self) -> QVBoxLayout:
        """Layout onde o conteúdo interno deve ser adicionado."""
        return self._content_layout

    @property
    def content_widget(self) -> QWidget:
        return self._content

    def toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_arrow()
        if self._expanded:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.collapsed_changed.emit(not self._expanded)

    def set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self.toggle()

    def is_expanded(self) -> bool:
        return self._expanded

    def _update_arrow(self):
        self._arrow_btn.setText("▼" if self._expanded else "▶")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), self._radius, self._radius)
        p.fillPath(path, QColor(11, 25, 41, 200))
        grad = QLinearGradient(0, 0, 0, h * 0.25)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)
        p.end()
