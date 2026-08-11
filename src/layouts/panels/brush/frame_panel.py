"""Frame Panel — aba 🖼 Moldura do BrushToolPanel.

Grid de thumbnails das imagens em library/frames/ com glow neon pulsante
na selecionada, mais opções de linha sólida/dupla.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from src.styles.tokens import Colors, combo_qss
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider

_BG_SECTION = "rgba(255, 255, 255, 0.04)"
_BORDER     = "rgba(255, 255, 255, 0.10)"
_ACCENT     = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM
_TEXT       = Colors.TEXT_PRIMARY
_TEXT_SEC   = Colors.TEXT_SECONDARY
_TEXT_MUTED = Colors.TEXT_MUTED

_FRAMES_DIR = Path(__file__).resolve().parents[4] / "library" / "frames"
_EXTS       = {".png", ".jpg", ".jpeg", ".webp"}


# ─── Neon thumb ──────────────────────────────────────────────────────────────

class _NeonFrameThumb(QToolButton):
    """Thumbnail de moldura com glow neon pulsante quando selecionado."""

    _NEON         = QColor(0, 230, 255)   # ciano neon
    _PULSE_INTERVAL = 40
    _PULSE_MIN    = 60
    _PULSE_MAX    = 220
    _PULSE_STEP   = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._glow_alpha = 0
        self._glow_dir   = 1
        self._timer      = None
        self._apply_style(False)

    def set_selected(self, selected: bool):
        self.setChecked(selected)
        self._apply_style(selected)
        if selected:
            if self._timer is None:
                from PySide6.QtCore import QTimer
                self._timer = QTimer(self)
                self._timer.setInterval(self._PULSE_INTERVAL)
                self._timer.timeout.connect(self._tick)
            self._glow_alpha = self._PULSE_MIN
            self._timer.start()
        else:
            if self._timer:
                self._timer.stop()
            self._glow_alpha = 0
            self.update()

    def _tick(self):
        self._glow_alpha += self._PULSE_STEP * self._glow_dir
        if self._glow_alpha >= self._PULSE_MAX:
            self._glow_alpha = self._PULSE_MAX
            self._glow_dir = -1
        elif self._glow_alpha <= self._PULSE_MIN:
            self._glow_alpha = self._PULSE_MIN
            self._glow_dir = 1
        self.update()

    def _apply_style(self, selected: bool):
        border = _ACCENT if selected else _BORDER
        bg     = _ACCENT_DIM if selected else _BG_SECTION
        self.setStyleSheet(f"""
            QToolButton {{
                border: 2px solid {border}; border-radius: 6px;
                background: {bg};
            }}
            QToolButton:hover {{ border-color: {_TEXT_SEC}; }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked() or self._glow_alpha <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        glow = QColor(self._NEON)
        glow.setAlpha(int(self._glow_alpha * 0.4))
        p.setPen(QPen(glow, 8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)
        core = QColor(255, 255, 255)  # branco
        core.setAlpha(self._glow_alpha)
        p.setPen(QPen(core, 2))
        p.drawRoundedRect(r, 6, 6)
        p.end()


# ─── Frame Panel ─────────────────────────────────────────────────────────────

class FramePanel(QWidget):
    """Página da aba Moldura — tipo + opções de linha + grid de imagens."""

    frame_changed = Signal()  # emitido sempre que qualquer opção muda

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._asset_path = ""
        self._frame_color = "#4FC3F7"
        self._thumb_btns: list[_NeonFrameThumb] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Tipo ──
        top = QWidget()
        top.setStyleSheet("background: transparent;")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(10, 8, 10, 6)
        top_lay.setSpacing(6)

        lbl = QLabel("TIPO DE MOLDURA")
        lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        top_lay.addWidget(lbl)

        self._type_combo = QComboBox()
        for value, label in [("none", "Nenhuma"), ("solid", "Linha sólida"), ("double", "Linha dupla"), ("asset", "Imagem")]:
            self._type_combo.addItem(label, value)
        self._type_combo.setStyleSheet(combo_qss())
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_lay.addWidget(self._type_combo)
        outer.addWidget(top)

        # ── Opções de linha ──
        self._line_widget = self._build_line_options()
        outer.addWidget(self._line_widget)

        # ── Grid de imagens ──
        self._asset_widget = self._build_asset_grid()
        outer.addWidget(self._asset_widget, 1)

        self._on_type_changed(0)

    # ─── Linha ───────────────────────────────────────────────────────────

    def _build_line_options(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 0, 10, 8)
        lay.setSpacing(6)

        # Cor
        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        color_lbl = QLabel("Cor")
        color_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        color_row.addWidget(color_lbl)
        color_row.addStretch()
        self._color_btn = QToolButton()
        self._color_btn.setFixedSize(32, 20)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        color_row.addWidget(self._color_btn)
        lay.addLayout(color_row)

        self._color_picker = self._build_color_picker()
        self._color_picker.hide()
        lay.addWidget(self._color_picker)

        # Espessura
        width_row = QHBoxLayout()
        width_row.setSpacing(6)
        width_lbl = QLabel("Espessura")
        width_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        width_row.addWidget(width_lbl)
        width_row.addStretch()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 60)
        self._width_spin.setValue(6)
        self._width_spin.setSuffix(" px")
        self._width_spin.setFixedWidth(70)
        self._width_spin.setStyleSheet(self._spin_qss())
        width_row.addWidget(self._width_spin)
        lay.addLayout(width_row)

        # Estilo
        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        style_lbl = QLabel("Estilo")
        style_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        style_row.addWidget(style_lbl)
        style_row.addStretch()
        self._style_combo = QComboBox()
        for value, label in [("solid", "Sólida"), ("dashed", "Tracejada"), ("double", "Dupla")]:
            self._style_combo.addItem(label, value)
        self._style_combo.setFixedWidth(100)
        self._style_combo.setStyleSheet(combo_qss())
        style_row.addWidget(self._style_combo)
        lay.addLayout(style_row)

        # Raio
        radius_row = QHBoxLayout()
        radius_row.setSpacing(6)
        radius_lbl = QLabel("Raio dos cantos")
        radius_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        radius_row.addWidget(radius_lbl)
        radius_row.addStretch()
        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(0, 120)
        self._radius_spin.setValue(0)
        self._radius_spin.setSuffix(" px")
        self._radius_spin.setFixedWidth(70)
        self._radius_spin.setStyleSheet(self._spin_qss())
        radius_row.addWidget(self._radius_spin)
        lay.addLayout(radius_row)

        return w

    def _spin_qss(self) -> str:
        return f"""
            QSpinBox {{
                background: rgba(255,255,255,0.06); border: 1px solid {_BORDER};
                border-radius: 4px; color: {_TEXT}; font-size: 11px; padding: 2px 4px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; }}
        """

    # ─── Grid de imagens ─────────────────────────────────────────────────

    def _build_asset_grid(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 3px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {_TEXT_MUTED}; border-radius: 1px; min-height: 16px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = FlowLayout(self._grid_container, spacing=4)
        self._grid_layout.setContentsMargins(10, 6, 10, 6)
        scroll.setWidget(self._grid_container)
        lay.addWidget(scroll)
        return w

    # ─── Lógica ──────────────────────────────────────────────────────────

    def _on_type_changed(self, _index: int):
        ftype = self._type_combo.currentData()
        self._line_widget.setVisible(ftype in ("solid", "double"))
        self._asset_widget.setVisible(ftype == "asset")
        self.frame_changed.emit()

    def content_height(self) -> int:
        """Altura real do conteúdo visível — sem grid fixo para 'Nenhuma',
        com opções de linha para solid/double, com grid para asset."""
        ftype = self._type_combo.currentData()
        # bloco do tipo (label + combo)
        top = self.layout().itemAt(0).widget()
        top.adjustSize()
        h = top.sizeHint().height()
        if ftype in ("solid", "double"):
            self._line_widget.adjustSize()
            h += self._line_widget.sizeHint().height()
        elif ftype == "asset":
            h += 220  # grid com scroll — altura mínima útil
        return h + 8

    # ─── Cor (in-panel picker — no native OS QColorDialog, which renders
    # as a window outside the app; same pattern as RegionEditPanel's
    # _build_color_picker/terrain's BackgroundSection) ─────────────────

    def _build_color_picker(self) -> QFrame:
        widget = QFrame()
        widget.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(16)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        lay.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(90)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        lay.addWidget(self._sv_square)

        color = QColor(self._frame_color)
        self._r_slider = ColorSlider("R", 0, 255, color.red())
        self._g_slider = ColorSlider("G", 0, 255, color.green())
        self._b_slider = ColorSlider("B", 0, 255, color.blue())
        for slider in (self._r_slider, self._g_slider, self._b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
        lay.addWidget(self._r_slider)
        lay.addWidget(self._g_slider)
        lay.addWidget(self._b_slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
        self._hex_input = QLineEdit()
        self._hex_input.setFixedHeight(22)
        self._hex_input.setMaxLength(6)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {_BORDER};
                border-radius: 4px; color: {_TEXT}; font-size: 10px; padding: 0 4px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_input, 1)
        lay.addLayout(hex_row)

        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_hex_input()
        return widget

    def _pick_color(self):
        self._color_picker.setVisible(not self._color_picker.isVisible())
        self.frame_changed.emit()

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
        self._set_frame_color(color)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value())
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._set_frame_color(color)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) != 6:
            return
        try:
            r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            return
        color = QColor(r, g, b)
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_rgb_sliders(color)
        self._set_frame_color(color)

    def _sync_rgb_sliders(self, color: QColor):
        for slider, value in ((self._r_slider, color.red()), (self._g_slider, color.green()),
                               (self._b_slider, color.blue())):
            slider.blockSignals(True)
            slider.set_value(value)
            slider.blockSignals(False)

    def _sync_hex_input(self):
        self._hex_input.blockSignals(True)
        self._hex_input.setText(QColor(self._frame_color).name(QColor.NameFormat.HexRgb).lstrip("#").upper())
        self._hex_input.blockSignals(False)

    def _set_frame_color(self, color: QColor):
        self._frame_color = color.name()
        self._sync_hex_input()
        self._refresh_color_btn()
        self.frame_changed.emit()

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(f"""
            QToolButton {{
                background: {self._frame_color}; border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
        """)

    def refresh_assets(self):
        """Recarrega o grid com os arquivos atuais de library/frames/."""
        _FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(f for f in _FRAMES_DIR.rglob("*") if f.is_file() and f.suffix.lower() in _EXTS)

        for btn in self._thumb_btns:
            self._grid_layout.removeWidget(btn)
            btn.set_selected(False)
            btn.hide()
            btn.deleteLater()
        self._thumb_btns.clear()

        none_btn = _NeonFrameThumb()
        none_btn.setText("\u2205")
        none_btn.setToolTip("Nenhuma")
        none_btn.set_selected(not self._asset_path)
        none_btn.clicked.connect(lambda: self._select("", none_btn))
        self._grid_layout.addWidget(none_btn)
        none_btn.show()
        self._thumb_btns.append(none_btn)

        for f in files:
            btn = _NeonFrameThumb()
            btn.setToolTip(f.stem)
            pix = QPixmap(str(f)).scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not pix.isNull():
                if pix.width() > 48 or pix.height() > 48:
                    x, y = (pix.width() - 48) // 2, (pix.height() - 48) // 2
                    pix = pix.copy(x, y, 48, 48)
                btn.setIcon(pix)
                btn.setIconSize(pix.size())
            btn.set_selected(str(f) == self._asset_path)
            path_str = str(f)
            btn.clicked.connect(lambda _=False, p=path_str, b=btn: self._select(p, b))
            self._grid_layout.addWidget(btn)
            btn.show()
            self._thumb_btns.append(btn)

        self._grid_layout.invalidate()

    def _select(self, path: str, selected_btn: _NeonFrameThumb):
        self._asset_path = path
        for btn in self._thumb_btns:
            btn.set_selected(btn is selected_btn)
        self.frame_changed.emit()

    # ─── Public API ──────────────────────────────────────────────────────

    def frame_options(self) -> dict:
        """Dict no formato que map_exporter espera."""
        ftype = self._type_combo.currentData()
        if ftype == "none":
            return {"frame_type": "none"}
        if ftype == "asset":
            return {"frame_type": "asset", "frame_asset_path": self._asset_path}
        style = self._style_combo.currentData()
        return {
            "frame_type": "solid",
            "frame_style": "double" if ftype == "double" else style,
            "frame_color": self._frame_color,
            "frame_width": self._width_spin.value(),
            "frame_radius": self._radius_spin.value(),
        }
