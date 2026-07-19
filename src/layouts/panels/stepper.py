"""NumberStepper — compact "- value +" numeric input.

For settings where a slider's click-and-drag is the wrong fit — either
because the exact number matters (an integer count) or because dragging a
100px track can't comfortably resolve a decimal (a cell size in meters).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QStackedWidget, QLineEdit,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors

_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_BORDER = Colors.BORDER_SUBTLE
_ACCENT = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM


class NumberStepper(QFrame):
    """Icon + label header, "- value +" row underneath. Emits `value_changed`."""

    value_changed = Signal(float)

    def __init__(self, label: str, icon: str, min_val: float, max_val: float,
                 default: float, step: float = 1.0, decimals: int = 0,
                 suffix: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._min = min_val
        self._max = max_val
        self._step = step
        self._decimals = decimals
        self._suffix = suffix
        self._value = self._clamp(default)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(4)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        top.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none;")
        top.addWidget(name_lbl, 1)
        layout.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(4)

        btn_style = f"""
            QToolButton {{
                border: 1px solid {_BORDER}; border-radius: 4px;
                background: rgba(255,255,255,0.04); color: {_TEXT_SEC};
                font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
            QToolButton:pressed {{ background: {_ACCENT_DIM}; }}
        """

        self._minus_btn = QToolButton()
        self._minus_btn.setText("−")
        self._minus_btn.setFixedSize(20, 20)
        self._minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._minus_btn.setStyleSheet(btn_style)
        self._minus_btn.clicked.connect(lambda: self._step_by(-1))
        row.addWidget(self._minus_btn)

        # Value display doubles as an exact-entry field — the +/- buttons
        # are fine for coarse adjustments, but a fine step (e.g. 0.001 for
        # parallax speed) would take forever to reach an arbitrary target
        # by clicking alone. Double-click swaps in a QLineEdit, same
        # label/edit-swap pattern used for rename-in-place elsewhere.
        self._value_stack = QStackedWidget()
        self._value_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._value_label = QLabel(self._format(self._value))
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet(f"""
            color: {_TEXT}; font-size: 10px; font-weight: bold;
            background: rgba(255,255,255,0.04); border: 1px solid {_BORDER};
            border-radius: 4px; padding: 2px 4px;
        """)
        self._value_label.mouseDoubleClickEvent = lambda e: self._start_edit()

        self._value_edit = QLineEdit()
        self._value_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {_TEXT}; font-size: 10px; font-weight: bold;
                background: rgba(255,255,255,0.08); border: 1px solid {_ACCENT};
                border-radius: 4px; padding: 2px 4px;
            }}
        """)
        self._value_edit.returnPressed.connect(self._finish_edit)
        self._value_edit.editingFinished.connect(self._finish_edit)

        self._value_stack.addWidget(self._value_label)
        self._value_stack.addWidget(self._value_edit)
        row.addWidget(self._value_stack, 1)

        self._plus_btn = QToolButton()
        self._plus_btn.setText("+")
        self._plus_btn.setFixedSize(20, 20)
        self._plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._plus_btn.setStyleSheet(btn_style)
        self._plus_btn.clicked.connect(lambda: self._step_by(1))
        row.addWidget(self._plus_btn)

        layout.addLayout(row)

    def _clamp(self, v: float) -> float:
        v = max(self._min, min(self._max, v))
        return round(v, self._decimals) if self._decimals > 0 else round(v)

    def _format(self, v: float) -> str:
        if self._decimals > 0:
            return f"{v:.{self._decimals}f}{self._suffix}"
        return f"{int(v)}{self._suffix}"

    def _step_by(self, direction: int):
        self.set_value(self._value + direction * self._step)

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, val: float, emit: bool = True):
        val = self._clamp(val)
        if val == self._value and self._value_label.text() == self._format(val):
            return
        self._value = val
        self._value_label.setText(self._format(val))
        if emit:
            self.value_changed.emit(val)

    def _start_edit(self):
        self._value_edit.setText(
            f"{self._value:.{self._decimals}f}" if self._decimals > 0 else str(int(self._value))
        )
        self._value_stack.setCurrentIndex(1)
        self._value_edit.setFocus()
        self._value_edit.selectAll()

    def _finish_edit(self):
        if self._value_stack.currentIndex() != 1:
            return
        text = self._value_edit.text().strip().replace(",", ".")
        try:
            self.set_value(float(text))
        except ValueError:
            pass  # leave the value unchanged on unparseable input
        self._value_stack.setCurrentIndex(0)
