"""RegionEditPanel — "Região Selecionada" detail/edit side panel.

Opened by RegionMediator on "Nova Região" (blank, arms RegionBrushTool in
create mode) or on selecting an existing card (pre-filled, arms
RegionBrushTool in edit mode). Mirrors GridSettingsPanel/BrushToolPanel's
glass-panel shell.

Split into 3 collapsible sections (Informações, Ferramentas de Pintura,
Detalhes) — each with a show/hide arrow header, same collapse mechanics
the old category sections used. The Adicionar/Remover mode toggle sits
below all three sections, not inside any of them, since it's the one
control you're likely to keep flipping mid-paint regardless of which
section is open.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton,
    QLineEdit, QComboBox, QTextEdit, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.region.star_rating import StarRating
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider

ESTILOS = ["Nenhum", "Vapor"]


class RegionEditPanel(QFrame):
    """Side panel to create/edit a single região's properties + brush params."""

    PANEL_WIDTH = 300

    name_changed = Signal(str)
    terrain_changed = Signal(str)         # terrain_id ("" = Mapa Infinito)
    category_changed = Signal(str)       # category_key
    color_changed = Signal(QColor)
    radius_changed = Signal(float)
    mode_changed = Signal(str)           # "add" | "remove"
    opacity_changed = Signal(float)
    stars_changed = Signal(int)
    estilo_changed = Signal(str)
    observacao_changed = Signal(str)
    close_requested = Signal()
    save_requested = Signal()  # "Salvar Região" — only shown while creating
    content_changed = Signal()  # a section expanded/collapsed — panel needs re-sizing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self._color = QColor(120, 200, 220, 90)
        self._mode = "add"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
        )

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(8)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)
        icon = QLabel("🏙")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)
        title = QLabel("REGIÃO SELECIONADA")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        layout.addWidget(self._sep())

        # ═══ Pintando em: <terreno> — always visible, not inside a
        # collapsible section, same spirit as the Brush panel's own
        # "Pintando em" indicator, but a real dropdown here so the brush
        # can be constrained to any already-created terrain's bounds
        # (or "Mapa Infinito") independently of whatever's selected over
        # in the Terrain panel. ═══
        terrain_row = QHBoxLayout()
        terrain_row.setSpacing(6)
        terrain_icon = QLabel("🖌")
        terrain_icon.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        terrain_row.addWidget(terrain_icon)
        terrain_label = QLabel("Pintando em")
        terrain_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        terrain_row.addWidget(terrain_label)
        self._terrain_combo = QComboBox()
        self._terrain_combo.addItem("🌍 Mapa Infinito", "")
        self._terrain_combo.setStyleSheet(self._combo_style())
        self._terrain_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._terrain_combo.currentIndexChanged.connect(
            lambda i: self.terrain_changed.emit(self._terrain_combo.itemData(i))
        )
        terrain_row.addWidget(self._terrain_combo, 1)
        layout.addLayout(terrain_row)
        layout.addWidget(self._sep())

        # ═══ Seção 1 — Informações ═══
        info_section = CollapsibleSection("Informações")
        info_section.content_changed.connect(self.content_changed.emit)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome da região...")
        self._name_edit.setStyleSheet(self._input_style())
        self._name_edit.editingFinished.connect(lambda: self.name_changed.emit(self._name_edit.text().strip()))
        info_section.content_layout.addWidget(self._field_row("Nome", self._name_edit))

        self._type_edit = QLineEdit()
        self._type_edit.setPlaceholderText("Ex: Residencial, Zona Portuária...")
        self._type_edit.setStyleSheet(self._input_style())
        self._type_edit.editingFinished.connect(lambda: self.category_changed.emit(self._type_edit.text().strip()))
        info_section.content_layout.addWidget(self._field_row("Tipo", self._type_edit))

        self._color_btn = QToolButton()
        self._color_btn.setFixedHeight(24)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.clicked.connect(self._toggle_color_picker)
        self._refresh_color_btn()
        info_section.content_layout.addWidget(self._field_row("Cor da região", self._color_btn))

        self._color_picker = self._build_color_picker()
        self._color_picker.hide()
        info_section.content_layout.addWidget(self._color_picker)

        layout.addWidget(info_section)
        layout.addWidget(self._sep())

        # ═══ Seção 2 — Ferramentas de Pintura ═══
        tools_section = CollapsibleSection("Ferramentas de Pintura")
        tools_section.content_changed.connect(self.content_changed.emit)

        self.radius_slider = BrushSlider("Raio do pincel", "◯", 5, 500, 50, "m")
        self.radius_slider.value_changed.connect(self.radius_changed.emit)
        tools_section.content_layout.addWidget(self.radius_slider)

        # "Opacidade" is the região's own live transparency (RegionLayer.
        # set_opacity, a real QGraphicsItem opacity) — NOT the brush's
        # paint-mask alpha, which only ever accumulates and can't be
        # lowered once painted. Wired that way specifically so this
        # always visibly does something the instant it's dragged,
        # regardless of how much of the área is already painted.
        self.opacity_slider = BrushSlider("Opacidade", "▦", 5, 100, 50, "%")
        self.opacity_slider.value_changed.connect(lambda v: self.opacity_changed.emit(v / 100.0))
        tools_section.content_layout.addWidget(self.opacity_slider)

        layout.addWidget(tools_section)
        layout.addWidget(self._sep())

        # ═══ Seção 3 — Detalhes ═══
        details_section = CollapsibleSection("Detalhes")
        details_section.content_changed.connect(self.content_changed.emit)

        diff_row = QHBoxLayout()
        diff_label = QLabel("Dificuldade")
        diff_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        diff_row.addWidget(diff_label)
        diff_row.addStretch()
        self.stars = StarRating(0, button_size=18, font_size=14)
        self.stars.stars_changed.connect(self.stars_changed.emit)
        diff_row.addWidget(self.stars)
        details_section.content_layout.addLayout(diff_row)

        self._estilo_combo = QComboBox()
        self._estilo_combo.addItems(ESTILOS)
        self._estilo_combo.setStyleSheet(self._combo_style())
        self._estilo_combo.currentTextChanged.connect(self.estilo_changed.emit)
        details_section.content_layout.addWidget(self._field_row("Estilo", self._estilo_combo))

        obs_label = QLabel("Observação")
        obs_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        details_section.content_layout.addWidget(obs_label)
        self._obs_edit = QTextEdit()
        self._obs_edit.setFixedHeight(70)
        self._obs_edit.setStyleSheet(f"""
            QTextEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 10px;
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px;
            }}
        """)
        self._obs_edit.focusOutEvent = self._make_obs_focus_out(self._obs_edit)
        details_section.content_layout.addWidget(self._obs_edit)

        layout.addWidget(details_section)
        layout.addWidget(self._sep())

        # ═══ Salvar — only visible while creating a new região ═══
        self._save_btn = QToolButton()
        self._save_btn.setText("✓ Salvar Região")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setMinimumHeight(34)
        self._save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._save_btn.setStyleSheet(f"""
            QToolButton {{
                background: {Colors.SUCCESS}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ background: #7bc97e; }}
        """)
        self._save_btn.clicked.connect(self.save_requested.emit)
        self._save_btn.hide()
        layout.addWidget(self._save_btn)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    # ─── Helpers ───

    def _make_obs_focus_out(self, edit: QTextEdit):
        def handler(event):
            self.observacao_changed.emit(edit.toPlainText())
            QTextEdit.focusOutEvent(edit, event)
        return handler

    def _field_row(self, label: str, widget) -> QWidget:
        row = QWidget()
        lay = QVBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return row

    def _input_style(self) -> str:
        return f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: rgba(255,255,255,0.04); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                padding: 3px 8px; font-size: 10px;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; selection-background-color: {Colors.ACCENT_DIM};
            }}
        """

    def _sep(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    # ─── In-panel color picker (no external QColorDialog — same pattern
    # as terrain's BackgroundSection/color_picker.py) ───────────────────

    def _build_color_picker(self) -> QFrame:
        """HueBar + saturation/value square + R/G/B/A sliders + hex entry,
        all embedded directly in this panel — clicking the color swatch
        toggles this open/closed instead of popping a native OS dialog."""
        widget = QFrame()
        widget.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(16)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        lay.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(90)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        lay.addWidget(self._sv_square)

        self._r_slider = ColorSlider("R", 0, 255, self._color.red())
        self._g_slider = ColorSlider("G", 0, 255, self._color.green())
        self._b_slider = ColorSlider("B", 0, 255, self._color.blue())
        self._a_slider = ColorSlider("A", 0, 255, self._color.alpha())
        for slider in (self._r_slider, self._g_slider, self._b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
        self._a_slider.value_changed.connect(self._on_alpha_slider_changed)
        lay.addWidget(self._r_slider)
        lay.addWidget(self._g_slider)
        lay.addWidget(self._b_slider)
        lay.addWidget(self._a_slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
        self._hex_input = QLineEdit()
        self._hex_input.setFixedHeight(22)
        self._hex_input.setMaxLength(6)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 0 4px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_input, 1)
        lay.addLayout(hex_row)

        h, s, v, _a = self._color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_hex_input()
        return widget

    def _toggle_color_picker(self):
        self._color_picker.setVisible(not self._color_picker.isVisible())
        self.content_changed.emit()

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1], self._hsv[2] = s, v
        self._apply_hsv()

    def _apply_hsv(self):
        h, s, v = self._hsv
        color = QColor.fromHsv(h, round(s * 255 / 100), round(v * 255 / 100))
        color.setAlpha(self._color.alpha())
        self._sync_rgb_sliders(color)
        self._sync_hex_input(color)
        self.set_color(color, emit=True, sync_picker=False)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value(), self._color.alpha())
        h, s, v, _a = color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sync_hex_input(color)
        self.set_color(color, emit=True, sync_picker=False)

    def _on_alpha_slider_changed(self, value: int):
        color = QColor(self._color)
        color.setAlpha(value)
        self.set_color(color, emit=True, sync_picker=False)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) != 6:
            return
        try:
            r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            return
        self.set_color(QColor(r, g, b, self._color.alpha()), emit=True)

    def _sync_rgb_sliders(self, color: QColor):
        for slider, value in ((self._r_slider, color.red()), (self._g_slider, color.green()),
                               (self._b_slider, color.blue())):
            slider.blockSignals(True)
            slider.set_value(value)
            slider.blockSignals(False)

    def _sync_hex_input(self, color: QColor | None = None):
        color = color or self._color
        self._hex_input.blockSignals(True)
        self._hex_input.setText(color.name(QColor.NameFormat.HexRgb).lstrip("#").upper())
        self._hex_input.blockSignals(False)

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(f"""
            QToolButton {{
                background: {self._color.name()}; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px;
            }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)

    # ─── Public API (populate without re-emitting signals) ───

    def set_terrain_options(self, options: list[tuple[str, str]]):
        """Rebuild the "Pintando em" dropdown. `options` is a list of
        (terrain_id, name) for every currently-existing terrain — "Mapa
        Infinito" (id "") is always prepended automatically."""
        self._terrain_combo.blockSignals(True)
        self._terrain_combo.clear()
        self._terrain_combo.addItem("🌍 Mapa Infinito", "")
        for terrain_id, name in options:
            self._terrain_combo.addItem(f"🗺 {name}", terrain_id)
        self._terrain_combo.blockSignals(False)

    def set_terrain_id(self, terrain_id: str):
        """Sync the combo's selection without re-emitting terrain_changed —
        used when the terrain is changed from elsewhere (e.g. the card's
        own dropdown) while this panel is open for the same region."""
        self._terrain_combo.blockSignals(True)
        idx = self._terrain_combo.findData(terrain_id)
        self._terrain_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._terrain_combo.blockSignals(False)

    def load(self, name: str, category_key: str, color: QColor,
             radius: float, softness: float, mode: str, opacity: float,
             stars: int, estilo: str, observacao: str, terrain_id: str = ""):
        # `softness` is accepted (unused) purely to keep both call sites
        # (RegionMediator.on_add_requested/_open_edit) unchanged — the
        # "Suavização" slider itself was removed (see __init__): with the
        # fill now hard-clipped to the traced border (RegionLayer.
        # _bordered_result), it had almost no visible effect left, and
        # nobody could tell what it did.
        self._name_edit.blockSignals(True)
        self._name_edit.setText(name)
        self._name_edit.blockSignals(False)

        self._terrain_combo.blockSignals(True)
        idx = self._terrain_combo.findData(terrain_id)
        self._terrain_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._terrain_combo.blockSignals(False)

        self._type_edit.blockSignals(True)
        self._type_edit.setText(category_key)
        self._type_edit.blockSignals(False)

        self.set_color(color, emit=False)

        self.radius_slider.set_value(radius)
        self.opacity_slider.set_value(opacity * 100)
        self._mode = mode

        self.stars.set_stars(stars, emit=False)

        self._estilo_combo.blockSignals(True)
        i = self._estilo_combo.findText(estilo)
        if i >= 0:
            self._estilo_combo.setCurrentIndex(i)
        self._estilo_combo.blockSignals(False)

        self._obs_edit.blockSignals(True)
        self._obs_edit.setPlainText(observacao)
        self._obs_edit.blockSignals(False)

    def set_color(self, color: QColor, emit: bool = True, sync_picker: bool = True):
        self._color = QColor(color)
        self._refresh_color_btn()
        if sync_picker and hasattr(self, "_hue_bar"):
            # Re-sync every picker sub-widget to the new color — used when
            # the change came from OUTSIDE the picker itself (load(), hex
            # entry). Callers that already updated their own sibling
            # widgets before calling this (hue bar, sv square, rgb/alpha
            # sliders) pass sync_picker=False to avoid redundant, blocked-
            # signal round-trips.
            h, s, v, _a = self._color.getHsv()
            self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
            self._hue_bar.set_hue(self._hsv[0])
            self._sv_square.set_hue(self._hsv[0])
            self._sv_square.set_sv(self._hsv[1], self._hsv[2])
            self._sync_rgb_sliders(self._color)
            self._a_slider.blockSignals(True)
            self._a_slider.set_value(self._color.alpha())
            self._a_slider.blockSignals(False)
            self._sync_hex_input(self._color)
        if emit:
            self.color_changed.emit(self._color)

    def set_name(self, name: str):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(name)
        self._name_edit.blockSignals(False)

    def set_create_mode(self, is_creating: bool):
        """Show "Salvar Região" only while creating a brand-new região —
        editing an existing card auto-persists each field as it changes."""
        self._save_btn.setVisible(is_creating)
        self.content_changed.emit()

    def focus_name(self):
        self._name_edit.setFocus()
        self._name_edit.selectAll()

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
