"""LightEditPanel — shown when an existing LightItem is selected. Shares
the same PanelManager dock slot as LightPanel (never visible together —
see LightMediator), same trick MarkerEditPanel/MarkerToolPanel use."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QComboBox, QCheckBox, QLineEdit,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider
from src.engines.light import GLOBAL_TYPES, LIGHT_TYPES, POSITIONED_TYPES


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
    """Flat-color button — clicking it toggles an in-panel picker (see
    _ColorField below) instead of popping a native OS QColorDialog, which
    renders as a separate top-level window outside the app (same fix as
    RegionEditPanel's color field / terrain's BackgroundSection)."""

    color_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#FFCB6B"
        self.setFixedSize(60, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply()

    def set_color(self, hex_color: str, emit: bool = False):
        self._color = hex_color
        self._apply()
        if emit:
            self.color_changed.emit(hex_color)

    def _apply(self):
        self.setStyleSheet(f"""
            QToolButton {{ background: {self._color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)


class _ColorField(QFrame):
    """Label + swatch button that toggles an inline HueBar/SatValSquare/RGB
    picker embedded directly in the panel — same pattern as
    RegionEditPanel._build_color_picker, reusing the same widgets from
    terrain/color_picker.py."""

    color_changed = Signal(str)
    toggled = Signal()  # picker expanded/collapsed — panel needs re-sizing

    def __init__(self, label: str, parent=None, presets: list[str] | None = None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._color = QColor("#FFCB6B")
        self._original_color = QColor(self._color)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_field_label(label))
        self.swatch = _ColorSwatch()
        self.swatch.clicked.connect(self._toggle)
        row.addWidget(self.swatch)

        self._revert_btn = QToolButton()
        self._revert_btn.setText("↺")
        self._revert_btn.setFixedSize(22, 22)
        self._revert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert_btn.setToolTip("Voltar à cor anterior")
        self._revert_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 12px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
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
        self._revert_btn.clicked.connect(self._revert)
        row.addWidget(self._revert_btn)
        row.addStretch()
        outer.addLayout(row)

        # Presets — one click to jump straight to a known-good color instead
        # of hunting for it again in the HSV picker (the exact complaint
        # that prompted adding this: no way back to a color once it's
        # overwritten, short of remembering its hex by heart).
        if presets:
            preset_row = QHBoxLayout()
            preset_row.setSpacing(4)
            for hex_color in presets:
                swatch = QToolButton()
                swatch.setFixedSize(18, 18)
                swatch.setCursor(Qt.CursorShape.PointingHandCursor)
                swatch.setToolTip(hex_color)
                swatch.setStyleSheet(f"""
                    QToolButton {{ background: {hex_color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 3px; }}
                    QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
                    QToolTip {{
                        background-color: {Colors.BG_ELEVATED};
                        color: {Colors.TEXT_PRIMARY};
                        border: 1px solid {Colors.BORDER};
                        border-radius: 8px;
                        padding: 6px 10px;
                        font-size: 11px;
                    }}
                """)
                swatch.clicked.connect(lambda _checked=False, c=hex_color: self.set_color(c, emit=True))
                preset_row.addWidget(swatch)
            preset_row.addStretch()
            outer.addLayout(preset_row)

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

        self._r_slider = ColorSlider("R", 0, 255, self._color.red())
        self._g_slider = ColorSlider("G", 0, 255, self._color.green())
        self._b_slider = ColorSlider("B", 0, 255, self._color.blue())
        for slider in (self._r_slider, self._g_slider, self._b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
        picker_lay.addWidget(self._r_slider)
        picker_lay.addWidget(self._g_slider)
        picker_lay.addWidget(self._b_slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
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

        h, s, v, _a = self._color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._sync_picker()

    def _toggle(self):
        self._picker.setVisible(not self._picker.isVisible())
        self.toggled.emit()

    def _revert(self):
        self.set_color(self._original_color.name(), emit=True)

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
        self.set_color(color.name(), emit=True, sync_picker=False)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value())
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_hex_input(color)
        self.set_color(color.name(), emit=True, sync_picker=False)

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

    def _sync_picker(self):
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_rgb_sliders(self._color)
        self._sync_hex_input()

    def set_color(self, hex_color: str, emit: bool = False, sync_picker: bool = True):
        self._color = QColor(hex_color)
        self.swatch.set_color(hex_color)
        if sync_picker:
            h, s, v, _a = self._color.getHsv()
            self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
            self._sync_picker()
        if not emit:
            # A non-emitting call is always an external load (set_data, on
            # panel open) rather than the user actively picking a color —
            # that's the baseline the ↺ revert button restores, so an
            # interactive edit followed by a revert always lands back on
            # "the color it was" instead of wherever the user last dragged
            # a slider to.
            self._original_color = QColor(hex_color)
        else:
            self.color_changed.emit(hex_color)


class LightEditPanel(QFrame):
    PANEL_WIDTH = 280

    type_changed = Signal(str)
    intensity_changed = Signal(float)
    radius_changed = Signal(float)
    falloff_changed = Signal(float)
    color_changed = Signal(str)
    shadows_changed = Signal(bool)
    volumetric_changed = Signal(bool)
    direction_changed = Signal(float)
    cone_changed = Signal(float)
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
        close_btn.setToolTip("Fechar")
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
                background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        # "sky" isn't a placeable object (see GLOBAL_TYPES) — an already
        # placed light can't be switched into being the map's single global
        # day/night setting, so it's left out of this per-item dropdown.
        for key, icon, label in LIGHT_TYPES:
            if key in GLOBAL_TYPES:
                continue
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

        # How evenly the light's own brightness spreads across its radius —
        # 0 = concentrated (a hot little core with a sharp cutoff near the
        # edge), 100 = diffuse (fades gradually, no hot spot). Separate from
        # radius (how far it reaches) — see LightProperties.falloff.
        self.falloff_slider = BrushSlider("Difusão", "◐", 0, 100, 50, "%")
        self.falloff_slider.value_changed.connect(lambda v: self._emit(self.falloff_changed, v))
        layout.addWidget(self.falloff_slider)

        # Only meaningful for "spot" (aims/narrows its cone) — hidden for
        # every other type, same show/hide trick as _pos_widget below.
        self.direction_slider = BrushSlider("Direção", "➤", 0, 360, 0, "°")
        self.direction_slider.value_changed.connect(lambda v: self._emit(self.direction_changed, v))
        layout.addWidget(self.direction_slider)

        self.cone_slider = BrushSlider("Abertura", "◺", 5, 180, 45, "°")
        self.cone_slider.value_changed.connect(lambda v: self._emit(self.cone_changed, v))
        layout.addWidget(self.cone_slider)

        self.color_field = _ColorField("Cor")
        self.color_field.color_changed.connect(lambda c: self._emit(self.color_changed, c))
        self.color_field.toggled.connect(self.content_changed.emit)
        layout.addWidget(self.color_field)

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
        is_spot = key == "spot"
        self.direction_slider.setVisible(is_spot)
        self.cone_slider.setVisible(is_spot)
        self.content_changed.emit()
        if not self._syncing:
            self.type_changed.emit(key)

    # ─── Public API ───

    def set_data(self, props, pos_x: float, pos_y: float):
        self._syncing = True
        idx = self.type_combo.findData(props.light_type)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._pos_widget.setVisible(props.light_type in POSITIONED_TYPES)
        is_spot = props.light_type == "spot"
        self.direction_slider.setVisible(is_spot)
        self.cone_slider.setVisible(is_spot)
        self.pos_x_row.set_value(f"{pos_x:.0f} m")
        self.pos_y_row.set_value(f"{pos_y:.0f} m")
        self.intensity_slider.set_value(props.intensity * 100)
        self.radius_slider.set_value(props.radius)
        self.falloff_slider.set_value(props.falloff)
        self.direction_slider.set_value(props.direction_deg)
        self.cone_slider.set_value(props.cone_angle_deg)
        self.color_field.set_color(props.color)
        self.shadows_check.setChecked(props.shadows)
        self.volumetric_check.setChecked(props.volumetric)
        self._syncing = False

    def paintEvent(self, event):
        paint_glass_panel(self)
