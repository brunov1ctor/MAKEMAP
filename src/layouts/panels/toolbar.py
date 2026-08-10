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

# (icon, name, shortcut, is_tool, is_toggle=False, label=name) — hoisted to
# module level (rather than built inline in __init__) so TOOL_ICON_BY_NAME
# below can derive a name->icon lookup other panels (e.g. the map Explorer)
# reuse to keep their own default icons in sync with the toolbar's.
TOOL_DEFS = [
    ("⬚", "Selecionar", "V", True),
    ("🌎", "Terreno", "", False, True),  # toggle action
    ("🖌", "Brush", "B", True, False, "Pincel"),
    ("🌳", "Região", "", False, True),  # toggle action — opens the CRUD panel
    ("T", "Texto", "T", True),
    ("👾", "Spawn", "", True),
    ("📍", "Marcador", "K", True),
    ("💡", "Iluminação", "", False, True),  # toggle action
    None,
    ("📐", "Grid", "G", False),
    "__view__",
    ("🖼", "Plano de Fundo", "", False, True),  # toggle action
    None,
    ("↶", "Undo", "Ctrl+Z", False),
    ("↷", "Redo", "Ctrl+Y", False),
    None,
    ("📤", "Exportar", "", False),
]

TOOL_ICON_BY_NAME: dict[str, str] = {
    item[1]: item[0] for item in TOOL_DEFS if isinstance(item, tuple)
}


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
        # Actual active tool name (CanvasEngine defaults to Pan at
        # construction) — distinct from any button's checked state, which
        # can be True for a whole _member_names family (e.g. Brush shows
        # checked while Rio/Estrada is active) rather than just this exact
        # tool. See _on_tool_toggled for why that distinction matters.
        self._active_tool_name = "Pan"

        self._tool_defs = TOOL_DEFS

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
            QLabel {{
                color: {Colors.TEXT_MUTED}; font-size: 11px;
                background: transparent; border: none;
            }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
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
                QToolTip {{
                    background-color: {Colors.BG_ELEVATED};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 8px;
                    padding: 6px 10px;
                    font-size: 11px;
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
            if name == "Brush":
                # Picking a water/road asset switches the active tool to
                # the dedicated "Rio"/"Estrada" path-tracing tool instead
                # of the plain terrain-painting Brush (see
                # BrushMediator.on_asset_selected) — but both are still
                # picked from the SAME brush asset panel, so from the
                # user's POV they never left the Brush workflow. Without
                # this, the Brush button unchecked itself the moment a
                # water/road asset was chosen, making it look like the
                # tool had silently switched away/broken.
                btn._member_names = {"Brush", "Rio", "Estrada"}
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
        if checked:
            self._on_tool(name)
            return
        # Unchecking a button only really means "switch to Pan" when the
        # active tool WAS this button's own name — a button showing checked
        # because a family member is active (e.g. Brush shown checked while
        # Rio/Estrada is the real active tool, via _member_names) unchecks
        # itself on this same click too (Qt's own toggle, we don't control
        # that), but the user's intent in that case is "switch to Brush
        # itself", not "turn selection off". Falling through to Pan here
        # made clicking Pincel while Rio was active a dead click that
        # silently switched to Pan instead of Brush.
        if self._active_tool_name == name:
            self._on_tool("Pan")
        else:
            self._on_tool(name)

    def _on_tool(self, name: str):
        self._active_tool_name = name
        for n, btn, is_tool, is_toggle in self._tool_buttons:
            if is_tool:
                # A button may cover more than one underlying tool name via
                # `_member_names` — e.g. Brush also covers Rio/Estrada,
                # since those are picked from the same asset panel (see
                # toolbar.py's "Brush" registration).
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

    def sync_active(self, name: str):
        """Reflect a tool activated programmatically (not via a button
        click) in the button states, without re-emitting tool_selected —
        e.g. TextTool switching back to Pan once a placed label's first
        edit commits, or BrushMediator.on_asset_selected switching straight
        to Rio/Estrada when a water/road asset is picked."""
        self._active_tool_name = name
        for n, btn, is_tool, is_toggle in self._tool_buttons:
            if is_tool:
                members = getattr(btn, "_member_names", None) or {n}
                btn.blockSignals(True)
                btn.setChecked(name in members)
                btn.blockSignals(False)
            elif is_toggle:
                # _on_tool() (a direct toolbar click) already clears toggle
                # buttons (Terreno/Região/Iluminação/Plano de Fundo) when a
                # real tool is picked — this path (a tool re-activated
                # PROGRAMMATICALLY, e.g. re-selecting "Selecionar" as a side
                # effect of clicking an item on canvas while a toggle panel
                # was still open) skipped that entirely, leaving the toggle
                # button's checked state stuck from whenever it was opened —
                # two toolbar icons highlighted at once even though only one
                # tool is actually active.
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)

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
