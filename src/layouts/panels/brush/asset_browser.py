"""Asset Browser Panel — category tabs + search + material grid.

Split out of BrushToolPanel so activating the Brush tool shows just the
brush *config* (size/opacity/material name/transform) — compact enough to
sit next to the canvas without eating the view — while this panel handles
the (taller, grid-heavy) job of actually picking which asset to paint with.
Shown/hidden together with BrushToolPanel by MainLayout, positioned right
next to it.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QScrollArea, QWidget, QToolButton, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.styles.tokens import Colors
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panel_manager import paint_glass_panel
from src.engines.assets.library import DEFAULT_STYLE, list_styles


_BG_SECTION = "rgba(255, 255, 255, 0.04)"
_BORDER = "rgba(255, 255, 255, 0.10)"
_ACCENT = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM
_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_TEXT_MUTED = Colors.TEXT_MUTED


# ─── Material Thumbnail ─────────────────────────────────────────────────────

class MaterialThumbnail(QToolButton):
    """Clickable material thumbnail for the grid."""

    favorited = Signal(str)

    def __init__(self, asset_id: str = "", name: str = "", parent=None):
        super().__init__(parent)
        self.asset_id = asset_id
        self._is_favorite = False
        self.setFixedSize(52, 58)
        self.setCheckable(True)
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(36, 36))
        self.setText(name[:7] if len(name) > 7 else name)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_right_click)
        self._update_style()

    def set_favorite(self, fav: bool):
        # No QGraphicsDropShadowEffect here on purpose — its blur extends
        # well past this button's 52x58 bounds, and the grid packs items
        # with only 2px of spacing, so the glow painted over whichever
        # neighbor comes after it in the FlowLayout. The border-color swap
        # in _update_style() already marks favorites clearly on its own.
        self._is_favorite = fav
        self._update_style()

    def _update_style(self):
        border = _ACCENT if self._is_favorite else _BORDER
        self.setStyleSheet(f"""
            QToolButton {{
                border: 2px solid {border}; border-radius: 4px;
                background: {_BG_SECTION}; padding: 2px;
                font-size: 10px; color: {_TEXT_MUTED};
            }}
            QToolButton:hover {{ border-color: {_TEXT_SEC}; }}
            QToolButton:checked {{
                border-color: {_ACCENT}; background: {_ACCENT_DIM};
            }}
        """)

    def _on_right_click(self, pos):
        self.favorited.emit(self.asset_id)

    def set_pixmap(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            QSize(36, 36),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setIcon(QIcon(scaled))


def _separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORDER}; border: none;")
    return sep


# ─── Main Panel ─────────────────────────────────────────────────────────────

class AssetBrowserPanel(QFrame):
    """Category tabs + search + material grid — picks which asset to paint with."""

    PANEL_WIDTH = 260

    asset_selected = Signal(str)
    favorite_toggled = Signal(str)
    tab_changed = Signal(str)
    style_changed = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── header ──
        header = QHBoxLayout()
        header.setContentsMargins(10, 6, 10, 0)
        header.setSpacing(6)

        icon = QLabel("🎨")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Assets")
        title.setStyleSheet(f"""
            color: {_TEXT}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {_TEXT_SEC}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        root.addLayout(header)
        root.addWidget(_separator())

        # ── abas de estilo (pai das abas de categoria abaixo) ──
        self._style_tab_container = QWidget()
        self._style_tab_container.setStyleSheet("background: transparent;")
        style_tab_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        style_tab_policy.setHeightForWidth(True)
        self._style_tab_container.setSizePolicy(style_tab_policy)
        self._style_tab_container.setMinimumHeight(24)
        self._style_tab_flow = FlowLayout(self._style_tab_container, spacing=2)
        self._style_tab_flow.setContentsMargins(10, 4, 10, 0)

        # Reflects whatever styles actually exist on disk at construction
        # time — a style deleted via the Config panel in an earlier session
        # (or before this panel was built) won't show up here as a dead tab.
        self._style_keys = list_styles()
        self._style_buttons: list[QToolButton] = []

        for i, key in enumerate(self._style_keys):
            btn = QToolButton()
            btn.setText(key.capitalize())
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: transparent; color: {_TEXT_SEC};
                    padding: 3px 6px; font-size: 9px; border: none;
                    border-bottom: 2px solid transparent;
                }}
                QToolButton:checked {{
                    color: {_ACCENT}; border-bottom-color: {_ACCENT};
                }}
                QToolButton:hover {{ color: {_TEXT}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_style_tab_clicked(idx))
            self._style_tab_flow.addWidget(btn)
            self._style_buttons.append(btn)

        default_idx = self._style_keys.index(DEFAULT_STYLE) if DEFAULT_STYLE in self._style_keys else 0
        if self._style_buttons:
            self._style_buttons[default_idx].setChecked(True)
        root.addWidget(self._style_tab_container)
        root.addWidget(_separator())

        # ── abas ──
        self._tab_container = QWidget()
        self._tab_container.setStyleSheet("background: transparent;")
        tab_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tab_policy.setHeightForWidth(True)
        self._tab_container.setSizePolicy(tab_policy)
        self._tab_container.setMinimumHeight(48)
        self._tab_flow = FlowLayout(self._tab_container, spacing=2)
        self._tab_flow.setContentsMargins(10, 4, 10, 4)

        self._tab_categories = ["terrain", "trees", "rocks", "mountains", "buildings", "effects", "misc"]
        self._tab_labels = ["🌍 Terrain", "🌲 Trees", "🪨 Rocks", "⛰ Mountains", "🏠 Buildings", "✨ Effects", "📦 Misc", "★"]
        self._tab_buttons: list[QToolButton] = []

        for i, label in enumerate(self._tab_labels):
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: transparent; color: {_TEXT_SEC};
                    padding: 3px 6px; font-size: 9px; border: none;
                    border-bottom: 2px solid transparent;
                }}
                QToolButton:checked {{
                    color: {_ACCENT}; border-bottom-color: {_ACCENT};
                }}
                QToolButton:hover {{ color: {_TEXT}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_tab_clicked(idx))
            self._tab_flow.addWidget(btn)
            self._tab_buttons.append(btn)

        if self._tab_buttons:
            self._tab_buttons[0].setChecked(True)
        root.addWidget(self._tab_container)

        # ── busca ──
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Buscar material...")
        self._search.setFixedHeight(26)
        self._search.setContentsMargins(10, 0, 10, 0)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {_BG_SECTION}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 2px 8px; font-size: 10px;
                margin: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._search.textChanged.connect(self._on_search)
        root.addWidget(self._search)

        # ── grid de assets ──
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._grid_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._grid_scroll.setMinimumHeight(120)
        self._grid_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._grid_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 3px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {_TEXT_MUTED}; border-radius: 1px; min-height: 16px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        grid_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid_policy.setHeightForWidth(True)
        self._grid_container.setSizePolicy(grid_policy)
        self._grid_layout = FlowLayout(self._grid_container, spacing=2)
        self._grid_layout.setContentsMargins(10, 6, 10, 6)
        self._grid_scroll.setWidget(self._grid_container)
        root.addWidget(self._grid_scroll, 1)

        self._asset_buttons: list[MaterialThumbnail] = []

    # ─── Public API ──────────────────────────────────────────────────────

    def set_assets(self, assets: list[dict]):
        """Populate material grid. Each dict: {id, name, pixmap, favorite}."""
        for btn in self._asset_buttons:
            self._grid_layout.removeWidget(btn)
            btn.deleteLater()
        self._asset_buttons.clear()

        for asset in assets:
            btn = MaterialThumbnail(asset.get("id", ""), asset.get("name", ""))
            if "pixmap" in asset and asset["pixmap"]:
                btn.set_pixmap(asset["pixmap"])
            if asset.get("favorite"):
                btn.set_favorite(True)
            btn.clicked.connect(lambda checked, a=asset: self._on_asset_clicked(a))
            btn.favorited.connect(self.favorite_toggled.emit)
            self._grid_layout.addWidget(btn)
            self._asset_buttons.append(btn)

    def current_category(self) -> str:
        idx = next((i for i, b in enumerate(self._tab_buttons) if b.isChecked()), 0)
        return self._tab_categories[idx] if idx < len(self._tab_categories) else "__favorites__"

    def current_style(self) -> str:
        idx = next((i for i, b in enumerate(self._style_buttons) if b.isChecked()), 0)
        return self._style_keys[idx] if idx < len(self._style_keys) else DEFAULT_STYLE

    def _on_style_tab_clicked(self, index: int):
        for i, btn in enumerate(self._style_buttons):
            btn.setChecked(i == index)
        if index < len(self._style_keys):
            self.style_changed.emit(self._style_keys[index])

    def _on_search(self, text: str):
        query = text.strip().lower()
        for btn in self._asset_buttons:
            btn.setVisible(not query or query in btn.toolTip().lower())
        self._grid_container.adjustSize()
        self._grid_layout.update()

    def _on_asset_clicked(self, asset: dict):
        for btn in self._asset_buttons:
            if btn.asset_id != asset.get("id", ""):
                btn.setChecked(False)
        self.asset_selected.emit(asset.get("id", ""))

    def _on_tab_clicked(self, index: int):
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == index)
        self._search.clear()
        if index < len(self._tab_categories):
            category = self._tab_categories[index]
        else:
            category = "__favorites__"
        self.tab_changed.emit(category)

    def showEvent(self, event):
        super().showEvent(event)
        # Tab buttons are built once while the panel is still hidden, so FlowLayout's
        # first real pass sees them all as invisible and never positions them. Force a
        # fresh pass now that they're actually visible.
        self._style_tab_flow.invalidate()
        self._tab_flow.invalidate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # QScrollArea's automatic widget-resizable negotiation can latch onto
        # FlowLayout's self-referential sizeHint() and never correct the grid
        # widget's width afterward. Force it to track the viewport explicitly.
        vp_w = self._grid_scroll.viewport().width()
        if vp_w > 0 and self._grid_container.width() != vp_w:
            self._grid_container.resize(vp_w, self._grid_container.heightForWidth(vp_w))

    def paintEvent(self, event):
        paint_glass_panel(self)
