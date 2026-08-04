"""Select Tool Panel — layer-filter checklist controlling what the Select
tool can pick. Shown/hidden together with the "Selecionar" tool, same as
BrushToolPanel is with "Brush" — a real panel, not a toolbar dropdown.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QToolButton, QCheckBox, QSizePolicy,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.light.edit_panel import _ColorField

# (key, label) — key matches the "item_type" tag set on scene items at
# creation time (TerrainLayer, brush-stamped/generated assets, zones).
LAYER_ITEMS = [
    ("terrain", "Terreno"),
    ("asset", "Assets"),
    ("zone", "Zonas"),
    ("mob_spawn", "Mobs"),
    ("marker", "Marcadores"),
    ("light", "Luz"),
    ("text", "Texto"),
]


class SelectToolPanel(QFrame):
    """Compact panel shown while the Select tool is active — restricts
    box/lasso/click selection on the canvas to the checked layer types.
    All checked by default (no filtering)."""

    PANEL_WIDTH = 190

    layers_changed = Signal(object)  # set[str] | None (None = no filtering)
    color_changed = Signal(str)
    close_requested = Signal()
    content_changed = Signal()  # emitted when visible content changes size (e.g. color picker expands)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Same scroll-wrapped-container pattern as every other toolbar
        # panel (Brush/Terrain/Text/Grid): grows with its content and only
        # shows a scrollbar when the window is too short to fit it.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        outer.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("⬚")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Selecionar")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        layout.addWidget(sep)

        # ─── Layer checklist ───
        hint = QLabel("Camadas selecionáveis")
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9pt; background: transparent; border: none;")
        layout.addWidget(hint)

        # 2 columns instead of one long vertical stack — the panel is fixed
        # at PANEL_WIDTH (190px), plenty for two short labels ("Terreno" +
        # "Assets") side by side, and it cuts the checklist's height
        # roughly in half.
        checks_grid = QGridLayout()
        checks_grid.setHorizontalSpacing(10)
        checks_grid.setVerticalSpacing(4)
        _CHECK_COLS = 2

        self._checks: dict[str, QCheckBox] = {}
        for i, (key, text) in enumerate(LAYER_ITEMS):
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                    background: transparent; spacing: 6px;
                }}
            """)
            cb.toggled.connect(self._on_toggle)
            checks_grid.addWidget(cb, i // _CHECK_COLS, i % _CHECK_COLS)
            self._checks[key] = cb
        layout.addLayout(checks_grid)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        layout.addWidget(sep2)

        # ─── Selection outline color — was hardcoded pink (Colors.PURPLE)
        # in TransformEngine.show_handles, now user-configurable ───
        self.color_field = _ColorField("Cor da seleção")
        self.color_field.set_color(Colors.PURPLE)
        self.color_field.color_changed.connect(self.color_changed.emit)
        # _ColorField's swatch click already expands/collapses its own
        # inline HSV picker (see _ColorField._toggle) — but this panel's own
        # geometry is fixed by PanelManager to whatever height its content
        # needed at the time it was last laid out, so without re-triggering
        # a layout pass here the newly-revealed picker just gets clipped by
        # the panel's own (still-old) height instead of the panel actually
        # growing to show it.
        self.color_field.toggled.connect(self.content_changed.emit)
        layout.addWidget(self.color_field)

        scroll.setWidget(container)

    def _on_toggle(self, _checked: bool):
        allowed = {key for key, cb in self._checks.items() if cb.isChecked()}
        if len(allowed) == len(self._checks):
            allowed = None  # everything checked = no filtering
        self.layers_changed.emit(allowed)

    def paintEvent(self, event):
        paint_glass_panel(self)
