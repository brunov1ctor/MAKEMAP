"""BrushSlider — reusable slider with icon, label, and value display."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QSizePolicy,
    QStackedWidget, QLineEdit, QApplication,
)
from PySide6.QtCore import Qt, Signal, QEvent, QObject

from src.styles.tokens import Colors


_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_SLIDER_GROOVE = Colors.BORDER_SUBTLE
_SLIDER_HANDLE = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM
_ACCENT = Colors.ACCENT
_BORDER = Colors.BORDER_SUBTLE


class _NextClickSwallower(QObject):
    """One-shot app-wide filter that eats the very next mouse press.

    Installed the instant a value field commits via focus-out (i.e. the
    user clicked somewhere else to confirm it) — that same click would
    otherwise land on whatever's underneath (the canvas, most commonly)
    and register as e.g. a brush stroke. Removes itself after one press,
    matched or not, so it never lingers.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
            return True
        return False


class BrushSlider(QFrame):
    """Slider with icon, label, and an editable value display."""

    value_changed = Signal(float)

    def __init__(self, label: str, icon: str, min_val: float, max_val: float,
                 default: float, suffix: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._min = min_val
        self._max = max_val
        self._suffix = suffix
        self._value = default
        self._click_filter: _NextClickSwallower | None = None

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

        # Value display doubles as an exact-entry field — click it, type a
        # value, and either Enter or clicking away commits it (clicking away
        # also swallows that click so it doesn't fall through to the canvas).
        self._value_stack = QStackedWidget()
        self._value_stack.setFixedWidth(56)

        self._value_label = QLabel(self._format(default))
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value_label.setCursor(Qt.CursorShape.IBeamCursor)
        self._value_label.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        self._value_label.mousePressEvent = lambda e: self._start_edit()

        self._value_edit = QLineEdit()
        self._value_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {_TEXT}; font-size: 10px; font-weight: bold;
                background: rgba(255,255,255,0.08); border: 1px solid {_ACCENT};
                border-radius: 3px; padding: 0px 2px;
            }}
        """)
        self._value_edit.returnPressed.connect(self._finish_edit_via_enter)
        self._value_edit.editingFinished.connect(self._finish_edit_via_focus_loss)

        self._value_stack.addWidget(self._value_label)
        self._value_stack.addWidget(self._value_edit)
        top.addWidget(self._value_stack)
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
        if self._suffix == "m":
            return f"{val:.2f}{self._suffix}"
        if self._suffix == "°":
            return f"{val:.0f}{self._suffix}"
        if self._max > 10:
            return f"{val:.0f}{self._suffix}"
        return f"{val:.0f}{self._suffix}" if self._suffix == "%" else f"{val:.2f}{self._suffix}"

    def _on_change(self, pos: int):
        val = self._from_slider(pos)
        self._value = val
        self._value_label.setText(self._format(val))
        self.value_changed.emit(val)

    @property
    def value(self) -> float:
        return self._from_slider(self._slider.value())

    def set_value(self, val: float):
        self._value = max(self._min, min(self._max, val))
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(self._value))
        self._value_label.setText(self._format(self._value))
        self._slider.blockSignals(False)

    # ─── Click-to-edit ──────────────────────────────────────────────────

    def _start_edit(self):
        self._value_edit.setText(f"{self._value:.2f}" if self._suffix == "m" else self._format(self._value).rstrip(self._suffix))
        self._value_stack.setCurrentIndex(1)
        self._value_edit.setFocus()
        self._value_edit.selectAll()

    def _finish_edit_via_enter(self):
        # returnPressed fires before editingFinished (which follows the
        # subsequent focus loss) — commit once here and let the focus-loss
        # path below no-op via the stack index check.
        self._commit_edit()

    def _finish_edit_via_focus_loss(self):
        if self._value_stack.currentIndex() != 1:
            return
        self._commit_edit()
        # The click that took focus away from the edit field is still
        # in flight and would otherwise reach whatever's underneath
        # (typically the canvas) — swallow it once.
        app = QApplication.instance()
        if app:
            self._click_filter = _NextClickSwallower()
            app.installEventFilter(self._click_filter)

    def _commit_edit(self):
        if self._value_stack.currentIndex() != 1:
            return
        text = self._value_edit.text().strip().replace(",", ".")
        try:
            self.set_value(float(text))
            self.value_changed.emit(self._value)
        except ValueError:
            pass  # leave the value unchanged on unparseable input
        self._value_stack.setCurrentIndex(0)
