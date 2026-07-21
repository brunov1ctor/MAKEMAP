"""ColorField — a swatch (quick pick via the native QColorDialog) plus a
"Personalizar" button (opens the in-app ColorCustomizePanel riding sub-panel
instead). Shared by the Texto and Estilo text panels (text color, shadow,
outline, and glow colors all use the same swatch+picker control)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QColorDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.styles.tokens import Colors


class ColorField(QWidget):
    """A color swatch plus a "Personalizar" button; both open the same
    QColorDialog. Emits color_changed(hex) only when the user actually
    picks a new color — call set_color(..., emit=False) to sync from a
    model without echoing the signal back."""

    color_changed = Signal(str)
    customize_requested = Signal()

    def __init__(self, initial: str = "#FFFFFF", dialog_title: str = "Cor", parent=None):
        super().__init__(parent)
        self._color = initial
        self._dialog_title = dialog_title

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.swatch = QToolButton()
        self.swatch.setFixedSize(28, 24)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.clicked.connect(self._pick)
        layout.addWidget(self.swatch)

        self.custom_btn = QToolButton()
        self.custom_btn.setText("Personalizar")
        self.custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.04);
                padding: 3px 8px; font-size: 10px;
            }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self.custom_btn.clicked.connect(self.customize_requested.emit)
        layout.addWidget(self.custom_btn)
        layout.addStretch()

        self._apply_swatch()

    def _pick(self):
        color = QColorDialog.getColor(QColor(self._color), self, self._dialog_title)
        if color.isValid():
            self.set_color(color.name(), emit=True)

    def set_color(self, hex_color: str, emit: bool = False):
        self._color = hex_color
        self._apply_swatch()
        if emit:
            self.color_changed.emit(self._color)

    def color(self) -> str:
        return self._color

    def _apply_swatch(self):
        self.swatch.setStyleSheet(f"""
            QToolButton {{
                background: {self._color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
            }}
        """)
