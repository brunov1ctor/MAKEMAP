"""InfoModal — one-off message centered over the canvas.

Two modes:
- show_message(text)          — informational, single OK button.
- show_confirm(text, on_confirm) — destructive confirmation, Cancel + confirm button.
"""

from __future__ import annotations
from typing import Callable

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel


class InfoModal(QFrame):
    PANEL_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        icon_row = QHBoxLayout()
        self._icon = QLabel("⚠")
        self._icon.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        icon_row.addWidget(self._icon)
        icon_row.addStretch()
        layout.addLayout(icon_row)

        self._message = QLabel("")
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 12px;
            background: transparent; border: none;
        """)
        layout.addWidget(self._message)

        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(8)

        self._cancel_btn = QToolButton()
        self._cancel_btn.setText("Cancelar")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setMinimumHeight(30)
        self._cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._cancel_btn.setStyleSheet(f"""
            QToolButton {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; color: {Colors.TEXT_SECONDARY};
                font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        self._cancel_btn.clicked.connect(self.hide)
        self._btn_row.addWidget(self._cancel_btn)

        self._confirm_btn = QToolButton()
        self._confirm_btn.setText("OK")
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setMinimumHeight(30)
        self._confirm_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._confirm_btn.setStyleSheet(f"""
            QToolButton {{
                background: {Colors.ACCENT}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ opacity: 0.85; }}
        """)
        self._btn_row.addWidget(self._confirm_btn)
        layout.addLayout(self._btn_row)

        self._on_confirm: Callable | None = None
        self._confirm_btn.clicked.connect(self._handle_confirm)

    def _handle_confirm(self):
        self.hide()
        if self._on_confirm:
            self._on_confirm()
            self._on_confirm = None

    def show_message(self, message: str):
        """Informational — single OK button, no cancel."""
        self._message.setText(message)
        self._cancel_btn.hide()
        self._confirm_btn.setText("OK")
        self._confirm_btn.setStyleSheet(f"""
            QToolButton {{
                background: {Colors.ACCENT}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ background: #5bc8fb; }}
        """)
        self._on_confirm = None
        self.adjustSize()
        self.show()
        self.raise_()

    def show_confirm(self, message: str, confirm_label: str,
                     on_confirm: Callable, destructive: bool = True):
        """Confirmation — Cancel + action button."""
        self._message.setText(message)
        self._cancel_btn.show()
        self._confirm_btn.setText(confirm_label)
        danger = Colors.ERROR if destructive else Colors.ACCENT
        self._confirm_btn.setStyleSheet(f"""
            QToolButton {{
                background: {danger}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ opacity: 0.85; }}
        """)
        self._on_confirm = on_confirm
        self.adjustSize()
        self.show()
        self.raise_()

    def paintEvent(self, event):
        paint_glass_panel(self)
