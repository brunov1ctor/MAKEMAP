"""Text Tool Panel — two sections: "Texto" (content, font family/weight/
size, color, alignment, line/letter spacing) and "Estilo" (shadow, outline,
glow, curvature, opacity, Enfeites). Shown/hidden together with the "Texto"
tool or whenever a text object is selected, same pattern as SelectToolPanel
is with "Selecionar". Scrolls when expanded sections don't fit the
available height — same QScrollArea-wrapped-container structure as
TerrainSettingsPanel, so PanelManager's generic content-height measuring
(which special-cases a QScrollArea child) sizes it correctly without needing
its own content_height() override."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QToolButton,
    QDoubleSpinBox, QComboBox, QSizePolicy, QButtonGroup, QSlider, QCheckBox,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panels.color_field import ColorField
from src.engines.typography import TextAlign, TextProperties

FONT_FAMILIES = ["Poppins", "Segoe UI", "Arial", "Georgia", "Roboto", "Montserrat", "Times New Roman"]

# (display name, QFont weight value) — used by both the Fonte weight combo
# and the quick Bold toggle button.
FONT_WEIGHTS = [
    ("Thin", 100), ("Light", 300), ("Regular", 400), ("Medium", 500),
    ("Semibold", 600), ("Bold", 700), ("Black", 900),
]

_ALIGN_OPTIONS = [
    (TextAlign.LEFT, "left"), (TextAlign.CENTER, "center"),
    (TextAlign.RIGHT, "right"), (TextAlign.JUSTIFY, "justify"),
]

# Curvature is exposed to the user as a plain 0-100% slider; TextCurve
# underneath is parameterized by an arc radius (smaller = tighter curve),
# so map one to the other at the panel boundary rather than teaching the
# renderer about percentages.
_CURVE_RADIUS_AT_0 = 630.0
_CURVE_RADIUS_AT_100 = 30.0


def radius_from_percent(percent: float) -> float:
    t = max(0.0, min(100.0, percent)) / 100.0
    return _CURVE_RADIUS_AT_0 + t * (_CURVE_RADIUS_AT_100 - _CURVE_RADIUS_AT_0)


def percent_from_radius(radius: float) -> float:
    t = (radius - _CURVE_RADIUS_AT_0) / (_CURVE_RADIUS_AT_100 - _CURVE_RADIUS_AT_0)
    return max(0.0, min(100.0, t * 100.0))


def _align_icon(kind: str, color: str) -> QPixmap:
    """Small hand-painted alignment icon — the project has no icon font, so
    alignment buttons draw their own lines-of-text glyph."""
    w, h = 16, 12
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(QColor(color))
    widths = {
        "left": [14, 9, 12, 7], "center": [14, 8, 12, 6],
        "right": [14, 9, 12, 7], "justify": [14, 14, 14, 14],
    }[kind]
    y = 1
    for line_w in widths:
        if kind == "right":
            x = w - line_w
        elif kind == "center":
            x = (w - line_w) // 2
        else:
            x = 0
        p.drawLine(x, y, x + line_w, y)
        y += 3
    p.end()
    return pm


class ToggleSwitch(QCheckBox):
    """Compact iOS-style pill toggle — the mockup's Sombra/Contorno/Brilho
    enable switches don't fit QCheckBox's default box-and-check look."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QCheckBox::indicator { width: 0px; height: 0px; }")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg = QColor(Colors.ACCENT) if self.isChecked() else QColor(60, 66, 78)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = rect.height() / 2
        p.drawRoundedRect(rect, radius, radius)
        knob_d = rect.height() - 4
        knob_x = rect.right() - knob_d - 1 if self.isChecked() else rect.left() + 1
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(knob_x, rect.top() + 2, knob_d, knob_d)


class TextToolPanel(QFrame):
    """Panel shown while the Texto tool is active (or a text object is
    selected) — edits the TextProperties of the current text object(s)."""

    PANEL_WIDTH = 300

    font_family_changed = Signal(str)
    font_weight_changed = Signal(int)
    font_size_changed = Signal(float)
    bold_changed = Signal(bool)
    italic_changed = Signal(bool)
    color_changed = Signal(str)
    align_changed = Signal(object)  # TextAlign
    line_height_changed = Signal(float)
    letter_spacing_changed = Signal(float)

    shadow_toggled = Signal(bool)
    shadow_color_changed = Signal(str)
    shadow_opacity_changed = Signal(float)  # 0-100
    shadow_x_changed = Signal(float)
    shadow_y_changed = Signal(float)
    shadow_blur_changed = Signal(float)

    outline_toggled = Signal(bool)
    outline_color_changed = Signal(str)
    outline_width_changed = Signal(float)

    glow_toggled = Signal(bool)
    glow_color_changed = Signal(str)
    glow_blur_changed = Signal(float)

    curvature_changed = Signal(float)  # 0-100
    opacity_changed = Signal(float)  # 0-100

    # Enfeites — outline_toggled (above) is reused for the "Contorno" checkbox.
    strikethrough_toggled = Signal(bool)
    overline_toggled = Signal(bool)
    underline_toggled = Signal(bool)
    double_underline_toggled = Signal(bool)
    box_toggled = Signal(bool)  # "Caixa" -> ribbon.enabled
    cloud_toggled = Signal(bool)
    serif_toggled = Signal(bool)

    content_changed = Signal()  # a section expanded/collapsed — panel needs re-sizing
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._syncing = False  # suppress signal emission while set_values() applies

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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
        self._container = container
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(8)
        scroll.setWidget(container)

        layout.addLayout(self._build_header())
        layout.addWidget(self._separator())

        # Section 1 — content, font, color, alignment, spacing: everything
        # you touch while actively writing a label, so it stays one section
        # instead of forcing extra clicks to reveal each group.
        text_section = CollapsibleSection("Texto")
        text_section.content_changed.connect(self.content_changed.emit)
        layout.addWidget(text_section)
        section_layout = text_section.content_layout
        font_row = QHBoxLayout()
        font_row.setSpacing(6)
        self.family_combo = QComboBox()
        self.family_combo.addItems(FONT_FAMILIES)
        self.family_combo.setStyleSheet(self._combo_style())
        self.family_combo.currentTextChanged.connect(lambda v: self._emit(self.font_family_changed, v))
        font_row.addWidget(self.family_combo, 3)
        self.weight_combo = QComboBox()
        for label, _value in FONT_WEIGHTS:
            self.weight_combo.addItem(label)
        self.weight_combo.setStyleSheet(self._combo_style())
        self.weight_combo.currentIndexChanged.connect(self._on_weight_combo)
        font_row.addWidget(self.weight_combo, 2)
        section_layout.addLayout(font_row)
        section_layout.addWidget(self._separator())

        size_peso_row = QHBoxLayout()
        size_peso_row.setSpacing(6)
        size_col = QVBoxLayout()
        size_col.addWidget(self._section_label("Tamanho"))
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(4.0, 200.0)
        self.size_spin.setDecimals(0)
        self.size_spin.setValue(20.0)
        self.size_spin.setSuffix(" px")
        self.size_spin.setStyleSheet(self._spin_style())
        self.size_spin.valueChanged.connect(lambda v: self._emit(self.font_size_changed, float(v)))
        size_col.addWidget(self.size_spin)
        size_peso_row.addLayout(size_col, 1)

        peso_col = QVBoxLayout()
        peso_col.addWidget(self._section_label("Peso"))
        peso_btns = QHBoxLayout()
        peso_btns.setSpacing(4)
        self.bold_btn = QToolButton()
        self.bold_btn.setText("B")
        self.bold_btn.setCheckable(True)
        self.bold_btn.setFixedSize(28, 26)
        self.bold_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bold_btn.setStyleSheet(self._toggle_style(bold=True))
        self.bold_btn.toggled.connect(self._on_bold_toggled)
        peso_btns.addWidget(self.bold_btn)

        self.italic_btn = QToolButton()
        self.italic_btn.setText("I")
        self.italic_btn.setCheckable(True)
        self.italic_btn.setFixedSize(28, 26)
        self.italic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.italic_btn.setStyleSheet(self._toggle_style(italic=True))
        self.italic_btn.toggled.connect(lambda v: self._emit(self.italic_changed, bool(v)))
        peso_btns.addWidget(self.italic_btn)

        self.caps_btn = QToolButton()
        self.caps_btn.setText("aA")
        self.caps_btn.setCheckable(True)
        self.caps_btn.setFixedSize(28, 26)
        self.caps_btn.setEnabled(False)
        self.caps_btn.setToolTip("Caixa alta — em breve")
        self.caps_btn.setStyleSheet(self._toggle_style())
        peso_btns.addWidget(self.caps_btn)
        peso_col.addLayout(peso_btns)
        size_peso_row.addLayout(peso_col, 1)
        section_layout.addLayout(size_peso_row)
        section_layout.addWidget(self._separator())

        section_layout.addWidget(self._section_label("Cor do Texto"))
        self.color_field = ColorField("#FFFFFF", "Cor do texto")
        self.color_field.color_changed.connect(lambda v: self._emit(self.color_changed, v))
        section_layout.addWidget(self.color_field)
        section_layout.addWidget(self._separator())

        section_layout.addWidget(self._section_label("Alinhamento"))
        align_row = QHBoxLayout()
        align_row.setSpacing(4)
        self._align_group = QButtonGroup(self)
        self._align_group.setExclusive(True)
        self._align_buttons: dict[TextAlign, QToolButton] = {}
        for align, kind in _ALIGN_OPTIONS:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setFixedSize(32, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(_align_icon(kind, Colors.TEXT_SECONDARY))
            btn.setStyleSheet(self._toggle_style())
            btn.clicked.connect(lambda _checked, a=align: self._on_align_clicked(a))
            self._align_group.addButton(btn)
            self._align_buttons[align] = btn
            align_row.addWidget(btn)
        align_row.addStretch()
        section_layout.addLayout(align_row)
        section_layout.addWidget(self._separator())

        section_layout.addWidget(self._section_label("Espaçamento"))
        spacing_row = QHBoxLayout()
        spacing_row.setSpacing(10)
        lh_col = QVBoxLayout()
        lh_label = QLabel("Entre Linhas")
        lh_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        lh_col.addWidget(lh_label)
        self.line_height_spin = QDoubleSpinBox()
        self.line_height_spin.setRange(0.5, 4.0)
        self.line_height_spin.setSingleStep(0.1)
        self.line_height_spin.setDecimals(1)
        self.line_height_spin.setValue(1.2)
        self.line_height_spin.setStyleSheet(self._spin_style())
        self.line_height_spin.valueChanged.connect(lambda v: self._emit(self.line_height_changed, float(v)))
        lh_col.addWidget(self.line_height_spin)
        spacing_row.addLayout(lh_col)

        ls_col = QVBoxLayout()
        ls_label = QLabel("Entre Letras")
        ls_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        ls_col.addWidget(ls_label)
        self.letter_spacing_spin = QDoubleSpinBox()
        self.letter_spacing_spin.setRange(-10.0, 50.0)
        self.letter_spacing_spin.setDecimals(0)
        self.letter_spacing_spin.setSuffix(" px")
        self.letter_spacing_spin.setValue(0.0)
        self.letter_spacing_spin.setStyleSheet(self._spin_style())
        self.letter_spacing_spin.valueChanged.connect(lambda v: self._emit(self.letter_spacing_changed, float(v)))
        ls_col.addWidget(self.letter_spacing_spin)
        spacing_row.addLayout(ls_col)
        section_layout.addLayout(spacing_row)

        self._align_buttons[TextAlign.CENTER].setChecked(True)

        # Section 2 — shadow / outline / glow / curvature / opacity.
        style_section = CollapsibleSection("Estilo")
        style_section.content_changed.connect(self.content_changed.emit)
        self._build_style_section(style_section.content_layout)
        layout.addWidget(style_section)

    # ─── Estilo section (shadow / outline / glow / curvature / opacity) ───

    def _build_style_section(self, layout: QVBoxLayout):
        self.shadow_toggle, shadow_body = self._build_shadow_section()
        layout.addLayout(self._toggle_row("Sombra", self.shadow_toggle))
        layout.addLayout(shadow_body)
        layout.addWidget(self._separator())

        self.outline_toggle, outline_body = self._build_outline_section()
        layout.addLayout(self._toggle_row("Contorno", self.outline_toggle))
        layout.addLayout(outline_body)
        layout.addWidget(self._separator())

        self.glow_toggle, glow_body = self._build_glow_section()
        layout.addLayout(self._toggle_row("Brilho", self.glow_toggle))
        layout.addLayout(glow_body)
        layout.addWidget(self._separator())

        layout.addWidget(self._section_label("Curvatura"))
        self.curvature_slider, self.curvature_value = self._build_slider(0)
        self.curvature_slider.valueChanged.connect(self._on_curvature_changed)
        layout.addLayout(self._slider_row(self.curvature_slider, self.curvature_value))
        layout.addWidget(self._separator())

        layout.addWidget(self._section_label("Opacidade"))
        self.opacity_slider, self.opacity_value = self._build_slider(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        layout.addLayout(self._slider_row(self.opacity_slider, self.opacity_value))
        layout.addWidget(self._separator())

        layout.addWidget(self._section_label("Enfeites"))
        layout.addLayout(self._build_effects_grid())

    def _build_effects_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        self.strikethrough_check = self._build_checkbox()
        self.strikethrough_check.toggled.connect(lambda v: self._emit(self.strikethrough_toggled, v))
        grid.addLayout(self._effects_row("Tachado", self.strikethrough_check), 0, 0)

        self.outline_effect_check = self._build_checkbox()
        self.outline_effect_check.toggled.connect(self._on_outline_effect_toggled)
        grid.addLayout(self._effects_row("Contorno", self.outline_effect_check), 0, 1)

        self.overline_check = self._build_checkbox()
        self.overline_check.toggled.connect(lambda v: self._emit(self.overline_toggled, v))
        grid.addLayout(self._effects_row("Linha Acima", self.overline_check), 1, 0)

        self.box_check = self._build_checkbox()
        self.box_check.toggled.connect(lambda v: self._emit(self.box_toggled, v))
        grid.addLayout(self._effects_row("Caixa", self.box_check), 1, 1)

        self.underline_check = self._build_checkbox()
        self.underline_check.toggled.connect(lambda v: self._emit(self.underline_toggled, v))
        grid.addLayout(self._effects_row("Sublinhado", self.underline_check), 2, 0)

        self.cloud_check = self._build_checkbox()
        self.cloud_check.toggled.connect(lambda v: self._emit(self.cloud_toggled, v))
        grid.addLayout(self._effects_row("Nuvem", self.cloud_check), 2, 1)

        self.double_underline_check = self._build_checkbox()
        self.double_underline_check.toggled.connect(lambda v: self._emit(self.double_underline_toggled, v))
        grid.addLayout(self._effects_row("Duplo Sublinhado", self.double_underline_check), 3, 0)

        self.serif_check = self._build_checkbox()
        self.serif_check.toggled.connect(lambda v: self._emit(self.serif_toggled, v))
        grid.addLayout(self._effects_row("Serifa", self.serif_check), 3, 1)

        return grid

    def _on_outline_effect_toggled(self, checked: bool):
        """The "Contorno" checkbox in Enfeites is a second control over the
        same outline.enabled as the Sombra-style toggle above — keep both
        in sync instead of tracking two independent booleans."""
        if not self._syncing:
            self.outline_toggle.blockSignals(True)
            self.outline_toggle.setChecked(checked)
            self.outline_toggle.blockSignals(False)
            self._set_section_enabled(self._outline_controls, checked)
        self._emit(self.outline_toggled, checked)

    def _effects_row(self, label_text: str, checkbox: QCheckBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9pt; background: transparent; border: none;")
        row.addWidget(label)
        row.addStretch()
        row.addWidget(checkbox)
        return row

    @staticmethod
    def _build_checkbox() -> QCheckBox:
        cb = QCheckBox()
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(f"""
            QCheckBox {{ background: transparent; spacing: 0px; }}
            QCheckBox::indicator {{
                width: 13px; height: 13px; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 2px; background: rgba(255,255,255,0.04);
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.TEXT_PRIMARY}; border-color: {Colors.TEXT_PRIMARY};
            }}
        """)
        return cb

    def _build_shadow_section(self):
        toggle = ToggleSwitch()
        toggle.toggled.connect(self._on_shadow_toggled)

        body = QVBoxLayout()
        body.setSpacing(6)
        self.shadow_color = ColorField("#000000", "Cor da sombra")
        self.shadow_color.color_changed.connect(lambda v: self._emit(self.shadow_color_changed, v))
        body.addWidget(self.shadow_color)

        self.shadow_opacity = self._labeled_spin(0, 100, 80, " %")
        self.shadow_opacity.valueChanged.connect(lambda v: self._emit(self.shadow_opacity_changed, float(v)))
        body.addLayout(self._field_row("Opacidade", self.shadow_opacity))

        xyz_row = QHBoxLayout()
        xyz_row.setSpacing(6)
        self.shadow_x = self._labeled_spin(-50, 50, 3)
        self.shadow_x.valueChanged.connect(lambda v: self._emit(self.shadow_x_changed, float(v)))
        self.shadow_y = self._labeled_spin(-50, 50, 3)
        self.shadow_y.valueChanged.connect(lambda v: self._emit(self.shadow_y_changed, float(v)))
        self.shadow_blur = self._labeled_spin(0, 100, 6)
        self.shadow_blur.valueChanged.connect(lambda v: self._emit(self.shadow_blur_changed, float(v)))
        for label, spin in (("X", self.shadow_x), ("Y", self.shadow_y), ("Desfoque", self.shadow_blur)):
            xyz_row.addLayout(self._field_col(label, spin))
        body.addLayout(xyz_row)

        self._shadow_controls = [self.shadow_color, self.shadow_opacity, self.shadow_x, self.shadow_y, self.shadow_blur]
        self._set_section_enabled(self._shadow_controls, False)
        return toggle, body

    def _build_outline_section(self):
        toggle = ToggleSwitch()
        toggle.toggled.connect(self._on_outline_toggled)

        body = QVBoxLayout()
        body.setSpacing(6)
        self.outline_color = ColorField("#FFFFFF", "Cor do contorno")
        self.outline_color.color_changed.connect(lambda v: self._emit(self.outline_color_changed, v))
        body.addWidget(self.outline_color)

        self.outline_width = self._labeled_spin(0, 40, 2)
        self.outline_width.valueChanged.connect(lambda v: self._emit(self.outline_width_changed, float(v)))
        body.addLayout(self._field_row("Tamanho", self.outline_width))

        self._outline_controls = [self.outline_color, self.outline_width]
        self._set_section_enabled(self._outline_controls, False)
        return toggle, body

    def _build_glow_section(self):
        toggle = ToggleSwitch()
        toggle.toggled.connect(self._on_glow_toggled)

        body = QVBoxLayout()
        body.setSpacing(6)
        self.glow_color = ColorField("#3B82F6", "Cor do brilho")
        self.glow_color.color_changed.connect(lambda v: self._emit(self.glow_color_changed, v))
        body.addWidget(self.glow_color)

        self.glow_blur = self._labeled_spin(0, 100, 12)
        self.glow_blur.valueChanged.connect(lambda v: self._emit(self.glow_blur_changed, float(v)))
        body.addLayout(self._field_row("Desfoque", self.glow_blur))

        self._glow_controls = [self.glow_color, self.glow_blur]
        self._set_section_enabled(self._glow_controls, False)
        return toggle, body

    def _on_shadow_toggled(self, checked: bool):
        self._set_section_enabled(self._shadow_controls, checked)
        self._emit(self.shadow_toggled, checked)

    def _on_outline_toggled(self, checked: bool):
        self._set_section_enabled(self._outline_controls, checked)
        if not self._syncing:
            self.outline_effect_check.blockSignals(True)
            self.outline_effect_check.setChecked(checked)
            self.outline_effect_check.blockSignals(False)
        self._emit(self.outline_toggled, checked)

    def _on_glow_toggled(self, checked: bool):
        self._set_section_enabled(self._glow_controls, checked)
        self._emit(self.glow_toggled, checked)

    def _on_curvature_changed(self, value: int):
        self.curvature_value.setText(f"{value}%")
        self._emit(self.curvature_changed, float(value))

    def _on_opacity_changed(self, value: int):
        self.opacity_value.setText(f"{value}%")
        self._emit(self.opacity_changed, float(value))

    @staticmethod
    def _set_section_enabled(controls: list, enabled: bool):
        for control in controls:
            control.setEnabled(enabled)

    def _toggle_row(self, text: str, toggle: ToggleSwitch) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._section_label(text))
        row.addStretch()
        row.addWidget(toggle)
        return row

    def _labeled_spin(self, lo: float, hi: float, value: float, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(0)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        spin.setStyleSheet(self._spin_style())
        return spin

    def _field_row(self, label_text: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        row.addWidget(label)
        row.addStretch()
        widget.setFixedWidth(80)
        row.addWidget(widget)
        return row

    def _field_col(self, label_text: str, widget) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        col.addWidget(label)
        widget.setFixedWidth(56)
        col.addWidget(widget)
        return col

    @staticmethod
    def _build_slider(initial: int) -> tuple:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(initial)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 3px; background: {Colors.BORDER_SUBTLE}; border-radius: 1px; }}
            QSlider::sub-page:horizontal {{ background: {Colors.ACCENT}; border-radius: 1px; }}
            QSlider::handle:horizontal {{
                background: {Colors.TEXT_PRIMARY}; width: 12px; height: 12px;
                margin: -5px 0; border-radius: 6px;
            }}
        """)
        value_label = QLabel(f"{initial}%")
        value_label.setFixedWidth(32)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9pt; background: transparent; border: none;")
        return slider, value_label

    @staticmethod
    def _slider_row(slider: QSlider, value_label: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        return row

    # ─── Header / shared building blocks ───

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("T")
        icon.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Texto")
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
        return header

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10pt; background: transparent; border: none;")
        return label

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    @staticmethod
    def _combo_style() -> str:
        return f"""
            QComboBox {{
                background: rgba(255,255,255,0.04); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                padding: 3px 6px; font-size: 9pt;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; selection-background-color: {Colors.ACCENT_DIM};
            }}
        """

    @staticmethod
    def _spin_style() -> str:
        return f"""
            QDoubleSpinBox {{
                background: rgba(10, 16, 30, 0.7); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 2px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
            }}
            QDoubleSpinBox:disabled {{ color: {Colors.TEXT_DISABLED}; }}
        """

    @staticmethod
    def _toggle_style(bold=False, italic=False) -> str:
        weight = "font-weight: bold;" if bold else ""
        style = "font-style: italic;" if italic else ""
        return f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; {weight} {style}
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; border-color: {Colors.ACCENT};
            }}
            QToolButton:disabled {{ color: {Colors.TEXT_DISABLED}; }}
        """

    # ─── Interaction ───

    def _on_weight_combo(self, index: int):
        if index < 0:
            return
        weight = FONT_WEIGHTS[index][1]
        if not self._syncing:
            self.bold_btn.blockSignals(True)
            self.bold_btn.setChecked(weight >= 700)
            self.bold_btn.blockSignals(False)
        self._emit(self.font_weight_changed, weight)

    def _on_bold_toggled(self, checked: bool):
        weight = 700 if checked else 400
        if not self._syncing:
            self._set_weight_combo(weight)
        self._emit(self.font_weight_changed, weight)
        self._emit(self.bold_changed, checked)

    def _on_align_clicked(self, align: TextAlign):
        self._emit(self.align_changed, align)

    def _set_weight_combo(self, weight: int):
        nearest_idx = min(range(len(FONT_WEIGHTS)), key=lambda i: abs(FONT_WEIGHTS[i][1] - weight))
        self.weight_combo.blockSignals(True)
        self.weight_combo.setCurrentIndex(nearest_idx)
        self.weight_combo.blockSignals(False)

    def _emit(self, signal, value):
        if not self._syncing:
            signal.emit(value)

    # ─── Sync from model ───

    def set_values(self, props: TextProperties):
        """Sync every control to a TextItem's current properties without
        re-emitting change signals (avoids feedback loops on selection
        change)."""
        self._syncing = True

        idx = self.family_combo.findText(props.font_family)
        self.family_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._set_weight_combo(props.font_weight)

        self.size_spin.setValue(props.font_size)
        self.bold_btn.setChecked(props.font_weight >= 700)
        self.italic_btn.setChecked(props.italic)

        self.color_field.set_color(props.color)

        btn = self._align_buttons.get(props.align)
        if btn:
            btn.setChecked(True)

        self.line_height_spin.setValue(props.spacing.line_height)
        self.letter_spacing_spin.setValue(props.spacing.letter_spacing)

        self.shadow_toggle.setChecked(props.shadow.enabled)
        self.shadow_color.set_color(props.shadow.color)
        self.shadow_opacity.setValue(round(props.shadow.opacity * 100))
        self.shadow_x.setValue(props.shadow.offset_x)
        self.shadow_y.setValue(props.shadow.offset_y)
        self.shadow_blur.setValue(props.shadow.blur)
        self._set_section_enabled(self._shadow_controls, props.shadow.enabled)

        self.outline_toggle.setChecked(props.outline.enabled)
        self.outline_effect_check.setChecked(props.outline.enabled)
        self.outline_color.set_color(props.outline.color)
        self.outline_width.setValue(props.outline.width)
        self._set_section_enabled(self._outline_controls, props.outline.enabled)

        self.glow_toggle.setChecked(props.glow.enabled)
        self.glow_color.set_color(props.glow.color)
        self.glow_blur.setValue(props.glow.radius)
        self._set_section_enabled(self._glow_controls, props.glow.enabled)

        curvature = percent_from_radius(props.curve.radius) if props.curve.enabled else 0.0
        self.curvature_slider.setValue(round(curvature))
        self.curvature_value.setText(f"{round(curvature)}%")

        opacity_pct = round(props.opacity * 100)
        self.opacity_slider.setValue(opacity_pct)
        self.opacity_value.setText(f"{opacity_pct}%")

        self.strikethrough_check.setChecked(props.strikethrough)
        self.overline_check.setChecked(props.overline)
        self.underline_check.setChecked(props.underline)
        self.double_underline_check.setChecked(props.double_underline)
        self.box_check.setChecked(props.ribbon.enabled)
        self.cloud_check.setChecked(props.cloud)
        self.serif_check.setChecked(props.serif)

        self._syncing = False

    def paintEvent(self, event):
        paint_glass_panel(self)
