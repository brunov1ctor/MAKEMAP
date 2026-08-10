"""IconPicker — a scrollable grid of checkable emoji buttons, shared by
MarkerToolPanel (picking an icon before placing) and MarkerEditPanel
(picking icon after placement). Grid + scroll instead of a single row so
the full ICONS palette (see src/engines/marker.py) fits without spilling
past the panel's fixed width."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QGridLayout, QToolButton, QButtonGroup, QScrollArea, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors

_COLUMNS = 6


class IconPicker(QScrollArea):
    icon_picked = Signal(str)

    def __init__(self, icons: list[str], button_size: int = 32, max_height: int = 150,
                 fill: bool = False, parent=None):
        """`fill=True` (MarkerToolPanel, which has nothing else competing
        for vertical space) makes this grow to whatever room its container
        actually gives it instead of a hard-capped `max_height` — so more
        of the (currently 80+) icons show at once without scrolling on a
        normal-sized window, scrolling only ever kicking in as real
        overflow protection. `fill=False` (the default, used by
        MarkerEditPanel where this sits among several OTHER fields)
        keeps the original fixed-height behavior — a compact picker
        that doesn't crowd out the fields below it."""
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if fill:
            self.setMinimumHeight(max_height)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
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
        # Tight enough that 6 columns of button_size-wide buttons actually
        # fit inside the panel's content width (accounting for the
        # QScrollArea's own border + the vertical scrollbar it almost
        # always shows, since the full ICONS palette overflows max_height)
        # — wider margins/spacing here used to clip the last column.
        grid.setContentsMargins(4, 6, 4, 6)
        grid.setSpacing(3)

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
