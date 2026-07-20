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
    QLineEdit, QComboBox, QCheckBox, QTextEdit, QColorDialog, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.region.star_rating import StarRating
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.engines.map.zones import ZONE_TYPES

ESTILOS = ["Nenhum", "Vapor"]


class RegionEditPanel(QFrame):
    """Side panel to create/edit a single região's properties + brush params."""

    PANEL_WIDTH = 300

    name_changed = Signal(str)
    terrain_changed = Signal(str)         # terrain_id ("" = Mapa Infinito)
    category_changed = Signal(str)       # category_key
    color_changed = Signal(QColor)
    visibility_changed = Signal(bool)
    radius_changed = Signal(float)
    softness_changed = Signal(float)
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

        self._type_combo = QComboBox()
        for key, _icon, label, _color in ZONE_TYPES:
            self._type_combo.addItem(label, key)
        self._type_combo.setStyleSheet(self._combo_style())
        self._type_combo.currentIndexChanged.connect(
            lambda i: self.category_changed.emit(self._type_combo.itemData(i))
        )
        info_section.content_layout.addWidget(self._field_row("Tipo", self._type_combo))

        self._color_btn = QToolButton()
        self._color_btn.setFixedHeight(24)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        info_section.content_layout.addWidget(self._field_row("Cor da região", self._color_btn))

        self._visible_check = QCheckBox("Visível")
        self._visible_check.setChecked(True)
        self._visible_check.setStyleSheet(f"""
            QCheckBox {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
            QCheckBox::indicator {{
                width: 30px; height: 16px; border-radius: 8px;
                border: 1px solid {Colors.BORDER}; background: rgba(255,255,255,0.06);
            }}
            QCheckBox::indicator:checked {{ background: {Colors.ACCENT}; border-color: {Colors.ACCENT}; }}
        """)
        self._visible_check.toggled.connect(self.visibility_changed.emit)
        info_section.content_layout.addWidget(self._visible_check)

        layout.addWidget(info_section)
        layout.addWidget(self._sep())

        # ═══ Seção 2 — Ferramentas de Pintura ═══
        tools_section = CollapsibleSection("Ferramentas de Pintura")
        tools_section.content_changed.connect(self.content_changed.emit)

        self.radius_slider = BrushSlider("Raio do pincel", "◯", 5, 500, 50, "m")
        self.radius_slider.value_changed.connect(self.radius_changed.emit)
        tools_section.content_layout.addWidget(self.radius_slider)

        self.softness_slider = BrushSlider("Suavização", "◐", 0, 100, 50, "%")
        self.softness_slider.value_changed.connect(lambda v: self.softness_changed.emit(v / 100.0))
        tools_section.content_layout.addWidget(self.softness_slider)

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

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Cor da região",
                                       QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color, emit=True)

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

    def load(self, name: str, category_key: str, color: QColor, visible: bool,
             radius: float, softness: float, mode: str, opacity: float,
             stars: int, estilo: str, observacao: str, terrain_id: str = ""):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(name)
        self._name_edit.blockSignals(False)

        self._terrain_combo.blockSignals(True)
        idx = self._terrain_combo.findData(terrain_id)
        self._terrain_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._terrain_combo.blockSignals(False)

        idx = self._type_combo.findData(category_key)
        self._type_combo.blockSignals(True)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)

        self.set_color(color, emit=False)

        self._visible_check.blockSignals(True)
        self._visible_check.setChecked(visible)
        self._visible_check.blockSignals(False)

        self.radius_slider.set_value(radius)
        self.softness_slider.set_value(softness * 100)
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

    def set_color(self, color: QColor, emit: bool = True):
        self._color = QColor(color)
        self._refresh_color_btn()
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

    def set_visible_checkbox(self, visible: bool):
        self._visible_check.blockSignals(True)
        self._visible_check.setChecked(visible)
        self._visible_check.blockSignals(False)

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
