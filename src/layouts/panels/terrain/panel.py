"""Terrain Settings Panel — Região-style flat CRUD list of terrain cards.

Creation (name/forma/dimensões/imagem/cor da borda) now lives entirely in
TerrainEditPanel, opened via "+ Novo Terreno" — this panel is just the
"Mapa Infinito" toggle plus the resulting card list, mirroring
RegionSettingsPanel.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QWidget, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.terrain.terrain_card import TerrainCard
from src.layouts.panel_manager import paint_glass_panel


class TerrainSettingsPanel(QFrame):
    """Side panel for Terreno CRUD — flat list of cards."""

    PANEL_WIDTH = 300
    DEFAULT_SHAPE = "rectangle"
    DEFAULT_WIDTH = 4096
    DEFAULT_HEIGHT = 4096

    # Signals
    infinite_toggled = Signal(bool)
    infinite_blocked = Signal()  # tentou desmarcar sem terrenos
    close_requested = Signal()
    terrain_add_requested = Signal()
    terrain_added = Signal(str, str)
    terrain_removed = Signal(str)
    terrain_delete_requested = Signal(str)  # pede confirmação antes de excluir
    terrain_selected = Signal(str)
    terrain_renamed = Signal(str, str)
    terrain_edit_requested = Signal(str)   # "Editar" from the "..." menu
    terrain_locate_requested = Signal(str)
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

        self._cards: dict[str, TerrainCard] = {}
        self._selected_id: str = ""
        self._color_idx = 0
        self._edit_open = False  # True while TerrainEditPanel is open (create or edit)

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
        top_layout.addLayout(header)

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
        self._inf_disabled = False
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
        top_layout.addWidget(self._infinite_widget)

        # ─── "+ Novo Terreno" — always visible, prominent ───
        new_btn = QToolButton()
        new_btn.setText("+ Novo Terreno")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setMinimumHeight(36)
        new_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        new_btn.clicked.connect(self.terrain_add_requested.emit)
        self._new_btn = new_btn
        self._refresh_new_btn_state()
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
        self._card_scroll = scroll
        self._card_scroll.setVisible(not self._inf_checked)
        outer.addWidget(scroll, 1)

    def showEvent(self, event):
        super().showEvent(event)
        # _toggle_terrain_panel's very first reposition() runs synchronously
        # right after show(), measuring content_height() before this
        # widget's own layout has actually settled — the resulting geometry
        # is too short, cards get clipped, and it only self-corrects once
        # something ELSE emits content_changed (any card add/edit already
        # wires to a QTimer.singleShot(0, ...) deferred reposition — see
        # TerrainMediator.connect_panel — because by the NEXT event-loop
        # tick Qt has finished laying the widget out for real). Emitting
        # content_changed here piggybacks on that same already-correct
        # deferred path for the first open too, instead of needing its own
        # separate fix.
        self.content_changed.emit()

    def content_height(self) -> int:
        """Natural height for THIS panel's actual content — header +
        infinite toggle + "+ Novo Terreno" button (outside the scroll
        area) plus the card list's own natural height (inside it). Same
        reasoning as RegionSettingsPanel.content_height."""
        self._top_container.adjustSize()
        top_h = self._top_container.sizeHint().height()
        self._list_container.adjustSize()
        list_h = self._list_container.sizeHint().height()
        return top_h + list_h + 16

    def set_new_button_enabled(self, enabled: bool):
        """Called by TerrainMediator: False while the edit sub painel is
        already open (create or edit in progress), same reasoning as
        RegionSettingsPanel.set_new_button_enabled. Combined here with the
        "Mapa Infinito" checkbox (see _refresh_new_btn_state) — a bounded
        terreno makes no sense to create while the map itself is
        unbounded, so that condition alone keeps the button disabled
        regardless of what's passed here."""
        self._edit_open = not enabled
        self._refresh_new_btn_state()

    def _refresh_new_btn_state(self):
        # Habilitado quando: não há edição em andamento E
        # (mapa finito OU não há terrenos ainda — para criar o primeiro).
        can_create = not self._edit_open and (not self._inf_checked or not self._cards)
        self._new_btn.setEnabled(can_create)
        if self._inf_checked and self._cards:
            self._new_btn.setToolTip("Desative o Mapa Infinito para criar um terreno")
        else:
            self._new_btn.setToolTip("")
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
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)

    # ─── Helpers ───

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _update_inf_style(self):
        if self._inf_disabled:
            self._infinite_widget.setCursor(Qt.CursorShape.ForbiddenCursor)
            self._inf_box.setStyleSheet(f"""
                background: rgba(79,195,247,0.25); border: 1px solid rgba(79,195,247,0.3);
                border-radius: 3px; color: rgba(255,255,255,0.4); font-size: 10px; font-weight: bold;
            """)
            self._inf_box.setText("✓")
        elif self._inf_checked:
            self._infinite_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            self._inf_box.setStyleSheet(f"""
                background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
                border-radius: 3px; color: #ffffff; font-size: 10px; font-weight: bold;
            """)
            self._inf_box.setText("✓")
        else:
            self._infinite_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            self._inf_box.setStyleSheet(f"""
                background: transparent; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 3px; color: transparent; font-size: 10px;
            """)
            self._inf_box.setText("")

    def _on_inf_click(self, event):
        if self._inf_disabled:
            return
        # Não permite desmarcar se não há terrenos criados.
        if self._inf_checked and not self._cards:
            self.infinite_blocked.emit()
            return
        self._inf_checked = not self._inf_checked
        self._update_inf_style()
        self._refresh_new_btn_state()
        self._card_scroll.setVisible(not self._inf_checked)
        self.content_changed.emit()
        self.infinite_toggled.emit(self._inf_checked)

    # ─── Card list ───

    def add_terrain_card(self, terrain_id: str, name: str, color: QColor,
                          area_m2: float = 0.0, object_count: int = 0,
                          photo: QPixmap | None = None) -> TerrainCard:
        card = TerrainCard(terrain_id, name, color, area_m2, object_count, photo)
        card.selected.connect(self._on_card_selected)
        card.deleted.connect(self._on_card_deleted)
        card.delete_requested.connect(self.terrain_delete_requested.emit)
        card.renamed.connect(self._on_card_renamed)
        card.locate_requested.connect(self.terrain_locate_requested.emit)
        card.edit_requested.connect(self.terrain_edit_requested.emit)
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._cards[terrain_id] = card
        self.content_changed.emit()
        self._refresh_new_btn_state()  # reavalia se o botão deve ficar habilitado
        self._update_inf_disabled()
        self.terrain_added.emit(terrain_id, name)
        return card

    def get_card(self, terrain_id: str) -> TerrainCard | None:
        return self._cards.get(terrain_id)

    def select_terrain(self, terrain_id: str):
        """Programmatic equivalent of clicking a card — used by
        TerrainMediator to auto-select the very first terreno created, so
        it's immediately ready for the brush without an extra click."""
        if terrain_id in self._cards:
            self._on_card_selected(terrain_id)

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
        self.content_changed.emit()
        self._refresh_new_btn_state()  # reavalia — se ficou sem terrenos, reabilita
        self._update_inf_disabled()
        self.terrain_removed.emit(terrain_id)

    def _update_inf_disabled(self):
        self.set_infinite_disabled(bool(self._cards))

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

    def next_palette_color(self) -> QColor:
        c = self._PALETTE[self._color_idx % len(self._PALETTE)]
        self._color_idx += 1
        return c

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
        self._update_inf_disabled()
        self.content_changed.emit()

    @property
    def selected_terrain_id(self) -> str:
        return self._selected_id

    @property
    def selected_terrain_name(self) -> str:
        card = self._cards.get(self._selected_id)
        return card.name if card else ""

    # ─── Properties ───

    def set_infinite(self, infinite: bool):
        """Ativa/desativa o mapa infinito programaticamente — mesmo efeito
        que o usuário clicar no checkbox, incluindo atualizar o visual e
        emitir infinite_toggled."""
        if self._inf_checked == infinite:
            return
        self._inf_checked = infinite
        self._update_inf_style()
        self._refresh_new_btn_state()
        self._card_scroll.setVisible(not self._inf_checked)
        self.content_changed.emit()
        self.infinite_toggled.emit(self._inf_checked)

    def set_infinite_disabled(self, disabled: bool):
        """Desabilita/habilita o checkbox de Mapa Infinito — desabilitado
        quando há terrenos criados (o usuário não pode voltar para infinito
        manualmente enquanto existirem terrenos)."""
        self._inf_disabled = disabled
        self._update_inf_style()

    @property
    def is_infinite(self) -> bool:
        return self._inf_checked

    def paintEvent(self, event):
        paint_glass_panel(self)
