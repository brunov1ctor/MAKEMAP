"""Brush Tool Panel — painel lateral completo estilo Inkarnate para edição de pincéis."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QComboBox, QSizePolicy, QScrollArea, QWidget, QToolButton,
    QCheckBox, QLineEdit, QTabBar, QLayout, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QRectF, QSize, QRect, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush,
    QPixmap, QIcon, QFont,
)

from src.styles.tokens import Colors, Typography


# ─── Flow Layout ─────────────────────────────────────────────────────────────

class FlowLayout(QLayout):
    """Layout that arranges items left-to-right, wrapping to next line."""

    def __init__(self, parent=None, spacing=4):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect, test_only=False):
        x = rect.x()
        y = rect.y()
        row_h = 0

        for item in self._items:
            item_size = item.sizeHint()
            if x + item_size.width() > rect.right() and row_h > 0:
                x = rect.x()
                y += row_h + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x += item_size.width() + self._spacing
            row_h = max(row_h, item_size.height())

        return y + row_h - rect.y()


# ─── Design Tokens (Glass) ───────────────────────────────────────────────────

_BG = "rgba(11, 25, 41, 0.92)"
_BG_SECTION = "rgba(255, 255, 255, 0.04)"
_BORDER = "rgba(255, 255, 255, 0.10)"
_ACCENT = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM
_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_TEXT_MUTED = Colors.TEXT_MUTED
_SLIDER_GROOVE = Colors.BORDER_SUBTLE
_SLIDER_HANDLE = Colors.ACCENT


# ─── Reusable Slider ────────────────────────────────────────────────────────

class BrushSlider(QFrame):
    """Slider with icon, label, and value display."""

    value_changed = Signal(float)

    def __init__(self, label: str, icon: str, min_val: float, max_val: float,
                 default: float, suffix: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._min = min_val
        self._max = max_val
        self._suffix = suffix

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)

        # Top row: icon + label + value
        top = QHBoxLayout()
        top.setSpacing(4)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 11px; background: transparent; border: none;")
        top.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none;")
        top.addWidget(name_lbl)
        top.addStretch()

        self._value_label = QLabel(self._format(default))
        self._value_label.setFixedWidth(40)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value_label.setStyleSheet(f"color: {_TEXT}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        top.addWidget(self._value_label)
        layout.addLayout(top)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(self._to_slider(default))
        self._slider.setFixedHeight(16)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.wheelEvent = lambda e: e.ignore()
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {_SLIDER_GROOVE}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px; height: 12px; margin: -4px 0;
                background: {_SLIDER_HANDLE}; border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_ACCENT_DIM}; border-radius: 2px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)

    def _to_slider(self, val: float) -> int:
        return int((val - self._min) / (self._max - self._min) * 100)

    def _from_slider(self, pos: int) -> float:
        return self._min + (pos / 100.0) * (self._max - self._min)

    def _format(self, val: float) -> str:
        if self._suffix == "°":
            return f"{val:.0f}{self._suffix}"
        if self._max > 10:
            return f"{val:.0f}{self._suffix}"
        return f"{val:.0f}{self._suffix}" if self._suffix == "%" else f"{val:.2f}{self._suffix}"

    def _on_change(self, pos: int):
        val = self._from_slider(pos)
        self._value_label.setText(self._format(val))
        self.value_changed.emit(val)

    @property
    def value(self) -> float:
        return self._from_slider(self._slider.value())

    def set_value(self, val: float):
        self._slider.blockSignals(True)
        self._slider.setValue(self._to_slider(val))
        self._value_label.setText(self._format(val))
        self._slider.blockSignals(False)


# ─── Material Thumbnail ─────────────────────────────────────────────────────

class MaterialThumbnail(QToolButton):
    """Clickable material thumbnail for the grid."""

    favorited = Signal(str)  # asset_id

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
        self._is_favorite = fav
        if fav:
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(12)
            glow.setOffset(0, 0)
            glow.setColor(QColor(_ACCENT))
            self.setGraphicsEffect(glow)
        else:
            self.setGraphicsEffect(None)
        self._update_style()

    def _update_style(self):
        border = _ACCENT if self._is_favorite else _BORDER
        self.setStyleSheet(f"""
            QToolButton {{
                border: 2px solid {border}; border-radius: 4px;
                background: {_BG_SECTION}; padding: 2px;
                font-size: 10px; color: {_TEXT_MUTED};
            }}
            QToolButton:hover {{
                border-color: {_TEXT_SEC};
            }}
            QToolButton:checked {{
                border-color: {_ACCENT};
                background: {_ACCENT_DIM};
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


# ─── Texture Preview ────────────────────────────────────────────────────────

class TexturePreviewWidget(QFrame):
    """Large texture preview reflecting current brush settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_BG_SECTION};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._rotation = 0.0
        self._opacity = 1.0

    def set_texture(self, pixmap: QPixmap | None):
        self._pixmap = pixmap
        self.update()

    def set_scale(self, scale: float):
        self._scale = max(0.1, scale)
        self.update()

    def set_rotation(self, rotation: float):
        self._rotation = rotation
        self.update()

    def set_opacity(self, opacity: float):
        self._opacity = max(0.0, min(1.0, opacity))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap or self._pixmap.isNull():
            return
        from PySide6.QtGui import QTransform
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(self._opacity)

        # Create scaled/rotated texture brush
        brush = QBrush(self._pixmap)
        t = QTransform()
        if self._rotation != 0.0:
            t.rotate(self._rotation)
        if self._scale != 1.0:
            t.scale(self._scale, self._scale)
        brush.setTransform(t)

        p.setBrush(brush)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 6, 6)
        p.end()


# ─── Section Separator ───────────────────────────────────────────────────────

def _separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORDER}; border: none;")
    return sep


# ─── Main Panel ─────────────────────────────────────────────────────────────

class BrushToolPanel(QFrame):
    """Complete brush tool panel — Inkarnate-style."""

    PANEL_WIDTH = 300

    # Signals
    asset_selected = Signal(str)
    favorite_toggled = Signal(str)  # asset_id
    mode_changed = Signal(str)  # "paint", "mask", "erase"
    tab_changed = Signal(str)   # category name
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        # Main scroll
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                width: 4px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {_TEXT_MUTED}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(10, 6, 10, 8)
        self._layout.setSpacing(2)

        self._build_header()
        self._layout.addWidget(_separator())
        self._build_settings_section()
        self._layout.addWidget(_separator())
        self._build_material_section()
        self._layout.addWidget(_separator())
        self._build_transform_section()
        self._layout.addWidget(_separator())
        self._build_favorites_section()
        self._layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._asset_buttons: list[MaterialThumbnail] = []
        self._current_mode = "paint"

    # ─── Header ──────────────────────────────────────────────────────────

    def _build_header(self):
        header = QHBoxLayout()
        header.setContentsMargins(0, 2, 0, 4)
        header.setSpacing(6)

        icon = QLabel("🖌")
        icon.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Brush Tool")
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

        self._layout.addLayout(header)

    # ─── Toolbar ─────────────────────────────────────────────────────────

    def _build_toolbar(self):
        pass

    # ─── Brush Settings ──────────────────────────────────────────────────

    def _build_settings_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(2)

        self.size_slider = BrushSlider("Brush Size", "🖌", 1, 1000, 100, "")
        self.opacity_slider = BrushSlider("Opacity", "💧", 0, 100, 100, "%")
        self.softness_slider = BrushSlider("Softness", "◎", 0, 100, 50, "%")

        section.addWidget(self.size_slider)
        section.addWidget(self.opacity_slider)
        section.addWidget(self.softness_slider)

        self._layout.addLayout(section)

    # ─── Material Section ────────────────────────────────────────────────

    def _build_material_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(4)

        # Material name + mode buttons
        mat_row = QHBoxLayout()
        mat_row.setSpacing(4)

        self._material_label = QLabel("Green Grass")
        self._material_label.setStyleSheet(f"""
            color: {_TEXT}; font-size: 11px; font-weight: bold;
            background: transparent; border: none;
        """)
        mat_row.addWidget(self._material_label)
        mat_row.addStretch()

        mode_style_active = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px;
                color: {_ACCENT}; background: {_ACCENT_DIM};
                padding: 3px 8px;
            }}
        """
        mode_style = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px;
                color: {_TEXT_SEC}; background: transparent;
                padding: 3px 8px;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
        """

        self._paint_btn = QToolButton()
        self._paint_btn.setText("🖌 Paint")
        self._paint_btn.setToolTip("Paint")
        self._paint_btn.setStyleSheet(mode_style_active)
        self._paint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paint_btn.clicked.connect(lambda: self._set_mode("paint"))
        mat_row.addWidget(self._paint_btn)

        self._mask_btn = QToolButton()
        self._mask_btn.setText("◑ Mask")
        self._mask_btn.setToolTip("Mask")
        self._mask_btn.setStyleSheet(mode_style)
        self._mask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mask_btn.clicked.connect(lambda: self._set_mode("mask"))
        mat_row.addWidget(self._mask_btn)

        self._erase_btn = QToolButton()
        self._erase_btn.setText("⌫ Erase")
        self._erase_btn.setToolTip("Erase")
        self._erase_btn.setStyleSheet(mode_style)
        self._erase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._erase_btn.clicked.connect(lambda: self._set_mode("erase"))
        mat_row.addWidget(self._erase_btn)

        section.addLayout(mat_row)

        # Texture preview
        self.texture_preview = TexturePreviewWidget()
        section.addWidget(self.texture_preview)

        self._layout.addLayout(section)

    def _set_mode(self, mode: str):
        self._current_mode = mode
        active = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px;
                color: {_ACCENT}; background: {_ACCENT_DIM};
                padding: 3px 8px;
            }}
        """
        inactive = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px;
                color: {_TEXT_SEC}; background: transparent;
                padding: 3px 8px;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
        """
        self._paint_btn.setStyleSheet(active if mode == "paint" else inactive)
        self._mask_btn.setStyleSheet(active if mode == "mask" else inactive)
        self._erase_btn.setStyleSheet(active if mode == "erase" else inactive)
        self.mode_changed.emit(mode)

    # ─── Transform Section ───────────────────────────────────────────────

    def _build_transform_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(2)

        self.scale_slider = BrushSlider("Texture Scale", "🔲", 10, 500, 100, "%")
        self.rotation_slider = BrushSlider("Rotation", "↻", 0, 360, 0, "°")

        section.addWidget(self.scale_slider)
        section.addWidget(self.rotation_slider)

        # Random rotation checkbox
        self.random_rotation_check = QCheckBox("Random Rotation")
        self.random_rotation_check.setStyleSheet(f"""
            QCheckBox {{ color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid {_BORDER}; background: {_BG_SECTION};
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT_DIM}; border-color: {_ACCENT};
            }}
        """)
        self.random_rotation_check.setChecked(True)
        section.addWidget(self.random_rotation_check)

        # Density slider
        self.density_slider = BrushSlider("Density", "▣", 1, 20, 3, "")

        section.addWidget(self.density_slider)

        self._layout.addLayout(section)

    # ─── Favorites / Material Grid ───────────────────────────────────────

    def _build_favorites_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(4)

        # Tabs (Property Sheet style — multiple rows)
        self._tab_container = QWidget()
        self._tab_container.setStyleSheet("background: transparent;")
        self._tab_flow = FlowLayout(self._tab_container, spacing=2)
        self._tab_flow.setContentsMargins(0, 0, 0, 0)

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
                QToolButton:hover {{
                    color: {_TEXT};
                }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_tab_clicked(idx))
            self._tab_flow.addWidget(btn)
            self._tab_buttons.append(btn)

        if self._tab_buttons:
            self._tab_buttons[0].setChecked(True)

        section.addWidget(self._tab_container)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Buscar material...")
        self._search.setFixedHeight(24)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {_BG_SECTION}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 2px 8px; font-size: 10px;
            }}
            QLineEdit:focus {{
                border-color: {_ACCENT};
            }}
        """)
        section.addWidget(self._search)

        # Grid
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._grid_scroll.setMinimumHeight(80)
        self._grid_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._grid_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                width: 3px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {_TEXT_MUTED}; border-radius: 1px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = FlowLayout(self._grid_container, spacing=4)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._grid_scroll.setWidget(self._grid_container)
        section.addWidget(self._grid_scroll)

        self._layout.addLayout(section)

    # ─── Public API ──────────────────────────────────────────────────────

    def set_assets(self, assets: list[dict]):
        """Populate material grid. Each dict: {id, name, pixmap, favorite}."""
        for btn in self._asset_buttons:
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

    def set_material_name(self, name: str):
        self._material_label.setText(name)

    def set_texture_preview(self, pixmap: QPixmap | None):
        self.texture_preview.set_texture(pixmap)

    def _on_asset_clicked(self, asset: dict):
        for btn in self._asset_buttons:
            if btn.asset_id != asset.get("id", ""):
                btn.setChecked(False)
        self._material_label.setText(asset.get("name", ""))
        self.asset_selected.emit(asset.get("id", ""))

    def _on_tab_clicked(self, index: int):
        """Handle tab button click — uncheck others and emit signal."""
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == index)
        if index < len(self._tab_categories):
            category = self._tab_categories[index]
        else:
            category = "__favorites__"
        self.tab_changed.emit(category)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 235))
        grad = QLinearGradient(0, 0, 0, h * 0.15)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawPath(path)
        p.end()
