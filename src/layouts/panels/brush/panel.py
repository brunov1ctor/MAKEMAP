"""Brush Tool Panel — configuração de pincel (tamanho, material, transform).

Two sections sharing one floating panel/header (see __init__): "Parâmetros"
(sliders) and "Assets" (material preview + mode + transform), swapped via a
small tab row. The asset GRID itself (category tabs + search + thumbnails)
isn't embedded here — it's a separate AssetBrowserPanel that rides next to
this one, opened by clicking the big texture-preview rectangle on the
Assets tab (same adjacent-panel pattern as Região's CRUD list +
RegionEditPanel), not another tab/page inside this panel.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSizePolicy, QScrollArea, QWidget, QToolButton,
    QCheckBox, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QBrush, QPixmap

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
    """Large texture preview reflecting current brush settings — click it
    to open the adjacent AssetBrowserPanel (grid), same as clicking a card
    opens Região's edit panel."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Escolher asset")
        self._hovered = False
        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._rotation = 0.0
        self._opacity = 1.0
        self._update_style()

    def _update_style(self):
        border = _ACCENT if self._hovered else _BORDER
        self.setStyleSheet(f"""
            QFrame {{
                background: {_BG_SECTION};
                border: 1px solid {border};
                border-radius: 6px;
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

    def enterEvent(self, event):
        self._hovered = True
        self._update_style()

    def leaveEvent(self, event):
        self._hovered = False
        self._update_style()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()

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
        # QBrush tiles the pixmap at its native PIXEL size regardless of
        # this widget's size — a texture larger than this ~60px-tall swatch
        # (most of them are, e.g. 512px) used to show only a tiny, extreme
        # close-up corner of it, reading as "stuck at some huge zoom" no
        # matter what _scale was. Normalize to the widget's own box first
        # (one full tile spans its height) and apply _scale — the brush's
        # actual canvas tiling density, 0.1-3.0 — on top of THAT baseline,
        # so it stays a legible material swatch that also reflects the
        # relative density the slider will paint at.
        if self._pixmap.height() > 0:
            base = self.height() / self._pixmap.height()
            total_scale = base * self._scale
            if total_scale != 1.0:
                t.scale(total_scale, total_scale)
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
    close_requested = Signal()
    assets_requested = Signal()
    content_changed = Signal()
    path_direction_changed = Signal(float)  # +1.0 or -1.0

    # Modos do painel
    MODE_BRUSH = "brush"
    MODE_RIVER = "river"
    MODE_ROAD  = "road"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._current_section = "params"  # read by _refresh_section_tab_style, built below
        self._terrain_names: dict[str, str] = {}
        self._active_terrain_id: str = ""
        self._panel_mode = self.MODE_BRUSH  # brush | river | road

        # layout raiz do QFrame — tudo dentro dele recebe o fundo glass via paintEvent
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── header + aba Parâmetros/Assets: sempre visíveis, fora da área
        # de scroll de qualquer uma das duas seções, já que servem às duas. ──
        top_container = QWidget()
        top_container.setStyleSheet("background: transparent;")
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(10, 6, 10, 0)
        top_layout.setSpacing(4)
        self._build_header(top_layout)
        top_layout.addWidget(_separator())
        self._build_section_tabs(top_layout)
        root.addWidget(top_container)
        self._top_container = top_container  # read back by content_height() — see its own docstring

        # ── Seção "Parâmetros" (sliders) — com scroll ──
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

        self._build_terrain_indicator()
        self._layout.addWidget(_separator())
        self._build_sliders_grid()
        self._layout.addStretch()

        # ── Seção "Assets" (preview do material atual + modo + transform) ──
        self._section_stack = QStackedWidget()
        self._section_stack.addWidget(self._top_scroll)
        self._section_stack.addWidget(self._build_assets_page())
        self._section_stack.addWidget(self._build_path_params_page())
        root.addWidget(self._section_stack, 1)

        self._current_mode = "paint"

    def _build_header(self, layout):
        header = QHBoxLayout()
        header.setContentsMargins(0, 2, 0, 4)
        header.setSpacing(6)

        self._header_icon = QLabel("🖌")
        self._header_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(self._header_icon)

        self._header_title = QLabel("Brush Tool")
        self._header_title.setStyleSheet(f"""
            color: {_TEXT}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(self._header_title)
        header.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {_TEXT_SEC}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

    def _build_section_tabs(self, layout):
        """⚙ Parâmetros / 🎨 Assets — swaps which QStackedWidget page is
        current. Note: "Assets" here is just material preview + mode +
        transform — the actual asset GRID lives in a separate
        AssetBrowserPanel opened by clicking the preview rectangle."""
        row = QHBoxLayout()
        row.setSpacing(4)

        self._params_tab_btn = QToolButton()
        self._params_tab_btn.setText("⚙ Parâmetros")
        self._params_tab_btn.setCheckable(True)
        self._params_tab_btn.setChecked(True)
        self._params_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._params_tab_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._params_tab_btn.clicked.connect(lambda: self.show_section("params"))
        row.addWidget(self._params_tab_btn)

        self._assets_tab_btn = QToolButton()
        self._assets_tab_btn.setText("🎨 Assets")
        self._assets_tab_btn.setCheckable(True)
        self._assets_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._assets_tab_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._assets_tab_btn.clicked.connect(lambda: self.show_section("assets"))
        row.addWidget(self._assets_tab_btn)

        layout.addLayout(row)
        self._refresh_section_tab_style()

    def show_section(self, section: str):
        """Public so MainLayout (resetting to Parâmetros whenever the
        Brush panel is reopened/closed) can drive it too."""
        self._current_section = section
        self._section_stack.setCurrentWidget(
            self._assets_page if section == "assets" else self._top_scroll
        )
        self._params_tab_btn.setChecked(section == "params")
        self._assets_tab_btn.setChecked(section == "assets")
        self._refresh_section_tab_style()
        self.content_changed.emit()

    def _refresh_section_tab_style(self):
        active = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px; font-weight: bold;
                color: {_ACCENT}; background: {_ACCENT_DIM};
                padding: 5px 8px;
            }}
        """
        inactive = f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 10px;
                color: {_TEXT_SEC}; background: transparent;
                padding: 5px 8px;
            }}
            QToolButton:hover {{ background: #333; color: {_TEXT}; }}
        """
        self._params_tab_btn.setStyleSheet(active if self._current_section == "params" else inactive)
        self._assets_tab_btn.setStyleSheet(active if self._current_section == "assets" else inactive)

    def _build_terrain_indicator(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(4)

        icon = QLabel("🗺")
        icon.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        row.addWidget(icon)

        label = QLabel("Pintando em")
        label.setStyleSheet(f"color: {_TEXT_SEC}; font-size: 10px; background: transparent; border: none;")
        row.addWidget(label)

        self._terrain_lbl = QLabel("Mapa Infinito")
        self._terrain_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        row.addWidget(self._terrain_lbl, 1)

        self._layout.addLayout(row)

    def set_terrain_options(self, options: list[tuple[str, str]]):
        self._terrain_names = {tid: name for tid, name in options}
        self._refresh_terrain_label()

    def active_terrain_name(self) -> str:
        if not self._active_terrain_id:
            return "Mapa Infinito"
        return self._terrain_names.get(self._active_terrain_id, "Mapa Infinito")

    def active_terrain_id(self) -> str:
        return self._active_terrain_id

    def set_active_terrain(self, terrain_id: str):
        self._active_terrain_id = terrain_id or ""
        self._refresh_terrain_label()

    def _refresh_terrain_label(self):
        name = self._terrain_names.get(self._active_terrain_id, "Mapa Infinito") \
            if self._active_terrain_id else "Mapa Infinito"
        self._terrain_lbl.setText(name)

    def _build_sliders_grid(self):
        # 2 columns — each BrushSlider's name label wraps (see slider.py)
        # so it survives the narrower ~130px column width instead of
        # clipping, and this halves the number of rows vs. one long
        # single-column stack, shrinking the panel's overall height.
        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.size_slider = BrushSlider("Size", "🖌", 1, 1000, 50, "m")
        self.opacity_slider = BrushSlider("Opacity", "💧", 0, 100, 100, "%")
        self.softness_slider = BrushSlider("Softness", "◎", 0, 100, 50, "%")
        self.scale_slider = BrushSlider("Scale", "🔲", 0, 100, 50, "%")
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
        for i, slider in enumerate(sliders):
            grid.addWidget(slider, i // 2, i % 2)

        self._layout.addLayout(grid)

    def _build_mode_section(self, target_layout):
        """Paint/Mask/Erase — brush behavior, lives on the Assets tab
        alongside the material preview/transform."""
        section = QVBoxLayout()
        section.setContentsMargins(0, 4, 0, 4)
        section.setSpacing(4)

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
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
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
        self._erase_btn.setToolTip("Apaga qualquer asset sob o pincel.\nAtalho: clique direito apaga sem trocar o modo.")
        self._erase_btn.setStyleSheet(mode_style)
        self._erase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._erase_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._erase_btn.clicked.connect(lambda: self._set_mode("erase"))
        mat_row.addWidget(self._erase_btn)

        section.addLayout(mat_row)
        target_layout.addLayout(section)

    def _build_assets_page(self) -> QWidget:
        """Material name + texture preview (click to open the adjacent
        asset grid subpanel) + mode + transform."""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 6, 10, 0)
        layout.setSpacing(4)

        # Elided — a long asset name shouldn't push the panel wider than
        # PANEL_WIDTH (the panel's horizontal scrollbar is off, so
        # overflow would be silently invisible, not scrollable).
        self._material_label = QLabel("")
        self._material_label.setStyleSheet(f"""
            color: {_TEXT}; font-size: 11px; font-weight: bold;
            background: transparent; border: none;
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        self._material_label.setMinimumWidth(0)
        layout.addWidget(self._material_label)

        self.texture_preview = TexturePreviewWidget()
        self.texture_preview.clicked.connect(self.assets_requested.emit)
        layout.addWidget(self.texture_preview)
        layout.addWidget(_separator())

        self._build_mode_section(layout)
        self._build_transform_section(layout)
        layout.addStretch()

        self._assets_page = page
        return page

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

    def _build_transform_section(self, target_layout):
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
        target_layout.addLayout(section)

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

    def _build_path_params_page(self) -> QWidget:
        """Página de parâmetros para Rio / Estrada — preview do material +
        dica de uso. Largura/Opacidade não têm sliders próprios aqui — são
        os mesmos Tamanho/Opacidade já editáveis na aba Parâmetros normal
        do pincel (ver BrushMediator.on_size_changed/on_opacity_changed,
        que já aplicam o valor às ferramentas Rio/Estrada também)."""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        # Preview da textura (mesma que o modo Assets)
        self._path_texture_preview = TexturePreviewWidget()
        self._path_texture_preview.clicked.connect(self.assets_requested.emit)
        lay.addWidget(self._path_texture_preview)
        lay.addWidget(_separator())

        # Nome do material
        self._path_material_lbl = QLabel("")
        self._path_material_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(self._path_material_lbl)

        lay.addWidget(_separator())

        # Dica de uso
        hint = QLabel(
            "\U0001f4a1 Clique para adicionar pontos \u2022 Arraste ponto para mover\n"
            "Arraste al\u00e7a para curvar \u2022 Duplo-clique para finalizar\n"
            "Clique direito no ponto para remover"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: 9px; "
            f"background: transparent; border: none; line-height: 1.4;"
        )
        lay.addWidget(hint)
        lay.addStretch()

        self._path_page = page
        return page

    def set_panel_mode(self, mode: str):
        """Troca o painel entre modo pincel (brush), rio (river) e estrada (road).
        Atualiza header, abas e página ativa do stack."""
        self._panel_mode = mode
        if mode == self.MODE_RIVER:
            self._header_icon.setText("🌊")
            self._header_title.setText("Rio")
            self._section_stack.setCurrentWidget(self._path_page)
            self._params_tab_btn.setChecked(False)
            self._assets_tab_btn.setChecked(False)
        elif mode == self.MODE_ROAD:
            self._header_icon.setText("🛤")
            self._header_title.setText("Estrada")
            self._section_stack.setCurrentWidget(self._path_page)
            self._params_tab_btn.setChecked(False)
            self._assets_tab_btn.setChecked(False)
        else:
            self._header_icon.setText("🖌")
            self._header_title.setText("Brush Tool")
            # Só reseta para Parâmetros se estava vindo de rio/estrada —
            # se já estava em modo brush, preserva a aba que o usuário escolheu.
            if self._panel_mode in (self.MODE_RIVER, self.MODE_ROAD):
                self._current_section = "params"
                self._params_tab_btn.setChecked(True)
                self._assets_tab_btn.setChecked(False)
                self._section_stack.setCurrentWidget(self._top_scroll)
            else:
                self._section_stack.setCurrentWidget(
                    self._assets_page if self._current_section == "assets" else self._top_scroll
                )
                self._params_tab_btn.setChecked(self._current_section == "params")
                self._assets_tab_btn.setChecked(self._current_section == "assets")
            self._refresh_section_tab_style()
        self.content_changed.emit()

    def set_path_material(self, name: str, pixmap: QPixmap | None):
        """Atualiza nome e preview de textura na página de path."""
        available = self.PANEL_WIDTH - 20
        metrics = self._path_material_lbl.fontMetrics()
        self._path_material_lbl.setText(
            metrics.elidedText(name or "", Qt.TextElideMode.ElideRight, available)
        )
        self._path_material_lbl.setToolTip(name or "")
        self._path_texture_preview.set_texture(pixmap)

    def content_height(self) -> int:
        """Own override — PanelManager's generic _content_height() only
        measures the first QScrollArea it finds (_top_scroll) and reports
        just ITS inner content height, which misses two things here:
        top_container (header + Parâmetros/Assets tabs) lives outside any
        scroll area, added straight to `root`, so its height was never
        counted at all (same "header outside the scroll" undercount as
        Terrain/Região's own content_height overrides) — that's what was
        clipping the bottom sliders. And on the Assets tab, findChild()
        would still land on _top_scroll (the only QScrollArea in the whole
        widget tree) regardless of which page is actually showing, sizing
        the panel off the WRONG (currently hidden) page's content instead
        of the Assets page actually on screen."""
        self._top_container.adjustSize()
        header_h = self._top_container.sizeHint().height()
        if self._current_section == "assets":
            self._assets_page.adjustSize()
            body_h = self._assets_page.sizeHint().height()
        else:
            body_widget = self._top_scroll.widget()
            body_widget.adjustSize()
            body_h = body_widget.sizeHint().height()
        return header_h + body_h + 20

    def paintEvent(self, event):
        paint_glass_panel(self)
