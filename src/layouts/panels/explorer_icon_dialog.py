"""ExplorerIconDialog — opened by double-clicking an element in the map
Explorer panel (see ExplorerSyncMediator._on_icon_edit). Lets the user pick
a replacement emoji and a label color for just that element, purely for how
the Explorer displays it (the element itself, and any other panel that
edits it, is untouched). Same glass-popup shape as
progression/node_dialog.py's ProgressionNodeDialog, trimmed down to just
the icon/color fields it needs.

The color picker reuses the same inline Hue/SV + hex widgets every other
panel in the app already uses (src/layouts/panels/terrain/color_picker.py
— see MarkerEditPanel, RegionEditPanel, LightEditPanel, ...) instead of a
separate QColorDialog popup or a one-off curated swatch list, so it looks
and behaves exactly like the rest of the app."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
)

from src.styles.tokens import Colors
from src.layouts.panels.shared.popup_overlay import PopupOverlay, IconPickerPopup
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare
from src.engines.marker import ICONS

_DEFAULT_COLOR = "#B0B7C3"


class ExplorerIconDialog(PopupOverlay):
    def __init__(self, icon: str, label_color: str | None, default_icon: str | None = None, parent=None):
        super().__init__(card_width=240, parent=parent)
        self._icon = icon
        self._label_color = label_color or _DEFAULT_COLOR
        self._default_icon = default_icon or icon
        self._accepted = False

        style = f"""
            QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
        """
        self.card.setStyleSheet(style)

        outer = QVBoxLayout(self.card)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel("Editar elemento")
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

        outer.addWidget(QLabel("Ícone"))
        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)
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
        icon_row.addWidget(self._icon_btn)

        icon_reset_btn = QToolButton()
        icon_reset_btn.setText("↺")
        icon_reset_btn.setFixedSize(28, 32)
        icon_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon_reset_btn.setToolTip(f"Voltar ao ícone padrão ({self._default_icon})")
        icon_reset_btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; border: 1px dashed {Colors.BORDER_SUBTLE};
                border-radius: 5px; color: {Colors.TEXT_MUTED}; font-size: 13px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        icon_reset_btn.clicked.connect(self._reset_icon)
        icon_row.addWidget(icon_reset_btn)
        icon_row.addStretch()
        outer.addLayout(icon_row)

        outer.addWidget(QLabel("Cor do label"))
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(6)
        self._swatch = QToolButton()
        self._swatch.setFixedSize(28, 24)
        self._swatch.setEnabled(False)  # preview only — color comes from the picker below
        swatch_row.addWidget(self._swatch)
        self._hex_input = QLineEdit()
        self._hex_input.setMaxLength(7)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        swatch_row.addWidget(self._hex_input, 1)
        outer.addLayout(swatch_row)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(14)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        outer.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(70)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        outer.addWidget(self._sv_square)

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

        self._set_color(QColor(self._label_color), sync_hsv=True)

    def _pick_icon(self):
        dlg = IconPickerPopup(ICONS, self._icon, parent=self)
        picked = dlg.exec()
        if picked:
            self._icon = picked
            self._icon_btn.setText(self._icon)

    def _reset_icon(self):
        self._icon = self._default_icon
        self._icon_btn.setText(self._icon)

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1], self._hsv[2] = s, v
        self._apply_hsv()

    def _apply_hsv(self):
        h, s, v = self._hsv
        self._set_color(QColor.fromHsv(h, round(s * 255 / 100), round(v * 255 / 100)), sync_hsv=False)

    def _on_hex_entered(self):
        color = QColor(self._hex_input.text().strip())
        if color.isValid():
            self._set_color(color, sync_hsv=True)

    def _set_color(self, color: QColor, sync_hsv: bool):
        self._label_color = color.name()
        if sync_hsv:
            h, s, v, _a = color.getHsv()
            self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
            self._hue_bar.blockSignals(True)
            self._hue_bar.set_hue(self._hsv[0])
            self._hue_bar.blockSignals(False)
            self._sv_square.blockSignals(True)
            self._sv_square.set_hue(self._hsv[0])
            self._sv_square.set_sv(self._hsv[1], self._hsv[2])
            self._sv_square.blockSignals(False)
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._label_color)
        self._hex_input.blockSignals(False)
        self._swatch.setStyleSheet(
            f"QToolButton {{ background: {self._label_color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}"
        )

    def _accept(self):
        self._accepted = True
        self._close()

    def exec(self) -> bool:
        self._run()
        return self._accepted

    def values(self) -> tuple[str, str | None]:
        return (self._icon, self._label_color)
