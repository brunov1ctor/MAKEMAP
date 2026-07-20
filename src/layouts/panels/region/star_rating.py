"""StarRating — reusable 5-button ★/☆ rating row.

Extracted from RegionCard's inline star row so the new RegionEditPanel's
"Dificuldade" field can share the exact same widget/behavior instead of a
second copy-pasted implementation.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors


class StarRating(QWidget):
    """Row of 5 clickable stars. Emits `stars_changed(int)` on click."""

    stars_changed = Signal(int)

    def __init__(self, stars: int = 0, button_size: int = 16, font_size: int = 11, parent=None):
        super().__init__(parent)
        self._stars = max(0, min(5, stars))
        self._buttons: list[QToolButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for i in range(1, 6):
            btn = QToolButton()
            btn.setFixedSize(button_size, button_size)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("_font_size", font_size)
            btn.clicked.connect(lambda checked=False, n=i: self._on_click(n))
            layout.addWidget(btn)
            self._buttons.append(btn)
        self._refresh()

    def _on_click(self, n: int):
        self.set_stars(n)
        self.stars_changed.emit(n)

    def set_stars(self, stars: int, emit: bool = False):
        self._stars = max(0, min(5, stars))
        self._refresh()
        if emit:
            self.stars_changed.emit(self._stars)

    @property
    def stars(self) -> int:
        return self._stars

    def _refresh(self):
        for i, btn in enumerate(self._buttons, start=1):
            filled = i <= self._stars
            font_size = btn.property("_font_size")
            btn.setText("★" if filled else "☆")
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; background: transparent; font-size: {font_size}px;
                    color: {Colors.ACCENT if filled else Colors.TEXT_MUTED}; padding: 0;
                }}
                QToolButton:hover {{ color: {Colors.ACCENT}; }}
            """)
