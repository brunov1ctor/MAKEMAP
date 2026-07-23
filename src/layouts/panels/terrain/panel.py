"""Terrain Settings Panel — orchestrator combining terrain cards, background, and boundary config."""

from __future__ import annotations

import os
import uuid

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QWidget, QButtonGroup, QScrollArea, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors
from src.layouts.panels.stepper import NumberStepper
from src.layouts.panels.terrain.terrain_card import TerrainCard
from src.layouts.panels.terrain.background import BackgroundSection
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panel_manager import paint_glass_panel


class TerrainSettingsPanel(QFrame):
    """Side panel for map terrain/boundary configuration."""

    PANEL_WIDTH = 300
    DEFAULT_SHAPE = "rectangle"
    DEFAULT_WIDTH = 4096
    DEFAULT_HEIGHT = 4096

    # Signals
    dimensions_changed = Signal(int, int)
    shape_changed = Signal(str)
    infinite_toggled = Signal(bool)
    close_requested = Signal()
    terrain_added = Signal(str, str)
    terrain_removed = Signal(str)
    terrain_selected = Signal(str)
    terrain_renamed = Signal(str, str)
    terrain_visibility = Signal(str, bool)
    background_changed = Signal(str, str)
    content_changed = Signal()  # emitted when visible content changes size

    _PALETTE = [
        QColor(34, 139, 34), QColor(210, 180, 100), QColor(30, 100, 180),
        QColor(128, 128, 128), QColor(101, 67, 33), QColor(207, 16, 32),
        QColor(240, 248, 255), QColor(80, 80, 80), QColor(139, 90, 43),
        QColor(26, 166, 154),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

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
                background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._container = container
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("🗺")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Terrain")
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
        layout.addWidget(self._sep())

        # ─── Infinite toggle ───
        self._infinite_widget = QFrame()
        self._infinite_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._infinite_widget.setStyleSheet("background: transparent; border: none;")
        inf_layout = QHBoxLayout(self._infinite_widget)
        inf_layout.setContentsMargins(4, 2, 8, 2)
        inf_layout.setSpacing(6)

        self._inf_box = QLabel("✓")
        self._inf_box.setFixedSize(16, 16)
        self._inf_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inf_checked = True
        self._update_inf_style()
        inf_layout.addWidget(self._inf_box)

        inf_label = QLabel("Mapa Infinito")
        inf_label.setStyleSheet(f"""
            font-size: 11px; color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        inf_layout.addWidget(inf_label)
        inf_layout.addStretch()
        self._infinite_widget.mousePressEvent = self._on_inf_click
        layout.addWidget(self._infinite_widget)

        # ─── Dimensions + Shape section (hidden when infinite) ───
        self._bounds_section = CollapsibleSection("Dimensões e Forma", expanded=True)
        self._bounds_section.content_changed.connect(self.content_changed.emit)
        bounds_layout = self._bounds_section.content_layout

        dims_header = QHBoxLayout()
        dims_header.setSpacing(6)
        dims_label = QLabel("Dimensões")
        dims_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        dims_header.addWidget(dims_label)
        dims_header.addStretch()

        # "Novo" replaces the old lone "+" — terrain creation (name + size +
        # shape) now happens together here instead of split across sections.
        new_btn = QToolButton()
        new_btn.setText("+ Novo")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                font-size: 10px; font-weight: bold; padding: 3px 8px;
                color: {Colors.ACCENT}; background: rgba(79,195,247,0.08);
            }}
            QToolButton:hover {{ background: rgba(79,195,247,0.2); }}
        """)
        new_btn.clicked.connect(self._on_add_terrain)
        dims_header.addWidget(new_btn)
        bounds_layout.addLayout(dims_header)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Nome do terreno...")
        self._name_input.setFixedHeight(26)
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._name_input.returnPressed.connect(self._on_add_terrain)
        bounds_layout.addWidget(self._name_input)

        # Meters, not pixels — 1 scene unit == 1 meter (see scale_bar.py) —
        # and a stepper reads exact values better than dragging a slider
        # across a 512-16384 range.
        self.width_slider = NumberStepper("Largura", "↔", 16, 16384, self.DEFAULT_WIDTH, step=64, decimals=1, suffix="m")
        self.height_slider = NumberStepper("Altura", "↕", 16, 16384, self.DEFAULT_HEIGHT, step=64, decimals=1, suffix="m")
        bounds_layout.addWidget(self.width_slider)
        bounds_layout.addWidget(self.height_slider)
        self.width_slider.value_changed.connect(self._on_dims_changed)
        self.height_slider.value_changed.connect(self._on_dims_changed)

        bounds_layout.addWidget(self._sep())

        shape_label = QLabel("Forma do Limite")
        shape_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        bounds_layout.addWidget(shape_label)

        shape_row1 = QHBoxLayout()
        shape_row1.setSpacing(6)
        shape_row2 = QHBoxLayout()
        shape_row2.setSpacing(6)

        self._shape_group = QButtonGroup(self)
        self._shape_group.setExclusive(True)
        self._shape_buttons: dict[str, QToolButton] = {}

        for icon_text, shape_id, tooltip in [
            ("▭", "rectangle", "Retângulo"), ("□", "square", "Quadrado"),
            ("○", "circle", "Círculo"), ("⬡", "hexagon", "Hexágono"),
        ]:
            btn = self._make_shape_btn(icon_text, shape_id, tooltip)
            shape_row1.addWidget(btn)
        shape_row1.addStretch()

        for icon_text, shape_id, tooltip in [
            ("△", "triangle", "Triângulo"), ("⬬", "ellipse", "Elipse"),
            ("⬠", "pentagon", "Pentágono"), ("✏", "freehand", "Forma Livre"),
        ]:
            btn = self._make_shape_btn(icon_text, shape_id, tooltip)
            shape_row2.addWidget(btn)
        shape_row2.addStretch()

        bounds_layout.addLayout(shape_row1)
        bounds_layout.addLayout(shape_row2)
        self._shape_buttons[self.DEFAULT_SHAPE].setChecked(True)
        self._current_shape = self.DEFAULT_SHAPE

        layout.addWidget(self._bounds_section)
        self._bounds_section.hide()

        # ─── Terrenos (CRUD list) section ───
        self._crud_section = CollapsibleSection("Terrenos", expanded=True)
        self._crud_section.content_changed.connect(self.content_changed.emit)
        crud_layout = self._crud_section.content_layout

        # Creation (name + "Novo") now lives up in Dimensões — this section
        # is just the resulting list.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                width: 4px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.2); border-radius: 2px;
            }}
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_widget)
        crud_layout.addWidget(self._scroll)

        layout.addWidget(self._crud_section)
        self._crud_section.hide()

        # ─── Plano de Fundo section ───
        bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "..", "..", "..", "library", "backgrounds")
        self._bg_section_inner = BackgroundSection(bg_dir)
        self._bg_section_inner.background_changed.connect(self.background_changed.emit)
        self._bg_section_inner.close_requested.connect(self.close_requested.emit)
        self._bg_section_inner.content_changed.connect(self.content_changed.emit)

        self._bg_section = CollapsibleSection("Plano de Fundo")
        self._bg_section.content_changed.connect(self.content_changed.emit)
        self._bg_section.content_layout.addWidget(self._bg_section_inner)
        layout.addWidget(self._bg_section)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # State
        self._cards: dict[str, TerrainCard] = {}
        self._selected_id: str = ""
        self._color_idx = 0

    def content_height(self) -> int:
        """Natural height of the panel's actual content.

        A QScrollArea's own sizeHint() doesn't grow with its scrolled
        content (it reports a nominal size regardless of how many terrain
        cards are inside), so measuring `self._container` alone silently
        ignores the card list growing/shrinking — same reason
        PanelManager's generic _content_height() has to reach into
        `scroll.widget()` instead of the QScrollArea itself. Here, on top
        of that, this panel nests scroll areas two levels deep (whole-panel
        → terrain-card-list), so it needs its own explicit correction: measure
        the list's actual inner widget and swap it in for whatever nominal
        size the scroll area itself contributed.
        """
        self._container.adjustSize()
        height = self._container.sizeHint().height()
        if self._crud_section.isVisible() and self._crud_section._expanded:
            self._list_widget.adjustSize()
            list_h = self._list_widget.sizeHint().height()
            height += max(0, list_h - self._scroll.sizeHint().height())
        return height + 20

    # ─── Helpers ───

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _update_inf_style(self):
        if self._inf_checked:
            self._inf_box.setStyleSheet(f"""
                background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
                border-radius: 3px; color: #ffffff; font-size: 10px; font-weight: bold;
            """)
            self._inf_box.setText("✓")
        else:
            self._inf_box.setStyleSheet(f"""
                background: transparent; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 3px; color: transparent; font-size: 10px;
            """)
            self._inf_box.setText("")

    def _on_inf_click(self, event):
        self._inf_checked = not self._inf_checked
        self._update_inf_style()
        self._on_infinite_toggled(self._inf_checked)

    def _make_shape_btn(self, icon_text: str, shape_id: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon_text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(48, 32)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;
                font-size: 16px; color: {Colors.TEXT_SECONDARY};
                background: rgba(255,255,255,0.04);
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
        """)
        btn.clicked.connect(lambda checked, s=shape_id: self._on_shape_selected(s))
        self._shape_group.addButton(btn)
        self._shape_buttons[shape_id] = btn
        return btn

    # ─── CRUD ───

    def _on_add_terrain(self):
        name = self._name_input.text().strip()
        if not name:
            name = f"Terreno {len(self._cards) + 1}"
        terrain_id = str(uuid.uuid4())
        color = self._PALETTE[self._color_idx % len(self._PALETTE)]
        self._color_idx += 1
        self._add_card(terrain_id, name, color)
        self._name_input.clear()
        # A new terrain must not silently inherit whatever shape/size was
        # last customized for the previously selected terrain — reset
        # before terrain_added fires, since on_added reads these widgets.
        self._reset_to_defaults()
        self.terrain_added.emit(terrain_id, name)
        # The new terrain becomes the live-edit target — otherwise the
        # previously-selected terrain stays selected and subsequent
        # shape/dimension tweaks (meant for the new one) mutate it instead.
        self._on_card_selected(terrain_id)

    def _add_card(self, terrain_id: str, name: str, color: QColor):
        card = TerrainCard(terrain_id, name, color)
        card.selected.connect(self._on_card_selected)
        card.deleted.connect(self._on_card_deleted)
        card.toggled.connect(self._on_card_toggled)
        card.renamed.connect(self._on_card_renamed)
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._cards[terrain_id] = card
        self._update_crud_visibility()
        self.content_changed.emit()

    def _on_card_selected(self, terrain_id: str):
        self._selected_id = terrain_id
        for tid, card in self._cards.items():
            card.set_selected(tid == terrain_id)
        self.terrain_selected.emit(terrain_id)

    def _on_card_deleted(self, terrain_id: str):
        card = self._cards.pop(terrain_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_id == terrain_id:
            self._selected_id = ""
            if self._cards:
                next_id = next(iter(self._cards))
                self._on_card_selected(next_id)
        self._update_crud_visibility()
        self.content_changed.emit()
        self.terrain_removed.emit(terrain_id)

    def _on_card_toggled(self, terrain_id: str, visible: bool):
        self.terrain_visibility.emit(terrain_id, visible)

    def _on_card_renamed(self, terrain_id: str, new_name: str):
        self.terrain_renamed.emit(terrain_id, new_name)

    def _reorder_card(self, source_id: str, target_id: str):
        source_card = self._cards.get(source_id)
        target_card = self._cards.get(target_id)
        if not source_card or not target_card:
            return
        self._list_layout.removeWidget(source_card)
        target_idx = self._list_layout.indexOf(target_card)
        self._list_layout.insertWidget(target_idx, source_card)

    # ─── Public API ───

    def add_terrain(self, terrain_id: str, name: str, color: QColor = None):
        if terrain_id in self._cards:
            return
        c = color or self._PALETTE[self._color_idx % len(self._PALETTE)]
        self._color_idx += 1
        self._add_card(terrain_id, name, c)

    def remove_terrain(self, terrain_id: str):
        self._on_card_deleted(terrain_id)

    def clear_terrains(self):
        """Drops every card without emitting terrain_removed — used when
        reloading a different project's terrains (TerrainMediator._load_from_db),
        where each one is being replaced, not individually deleted."""
        for terrain_id in list(self._cards):
            card = self._cards.pop(terrain_id, None)
            if card:
                self._list_layout.removeWidget(card)
                card.deleteLater()
        self._selected_id = ""
        self._update_crud_visibility()
        self.content_changed.emit()

    @property
    def selected_terrain_id(self) -> str:
        return self._selected_id

    @property
    def selected_terrain_name(self) -> str:
        card = self._cards.get(self._selected_id)
        return card.name if card else ""

    # ─── Signal handlers ───

    def _on_infinite_toggled(self, checked: bool):
        show = not checked
        self._bounds_section.setVisible(show)
        self._update_crud_visibility()
        self.content_changed.emit()
        self.infinite_toggled.emit(checked)

    def _update_crud_visibility(self):
        """"Terrenos" only makes sense when bounded (not infinite) AND at
        least one terrain already exists — an empty list here is just dead
        space, not a useful CRUD section."""
        self._crud_section.setVisible(not self._inf_checked and bool(self._cards))

    def _on_dims_changed(self, _value):
        w = int(self.width_slider.value)
        h = int(self.height_slider.value)
        if self._current_shape in ("square", "circle"):
            sender = self.sender()
            if sender is self.width_slider:
                self.height_slider.set_value(w, emit=False)
                h = w
            else:
                self.width_slider.set_value(h, emit=False)
                w = h
        self.dimensions_changed.emit(w, h)

    def _reset_to_defaults(self):
        """Restores shape/dimension controls to defaults for a newly
        created terrain, so it doesn't silently inherit whatever the
        previously selected/edited terrain left in these widgets."""
        self._current_shape = self.DEFAULT_SHAPE
        btn = self._shape_buttons.get(self.DEFAULT_SHAPE)
        if btn:
            btn.setChecked(True)
        self.width_slider.set_value(self.DEFAULT_WIDTH, emit=False)
        self.height_slider.set_value(self.DEFAULT_HEIGHT, emit=False)

    def sync_from_boundary(self, shape: str, width: int, height: int):
        """Reflects an existing terrain's stored shape/dimensions in the
        controls when it's (re)selected, without emitting shape_changed /
        dimensions_changed — those would re-apply the (unchanged) values to
        the boundary we just read them from."""
        self._current_shape = shape
        btn = self._shape_buttons.get(shape)
        if btn:
            btn.setChecked(True)
        self.width_slider.set_value(width, emit=False)
        self.height_slider.set_value(height, emit=False)

    def _on_shape_selected(self, shape: str):
        self._current_shape = shape
        if shape in ("square", "circle"):
            val = int(self.width_slider.value)
            self.height_slider.set_value(val, emit=False)
        self.shape_changed.emit(shape)

    # ─── Properties ───

    @property
    def is_infinite(self) -> bool:
        return self._inf_checked

    @property
    def map_width(self) -> int:
        return int(self.width_slider.value)

    @property
    def map_height(self) -> int:
        return int(self.height_slider.value)

    @property
    def map_shape(self) -> str:
        return self._current_shape

    def paintEvent(self, event):
        paint_glass_panel(self)
