"""Canvas Toolbar — ferramentas de edição profissional."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography


class CanvasToolbar(QFrame):
    """Toolbar superior completa — ferramentas de edição profissional."""

    tool_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            CanvasToolbar {{
                background: {Colors.GLASS_BG_STRONG};
                border-bottom: 1px solid {Colors.BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(1)

        tools = [
            ("⬚", "Selecionar", "V", True),
            ("✥", "Mover", "M", True),
            ("✋", "Pan", "H", True),
            None,
            ("🖌", "Brush", "B", True),
            ("▭", "Região", "R", True),
            ("⟋", "Estrada", "P", True),
            ("〰", "Rio", "W", True),
            ("◐", "Bioma", "I", True),
            ("T", "Texto", "T", True),
            ("📍", "Marcador", "K", True),
            None,
            ("🎨", "Assets", "A", False),
            ("☰", "Camadas", "L", False),
            None,
            ("⊞", "Grid", "G", False),
            ("⊡", "Snap", "S", False),
            None,
            ("↶", "Undo", "Ctrl+Z", False),
            ("↷", "Redo", "Ctrl+Y", False),
            None,
            ("📤", "Exportar", "", False),
        ]

        self._tool_buttons = []
        for item in tools:
            if item is None:
                layout.addWidget(self._sep())
                continue

            icon, name, shortcut, is_tool = item
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(f"{name} ({shortcut})" if shortcut else name)
            btn.setFixedSize(32, 32)
            btn.setCheckable(is_tool)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; border-radius: 6px;
                    font-size: 14px; color: {Colors.TEXT_SECONDARY};
                    background: transparent;
                }}
                QToolButton:hover {{
                    background: {Colors.PANEL_HOVER};
                    color: {Colors.TEXT_PRIMARY};
                }}
                QToolButton:checked {{
                    background: {Colors.ACCENT_DIM};
                    color: {Colors.ACCENT};
                    border: 1px solid {Colors.ACCENT};
                }}
            """)
            if is_tool:
                btn.clicked.connect(lambda checked, n=name: self._on_tool(n))
            layout.addWidget(btn)
            self._tool_buttons.append((name, btn, is_tool))

        layout.addStretch()

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        layout.addWidget(self.zoom_label)

    def _on_tool(self, name: str):
        for n, btn, is_tool in self._tool_buttons:
            if is_tool:
                btn.setChecked(n == name)
        self.tool_selected.emit(name)

    def _sep(self):
        s = QFrame()
        s.setFixedSize(1, 24)
        s.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return s
