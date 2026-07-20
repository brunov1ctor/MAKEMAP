"""Canvas Toolbar — ferramentas de edição profissional."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QSizePolicy, QLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Typography
from src.layouts.panels.view_dropdown import ViewDropdown


def _paint_glass(widget, event, radius=10):
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = widget.width(), widget.height()
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.fillPath(path, QColor(11, 25, 41, 200))
    grad = QLinearGradient(0, 0, 0, h * 0.25)
    grad.setColorAt(0.0, QColor(255, 255, 255, 10))
    grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(grad))
    p.setPen(QPen(QColor(255, 255, 255, 30), 1))
    p.drawPath(path)
    p.end()


_THICKNESS = 42  # fixed size along the toolbar's short axis, both orientations


class CanvasToolbar(QFrame):
    """Toolbar superior completa — ferramentas de edição profissional.

    Draggable (click-drag on any empty area — not on a button) and
    orientable (right-click flips horizontal <-> vertical). Placement and
    collision-avoidance against other panels is owned by MainLayout, which
    listens to `dragged` and moves/clamps this widget itself.
    """

    tool_selected = Signal(str)
    action_triggered = Signal(str)  # non-tool buttons (Grid, Undo, etc.)
    view_toggled = Signal(str, bool)  # forwarded from the View dropdown
    dragged = Signal(int, int)  # delta x, y in parent coordinates
    orientation_changed = Signal(str)  # "horizontal" | "vertical"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        self._orientation = "horizontal"
        self._dragging = False
        self._drag_last_global = None

        self._tool_defs = [
            ("⬚", "Selecionar", "V", True),
            ("🌎", "Terreno", "", False, True),  # toggle action
            ("🖌", "Brush", "B", True, False, "Pincel"),
            ("🌳", "Região", "", False, True),  # toggle action — opens the CRUD panel
            ("T", "Texto", "T", True),
            ("👾", "Spawn", "", True),
            ("📍", "Marcador", "K", True),
            ("🎯", "Eventos", "", True),
            ("💡", "Iluminação", "", False, True),  # toggle action
            None,
            ("📐", "Grid", "G", False),
            "__view__",
            None,
            ("↶", "Undo", "Ctrl+Z", False),
            ("↷", "Redo", "Ctrl+Y", False),
            None,
            ("📤", "Exportar", "", False),
        ]

        self._tool_buttons = []  # (name, btn, is_tool, is_toggle)
        self._items: list[QFrame | QToolButton] = []  # buttons + separators, in order
        self._build_items()

        # Dedicated grab handle — with buttons packed edge-to-edge there's no
        # reliable empty spot to click-drag on, so give the toolbar one.
        # WA_TransparentForMouseEvents means clicks fall through to this
        # QFrame's own mousePressEvent below, reusing the same drag/flip code.
        self._grip = QLabel("⣿")
        self._grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._grip.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 11px;
            background: transparent; border: none;
        """)
        self._grip.setToolTip("Arraste para mover • Clique direito para girar")
        self._grip_sep = self._make_separator()

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)

        self._apply_layout()

    # ─── Item construction (built once, re-laid-out on flip) ──────────────

    def _build_items(self):
        for item in self._tool_defs:
            if item is None:
                self._items.append(self._make_separator())
                continue
            if item == "__view__":
                view_btn = ViewDropdown(compact=True)
                view_btn.visibility_changed.connect(self.view_toggled.emit)
                self._items.append(view_btn)
                continue
            icon, name, shortcut, is_tool = item[:4]
            is_toggle = item[4] if len(item) > 4 else False
            label = item[5] if len(item) > 5 else name

            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(f"{label} ({shortcut})" if shortcut else label)
            btn.setFixedSize(32, 32)
            btn.setCheckable(is_tool or is_toggle)
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
                # Every tool button toggles off back to Pan (free map
                # dragging) on a second click, instead of behaving like a
                # radio that can only ever be switched to a different tool.
                # CanvasEngine defaults its active tool to Pan at
                # construction (map movable right away), so these all start
                # unchecked to match.
                btn.clicked.connect(lambda checked, n=name: self._on_tool_toggled(checked, n))
            else:
                btn.clicked.connect(lambda checked, n=name: self._on_action(n))
            self._items.append(btn)
            self._tool_buttons.append((name, btn, is_tool, is_toggle))

    def _make_separator(self) -> QFrame:
        s = QFrame()
        s.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return s

    # ─── Layout (horizontal <-> vertical) ──────────────────────────────────

    def _apply_layout(self):
        old_layout = self.layout()
        if old_layout is not None:
            # Drain items first — QLayout.takeAt() detaches a widget from the
            # layout without touching its QObject parent (still `self`), so
            # the buttons/separators survive. Handing the layout to a fresh
            # widget re-parents anything still IN it, so it must be empty
            # first, or our buttons would get deleted along with that widget.
            while old_layout.count():
                old_layout.takeAt(0)
            QWidget().setLayout(old_layout)

        horizontal = self._orientation == "horizontal"
        layout: QLayout = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        layout.setSpacing(1)
        if horizontal:
            layout.setContentsMargins(10, 0, 10, 0)
        else:
            layout.setContentsMargins(0, 10, 0, 10)

        self._grip.setFixedSize(16, 32) if horizontal else self._grip.setFixedSize(32, 16)
        layout.addWidget(self._grip)
        self._grip_sep.setFixedSize(1, 24) if horizontal else self._grip_sep.setFixedSize(24, 1)
        layout.addWidget(self._grip_sep)

        for item in self._items:
            if isinstance(item, QFrame):  # separators are QFrame; buttons are QToolButton
                item.setFixedSize(1, 24) if horizontal else item.setFixedSize(24, 1)
            layout.addWidget(item)

        layout.addStretch()
        layout.addWidget(self.zoom_label)

        if horizontal:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.setMinimumHeight(_THICKNESS)
            self.setMaximumHeight(_THICKNESS)
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            self.setMinimumWidth(_THICKNESS)
            self.setMaximumWidth(_THICKNESS)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

    def _flip_orientation(self):
        self._orientation = "vertical" if self._orientation == "horizontal" else "horizontal"
        self._apply_layout()
        self.orientation_changed.emit(self._orientation)

    @property
    def orientation(self) -> str:
        return self._orientation

    def paintEvent(self, event):
        _paint_glass(self, event, radius=10)

    def _on_tool_toggled(self, checked: bool, name: str):
        self._on_tool(name if checked else "Pan")

    def _on_tool(self, name: str):
        for n, btn, is_tool, is_toggle in self._tool_buttons:
            if is_tool:
                # A button may cover more than one underlying tool name via
                # `_member_names` (not used today, kept for buttons like
                # this that consolidate a small family of related tools).
                members = getattr(btn, "_member_names", None) or {n}
                btn.setChecked(name in members)
            elif is_toggle:
                btn.setChecked(False)
        self.tool_selected.emit(name)

    def _on_action(self, name: str):
        # Uncheck all tool buttons when a toggle action is activated
        for n, btn, is_tool, is_toggle in self._tool_buttons:
            if is_tool:
                btn.setChecked(False)
            elif is_toggle:
                btn.setChecked(n == name and btn.isChecked())
        self.action_triggered.emit(name)

    def uncheck_action(self, name: str):
        """Programmatically uncheck a toggle action button."""
        for n, btn, is_tool, is_toggle in self._tool_buttons:
            if n == name and is_toggle:
                btn.setChecked(False)
                break

    # ─── Drag (empty-area only — clicks on buttons never reach this) ──────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._flip_orientation()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_last_global = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            pos = event.globalPosition().toPoint()
            delta = pos - self._drag_last_global
            self._drag_last_global = pos
            if delta.x() or delta.y():
                self.dragged.emit(delta.x(), delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._drag_last_global = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
