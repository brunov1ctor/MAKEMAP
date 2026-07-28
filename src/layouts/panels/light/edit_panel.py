"""LightEditPanel — shown when an existing LightItem is selected. Shares
the same PanelManager dock slot as LightPanel (never visible together —
see LightMediator), same trick MarkerEditPanel/MarkerToolPanel use."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QComboBox, QCheckBox, QColorDialog,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.brush.slider import BrushSlider
from src.engines.light import LIGHT_TYPES, POSITIONED_TYPES


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
        font-weight: {Typography.WEIGHT_MEDIUM}; background: transparent; border: none;
    """)
    return lbl


class _InfoRow(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_field_label(label))
        self.value = QLabel("—")
        self.value.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_PRIMARY};
            background: transparent; border: none;
        """)
        layout.addWidget(self.value, 1)

    def set_value(self, text: str):
        self.value.setText(text)


class _ColorSwatch(QToolButton):
    """A simple flat-color picker (native QColorDialog) — unlike the text
    panel's ColorField, a light's color has no multi-color "pattern" concept
    behind it, so a direct native picker here is the right amount of UI."""

    color_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#FFCB6B"
        self.setFixedSize(60, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._apply()

    def _pick(self):
        color = QColorDialog.getColor(QColor(self._color), self, "Cor da luz")
        if color.isValid():
            self.set_color(color.name(), emit=True)

    def set_color(self, hex_color: str, emit: bool = False):
        self._color = hex_color
        self._apply()
        if emit:
            self.color_changed.emit(hex_color)

    def _apply(self):
        self.setStyleSheet(f"""
            QToolButton {{ background: {self._color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
        """)


class LightEditPanel(QFrame):
    PANEL_WIDTH = 280

    type_changed = Signal(str)
    intensity_changed = Signal(float)
    radius_changed = Signal(float)
    color_changed = Signal(str)
    shadows_changed = Signal(bool)
    volumetric_changed = Signal(bool)
    close_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("💡 ILUMINAÇÃO")
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
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        layout.addWidget(self._sep())

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_row.addWidget(_field_label("Tipo"))
        self.type_combo = QComboBox()
        self.type_combo.setFixedHeight(26)
        self.type_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(10, 16, 30, 0.7); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 3px 8px; color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_XS}px;
            }}
            QComboBox QAbstractItemView {{
                background: rgba(20, 32, 55, 0.95); border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        for key, icon, label in LIGHT_TYPES:
            self.type_combo.addItem(f"{icon} {label}", key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self.type_combo, 1)
        layout.addLayout(type_row)

        pos_row = QHBoxLayout()
        pos_row.setSpacing(16)
        self.pos_x_row = _InfoRow("X")
        self.pos_y_row = _InfoRow("Y")
        pos_row.addWidget(self.pos_x_row)
        pos_row.addWidget(self.pos_y_row)
        self._pos_widget = QFrame()
        self._pos_widget.setStyleSheet("background: transparent; border: none;")
        self._pos_widget.setLayout(pos_row)
        layout.addWidget(self._pos_widget)

        self.intensity_slider = BrushSlider("Intensidade", "☀", 0, 100, 75, "%")
        self.intensity_slider.value_changed.connect(lambda v: self._emit(self.intensity_changed, v / 100.0))
        layout.addWidget(self.intensity_slider)

        self.radius_slider = BrushSlider("Raio", "◎", 0, 2000, 50, "m")
        self.radius_slider.value_changed.connect(lambda v: self._emit(self.radius_changed, v))
        layout.addWidget(self.radius_slider)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        color_row.addWidget(_field_label("Cor"))
        self.color_swatch = _ColorSwatch()
        self.color_swatch.color_changed.connect(lambda c: self._emit(self.color_changed, c))
        color_row.addWidget(self.color_swatch)
        color_row.addStretch()
        layout.addLayout(color_row)

        self.shadows_check = QCheckBox("Ativadas")
        self.shadows_check.setStyleSheet(self._checkbox_style())
        self.shadows_check.toggled.connect(lambda c: self._emit(self.shadows_changed, c))
        layout.addLayout(self._check_row("Sombras", self.shadows_check))

        self.volumetric_check = QCheckBox("Ativado")
        self.volumetric_check.setStyleSheet(self._checkbox_style())
        self.volumetric_check.toggled.connect(lambda c: self._emit(self.volumetric_changed, c))
        layout.addLayout(self._check_row("Volumétrico", self.volumetric_check))

    @staticmethod
    def _checkbox_style() -> str:
        return f"""
            QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: {Typography.SIZE_XS}px; background: transparent; border: none; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 15px; height: 15px; border-radius: 3px;
                border: 1px solid {Colors.BORDER}; background: rgba(10, 16, 30, 0.7);
            }}
            QCheckBox::indicator:checked {{ background: {Colors.ACCENT}; border-color: {Colors.ACCENT}; }}
        """

    @staticmethod
    def _check_row(label: str, checkbox: QCheckBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_field_label(label))
        row.addWidget(checkbox)
        row.addStretch()
        return row

    @staticmethod
    def _sep() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _emit(self, signal, value):
        if not self._syncing:
            signal.emit(value)

    def _on_type_changed(self, index: int):
        key = self.type_combo.itemData(index)
        self._pos_widget.setVisible(key in POSITIONED_TYPES)
        self.content_changed.emit()
        if not self._syncing:
            self.type_changed.emit(key)

    # ─── Public API ───

    def set_data(self, props, pos_x: float, pos_y: float):
        self._syncing = True
        idx = self.type_combo.findData(props.light_type)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._pos_widget.setVisible(props.light_type in POSITIONED_TYPES)
        self.pos_x_row.set_value(f"{pos_x:.0f} m")
        self.pos_y_row.set_value(f"{pos_y:.0f} m")
        self.intensity_slider.set_value(props.intensity * 100)
        self.radius_slider.set_value(props.radius)
        self.color_swatch.set_color(props.color)
        self.shadows_check.setChecked(props.shadows)
        self.volumetric_check.setChecked(props.volumetric)
        self._syncing = False

    def paintEvent(self, event):
        paint_glass_panel(self)
