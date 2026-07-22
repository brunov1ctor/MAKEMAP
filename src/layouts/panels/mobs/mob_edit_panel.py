"""MobEditPanel — right-side detail/edit form for the selected mob.

Unlike RegionEditPanel (which binds live, field-by-field, straight into the
canvas layer as you type), this is a plain form-submit editor: `load()`
populates every field from a mob dict, `Salvar Alterações` (the panel's
only footer action) collects them back into a dict and emits
`save_requested` — there's no live canvas object to keep in sync with as
you type, so there's no implicit autosave either. A
lightweight "Salvo"/"Não salvo" indicator in the header tracks whether any
field has changed since the last load()/save(), driven generically off
every input widget's change signal (see `_wire_dirty_tracking`) rather than
hand-wiring each field.

This is the "shell" module for MobEditPanel — most of the actual field-
building/CRUD logic lives in the 3 section mixins (OverviewSectionMixin,
AtributosSectionMixin, ExtrasSectionMixin, one per collapsible section) and
in edit_widgets.py/edit_helpers.py (standalone widget classes and pure
builder functions). This file keeps only what's genuinely cross-cutting:
signals, __init__, top-level UI assembly, dirty-tracking, and the 3 core
methods (load/set_empty/collect_values) that touch every section's fields
directly.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QPushButton, QToolButton, QWidget, QMenu,
    QSizePolicy, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.mobs.categories import RARITY_DEFS, rarity_label
from src.layouts.panels.mobs.edit_helpers import _INPUT_STYLE, _no_wheel, _hr
from src.layouts.panels.mobs.edit_widgets import _CollapsibleSection
from src.layouts.panels.mobs.edit_overview_mixin import OverviewSectionMixin
from src.layouts.panels.mobs.edit_atributos_mixin import AtributosSectionMixin
from src.layouts.panels.mobs.edit_extras_mixin import ExtrasSectionMixin

logger = logging.getLogger("MAKEMAP")


class MobEditPanel(OverviewSectionMixin, AtributosSectionMixin, ExtrasSectionMixin, QFrame):
    """Detail / edit form for the selected (or newly created) mob."""

    # Bumped from 380 — Visão Geral's "Informações Gerais" card (portrait
    # + 3-column Nível/Tipo/Tier and 2-column Categoria/Subcategoria
    # rows, see OverviewSectionMixin._build_overview_section) needs more
    # room than the old compact stacked-label layout did before content
    # starts clipping.
    PANEL_WIDTH = 520

    save_requested = Signal(dict)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)
    asset_add_requested = Signal(str, dict)  # mob_id, {name, asset_type, file_path, file_size, rarity}
    asset_delete_requested = Signal(str, str)  # mob_id, asset_id

    def __init__(self, parent=None):
        super().__init__(parent)
        # Not setFixedWidth anymore — this panel now lives in the Mobs
        # screen's draggable QSplitter (see MobsPanel._build_ui), so its
        # width is a starting point the user can widen, not a hard lock.
        # minimumWidth stays at PANEL_WIDTH because every field below was
        # hand-tuned to fit exactly that with nothing scrolling (see the
        # QScrollArea note just below) — the splitter itself refuses to
        # drag this panel any narrower than its minimum size.
        self.setMinimumWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._mob_id = ""
        self._creating = False
        self._loading = True
        self._drops: list[dict] = []  # {"item_id","rate","qty"} — see _refresh_drops_display
        self._items_catalog: list[dict] = []  # set_items_catalog() — real Item rows for the drop picker
        self._drops_expanded = False
        self._abilities: list[dict] = []  # {"name","description","rarity"} — see _refresh_abilities_display
        self._ability_editing_index: int | None = None  # None while the inline editor is hidden or adding new
        self._assets: list[dict] = []  # mob_assets rows — set_assets(), see _refresh_assets_display

        self.setStyleSheet("background: transparent; border: none;" + _INPUT_STYLE)

        # self._layout is a single plain QVBoxLayout for the whole panel —
        # the panel widget itself is NOT the inside of a QScrollArea. An
        # outer QScrollArea wrapping this entire widget was tried once
        # (back when content lived in fixed-height tabs) and abandoned:
        # its viewport geometry could get stuck at a stale near-zero size
        # when the window reached its final size via showMaximized()
        # rather than a direct resize, so the tabs silently disappeared on
        # real launch despite rendering fine in an offscreen/synchronous
        # resize test. The 3 collapsible sections below (see
        # _CollapsibleSection) now ride in their own QScrollArea instead —
        # that scroll area is one ordinary child of self._layout, sitting
        # next to the header/footer as a sibling, not standing in for
        # self._layout itself — structurally the same relationship the old
        # per-tab QScrollAreas already had to their fixed-height QTabWidget
        # parent (which never hit the bug), just one level up.
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 5, 8, 5)
        self._layout.setSpacing(1)
        self._footer_layout = self._layout

        self._build_ui()
        # Generic pass over every spin/combo box, same findChildren()
        # sweep style as _wire_dirty_tracking below — catches every field
        # regardless of which section builder constructed it, instead of
        # threading _no_wheel() through each individual widget.
        for widget_type in (QComboBox, QSpinBox, QDoubleSpinBox):
            for w in self.findChildren(widget_type):
                _no_wheel(w)
        self._wire_dirty_tracking()
        self._loading = False
        self.set_empty(True)

    # ─── UI construction ───

    def _build_ui(self):
        # Header — paw badge + a plain (read-only) title mirroring whatever
        # load()/set_empty() puts in it, + favorite + a single "⋮" menu
        # (Duplicar/Excluir merged into one button). The actual EDITABLE
        # Nome field lives inside Visão Geral instead (see
        # OverviewSectionMixin._build_overview_section) — it was here
        # briefly during the last profile-card restyle, but that put the
        # only editable name field outside every collapsible section, i.e.
        # not actually "in" Visão Geral the way the reference implied and
        # the user expected.
        header = QHBoxLayout()
        header.setSpacing(10)

        paw_badge = QLabel("🐾")
        paw_badge.setFixedSize(36, 36)
        paw_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        paw_badge.setStyleSheet(f"""
            font-size: 16px; background: rgba(255,255,255,0.06);
            border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px;
        """)
        header.addWidget(paw_badge)

        self._title_label = QLabel("Nenhum mob selecionado")
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
        menu.addAction("📋 Duplicar", lambda: self.duplicate_requested.emit(self._mob_id))
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self._mob_id))
        menu_btn.setMenu(menu)
        header.addWidget(menu_btn)
        self._layout.addLayout(header)

        # "Salvo"/"Não salvo" indicator — its own slim row (ID moved into
        # Visão Geral alongside it, see above).
        status_row = QHBoxLayout()
        status_row.addStretch()
        self._save_status_label = QLabel("Salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        status_row.addWidget(self._save_status_label)
        self._layout.addLayout(status_row)

        # ─── The 3 collapsible sections — Visão Geral / Atributos /
        # Informações Extras — live in one shared QScrollArea so a
        # designer who expands all 3 at once still sees a scrollbar
        # instead of the footer (Ações rápidas, Cancelar/Salvar) getting
        # pushed off the bottom of the panel. Visão Geral and Atributos
        # start expanded (the two most commonly edited); Informações
        # Extras starts collapsed since it's the least frequently touched
        # and the tallest (5 free-text fields + drops). ───
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
        sections_lay.addWidget(_CollapsibleSection("👁 Visão Geral", self._build_overview_section(), expanded=True))
        sections_lay.addWidget(_CollapsibleSection("📊 Atributos", self._build_atributos_section(), expanded=True))
        sections_lay.addWidget(_CollapsibleSection("📄 Informações Extras", self._build_extra_section(), expanded=False))
        sections_lay.addStretch()
        # The Raridade badge lives in Visão Geral but reads from
        # _rarity_combo, built afterward in Atributos — refresh it now
        # that both exist, instead of at construction time in either
        # section builder (whichever ran first wouldn't have both yet).
        self._refresh_rarity_badge()
        sections_scroll.setWidget(sections_container)
        self._layout.addWidget(sections_scroll, 1)

        # ─── Salvar Alterações — the only footer action now (Ações
        # Rápidas and Cancelar removed); Duplicar/Excluir stay reachable
        # via the header icons instead. ───
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
        self._fav_btn.toggled.connect(lambda _c: self._mark_dirty())

    def _mark_dirty(self):
        if self._loading:
            return
        self._save_status_label.setText("Não salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.WARNING}; font-size: 9px; font-weight: bold; background: transparent; border: none;")

    def _mark_saved(self):
        self._save_status_label.setText("Salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")

    # ─── Core data plumbing (touches all 3 sections' fields directly) ───

    def set_empty(self, empty: bool):
        """Clears the form to a blank state when there's no mob to show —
        the form itself (tabs, fields, actions) stays visible either way,
        just with blank/default values, instead of being hidden behind a
        placeholder message."""
        was_loading = self._loading
        self._loading = True
        if empty:
            self._mob_id = ""
            self._creating = False
            self._title_label.setText("Nenhum mob selecionado")
            self._id_label.setText("")
            self._mark_saved()
            self._fav_btn.setChecked(False)
            self._image_path = ""
            self._thumb_pixmap = None
            self._refresh_thumb()
            self._name_edit.clear()
            self._desc_edit.clear()
            self._category_combo.setCurrentIndex(0)
            self._subcategory_edit.clear()
            self._tier_spin.setValue(1)
            self._level_spin.setValue(1)
            self._tipo_combo.setCurrentIndex(0)
            self._ambiente_edit.clear()
            self._status_combo.setCurrentIndex(0)
            self._rarity_combo.setCurrentIndex(0)
            self._refresh_rarity_badge()
            self._hp_spin.setValue(0)
            self._mana_spin.setValue(0)
            self._damage_spin.setValue(0)
            self._defense_spin.setValue(0)
            self._speed_spin.setValue(0)
            self._precision_spin.setValue(0)
            self._dodge_spin.setValue(0)
            self._resist_fisica_spin.setValue(0)
            self._resist_magica_spin.setValue(0)
            self._element_combo.setCurrentIndex(0)
            self._weight_spin.setValue(0)
            self._xp_spin.setValue(0)
            self._gold_spin.setValue(0)
            self._size_combo.setCurrentIndex(0)
            self._ai_combo.setCurrentIndex(0)
            self._behavior_combo.setCurrentIndex(0)
            self._alignment_combo.setCurrentIndex(0)
            self._crit_spin.setValue(0)
            self._faction_edit.clear()
            for spin in self._resistance_spins.values():
                spin.setValue(0)
            self._zone_combo.setCurrentIndex(0)
            self._respawn_spin.setValue(0)
            self._patrol_spin.setValue(0)
            self._spawn_notes.clear()
            self._animation_notes.clear()
            self._effect_combo.setCurrentIndex(0)
            self._notes_edit.clear()
            self._drops = []
            self._drops_expanded = False
            self._refresh_drops_display()
            self._abilities = []
            self._ability_editing_index = None
            self._ability_editor.setVisible(False)
            self._refresh_abilities_display()
            self._assets = []
            self._refresh_assets_display()
            logger.info("Editor: modo criação/vazio")
        self._loading = was_loading

    def load(self, mob: dict, creating: bool = False):
        self._loading = True
        self._mob_id = mob.get("id", "")
        self._creating = creating
        self.set_empty(False)
        self._title_label.setText(mob.get("name") or "Novo Mob")
        self._id_label.setText(
            f'<span style="color:{Colors.TEXT_MUTED};">ID:</span> MOB_{self._mob_id[:6].upper()}'
            if self._mob_id else ""
        )
        self._fav_btn.setChecked(bool(mob.get("favorite", 0)))

        self._name_edit.setText(mob.get("name", ""))
        self._desc_edit.setPlainText(mob.get("description", ""))

        self._image_path = mob.get("image_path", "") or ""
        pixmap = QPixmap(self._image_path) if self._image_path else QPixmap()
        self._thumb_pixmap = pixmap if not pixmap.isNull() else None
        self._refresh_thumb()

        category_key = mob.get("category", "outros") or "outros"
        # Falling back to index 0 here used to silently reassign the mob
        # to whatever folder happens to sort first (e.g. "outros" is the
        # DB column's default but migration 7 deleted that seeded folder,
        # so index 0 became "Chefes (Boss)") the moment the form was
        # saved — same loose-reference reasoning as mobs.category having
        # no FK (see migration 5's comment): a missing folder shouldn't
        # make the mob unloadable, but it also shouldn't get a DIFFERENT
        # real folder assigned just because this combo couldn't find it.
        # A placeholder entry keeps the mob's actual category value
        # intact instead.
        idx = self._category_combo.findData(category_key)
        if idx < 0:
            self._category_combo.addItem("❔ Sem categoria", category_key)
            idx = self._category_combo.count() - 1
        self._category_combo.setCurrentIndex(idx)
        self._subcategory_edit.setText(mob.get("subcategory", ""))
        self._tier_spin.setValue(int(mob.get("tier", 1) or 1))
        self._level_spin.setValue(int(mob.get("level", 1) or 1))
        tipo = mob.get("tipo", "Inimigo") or "Inimigo"
        if self._tipo_combo.findText(tipo) >= 0:
            self._tipo_combo.setCurrentText(tipo)
        self._ambiente_edit.setText(mob.get("ambiente", ""))
        status = mob.get("status", "ativo") or "ativo"
        self._status_combo.setCurrentIndex(1 if status == "inativo" else 0)
        self._rarity_combo.setCurrentText(rarity_label(mob.get("rarity", "normal")))
        self._refresh_rarity_badge()

        self._hp_spin.setValue(int(mob.get("health", 100) or 0))
        self._mana_spin.setValue(int(mob.get("mana", 50) or 0))
        self._damage_spin.setValue(int(mob.get("damage", 10) or 0))
        self._defense_spin.setValue(int(mob.get("defense", 5) or 0))
        self._speed_spin.setValue(float(mob.get("velocidade", 100) or 0))
        self._precision_spin.setValue(float(mob.get("precisao", 90) or 0))
        self._dodge_spin.setValue(float(mob.get("esquiva", 5) or 0))
        self._resist_fisica_spin.setValue(float(mob.get("resist_fisica", 0) or 0))
        self._resist_magica_spin.setValue(float(mob.get("resist_magica", 0) or 0))

        element = mob.get("element", "") or ""
        if element and self._element_combo.findText(element) < 0:
            self._element_combo.addItem(element)
        self._element_combo.setCurrentText(element)
        self._weight_spin.setValue(float(mob.get("peso", 0) or 0))
        self._xp_spin.setValue(int(mob.get("xp", 0) or 0))
        self._gold_spin.setValue(int(mob.get("ouro", 0) or 0))
        size = mob.get("tamanho", "Médio") or "Médio"
        if self._size_combo.findText(size) >= 0:
            self._size_combo.setCurrentText(size)
        ai = mob.get("ai_type", "Agressivo") or "Agressivo"
        if self._ai_combo.findText(ai) >= 0:
            self._ai_combo.setCurrentText(ai)
        behavior = mob.get("comportamento", "Territorial") or "Territorial"
        if self._behavior_combo.findText(behavior) >= 0:
            self._behavior_combo.setCurrentText(behavior)
        alignment = mob.get("alinhamento", "Neutro") or "Neutro"
        if self._alignment_combo.findText(alignment) >= 0:
            self._alignment_combo.setCurrentText(alignment)

        self._crit_spin.setValue(float(mob.get("critico", 5) or 0))
        self._faction_edit.setText(mob.get("faction", ""))

        try:
            res = json.loads(mob.get("resistances") or "{}")
        except (json.JSONDecodeError, TypeError):
            res = {}
        for key, spin in self._resistance_spins.items():
            spin.setValue(float(res.get(key, 0) or 0))

        zone_id = mob.get("zone_id", "") or ""
        idx = self._zone_combo.findData(zone_id)
        self._zone_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._respawn_spin.setValue(int(mob.get("respawn_time", 60) or 0))
        self._patrol_spin.setValue(float(mob.get("patrol_radius", 10) or 0))
        self._spawn_notes.setPlainText(mob.get("spawn_notes", ""))

        self._animation_notes.setPlainText(mob.get("animation_notes", ""))
        effect = mob.get("effect_notes", "") or ""
        if effect and self._effect_combo.findText(effect) < 0:
            self._effect_combo.addItem(effect)
        self._effect_combo.setCurrentText(effect)

        try:
            self._drops = json.loads(mob.get("drops_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            self._drops = []
        self._drops_expanded = False
        self._refresh_drops_display()

        try:
            self._abilities = json.loads(mob.get("abilities_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            self._abilities = []
        self._ability_editing_index = None
        self._ability_editor.setVisible(False)
        self._refresh_abilities_display()

        self._notes_edit.setPlainText(mob.get("notes", ""))
        self._loading = False
        self._mark_saved()
        logger.info("Editor: mob carregado id=%s nome='%s'", self._mob_id, mob.get("name"))

    def collect_values(self) -> dict:
        category_key = self._category_combo.currentData() or "outros"
        rarity_key = next((k for k, _c, label in RARITY_DEFS if label == self._rarity_combo.currentText()), "normal")
        resistances = {key: spin.value() for key, spin in self._resistance_spins.items()}

        return dict(
            id=self._mob_id,
            name=self._name_edit.text().strip() or "Novo Mob",
            description=self._desc_edit.toPlainText(),
            category=category_key,
            subcategory=self._subcategory_edit.text().strip(),
            tier=self._tier_spin.value(),
            level=self._level_spin.value(),
            tipo=self._tipo_combo.currentText(),
            ambiente=self._ambiente_edit.text().strip(),
            status="inativo" if self._status_combo.currentIndex() == 1 else "ativo",
            rarity=rarity_key,
            favorite=int(self._fav_btn.isChecked()),
            health=self._hp_spin.value(),
            mana=self._mana_spin.value(),
            damage=self._damage_spin.value(),
            defense=self._defense_spin.value(),
            velocidade=self._speed_spin.value(),
            precisao=self._precision_spin.value(),
            esquiva=self._dodge_spin.value(),
            resist_fisica=self._resist_fisica_spin.value(),
            resist_magica=self._resist_magica_spin.value(),
            element=self._element_combo.currentText(),
            peso=self._weight_spin.value(),
            xp=self._xp_spin.value(),
            ouro=self._gold_spin.value(),
            tamanho=self._size_combo.currentText(),
            ai_type=self._ai_combo.currentText(),
            comportamento=self._behavior_combo.currentText(),
            alinhamento=self._alignment_combo.currentText(),
            critico=self._crit_spin.value(),
            faction=self._faction_edit.text().strip(),
            resistances=json.dumps(resistances),
            zone_id=self._zone_combo.currentData() or "",
            respawn_time=self._respawn_spin.value(),
            patrol_radius=self._patrol_spin.value(),
            spawn_notes=self._spawn_notes.toPlainText(),
            abilities_json=json.dumps(self._abilities),
            animation_notes=self._animation_notes.toPlainText(),
            effect_notes=self._effect_combo.currentText(),
            drops_json=json.dumps(self._drops),
            notes=self._notes_edit.toPlainText(),
            image_path=self._image_path,
        )

    def content_height(self) -> int:
        self._layout.parentWidget().adjustSize()
        return self._layout.parentWidget().sizeHint().height() + 16

    def paintEvent(self, event):
        paint_glass_panel(self)
