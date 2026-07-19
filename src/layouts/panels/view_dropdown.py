"""ViewDropdown — checklist dropdown to show/hide the app's UI chrome panels."""

from PySide6.QtWidgets import QToolButton, QMenu
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors

# (key, label) — key is what MainLayout maps to an actual widget.
# The toolbar itself is deliberately absent: this dropdown lives inside it,
# so hiding "Toolbar" would strip away the only way to bring it back.
VIEW_ITEMS = [
    ("top_bar", "Barra Superior"),
    ("explorer", "Explorer"),
    ("inspector", "Inspector"),
    ("progression", "Progression"),
    ("status_bar", "Status Bar"),
    ("minimap", "Minimapa"),
    ("compass", "Bússola"),
]


class ViewDropdown(QToolButton):
    """Dropdown checklist to show/hide the app's UI chrome panels.

    Each entry is an independent checkable toggle (top bar, toolbar, side
    panels, ...) so the user can hide only what's in their way instead of an
    all-or-nothing fullscreen mode.
    """

    visibility_changed = Signal(str, bool)  # key, visible

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.setText("👁" if compact else "👁 View")
        self.setToolTip("View")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        if compact:
            self.setFixedSize(32, 32)
            self.setStyleSheet(f"""
                QToolButton {{
                    border: none; border-radius: 6px;
                    font-size: 14px; color: {Colors.TEXT_SECONDARY};
                    background: transparent;
                }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
                QToolButton::menu-indicator {{ image: none; }}
            """)
        else:
            self.setStyleSheet(f"""
                QToolButton {{
                    background: rgba(255,255,255,0.04); color: {Colors.TEXT_SECONDARY};
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                    padding: 3px 8px; font-size: 10px;
                }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
                QToolButton::menu-indicator {{ image: none; }}
            """)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; padding: 4px;
            }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        self._actions = {}
        for key, label in VIEW_ITEMS:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(True)
            act.toggled.connect(lambda checked, k=key: self.visibility_changed.emit(k, checked))
            self._actions[key] = act
        self.setMenu(menu)
