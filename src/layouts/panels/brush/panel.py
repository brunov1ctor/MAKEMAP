"""Brush Tool Panel — configuração de pincel (tamanho, material, transform).

Asset browsing (category tabs + search + grid) lives in AssetBrowserPanel,
shown alongside this one — see asset_browser.py for why they're split.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QScrollArea, QWidget, QToolButton,
    QCheckBox, QGraphicsDropShadowEffect, QComboBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QBrush, QPixmap, QColor

from src.styles.tokens import Colors
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panel_manager import paint_glass_panel


_BG_SECTION = "rgba(255, 255, 255, 0.04)"
_BORDER = "rgba(255, 255, 255, 0.10)"
_ACCENT = Colors.ACCENT
_ACCENT_DIM = Colors.ACCENT_DIM
_TEXT = Colors.TEXT_PRIMARY
_TEXT_SEC = Colors.TEXT_SECONDARY
_TEXT_MUTED = Colors.TEXT_MUTED


# ─── Texture Preview ────────────────────────────────────────────────────────

class TexturePreviewWidget(QFrame):
    """Large texture preview reflecting current brush settings.

    Click opens the Assets browser panel — this is the one entry point for
    it now (selecting the Brush tool no longer opens it automatically).
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clique para escolher um asset")
        self._hovered = False
        self._apply_frame_style()
        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._rotation = 0.0
        self._opacity = 1.0

    def _apply_frame_style(self):
        border = _ACCENT if self._hovered else _BORDER
        self.setStyleSheet(f"""
            QFrame {{
                background: {_BG_SECTION};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)

    def enterEvent(self, event):
        self._hovered = True
        self._apply_frame_style()
        # Only one widget, generously spaced from its siblings — safe to use
        # a real glow here (unlike the tightly-packed asset grid, where the
        # same effect bled onto neighboring thumbnails).
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setOffset(0, 0)
        glow.setColor(QColor(_ACCENT))
        self.setGraphicsEffect(glow)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_frame_style()
        self.setGraphicsEffect(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

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


# ─── Separator ───────────────────────────────────────────────────────────────

def _separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {_BORDER}; border: none;")
    return sep


# ─── Main Panel ─────────────────────────────────────────────────────────────

class BrushToolPanel(QFrame):
    """Brush config panel — size/opacity/style/material/transform."""

    PANEL_WIDTH = 300

    mode_changed = Signal(str)
    terrain_changed = Signal(str)  # terrain_id ("" = Mapa Infinito) — "Pintando em" dropdown
    assets_requested = Signal()  # texture preview clicked — open the Assets browser
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        # layout raiz do QFrame — tudo dentro dele recebe o fundo glass via paintEvent
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── parte superior com scroll (sliders) ──
        self._top_scroll = QScrollArea()
        self._top_scroll.setWidgetResizable(True)
        self._top_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._top_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._top_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._top_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._top_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {_TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        top_w = QWidget()
        top_w.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(top_w)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(4)
        self._top_scroll.setWidget(top_w)

        self._build_header()
        self._build_terrain_indicator()
        self._layout.addWidget(_separator())
        self._build_sliders_grid()
        self._layout.addWidget(_separator())
        self._build_material_section()
        self._layout.addWidget(_separator())
        self._build_transform_section()
        self._layout.addStretch()

        root.addWidget(self._top_scroll, 1)

        self._current_mode = "paint"

    def _build_header(self):
        header = QHBoxLayout()
        header.setContentsMargins(0, 2, 0, 4)
        header.setSpacing(6)

        icon = QLabel("🖌")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
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

    def _build_terrain_indicator(self):
        """"Pintando em" — a real dropdown (not just a label reflecting
        whatever's selected over in the Terrain panel), same as Região's
        own, so you can pick which terrain to paint into (or "Mapa
        Infinito") directly from here."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(4)

        icon = QLabel("🗺")
        icon.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        row.addWidget(icon)

        label = QLabel("Pintando em")
        label.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none;")
        row.addWidget(label)

        self._terrain_combo = QComboBox()
        self._terrain_combo.addItem("🌍 Mapa Infinito", "")
        self._terrain_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._terrain_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(255,255,255,0.04); color: {_TEXT_SEC};
                border: 1px solid {_BORDER}; border-radius: 4px;
                padding: 3px 8px; font-size: 10px;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {_TEXT};
                border: 1px solid {Colors.BORDER}; selection-background-color: {_ACCENT_DIM};
            }}
        """)
        self._terrain_combo.currentIndexChanged.connect(
            lambda i: self.terrain_changed.emit(self._terrain_combo.itemData(i))
        )
        row.addWidget(self._terrain_combo, 1)

        self._layout.addLayout(row)

    def set_terrain_options(self, options: list[tuple[str, str]]):
        """Rebuild the "Pintando em" dropdown. `options` is a list of
        (terrain_id, name) for every currently-existing terrain — "Mapa
        Infinito" (id "") is always prepended automatically."""
        current = self._terrain_combo.itemData(self._terrain_combo.currentIndex())
        self._terrain_combo.blockSignals(True)
        self._terrain_combo.clear()
        self._terrain_combo.addItem("🌍 Mapa Infinito", "")
        for terrain_id, name in options:
            self._terrain_combo.addItem(f"🗺 {name}", terrain_id)
        idx = self._terrain_combo.findData(current)
        self._terrain_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._terrain_combo.blockSignals(False)

    def _build_sliders_grid(self):
        # One column, not two — a 2-column grid in a 300px-wide panel doesn't
        # leave enough room for the icon+label+value row of a BrushSlider,
        # and since the panel's horizontal scrollbar is disabled, the excess
        # width was silently clipped instead of scrolling into view. Each
        # slider gets the full row instead.
        col = QVBoxLayout()
        col.setContentsMargins(0, 4, 0, 4)
        col.setSpacing(2)

        self.size_slider = BrushSlider("Brush Size", "🖌", 1, 1000, 100, "m")
        self.opacity_slider = BrushSlider("Opacity", "💧", 0, 100, 100, "%")
        self.softness_slider = BrushSlider("Softness", "◎", 0, 100, 50, "%")
        self.scale_slider = BrushSlider("Texture Scale", "🔲", 10, 500, 100, "%")
        self.rotation_slider = BrushSlider("Rotation", "↻", 0, 360, 0, "°")
        self.density_slider = BrushSlider("Density", "▣", 1, 20, 3, "")
        self.roughness_slider = BrushSlider("Roughness", "〰", 0, 100, 0, "%")
        self.roughness_slider.setToolTip(
            "Deixa a borda do pincel irregular. Sem efeito com Snap ativado — "
            "o preenchimento de célula não tem borda pra deixar irregular."
        )
        self.smoothness_slider = BrushSlider("Smoothness", "🫧", 0, 100, 0, "%")
        self.smoothness_slider.setToolTip(
            "Transição suave (fade) ao trocar de asset/material no meio da pintura."
        )

        sliders = [
            self.size_slider, self.opacity_slider,
            self.softness_slider, self.scale_slider,
            self.rotation_slider, self.density_slider,
            self.roughness_slider, self.smoothness_slider,
        ]
        for slider in sliders:
            col.addWidget(slider)

        self._layout.addLayout(col)

    def _build_material_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(4)

        # Material name gets its own row, elided — the 3 mode buttons below
        # (109+99+109px unelided) were already wider than the whole 300px
        # panel on their own; putting a name next to them made it worse. A
        # long asset name now just truncates with "…" instead of pushing
        # the buttons off the edge (panel's horizontal scrollbar is off, so
        # overflow was silently invisible, not scrollable).
        self._material_label = QLabel("")
        self._material_label.setStyleSheet(f"""
            color: {_TEXT}; font-size: 11px; font-weight: bold;
            background: transparent; border: none;
        """)
        self._material_label.setMinimumWidth(0)
        section.addWidget(self._material_label)

        mat_row = QHBoxLayout()
        mat_row.setSpacing(4)

        mode_style_active = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 9px;
                color: {_ACCENT}; background: {_ACCENT_DIM};
                padding: 3px 4px;
            }}
        """
        mode_style = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 9px;
                color: {_TEXT_SEC}; background: transparent;
                padding: 3px 4px;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
        """

        self._paint_btn = QToolButton()
        self._paint_btn.setText("🖌 Paint")
        self._paint_btn.setStyleSheet(mode_style_active)
        self._paint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paint_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._paint_btn.clicked.connect(lambda: self._set_mode("paint"))
        mat_row.addWidget(self._paint_btn)

        self._mask_btn = QToolButton()
        self._mask_btn.setText("◑ Mask")
        self._mask_btn.setStyleSheet(mode_style)
        self._mask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mask_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._mask_btn.clicked.connect(lambda: self._set_mode("mask"))
        mat_row.addWidget(self._mask_btn)

        self._erase_btn = QToolButton()
        self._erase_btn.setText("⌫ Erase")
        self._erase_btn.setStyleSheet(mode_style)
        self._erase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._erase_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._erase_btn.clicked.connect(lambda: self._set_mode("erase"))
        mat_row.addWidget(self._erase_btn)

        section.addLayout(mat_row)

        self.texture_preview = TexturePreviewWidget()
        self.texture_preview.clicked.connect(self.assets_requested.emit)
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

    def _build_transform_section(self):
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(2)

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
        self._layout.addLayout(section)

    # ─── Public API ──────────────────────────────────────────────────────

    def set_material_name(self, name: str):
        # Elide instead of letting a long asset name push the panel wider
        # than PANEL_WIDTH (the mode buttons row below is already tight).
        available = self.PANEL_WIDTH - 20  # minus the panel's own left/right margins
        metrics = self._material_label.fontMetrics()
        elided = metrics.elidedText(name, Qt.TextElideMode.ElideRight, available)
        self._material_label.setText(elided)
        self._material_label.setToolTip(name)


    def set_texture_preview(self, pixmap: QPixmap | None):
        self.texture_preview.set_texture(pixmap)

    def paintEvent(self, event):
        paint_glass_panel(self)
