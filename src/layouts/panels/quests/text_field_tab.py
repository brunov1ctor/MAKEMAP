"""TextFieldTab — aba de conteúdo genérica que edita uma única coluna de
texto livre da quest. Notas e Scripts têm exatamente essa forma (um
QTextEdit grande, sem mais nenhum campo), então compartilham esta classe em
vez de duas variações quase idênticas — a diferença entre elas é só título/
dica/nome da coluna, passados no construtor.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QTextEdit, QSizePolicy
from PySide6.QtCore import Signal

from src.styles.tokens import Colors
from src.layouts.panels.quests.constants import panel_frame_style, sub_header, _INPUT_STYLE


class TextFieldTab(QFrame):
    changed = Signal()

    def __init__(self, title: str, hint: str, field_key: str, placeholder: str = "", monospace: bool = False, parent=None):
        super().__init__(parent)
        self._field_key = field_key
        self._loading = False
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header(title))

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
            outer.addWidget(hint_lbl)

        self._text = QTextEdit()
        self._text.setPlaceholderText(placeholder)
        if monospace:
            self._text.setStyleSheet(self._text.styleSheet() + "QTextEdit { font-family: Consolas, monospace; }")
        self._text.textChanged.connect(self._on_field_changed)
        outer.addWidget(self._text, 1)

    def _on_field_changed(self):
        if not self._loading:
            self.changed.emit()

    def set_empty(self):
        self._loading = True
        try:
            self._text.clear()
        finally:
            self._loading = False
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._loading = True
        try:
            self._text.setPlainText(record.get(self._field_key) or "")
        finally:
            self._loading = False

    def collect(self) -> dict:
        return {self._field_key: self._text.toPlainText()}
