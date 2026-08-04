"""NPCEditPanel — right-side detail/edit form for the selected NPC.

Mirrors MobEditPanel's (src/layouts/panels/mobs/mob_edit_panel.py) shell
structure exactly: `load()` populates every field from an npc dict, "Salvar
Alterações" collects them back into a dict and emits `save_requested` —
plain form-submit, no live canvas binding, no implicit autosave. The
"Salvo"/"Não salvo" indicator is driven generically off every input
widget's change signal (see `_wire_dirty_tracking`).

This is the "shell" module for NPCEditPanel — the actual field-building
lives in the 3 section mixins (OverviewSectionMixin, AtributosSectionMixin,
ExtrasSectionMixin, one per collapsible section, all in this same package).
`_CollapsibleSection` and the shared `_INPUT_STYLE`/`_no_wheel`/`_hr` are
reused straight from src.layouts.panels.mobs — this package intentionally
has no edit_widgets.py/edit_helpers.py of its own.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QToolButton, QWidget, QMenu,
    QSizePolicy, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.mobs.edit_helpers import _INPUT_STYLE, _no_wheel, _hr
from src.layouts.panels.mobs.edit_widgets import _CollapsibleSection
from src.layouts.panels.npcs.edit_overview_mixin import OverviewSectionMixin, NPC_TYPE_OPTIONS
from src.layouts.panels.npcs.edit_atributos_mixin import (
    AtributosSectionMixin, INITIAL_STATE_OPTIONS, PLAYER_REACTION_OPTIONS,
)
from src.layouts.panels.npcs.edit_extras_mixin import ExtrasSectionMixin
from src.layouts.panels.npcs.categories import DEFAULT_CATEGORY_ID

logger = logging.getLogger("MAKEMAP")


class NPCEditPanel(OverviewSectionMixin, AtributosSectionMixin, ExtrasSectionMixin, QFrame):
    """Detail / edit form for the selected (or newly created) NPC."""

    PANEL_WIDTH = 480

    save_requested = Signal(dict)
    rename_requested = Signal(str, str)  # npc_id, new_name — only reachable via the ⋮ menu once an npc is saved
    delete_requested = Signal(str)
    asset_add_requested = Signal(str, dict)  # npc_id, {name, asset_type, file_path, file_size, rarity}
    asset_delete_requested = Signal(str, str)  # npc_id, asset_id
    item_open_requested = Signal(str)  # item_id — an Itens Fornecidos tile was clicked (not "✕")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._npc_id = ""
        self._creating = False
        self._loaded_name = ""  # last known-good name — see _finish_rename
        self._loading = True
        self._assets: list[dict] = []  # npc_assets rows — set_assets(), see _refresh_assets_display
        self._items_catalog: list[dict] = []  # set_items_catalog(), see edit_extras_mixin.py
        self._provided_items: list[dict] = []  # {"item_id","rate","qty"} — see _refresh_provided_items_display
        self._provided_items_expanded = False

        self.setStyleSheet("background: transparent; border: none;" + _INPUT_STYLE)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 5, 8, 5)
        self._layout.setSpacing(1)
        self._footer_layout = self._layout

        self._build_ui()
        self._name_edit.editingFinished.connect(self._finish_rename)
        for widget_type in (QComboBox, QSpinBox, QDoubleSpinBox):
            for w in self.findChildren(widget_type):
                _no_wheel(w)
        self._wire_dirty_tracking()
        self._loading = False
        self.set_empty(True)

    # ─── UI construction ───

    def _build_ui(self):
        header = QHBoxLayout()
        header.setSpacing(10)

        badge = QLabel("🧙")
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            font-size: 16px; background: rgba(255,255,255,0.06);
            border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px;
        """)
        header.addWidget(badge)

        self._title_label = QLabel("Nenhum NPC selecionado")
        self._title_label.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: bold; background: transparent; border: none;
        """)
        header.addWidget(self._title_label, 1)

        self._fav_btn = QToolButton()
        self._fav_btn.setText("☆")
        self._fav_btn.setCheckable(True)
        self._fav_btn.setFixedSize(28, 28)
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setToolTip("Favoritar")
        self._fav_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; background: rgba(255,255,255,0.06); font-size: 14px; color: gold; }}
        """)
        self._fav_btn.toggled.connect(lambda c: self._fav_btn.setText("★" if c else "☆"))
        header.addWidget(self._fav_btn)

        menu_btn = QToolButton()
        menu_btn.setText("⋮")
        menu_btn.setFixedSize(28, 28)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setToolTip("Mais opções")
        menu_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; background: rgba(255,255,255,0.06);
                font-size: 14px; font-weight: bold; color: {Colors.TEXT_SECONDARY}; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; width: 0; }}
        """)
        menu = QMenu(menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("✏ Renomear", self._begin_rename)
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self._npc_id))
        menu_btn.setMenu(menu)
        header.addWidget(menu_btn)
        self._layout.addLayout(header)

        status_row = QHBoxLayout()
        status_row.addStretch()
        self._save_status_label = QLabel("Salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        status_row.addWidget(self._save_status_label)
        self._layout.addLayout(status_row)

        # Informações Gerais and Comportamento start expanded (the two most
        # commonly edited); Posição no Mundo and Configurações Adicionais
        # start collapsed — mostly set by the Spawn tool on the canvas, not
        # hand-typed here.
        sections_scroll = QScrollArea()
        sections_scroll.setWidgetResizable(True)
        sections_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sections_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sections_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        sections_container = QWidget()
        sections_lay = QVBoxLayout(sections_container)
        sections_lay.setContentsMargins(0, 0, 0, 0)
        sections_lay.setSpacing(6)
        sections_lay.addWidget(_CollapsibleSection("👁 Informações Gerais", self._build_overview_section(), expanded=True))
        sections_lay.addWidget(_CollapsibleSection("🎭 Comportamento", self._build_atributos_section(), expanded=True))
        sections_lay.addWidget(_CollapsibleSection("📄 Informações Extras", self._build_extra_section(), expanded=False))
        sections_lay.addStretch()
        self._refresh_type_badge()
        sections_scroll.setWidget(sections_container)
        self._layout.addWidget(sections_scroll, 1)
        self._sections_scroll = sections_scroll

        save_btn = QPushButton("Salvar Alterações")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F;
                border: none; border-radius: 6px; padding: 8px; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        save_btn.clicked.connect(lambda: self.save_requested.emit(self.collect_values()))
        footer_sep = _hr()
        self._footer_layout.addWidget(footer_sep)
        self._footer_layout.addSpacing(3)
        self._footer_layout.addWidget(save_btn)

    # ─── Dirty tracking ("Salvo" / "Não salvo") ───

    def _wire_dirty_tracking(self):
        for w in self.findChildren(QLineEdit):
            w.textChanged.connect(self._mark_dirty)
        for w in self.findChildren(QTextEdit):
            w.textChanged.connect(self._mark_dirty)
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(lambda _i: self._mark_dirty())
        for w in self.findChildren(QSpinBox):
            w.valueChanged.connect(lambda _v: self._mark_dirty())
        for w in self.findChildren(QDoubleSpinBox):
            w.valueChanged.connect(lambda _v: self._mark_dirty())
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(lambda _c: self._mark_dirty())
        self._fav_btn.toggled.connect(lambda _c: self._mark_dirty())

    def _mark_dirty(self):
        if self._loading:
            return
        self._save_status_label.setText("Não salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.WARNING}; font-size: 9px; font-weight: bold; background: transparent; border: none;")

    def _mark_saved(self):
        self._save_status_label.setText("Salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")

    # ─── Nome — editable only while creating a brand-new (unsaved) npc; a
    # plain read-only label once saved, changeable only via "✏ Renomear". ───

    _NAME_STYLE_EDITABLE = """
        QLineEdit {{ background: rgba(255,255,255,0.05); border: 1px solid {border};
            border-radius: 6px; padding: 6px 10px; color: {text}; font-size: 13px; font-weight: bold; }}
        QLineEdit:focus {{ border-color: {accent}; }}
    """
    _NAME_STYLE_LABEL = """
        QLineEdit {{ background: transparent; border: none;
            padding: 6px 10px; color: {text}; font-size: 13px; font-weight: bold; }}
    """

    def _set_name_editable(self, editable: bool):
        self._name_edit.setReadOnly(not editable)
        style = self._NAME_STYLE_EDITABLE if editable else self._NAME_STYLE_LABEL
        self._name_edit.setStyleSheet(style.format(
            border=Colors.BORDER_SUBTLE, text=Colors.TEXT_PRIMARY, accent=Colors.ACCENT,
        ))

    def _begin_rename(self):
        if not self._npc_id:
            return
        self._set_name_editable(True)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _finish_rename(self):
        if not self._creating:
            self._set_name_editable(False)
        new_name = self._name_edit.text().strip()
        if self._creating:
            return  # still just editing the draft's initial name, not a rename
        if new_name and new_name != self._loaded_name and self._npc_id:
            self._loaded_name = new_name
            self._title_label.setText(new_name)
            self.rename_requested.emit(self._npc_id, new_name)
            self._mark_saved()
        else:
            self._name_edit.setText(self._loaded_name)

    # ─── Core data plumbing (touches all 3 sections' fields directly) ───

    def set_empty(self, empty: bool):
        """Clears the form to a blank state when there's no npc to show —
        the form itself stays visible either way, just with blank/default
        values."""
        was_loading = self._loading
        self._loading = True
        if empty:
            self._npc_id = ""
            self._creating = False
            self._loaded_name = ""
            self._set_name_editable(False)
            self._title_label.setText("Nenhum NPC selecionado")
            self._id_label.setText("")
            self._mark_saved()
            self._fav_btn.setChecked(False)
            self._image_path = ""
            self._thumb_pixmap = None
            self._refresh_thumb()
            self._name_edit.clear()
            self._title_edit.clear()
            self._npc_type_edit.clear()
            self._category_combo.setCurrentIndex(0)
            self._faction_combo.setCurrentIndex(-1)
            self._faction_combo.setCurrentText("")
            self._status_combo.setCurrentIndex(0)
            self._zone_combo.setCurrentIndex(0)
            self._subcategory_edit.clear()
            self._level_spin.setValue(1)
            self._health_spin.setValue(100)
            self._mana_spin.setValue(50)
            self._desc_edit.clear()
            self._refresh_type_badge()

            self._pos_x_spin.setValue(0.0)
            self._pos_y_spin.setValue(0.0)
            self._pos_z_spin.setValue(0.0)

            self._initial_state_combo.setCurrentIndex(0)
            self._player_reaction_combo.setCurrentIndex(0)
            self._can_be_attacked_check.setChecked(False)
            self._flees_when_attacked_check.setChecked(False)
            self._can_die_check.setChecked(True)
            self._can_respawn_check.setChecked(False)
            self._respawn_time_spin.setValue(0)
            self._spawn_radius_spin.setValue(0)
            self._shadow_pct_spin.setValue(0)

            self._visible_on_map_check.setChecked(True)
            self._shows_on_minimap_check.setChecked(True)
            self._shows_quest_icon_check.setChecked(True)
            self._uses_animations_check.setChecked(True)
            self._notes_edit.clear()
            self._provided_items = []
            self._provided_items_expanded = False
            self._refresh_provided_items_display()
            self._assets = []
            self._refresh_assets_display()
            logger.info("Editor: modo criação/vazio")
        self._loading = was_loading

    def load(self, npc: dict, creating: bool = False):
        self._loading = True
        self._npc_id = npc.get("id", "")
        self._creating = creating
        self.set_empty(False)
        # Same "no category set yet -> the first seeded preset tier" fallback
        # Mobs' own category combo applies (see mob_edit_panel.py) — without
        # it, a brand-new NPC created outside any folder (self._current_dir_id
        # is None, so NPCsPanel._on_new_npc never puts anything in the draft's
        # "category" at all) would stay uncategorized forever instead of
        # landing in "Figurante" like a fresh mob lands in "Normal".
        category_key = npc.get("category") or DEFAULT_CATEGORY_ID
        idx = self._category_combo.findData(category_key)
        self._category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._title_label.setText(npc.get("name") or "Novo NPC")
        self._id_label.setText(
            f'<span style="color:{Colors.TEXT_MUTED};">ID:</span> NPC_{self._npc_id[:6].upper()}'
            if self._npc_id else ""
        )
        self._fav_btn.setChecked(bool(npc.get("favorite", 0)))

        self._loaded_name = npc.get("name", "") or "Novo NPC"
        self._set_name_editable(creating)
        self._name_edit.setText(npc.get("name", ""))
        self._title_edit.setText(npc.get("title", "") or "")
        self._desc_edit.setPlainText(npc.get("description", "") or "")

        self._image_path = npc.get("image_path", "") or ""
        pixmap = QPixmap(self._image_path) if self._image_path else QPixmap()
        self._thumb_pixmap = pixmap if not pixmap.isNull() else None
        self._refresh_thumb()

        self._npc_type_edit.setText(npc.get("npc_type") or "")
        self._refresh_type_badge()

        self._faction_combo.setCurrentText(npc.get("faction", "") or "")
        status = npc.get("status", "ativo") or "ativo"
        self._status_combo.setCurrentIndex(1 if status == "inativo" else 0)

        zone_id = npc.get("zone_id", "") or ""
        idx = self._zone_combo.findData(zone_id)
        self._zone_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._subcategory_edit.setText(npc.get("subcategory", "") or "")

        self._level_spin.setValue(int(npc.get("level", 1) or 1))
        self._health_spin.setValue(int(npc.get("health", 100) or 0))
        self._mana_spin.setValue(int(npc.get("mana", 50) or 0))

        self._pos_x_spin.setValue(float(npc.get("position_x", 0) or 0))
        self._pos_y_spin.setValue(float(npc.get("position_y", 0) or 0))
        self._pos_z_spin.setValue(float(npc.get("position_z", 0) or 0))

        initial_state = npc.get("initial_state") or INITIAL_STATE_OPTIONS[0]
        if self._initial_state_combo.findText(initial_state) >= 0:
            self._initial_state_combo.setCurrentText(initial_state)
        player_reaction = npc.get("player_reaction") or PLAYER_REACTION_OPTIONS[0]
        if self._player_reaction_combo.findText(player_reaction) >= 0:
            self._player_reaction_combo.setCurrentText(player_reaction)
        self._can_be_attacked_check.setChecked(bool(npc.get("can_be_attacked", 0)))
        self._flees_when_attacked_check.setChecked(bool(npc.get("flees_when_attacked", 0)))
        self._can_die_check.setChecked(bool(npc.get("can_die", 1)))
        self._can_respawn_check.setChecked(bool(npc.get("can_respawn", 0)))
        self._respawn_time_spin.setValue(int(npc.get("respawn_time", 0) or 0))
        self._spawn_radius_spin.setValue(float(npc.get("spawn_radius", 0) or 0))
        self._shadow_pct_spin.setValue(float(npc.get("shadow_pct", 0) or 0))

        self._visible_on_map_check.setChecked(bool(npc.get("visible_on_map", 1)))
        self._shows_on_minimap_check.setChecked(bool(npc.get("shows_on_minimap", 1)))
        self._shows_quest_icon_check.setChecked(bool(npc.get("shows_quest_icon", 1)))
        self._uses_animations_check.setChecked(bool(npc.get("uses_animations", 1)))
        self._notes_edit.setPlainText(npc.get("notes", "") or "")

        try:
            self._provided_items = json.loads(npc.get("provides_items_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            self._provided_items = []
        self._provided_items_expanded = False
        self._refresh_provided_items_display()

        self._loading = False
        self._mark_saved()
        logger.info("Editor: npc carregado id=%s nome='%s'", self._npc_id, npc.get("name"))

    def collect_values(self) -> dict:
        return dict(
            id=self._npc_id,
            name=self._name_edit.text().strip() or "Novo NPC",
            title=self._title_edit.text().strip(),
            description=self._desc_edit.toPlainText(),
            category=self._category_combo.currentData() or "",
            npc_type=self._npc_type_edit.text().strip() or NPC_TYPE_OPTIONS[0],
            faction=self._faction_combo.currentText().strip(),
            status="inativo" if self._status_combo.currentIndex() == 1 else "ativo",
            favorite=int(self._fav_btn.isChecked()),
            zone_id=self._zone_combo.currentData() or "",
            subcategory=self._subcategory_edit.text().strip(),
            level=self._level_spin.value(),
            health=self._health_spin.value(),
            mana=self._mana_spin.value(),
            position_x=self._pos_x_spin.value(),
            position_y=self._pos_y_spin.value(),
            position_z=self._pos_z_spin.value(),
            initial_state=self._initial_state_combo.currentText(),
            player_reaction=self._player_reaction_combo.currentText(),
            can_be_attacked=int(self._can_be_attacked_check.isChecked()),
            flees_when_attacked=int(self._flees_when_attacked_check.isChecked()),
            can_die=int(self._can_die_check.isChecked()),
            can_respawn=int(self._can_respawn_check.isChecked()),
            respawn_time=self._respawn_time_spin.value(),
            spawn_radius=self._spawn_radius_spin.value(),
            shadow_pct=self._shadow_pct_spin.value(),
            visible_on_map=int(self._visible_on_map_check.isChecked()),
            shows_on_minimap=int(self._shows_on_minimap_check.isChecked()),
            shows_quest_icon=int(self._shows_quest_icon_check.isChecked()),
            uses_animations=int(self._uses_animations_check.isChecked()),
            notes=self._notes_edit.toPlainText(),
            provides_items_json=json.dumps(self._provided_items),
            image_path=self._image_path,
        )

    def content_height(self) -> int:
        self._layout.parentWidget().adjustSize()
        return self._layout.parentWidget().sizeHint().height() + 16

    def paintEvent(self, event):
        paint_glass_panel(self)
