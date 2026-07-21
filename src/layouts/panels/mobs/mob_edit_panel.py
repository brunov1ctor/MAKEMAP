"""MobEditPanel — right-side detail/edit form for the selected mob.

Unlike RegionEditPanel (which binds live, field-by-field, straight into the
canvas layer as you type), this is a plain form-submit editor: `load()`
populates every field from a mob dict, `Salvar Alterações` collects them
back into a dict and emits `save_requested`. That matches the mock's
explicit Cancelar/Salvar pair at the bottom instead of implicit autosave —
there's no live canvas object to keep in sync with as you type. A
lightweight "Salvo"/"Não salvo" indicator in the header tracks whether any
field has changed since the last load()/save(), driven generically off
every input widget's change signal (see `_wire_dirty_tracking`) rather than
hand-wiring each field.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QPushButton, QToolButton, QTabWidget, QWidget,
    QSizePolicy, QGridLayout, QScrollArea, QAbstractSpinBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QIcon

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.mobs.categories import (
    CATEGORY_DEFS, RARITY_DEFS, ELEMENT_OPTIONS, AI_TYPE_OPTIONS,
    BEHAVIOR_OPTIONS, ALIGNMENT_OPTIONS, RESISTANCE_KEYS, STATUS_OPTIONS, SIZE_OPTIONS,
)

_INPUT_STYLE = f"""
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
        border-radius: 5px; padding: 1px 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {Colors.ACCENT};
    }}
    QComboBox QAbstractItemView {{
        background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
        selection-background-color: {Colors.ACCENT_DIM}; border: 1px solid {Colors.BORDER};
    }}
    QComboBox::drop-down {{ width: 12px; border: none; }}
    QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
"""


def _combo(options: list[str], current: str = "") -> QComboBox:
    c = QComboBox()
    c.addItems(options)
    if current and current in options:
        c.setCurrentText(current)
    return c


def _spin(minimum=0, maximum=999999, value=0) -> QSpinBox:
    s = QSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    # Up/down buttons dropped entirely (not just hidden via QSS — a
    # stylesheet width:0 on the button still leaves the arrow glyph
    # painted, overlapping the value text) so the full number is legible
    # in the narrow columns this panel now uses.
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return s


def _dspin(minimum=0.0, maximum=100.0, value=0.0, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    if suffix:
        s.setSuffix(suffix)
    return s


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
    return lbl


def _hr() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line


class MobEditPanel(QFrame):
    """Detail / edit form for the selected (or newly created) mob."""

    PANEL_WIDTH = 380
    _TABS_HEIGHT = 314

    save_requested = Signal(dict)
    cancel_requested = Signal()
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)
    test_requested = Signal(str)
    generate_loot_requested = Signal(str)
    locate_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._mob_id = ""
        self._creating = False
        self._loading = True

        self.setStyleSheet("background: transparent; border: none;" + _INPUT_STYLE)

        # A single plain QVBoxLayout for the whole panel (no outer
        # QScrollArea): every field is sized to fit the panel's natural
        # height (see _TABS_HEIGHT and the compact thumb/description
        # sizing below) so nothing needs to scroll. An outer QScrollArea
        # was tried here as a safety net, but QScrollArea's viewport
        # geometry can get stuck at a stale (near-zero) size when the
        # window reaches its final size via showMaximized() rather than
        # a direct resize — it never re-settles, so the tabs silently
        # disappear on real launch even though everything renders fine
        # in an offscreen/synchronous resize test. Each individual tab's
        # own QScrollArea (see _add_tab) doesn't hit this, since those
        # scroll areas are created and sized only once their fixed-height
        # parent (_tabs) is already at its final size.
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 5, 8, 5)
        self._layout.setSpacing(1)
        self._footer_layout = self._layout

        self._build_ui()
        self._wire_dirty_tracking()
        self._loading = False
        self.set_empty(True)

    # ─── UI construction ───

    def _build_ui(self):
        # Header row 1 — small clickable avatar (doubles as the image
        # picker, replacing what used to be a separate full-width image
        # row — a whole row's height saved) + name, favorite star + rarity
        # badge, then duplicate/delete icons.
        header = QHBoxLayout()
        self._thumb = QToolButton()
        self._thumb.setFixedSize(28, 28)
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.setToolTip("Alterar imagem")
        self._thumb.setIconSize(self._thumb.size())
        self._thumb_pixmap = None
        self._image_path = ""
        self._thumb.clicked.connect(self._on_pick_image)
        header.addWidget(self._thumb)
        title = QLabel("Mob Selecionado")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        self._title_label = title
        header.addWidget(title, 1)

        self._fav_btn = QToolButton()
        self._fav_btn.setText("☆")
        self._fav_btn.setCheckable(True)
        self._fav_btn.setFixedSize(20, 20)
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setToolTip("Favoritar")
        self._fav_btn.setStyleSheet("QToolButton { border: none; background: transparent; font-size: 14px; color: gold; }")
        self._fav_btn.toggled.connect(lambda c: self._fav_btn.setText("★" if c else "☆"))
        header.addWidget(self._fav_btn)

        self._rarity_badge = QLabel("")
        self._rarity_badge.setStyleSheet("font-size: 9px; font-weight: bold; border-radius: 8px; padding: 2px 8px;")
        header.addWidget(self._rarity_badge)

        header.addWidget(self._icon_button("📋", "Duplicar mob", lambda: self.duplicate_requested.emit(self._mob_id)))
        header.addWidget(self._icon_button("🗑", "Excluir mob", lambda: self.delete_requested.emit(self._mob_id)))
        self._layout.addLayout(header)

        # Header row 2 — ID, then a "Salvo"/"Não salvo" indicator — folded
        # into a single slim row (rather than its own section) to save a
        # full row's worth of height in a panel that's already tight on
        # vertical space.
        id_row = QHBoxLayout()
        self._id_label = QLabel("")
        self._id_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        id_row.addWidget(self._id_label)
        id_row.addStretch()
        self._save_status_label = QLabel("Salvo")
        self._save_status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        id_row.addWidget(self._save_status_label)
        self._layout.addLayout(id_row)
        self._refresh_thumb()

        # ─── Nome — placeholder text stands in for a separate "Nome"
        # label, saving a whole row's height. ───
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome do mob")
        self._layout.addWidget(self._name_edit)

        # ─── Categoria | Subcategoria — plain QHBoxLayout, same pattern as
        # the Tier/Nível and Status/Raridade rows below (QFormLayout nested
        # directly in a QVBoxLayout rendered its field column collapsed and
        # shoved to the right instead of a proper full-width combo/edit). ───
        cat_row = QHBoxLayout()
        cat_row.setSpacing(6)
        self._category_combo = QComboBox()
        for key, _icon, label in CATEGORY_DEFS:
            self._category_combo.addItem(label, key)
        self._subcategory_edit = QLineEdit()
        self._subcategory_edit.setPlaceholderText("Opcional")
        cat_row.addWidget(QLabel("Categoria"))
        cat_row.addWidget(self._category_combo, 1)
        cat_row.addWidget(QLabel("Subcategoria"))
        cat_row.addWidget(self._subcategory_edit, 1)
        self._layout.addLayout(cat_row)

        # ─── Tier | Nível | Status | Raridade — one dense row instead of
        # two, since none of these labels or values need much width. ───
        stats_row = QHBoxLayout()
        stats_row.setSpacing(4)
        self._tier_spin = _spin(1, 10, 1)
        self._level_spin = _spin(1, 999, 1)
        self._status_combo = _combo(STATUS_OPTIONS)
        self._rarity_combo = _combo([label for _k, _c, label in RARITY_DEFS])
        self._rarity_combo.currentIndexChanged.connect(self._refresh_rarity_badge)
        for w in (self._tier_spin, self._level_spin):
            w.setMaximumWidth(44)
        for label, widget in (("Tier", self._tier_spin), ("Nível", self._level_spin),
                               ("Status", self._status_combo), ("Raridade", self._rarity_combo)):
            stats_row.addWidget(QLabel(label))
            stats_row.addWidget(widget)
        self._layout.addLayout(stats_row)
        self._refresh_rarity_badge()

        # ─── Descrição — placeholder text stands in for a separate label
        # here too, same reasoning as Nome above. ───
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição...")
        self._desc_edit.setFixedHeight(20)
        self._layout.addWidget(self._desc_edit)

        # ─── Tabs — each page rides in its own QScrollArea and the
        # QTabWidget itself is height-capped, so a content-heavy page (like
        # Atributos, with its general-stats + resistências + drops
        # sections) scrolls internally instead of forcing the whole panel
        # to grow past the window and push the footer off-screen. ───
        self._tabs = QTabWidget()
        self._tabs.setFixedHeight(self._TABS_HEIGHT)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; top: -1px; }}
            QTabBar::tab {{
                background: transparent; color: {Colors.TEXT_MUTED}; padding: 5px 8px; font-size: 9px;
            }}
            QTabBar::tab:selected {{ color: {Colors.ACCENT}; border-bottom: 2px solid {Colors.ACCENT}; }}
        """)
        self._add_tab(self._build_atributos_tab(), "Atributos")
        self._add_tab(self._build_combate_tab(), "Combate")
        self._add_tab(self._build_text_tab("abilities"), "Habilidades")
        self._add_tab(self._build_spawn_tab(), "Spawn")
        self._add_tab(self._build_text_tab("animation"), "Animações")
        self._add_tab(self._build_text_tab("effect"), "Efeitos")
        self._add_tab(self._build_notas_tab(), "Notas")
        self._layout.addWidget(self._tabs)

        # ─── Ações rápidas ───
        self._layout.addWidget(_section_label("AÇÕES RÁPIDAS"))
        actions_grid = QGridLayout()
        actions_grid.setSpacing(6)
        btn_dup = self._action_button("⧉ Duplicar", lambda: self.duplicate_requested.emit(self._mob_id))
        btn_loot = self._action_button("🎁 Gerar Loot", lambda: self.generate_loot_requested.emit(self._mob_id))
        btn_test = self._action_button("▶ Testar no Jogo", lambda: self.test_requested.emit(self._mob_id))
        btn_map = self._action_button("📍 Ver no Mapa", lambda: self.locate_requested.emit(self._mob_id))
        actions_grid.addWidget(btn_dup, 0, 0)
        actions_grid.addWidget(btn_loot, 0, 1)
        actions_grid.addWidget(btn_test, 1, 0)
        actions_grid.addWidget(btn_map, 1, 1)
        self._layout.addLayout(actions_grid)
        self._action_buttons = [btn_dup, btn_loot, btn_test, btn_map]

        # ─── Cancelar / Salvar Alterações ───
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY};
                border: none; border-radius: 6px; padding: 8px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        cancel_btn.clicked.connect(self.cancel_requested.emit)
        save_btn = QPushButton("Salvar Alterações")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F;
                border: none; border-radius: 6px; padding: 8px; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        save_btn.clicked.connect(lambda: self.save_requested.emit(self.collect_values()))
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        footer_sep = _hr()
        self._footer_layout.addWidget(footer_sep)
        self._footer_layout.addSpacing(3)
        self._footer_layout.addLayout(btn_row)

    def _add_tab(self, widget: QWidget, label: str):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        scroll.setWidget(widget)
        self._tabs.addTab(scroll, label)

    def _action_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 6px; font-size: 9px; text-align: left; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); color: {Colors.TEXT_PRIMARY}; }}
        """)
        btn.clicked.connect(slot)
        return btn

    def _icon_button(self, text: str, tooltip: str, slot) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 12px; color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.05); }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); color: {Colors.TEXT_PRIMARY}; }}
        """)
        btn.clicked.connect(slot)
        return btn

    def _refresh_rarity_badge(self):
        key = next((k for k, _c, label in RARITY_DEFS if label == self._rarity_combo.currentText()), "normal")
        color = next((c for k, c, _l in RARITY_DEFS if k == key), "#9AA5B1")
        self._rarity_badge.setText(f"⭐ {self._rarity_combo.currentText()}")
        self._rarity_badge.setStyleSheet(
            f"font-size: 9px; font-weight: bold; border-radius: 8px; padding: 2px 8px; "
            f"background: {color}33; color: {color};"
        )

    def _refresh_thumb(self):
        if self._thumb_pixmap is not None:
            self._thumb.setIcon(QIcon(self._thumb_pixmap))
            self._thumb.setText("")
            self._thumb.setStyleSheet("""
                QToolButton { border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); }
            """)
        else:
            self._thumb.setIcon(QIcon())
            self._thumb.setText("👹")
            self._thumb.setStyleSheet(f"""
                QToolButton {{ border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);
                background: rgba(255,255,255,0.05); font-size: 13px; color: {Colors.TEXT_MUTED}; }}
            """)

    def _on_pick_image(self):
        from PySide6.QtWidgets import QFileDialog
        path, _filter = QFileDialog.getOpenFileName(self, "Selecionar Imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._image_path = path
        self._thumb_pixmap = pixmap
        self._refresh_thumb()
        self._mark_dirty()

    def add_custom_category(self, key: str, label: str):
        """Feeds a user-created category (sidebar "+ Nova categoria") into
        the Categoria dropdown so mobs can actually be assigned to it."""
        if self._category_combo.findData(key) < 0:
            self._category_combo.addItem(label, key)

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

    # ─── Tabs ───

    def _build_atributos_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(2)

        outer.addWidget(_section_label("ATRIBUTOS GERAIS"))
        outer.addWidget(_hr())

        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setVerticalSpacing(2)
        self._hp_spin = _spin(1, 9_999_999, 100)
        self._mana_spin = _spin(0, 999999, 50)
        self._damage_spin = _spin(0, 999999, 10)
        self._defense_spin = _spin(0, 999999, 5)
        self._speed_spin = _dspin(0, 2000, 100, " u/s")
        self._precision_spin = _dspin(0, 100, 90, " %")
        self._dodge_spin = _dspin(0, 100, 5, " %")
        self._resist_fisica_spin = _dspin(-100, 100, 0, " %")
        self._resist_magica_spin = _dspin(-100, 100, 0, " %")
        self._element_combo = _combo(ELEMENT_OPTIONS)
        self._weight_spin = _dspin(0, 99999, 0, " kg")
        self._xp_spin = _spin(0, 9_999_999, 0)
        self._gold_spin = _spin(0, 9_999_999, 0)
        self._size_combo = _combo(SIZE_OPTIONS)
        self._ai_combo = _combo(AI_TYPE_OPTIONS)
        self._behavior_combo = _combo(BEHAVIOR_OPTIONS)
        self._alignment_combo = _combo(ALIGNMENT_OPTIONS)

        # All 17 general fields packed 3 label+field pairs per row (6
        # grid columns) instead of 2 — the panel is only 380px wide, so
        # fitting everything without a scrollbar means trading row count
        # for column count wherever the labels are short enough to allow it.
        all_fields = [
            ("HP Máx.", self._hp_spin), ("Mana Máx.", self._mana_spin),
            ("Ataque", self._damage_spin), ("Defesa", self._defense_spin),
            ("Velocidade", self._speed_spin), ("Precisão", self._precision_spin),
            ("Esquiva", self._dodge_spin), ("R. Física", self._resist_fisica_spin),
            ("R. Mágica", self._resist_magica_spin), ("Elemento", self._element_combo),
            ("Peso", self._weight_spin), ("XP", self._xp_spin),
            ("Ouro", self._gold_spin), ("Tamanho", self._size_combo),
            ("Tipo IA", self._ai_combo), ("Comport.", self._behavior_combo),
            ("Alinhamento", self._alignment_combo),
        ]
        for _label, widget in all_fields:
            widget.setMaximumWidth(48 if isinstance(widget, (QSpinBox, QDoubleSpinBox)) else 66)
            if isinstance(widget, QDoubleSpinBox):
                widget.setDecimals(1)

        for i, (label, widget) in enumerate(all_fields):
            row, col = i // 3, (i % 3) * 2
            lbl = QLabel(label)
            lbl.setToolTip(label)
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row, col + 1)
        for col in (1, 3, 5):
            grid.setColumnStretch(col, 0)
        outer.addLayout(grid)

        outer.addWidget(_section_label("RESISTÊNCIAS"))
        outer.addWidget(_hr())
        res_grid = QGridLayout()
        res_grid.setHorizontalSpacing(2)
        res_grid.setVerticalSpacing(2)
        self._resistance_spins: dict[str, QDoubleSpinBox] = {}
        for i, (key, label) in enumerate(RESISTANCE_KEYS):
            spin = _dspin(-100, 100, 0, " %")
            spin.setDecimals(0)
            spin.setMaximumWidth(44)
            self._resistance_spins[key] = spin
            res_grid.addWidget(QLabel(label), i // 4, (i % 4) * 2)
            res_grid.addWidget(spin, i // 4, (i % 4) * 2 + 1)
        outer.addLayout(res_grid)

        outer.addWidget(_section_label("DROPS PRINCIPAIS"))
        outer.addWidget(_hr())
        self._drops_edit = QTextEdit()
        self._drops_edit.setPlaceholderText("Um item por linha: Nome do item, taxa %, qtd")
        self._drops_edit.setFixedHeight(26)
        outer.addWidget(self._drops_edit)
        outer.addStretch()
        return w

    def _build_combate_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(6)
        self._crit_spin = _dspin(0, 100, 5, " %")
        self._faction_edit = QLineEdit()
        self._faction_edit.setPlaceholderText("Ex: Bandidos, Guarda Real...")
        for label, widget in (("Crítico", self._crit_spin), ("Facção", self._faction_edit)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
            outer.addLayout(row)
        outer.addStretch()
        return w

    def _build_spawn_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(6)
        self._zone_combo = QComboBox()
        self._zone_combo.addItem("Sem região", "")
        self._respawn_spin = _spin(0, 999999, 60)
        self._patrol_spin = _dspin(0, 99999, 10, " m")
        for label, widget in (("Região", self._zone_combo), ("Tempo de Respawn", self._respawn_spin),
                              ("Raio de Patrulha", self._patrol_spin)):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
            outer.addLayout(row)
        self._spawn_notes = QTextEdit()
        self._spawn_notes.setPlaceholderText("Condições de spawn, pontos de invocação, frequência...")
        outer.addWidget(self._spawn_notes, 1)
        return w

    def _build_notas_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(6)
        outer.addWidget(_section_label("NOTAS DO DESIGNER"))
        self._notes_edit = QTextEdit()
        outer.addWidget(self._notes_edit, 1)
        return w

    def _build_text_tab(self, key: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        edit = QTextEdit()
        placeholders = {
            "abilities": "Uma habilidade por linha: Nome — descrição (cooldown)",
            "animation": "Animações: idle, ataque, morte, referências de sprite/arquivo...",
            "effect": "Efeitos visuais/sonoros: auras, partículas, sons de ataque...",
        }
        edit.setPlaceholderText(placeholders.get(key, ""))
        lay.addWidget(edit)
        setattr(self, f"_{key}_notes", edit)
        return w

    # ─── Data plumbing ───

    def set_zone_options(self, options: list[tuple[str, str]]):
        current = self._zone_combo.currentData()
        self._zone_combo.blockSignals(True)
        self._zone_combo.clear()
        self._zone_combo.addItem("Sem região", "")
        idx = 0
        for i, (zid, name) in enumerate(options, start=1):
            self._zone_combo.addItem(name, zid)
            if zid == current:
                idx = i
        self._zone_combo.setCurrentIndex(idx)
        self._zone_combo.blockSignals(False)

    def set_empty(self, empty: bool):
        """Clears the form to a blank state when there's no mob to show —
        the form itself (tabs, fields, actions) stays visible either way,
        just with blank/default values, instead of being hidden behind a
        placeholder message."""
        was_loading = self._loading
        self._loading = True
        for btn in getattr(self, "_action_buttons", []):
            btn.setEnabled(not empty)
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
            self._abilities_notes.clear()
            self._animation_notes.clear()
            self._effect_notes.clear()
            self._drops_edit.clear()
            self._notes_edit.clear()
        self._loading = was_loading

    def load(self, mob: dict, creating: bool = False):
        self._loading = True
        self._mob_id = mob.get("id", "")
        self._creating = creating
        self.set_empty(False)
        self._title_label.setText(mob.get("name") or "Novo Mob")
        self._id_label.setText(f"MOB_{self._mob_id[:6].upper()}" if self._mob_id else "")
        self._fav_btn.setChecked(bool(mob.get("favorite", 0)))

        self._name_edit.setText(mob.get("name", ""))
        self._desc_edit.setPlainText(mob.get("description", ""))

        self._image_path = mob.get("image_path", "") or ""
        pixmap = QPixmap(self._image_path) if self._image_path else QPixmap()
        self._thumb_pixmap = pixmap if not pixmap.isNull() else None
        self._refresh_thumb()

        from src.layouts.panels.mobs.categories import category_label, rarity_label
        category_key = mob.get("category", "outros") or "outros"
        idx = self._category_combo.findData(category_key)
        if idx < 0:
            self.add_custom_category(category_key, category_label(category_key))
            idx = self._category_combo.findData(category_key)
        self._category_combo.setCurrentIndex(max(idx, 0))
        self._subcategory_edit.setText(mob.get("subcategory", ""))
        self._tier_spin.setValue(int(mob.get("tier", 1) or 1))
        self._level_spin.setValue(int(mob.get("level", 1) or 1))
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

        self._abilities_notes.setPlainText(mob.get("abilities_notes", ""))
        self._animation_notes.setPlainText(mob.get("animation_notes", ""))
        self._effect_notes.setPlainText(mob.get("effect_notes", ""))

        try:
            drops = json.loads(mob.get("drops_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            drops = []
        self._drops_edit.setPlainText("\n".join(
            f"{d.get('name', '')}, {d.get('rate', 0)}%, {d.get('qty', 1)}" for d in drops
        ))
        self._notes_edit.setPlainText(mob.get("notes", ""))
        self._loading = False
        self._mark_saved()

    def collect_values(self) -> dict:
        category_key = self._category_combo.currentData() or "outros"
        rarity_key = next((k for k, _c, label in RARITY_DEFS if label == self._rarity_combo.currentText()), "normal")
        resistances = {key: spin.value() for key, spin in self._resistance_spins.items()}

        drops = []
        for line in self._drops_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            name = parts[0] if parts else ""
            rate = 0.0
            qty = 1
            if len(parts) > 1:
                try:
                    rate = float(parts[1].replace("%", "").strip())
                except ValueError:
                    rate = 0.0
            if len(parts) > 2:
                try:
                    qty = int(parts[2])
                except ValueError:
                    qty = 1
            if name:
                drops.append({"name": name, "rate": rate, "qty": qty})

        return dict(
            id=self._mob_id,
            name=self._name_edit.text().strip() or "Novo Mob",
            description=self._desc_edit.toPlainText(),
            category=category_key,
            subcategory=self._subcategory_edit.text().strip(),
            tier=self._tier_spin.value(),
            level=self._level_spin.value(),
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
            abilities_notes=self._abilities_notes.toPlainText(),
            animation_notes=self._animation_notes.toPlainText(),
            effect_notes=self._effect_notes.toPlainText(),
            drops_json=json.dumps(drops),
            notes=self._notes_edit.toPlainText(),
            image_path=self._image_path,
        )

    def content_height(self) -> int:
        self._layout.parentWidget().adjustSize()
        return self._layout.parentWidget().sizeHint().height() + 16

    def paintEvent(self, event):
        paint_glass_panel(self)
