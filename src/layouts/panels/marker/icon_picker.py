"""IconPicker — a scrollable grid of checkable emoji buttons, shared by
MarkerToolPanel (picking an icon before placing) and MarkerEditPanel
(picking icon after placement). Grid + scroll instead of a single row so
the full ICONS palette (see src/engines/marker.py) fits without spilling
past the panel's fixed width."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QGridLayout, QToolButton, QButtonGroup, QScrollArea
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors

_COLUMNS = 6


class IconPicker(QScrollArea):
    icon_picked = Signal(str)

    def __init__(self, icons: list[str], button_size: int = 32, max_height: int = 150, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFixedHeight(max_height)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        grid = QGridLayout(container)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(6)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for i, icon in enumerate(icons):
            btn = QToolButton()
            btn.setText(icon)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(button_size, button_size)
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 7px;
                    background: rgba(255,255,255,0.04); font-size: {int(button_size * 0.44)}px;
                }}
                QToolButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}
                QToolButton:checked {{ border-color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            """)
            btn.clicked.connect(lambda _=False, ic=icon: self.icon_picked.emit(ic))
            self._group.addButton(btn)
            self._buttons[icon] = btn
            grid.addWidget(btn, i // _COLUMNS, i % _COLUMNS)

        self.setWidget(container)

    def set_checked(self, icon: str):
        btn = self._buttons.get(icon)
        if btn:
            btn.setChecked(True)
