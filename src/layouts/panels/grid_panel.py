"""Grid Settings Panel — sub-panel for grid configuration."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QCheckBox, QComboBox
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography
from src.layouts.panels.brush_panel import BrushSlider


class GridSettingsPanel(QFrame):
    """Sub-panel that appears when Grid is active."""

    snap_toggled = Signal(bool)
    shape_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(1)

        # Header
        header = QHBoxLayout()
        title = QLabel("\u229e Grid")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: {Typography.SIZE_SM}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        header.addWidget(title)

        # Shape selector
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["Quadrado", "Hex\u00e1gono", "Tri\u00e2ngulo", "Losango", "Isom\u00e9trico"])
        self.shape_combo.setFixedWidth(100)
        self.shape_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.PANEL}; color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                padding: 2px 6px; font-size: {Typography.SIZE_XS}px;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; selection-background-color: {Colors.ACCENT_DIM};
            }}
        """)
        self.shape_combo.currentTextChanged.connect(self.shape_changed.emit)
        self.shape_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shape_combo.wheelEvent = lambda e: e.ignore()
        header.addWidget(self.shape_combo)

        self.snap_check = QCheckBox("Snap")
        self.snap_check.setStyleSheet(f"""
            QCheckBox {{ color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_XS}px; background: transparent; border: none; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid {Colors.BORDER}; background: transparent; }}
            QCheckBox::indicator:checked {{ background: {Colors.ACCENT_DIM}; border-color: {Colors.ACCENT}; }}
        """)
        self.snap_check.toggled.connect(self.snap_toggled.emit)
        header.addWidget(self.snap_check)
        layout.addLayout(header)

        # Sliders
        self.size_slider = BrushSlider("Tamanho", "⊞", 16, 256, 64, "px")
        self.subdivisions_slider = BrushSlider("Subdiv.", "▦", 1, 8, 4, "")
        self.opacity_slider = BrushSlider("Opacidade", "◐", 5, 100, 30, "%")

        layout.addWidget(self.size_slider)
        layout.addWidget(self.subdivisions_slider)
        layout.addWidget(self.opacity_slider)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 210))
        grad = QLinearGradient(0, 0, 0, h * 0.2)
        grad.setColorAt(0.0, QColor(255, 255, 255, 8))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawPath(path)
        p.end()
