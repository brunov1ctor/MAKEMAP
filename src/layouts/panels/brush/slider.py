"""BrushSlider — reusable slider with icon, label, and value display."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors


_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_SLIDER_GROOVE = Colors.BORDER_SUBTLE
_SLIDER_HANDLE = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM


class BrushSlider(QFrame):
    """Slider with icon, label, and value display."""

    value_changed = Signal(float)

    def __init__(self, label: str, icon: str, min_val: float, max_val: float,
                 default: float, suffix: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._min = min_val
        self._max = max_val
        self._suffix = suffix

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
        name_lbl.setMinimumWidth(0)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        name_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none;")
        top.addWidget(name_lbl, 1)

        self._value_label = QLabel(self._format(default))
        self._value_label.setFixedWidth(40)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value_label.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        top.addWidget(self._value_label)
        layout.addLayout(top)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(self._to_slider(default))
        self._slider.setFixedHeight(16)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.wheelEvent = lambda e: e.ignore()
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {_SLIDER_GROOVE}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px; height: 12px; margin: -4px 0;
                background: {_SLIDER_HANDLE}; border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_ACCENT_DIM}; border-radius: 2px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)

    def _to_slider(self, val: float) -> int:
        return int((val - self._min) / (self._max - self._min) * 100)

    def _from_slider(self, pos: int) -> float:
        return self._min + (pos / 100.0) * (self._max - self._min)

    def _format(self, val: float) -> str:
        if self._suffix == "°":
            return f"{val:.0f}{self._suffix}"
        if self._max > 10:
            return f"{val:.0f}{self._suffix}"
        return f"{val:.0f}{self._suffix}" if self._suffix == "%" else f"{val:.2f}{self._suffix}"

    def _on_change(self, pos: int):
        val = self._from_slider(pos)
        self._value_label.setText(self._format(val))
        self.value_changed.emit(val)

    @property
    def value(self) -> float:
        return self._from_slider(self._slider.value())

    def set_value(self, val: float):
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(val))
        self._value_label.setText(self._format(val))
        self._slider.blockSignals(False)
