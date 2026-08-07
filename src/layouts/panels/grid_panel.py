"""Grid Settings Panel — side panel matching brush panel style."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
    QCheckBox, QComboBox, QToolButton, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography, combo_popup_qss
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.stepper import NumberStepper
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider


class GridColorField(QFrame):
    """Label + swatch that toggles an inline HueBar/SatValSquare/RGB/hex
    picker embedded directly in the panel — same pattern as
    LightEditPanel's _ColorField, trimmed of presets/revert (the grid line
    color has no "previous value" worth restoring)."""

    color_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._color = QColor(255, 255, 255)
        self._hsv = [0, 0, 100]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("Color")
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        row.addWidget(label)

        self.swatch = QToolButton()
        self.swatch.setFixedSize(28, 20)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.clicked.connect(self._toggle)
        row.addWidget(self.swatch)
        row.addStretch()
        outer.addLayout(row)

        self._picker = QFrame()
        self._picker.setStyleSheet("background: transparent; border: none;")
        picker_lay = QVBoxLayout(self._picker)
        picker_lay.setContentsMargins(0, 0, 0, 0)
        picker_lay.setSpacing(6)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(14)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        picker_lay.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(80)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        picker_lay.addWidget(self._sv_square)

        self._r_slider = ColorSlider("R", 0, 255, 255)
        self._g_slider = ColorSlider("G", 0, 255, 255)
        self._b_slider = ColorSlider("B", 0, 255, 255)
        for slider in (self._r_slider, self._g_slider, self._b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
            picker_lay.addWidget(slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hash_label = QLabel("#")
        hash_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hash_label)
        self._hex_input = QLineEdit()
        self._hex_input.setFixedHeight(22)
        self._hex_input.setMaxLength(6)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 0 4px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_input, 1)
        picker_lay.addLayout(hex_row)

        outer.addWidget(self._picker)
        self._picker.hide()

        self._apply_swatch()

    def _toggle(self):
        self._picker.setVisible(not self._picker.isVisible())

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1], self._hsv[2] = s, v
        self._apply_hsv()

    def _apply_hsv(self):
        h, s, v = self._hsv
        color = QColor.fromHsv(h, round(s * 255 / 100), round(v * 255 / 100))
        self._sync_rgb_sliders(color)
        self._sync_hex_input(color)
        self._set_color(color, emit=True)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value())
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.blockSignals(True)
        self._hue_bar.set_hue(self._hsv[0])
        self._hue_bar.blockSignals(False)
        self._sv_square.blockSignals(True)
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sv_square.blockSignals(False)
        self._sync_hex_input(color)
        self._set_color(color, emit=True)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) != 6:
            return
        try:
            r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            return
        self.set_color(QColor(r, g, b).name(), emit=True)

    def _sync_rgb_sliders(self, color: QColor):
        for slider, value in ((self._r_slider, color.red()), (self._g_slider, color.green()),
                               (self._b_slider, color.blue())):
            slider.blockSignals(True)
            slider.set_value(value)
            slider.blockSignals(False)

    def _sync_hex_input(self, color: QColor | None = None):
        color = color or self._color
        self._hex_input.blockSignals(True)
        self._hex_input.setText(color.name(QColor.NameFormat.HexRgb).lstrip("#").upper())
        self._hex_input.blockSignals(False)

    def _apply_swatch(self):
        self.swatch.setStyleSheet(f"""
            QToolButton {{ background: {self._color.name()}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)

    def _set_color(self, color: QColor, emit: bool):
        self._color = color
        self._apply_swatch()
        if emit:
            self.color_changed.emit(color.name())

    def set_color(self, hex_color: str, emit: bool = False):
        """Sync the field (swatch + picker) to hex_color without necessarily
        emitting — used to load the grid's current color on panel open."""
        color = QColor(hex_color)
        if not color.isValid():
            return
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_rgb_sliders(color)
        self._sync_hex_input(color)
        self._set_color(color, emit=emit)

    def color(self) -> str:
        return self._color.name()


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
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Same scroll-wrapped-container pattern as every other toolbar
        # panel (Brush/Terrain/Text): grows with its content and only
        # shows a scrollbar when the window is too short to fit it, instead
        # of silently clipping.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        outer.addWidget(scroll)

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
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
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
            {combo_popup_qss()}
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

        layout.addWidget(self._sep())
        self.color_field = GridColorField()
        layout.addWidget(self.color_field)

        scroll.setWidget(container)

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
        from src.layouts.panel_manager import paint_glass_panel
        paint_glass_panel(self)
