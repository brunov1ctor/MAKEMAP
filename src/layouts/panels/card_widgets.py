"""Shared small widgets reused across flat-list CRUD cards (terrain, region, ...)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton

from src.styles.tokens import Colors, menu_qss


def overflow_menu_button(tooltip: str = "Mais opções") -> tuple[QToolButton, QMenu]:
    """The "⋯" overflow button + its attached (empty) QMenu, styled and wired
    together. Caller populates the returned menu with addAction/addSeparator/
    addMenu in whatever order the card needs."""
    btn = QToolButton()
    btn.setText("⋯")
    btn.setFixedSize(22, 22)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(f"""
        QToolButton {{
            border: none; border-radius: 4px; font-size: 14px; font-weight: bold;
            color: {Colors.TEXT_SECONDARY}; background: transparent;
        }}
        QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
        QToolButton::menu-indicator {{ image: none; }}
        QToolTip {{
            background-color: {Colors.BG_ELEVATED};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER};
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 11px;
        }}
    """)

    menu = QMenu(btn)
    menu.setStyleSheet(menu_qss())
    btn.setMenu(menu)
    return btn, menu
