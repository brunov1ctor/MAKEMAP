"""ProgressionNodeDialog — the card's only editor: icon/name/level/notes/
border color, opened via the card's "⋮" menu (Editar) or a
double-click (see items.py._show_menu/mouseDoubleClickEvent) — the card
face itself has no click-to-edit affordances, everything routes through
here.

A plain child QWidget (semi-transparent backdrop + a glass card) — not a
QDialog, and (after trying it) not a separate top-level window either: a
real top-level window fixed the keyboard-focus race described below, but
introduced a worse problem — it's a genuinely different OS window, so
things like Alt-Tab/window-manager focus changes could leave the main app
window looking "hidden" behind it. Staying an embedded child keeps this
reading as an in-app floating panel, same as every other panel here.

That embedding is exactly why grabbing keyboard focus for a field needs
care: a child widget shares its parent's own top-level window, so if this
popup opens right after another popup (the "⋮" menu) closes on the same
tick, our setFocus() call can race Windows' own in-flight restoration of
focus to whatever that parent window had before — and lose, leaving
keystrokes routed to the map's WASD-pan shortcut instead of the field.
_run()/_claim_focus() below retries setFocus() a few times, a few ms
apart, stopping the instant hasFocus() actually confirms it — self-
correcting rather than trusting a single guessed delay (an earlier
version tried draining the queue with QApplication.processEvents()
instead, which turned out to have its own trap: it can dispatch an
already-queued close request before the popup's own QEventLoop starts
running, and QEventLoop.quit() silently no-ops when the loop isn't
executing yet — a real deadlock, not just a hypothetical).

Same run-a-local-QEventLoop pattern as mobs/edit_widgets.py's
_CatalogPickerDialog so `.exec()` still blocks the caller the way a real
QDialog's would. The map pin isn't edited here — it lives on the card's
own 📍/🎯 button (see items.py), since a modal popup would block clicking
the main map to place it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QToolButton,
)

from src.styles.tokens import Colors
from src.layouts.panels.shared.popup_overlay import PopupOverlay, IconPickerPopup
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider
from src.engines.marker import ICONS


class ProgressionNodeDialog(PopupOverlay):
    def __init__(self, icon: str, name: str, levels: str, notes: str,
                 border_color: str | None, auto_color: str, parent=None):
        super().__init__(card_width=340, parent=parent)
        self._icon = icon
        self._border_color = border_color
        self._auto_color = auto_color
        self._accepted = False

        style = f"""
            QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
            QLineEdit, QTextEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 5px; padding: 5px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
            QLineEdit:focus, QTextEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """
        self.card.setStyleSheet(style)

        outer = QVBoxLayout(self.card)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Editar bloco de progressão")
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(title_lbl)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 12px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self._cancel)
        header.addWidget(close_btn)
        outer.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(8)
        icon_col = QVBoxLayout()
        icon_col.addWidget(QLabel("Ícone"))
        self._icon_btn = QToolButton()
        self._icon_btn.setText(icon)
        self._icon_btn.setFixedSize(36, 32)
        self._icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 5px; font-size: 15px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)
        self._icon_btn.clicked.connect(self._pick_icon)
        icon_col.addWidget(self._icon_btn)
        row.addLayout(icon_col)
        name_col = QVBoxLayout()
        name_col.addWidget(QLabel("Nome"))
        self._name = QLineEdit(name)
        name_col.addWidget(self._name)
        row.addLayout(name_col, 1)
        outer.addLayout(row)

        outer.addWidget(QLabel("Nível (ex.: Lv 1-10)"))
        self._levels = QLineEdit(levels)
        outer.addWidget(self._levels)

        outer.addWidget(QLabel("Cor da borda"))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self._color_swatch = QToolButton()
        self._color_swatch.setFixedSize(28, 24)
        self._color_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_swatch.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_swatch)
        reset_btn = QPushButton("Automática")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip("Volta a cor derivada do nome do bioma")
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 4px 10px; font-size: 9px; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        reset_btn.clicked.connect(self._reset_color)
        color_row.addWidget(reset_btn)
        color_row.addStretch()
        outer.addLayout(color_row)

        self._color_picker = self._build_color_picker()
        self._color_picker.hide()
        outer.addWidget(self._color_picker)

        self._refresh_swatch()

        outer.addWidget(QLabel("Notas"))
        self._notes = QTextEdit(notes)
        self._notes.setFixedHeight(80)
        outer.addWidget(self._notes)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 6px 14px; font-size: 10px; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        cancel.clicked.connect(self._cancel)
        ok = QPushButton("Salvar")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        ok.clicked.connect(self._accept)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        outer.addLayout(btn_row)

        self._initial_focus = self._name

    def _accept(self):
        self._accepted = True
        self._close()

    def _refresh_swatch(self):
        shown = self._border_color or self._auto_color
        self._color_swatch.setStyleSheet(f"""
            QToolButton {{ background: {shown}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
        """)

    def _pick_icon(self):
        dlg = IconPickerPopup(ICONS, self._icon, parent=self)
        picked = dlg.exec()
        if picked:
            self._icon = picked
            self._icon_btn.setText(self._icon)

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

        color = QColor(self._border_color or self._auto_color)
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
        self._set_border_color(color)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value())
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._set_border_color(color)

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
        self._set_border_color(color)

    def _sync_rgb_sliders(self, color: QColor):
        for slider, value in ((self._r_slider, color.red()), (self._g_slider, color.green()),
                               (self._b_slider, color.blue())):
            slider.blockSignals(True)
            slider.set_value(value)
            slider.blockSignals(False)

    def _sync_hex_input(self):
        self._hex_input.blockSignals(True)
        self._hex_input.setText(QColor(self._border_color or self._auto_color).name(QColor.NameFormat.HexRgb).lstrip("#").upper())
        self._hex_input.blockSignals(False)

    def _set_border_color(self, color: QColor):
        self._border_color = color.name()
        self._sync_hex_input()
        self._refresh_swatch()

    def _reset_color(self):
        self._border_color = None
        self._refresh_swatch()
        color = QColor(self._auto_color)
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_rgb_sliders(color)
        self._sync_hex_input()

    def exec(self) -> bool:
        self._run()
        return self._accepted

    def values(self) -> tuple[str, str, str, str, str | None]:
        return (
            self._icon,
            self._name.text().strip() or "Novo",
            self._levels.text().strip(),
            self._notes.toPlainText().strip(),
            self._border_color,
        )
