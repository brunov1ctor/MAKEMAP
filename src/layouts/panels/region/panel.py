"""Region Settings Panel — flat CRUD list of região cards.

Cities-Skylines-style zone tagging, but a flat list (no categories) per
the mock: a single prominent "Nova Região" button on top, then every
painted region as its own card underneath. "Tipo" is just a per-region
field (see ZONE_TYPES / RegionEditPanel's combo), not a grouping.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QWidget, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.region.region_card import RegionCard


class RegionSettingsPanel(QFrame):
    """Side panel for Região (zone) CRUD — flat list of cards."""

    PANEL_WIDTH = 300

    region_add_requested = Signal()         # "Nova Região" clicked
    region_renamed = Signal(str, str)       # region_id, new_name
    region_removed = Signal(str)            # region_id
    region_selected = Signal(str)           # region_id — highlight only, no panel
    region_edit_requested = Signal(str)     # region_id — "Editar" from the "..." menu
    region_locate_requested = Signal(str)   # region_id
    region_visibility_toggled = Signal(str, bool)  # region_id, visible
    region_paint_cleared = Signal(str)      # region_id
    region_terrain_changed = Signal(str, str)  # region_id, terrain_id ("" = Mapa Infinito)
    close_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._cards: dict[str, RegionCard] = {}
        self._selected_id = ""
        self._terrain_options: list[tuple[str, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        top_layout = QVBoxLayout(container)
        top_layout.setContentsMargins(10, 6, 10, 8)
        top_layout.setSpacing(8)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("🏙")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Região")
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
        top_layout.addLayout(header)

        # ─── "Nova Região" — always visible, prominent ───
        new_btn = QToolButton()
        new_btn.setText("+ Nova Região")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setMinimumHeight(36)
        new_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        new_btn.clicked.connect(self.region_add_requested.emit)
        self._new_btn = new_btn
        self._refresh_new_btn_style()
        top_layout.addWidget(new_btn)
        top_layout.addWidget(self._sep())

        self._top_container = container
        outer.addWidget(container)

        # ─── Card list (scrollable) ───
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

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(list_container)
        self._list_layout.setContentsMargins(10, 0, 10, 8)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        self._list_container = list_container
        scroll.setWidget(list_container)
        outer.addWidget(scroll, 1)

    def content_height(self) -> int:
        """Natural height for THIS panel's actual content — header + "Nova
        Região" button (outside the scroll area) plus the card list's own
        natural height (inside it). PanelManager._content_height() alone
        only measures the first QScrollArea it finds, which would ignore
        the header/button entirely — same issue the edit panel had."""
        self._top_container.adjustSize()
        top_h = self._top_container.sizeHint().height()
        self._list_container.adjustSize()
        list_h = self._list_container.sizeHint().height()
        return top_h + list_h + 16

    def set_new_button_enabled(self, enabled: bool):
        """Disabled (dimmed) while the edit sub painel is already open —
        its only job is to open that panel, so leaving it clickable while
        it's already open (creating or editing something) doesn't do
        anything useful."""
        self._new_btn.setEnabled(enabled)
        self._refresh_new_btn_style()

    def _refresh_new_btn_style(self):
        enabled = self._new_btn.isEnabled()
        bg = Colors.SUCCESS if enabled else "rgba(255,255,255,0.06)"
        color = "white" if enabled else Colors.TEXT_MUTED
        hover = "#7bc97e" if enabled else "rgba(255,255,255,0.06)"
        self._new_btn.setStyleSheet(f"""
            QToolButton {{
                background: {bg};
                border: none; border-radius: 6px; padding: 8px;
                color: {color}; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ background: {hover}; }}
        """)

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    # ─── Public API (called by RegionMediator) ───

    def add_region_card(self, region_id: str, name: str, category_label: str, color: QColor,
                         area_m2: float = 0.0, object_count: int = 0, visible: bool = True,
                         thumbnail=None, terrain_label: str = "Mapa Infinito",
                         terrain_id: str = "") -> RegionCard:
        card = RegionCard(region_id, name, color, category_label, area_m2, object_count,
                           visible, thumbnail, terrain_label, terrain_id)
        card.selected.connect(self._on_card_selected)
        card.deleted.connect(self._on_card_deleted)
        card.renamed.connect(self.region_renamed.emit)
        card.locate_requested.connect(self.region_locate_requested.emit)
        card.edit_requested.connect(self.region_edit_requested.emit)
        card.visibility_toggled.connect(self.region_visibility_toggled.emit)
        card.paint_cleared.connect(self.region_paint_cleared.emit)
        card.terrain_changed.connect(self.region_terrain_changed.emit)
        card.set_terrain_options(self._terrain_options)
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._cards[region_id] = card
        self.content_changed.emit()
        return card

    def set_terrain_options(self, options: list[tuple[str, str]]):
        """Feeds every card's "pintando em" dropdown — called whenever
        terrains are added/renamed/removed, same list the edit panel and
        brush panel dropdowns use."""
        self._terrain_options = options
        for card in self._cards.values():
            card.set_terrain_options(options)

    def get_card(self, region_id: str) -> RegionCard | None:
        return self._cards.get(region_id)

    def region_count(self) -> int:
        return len(self._cards)

    # ─── Card signal handlers ───

    def _on_card_selected(self, region_id: str):
        self._selected_id = region_id
        for card in self._cards.values():
            card.set_selected(card.region_id == region_id)
        self.region_selected.emit(region_id)

    def _on_card_deleted(self, region_id: str):
        card = self._cards.pop(region_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_id == region_id:
            self._selected_id = ""
        self.region_removed.emit(region_id)
        self.content_changed.emit()

    def paintEvent(self, event):
        paint_glass_panel(self)
