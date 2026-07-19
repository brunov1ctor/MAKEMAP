"""Grid Settings Panel — side panel matching brush panel style."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QCheckBox, QComboBox, QToolButton, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.stepper import NumberStepper


class GridSettingsPanel(QFrame):
    """Side panel for grid configuration — same size/style as BrushToolPanel."""

    PANEL_WIDTH = 300

    snap_toggled = Signal(bool)
    measurements_toggled = Signal(bool)
    shape_changed = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("⊞")
        icon.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Grid Settings")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # ─── Separator ───
        layout.addWidget(self._sep())

        # ─── Shape row ───
        row = QHBoxLayout()
        row.setSpacing(8)

        shape_label = QLabel("Shape")
        shape_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px;
            background: transparent; border: none;
        """)
        row.addWidget(shape_label)

        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["Nenhum", "Quadrado", "Hexágono", "Triângulo", "Losango", "Isométrico"])
        self.shape_combo.setFixedWidth(110)
        self.shape_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shape_combo.wheelEvent = lambda e: e.ignore()
        self.shape_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(255,255,255,0.04); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                padding: 3px 8px; font-size: 10px;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; selection-background-color: {Colors.ACCENT_DIM};
            }}
        """)
        self.shape_combo.currentTextChanged.connect(self.shape_changed.emit)
        row.addWidget(self.shape_combo)
        row.addStretch()
        layout.addLayout(row)

        # ─── Snap + Medidas row ───
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(12)

        # Snap has nothing to snap to without a grid shape — hidden rather
        # than just disabled, so it doesn't clutter the panel when unusable.
        self.snap_check = self._make_checkbox("Snap")
        self.snap_check.toggled.connect(self.snap_toggled.emit)
        toggles_row.addWidget(self.snap_check)

        self.measurements_check = self._make_checkbox("Medidas (m)")
        self.measurements_check.setChecked(False)
        self.measurements_check.toggled.connect(self.measurements_toggled.emit)
        toggles_row.addWidget(self.measurements_check)

        toggles_row.addStretch()
        layout.addLayout(toggles_row)

        self.shape_combo.currentTextChanged.connect(self._sync_snap_visibility)
        self._sync_snap_visibility(self.shape_combo.currentText())

        # ─── Separator ───
        layout.addWidget(self._sep())

        # ─── Cell Size / Subdivisions / Opacity ───
        # Cell Size and Subdivisions are exact-value settings (a decimal
        # meter size, a whole-number count) where dragging a slider is
        # fiddlier than just stepping to the number you want.
        # No upper bound: with infinite maps, the grid isn't confined to a
        # fixed terrain size, so a cell measurement shouldn't be either —
        # only clamped on the low end to stay a sane cell size.
        self.size_slider = NumberStepper("Cell Size", "⊞", 1, float("inf"), 100, step=0.5, decimals=1, suffix="m")
        self.subdivisions_slider = NumberStepper("Subdivisions", "▦", 1, 8, 1, step=1, decimals=0)
        self.opacity_slider = BrushSlider("Opacity", "◐", 5, 100, 30, "%")

        layout.addWidget(self.size_slider)
        layout.addWidget(self.subdivisions_slider)
        layout.addWidget(self.opacity_slider)

        outer.addWidget(container)

    def _sync_snap_visibility(self, shape_name: str):
        self.snap_check.setVisible(shape_name != "Nenhum")

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: rgba(255,255,255,0.10); border: none;")
        return sep

    @staticmethod
    def _make_checkbox(label: str) -> QCheckBox:
        box = QCheckBox(label)
        box.setStyleSheet(f"""
            QCheckBox {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid {Colors.BORDER}; background: rgba(255,255,255,0.04);
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT_DIM}; border-color: {Colors.ACCENT};
            }}
        """)
        return box

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 235))
        grad = QLinearGradient(0, 0, 0, h * 0.15)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawPath(path)
        p.end()
