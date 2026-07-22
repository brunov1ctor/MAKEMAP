"""GridFilterMixin — the center card grid/list, its filter row, and card
selection. Mixed into MobsPanel (see panel.py) — operates on self.*
attributes MobsPanel owns; not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QToolButton, QScrollArea, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.mobs.categories import ELEMENT_OPTIONS
from src.layouts.panels.mobs.mob_card import MobCard
from src.layouts.panels.mobs.panel_helpers import _LEVEL_BANDS, _SORT_OPTIONS

logger = logging.getLogger("MAKEMAP")


class GridFilterMixin:
    """Search + Tier/Região/Elemento/Tipo/Nível filters, Ordenar por +
    Grade/Lista toggle, and the resulting card grid/list."""

    def _labeled_combo(self, icon: str, caption: str) -> QComboBox:
        """A small "ICON CAPTION" label stacked above a combo box — matches
        the Tier/Região/Elemento/Tipo/Nível filter columns in the mock."""
        combo = QComboBox()
        combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; min-width: 84px; }}
            QComboBox QAbstractItemView {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_DIM}; }}
        """)
        combo.currentIndexChanged.connect(lambda _i: self._apply_filters())
        combo._caption_widget = QLabel(f"{icon} {caption}")
        combo._caption_widget.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        return combo

    def _build_center(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        # ── Row 1: search + Tier/Região/Elemento/Tipo/Nível ──
        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Pesquisar mobs...")
        self._search_edit.textChanged.connect(self._apply_filters)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 6px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 11px; }}
        """)
        filters.addWidget(self._search_edit, 1)

        self._tier_combo = self._labeled_combo("🛡", "Tier")
        self._tier_combo.addItem("Todos", "")
        for t in range(1, 11):
            self._tier_combo.addItem(str(t), t)

        self._region_combo = self._labeled_combo("🗺", "Região")
        self._region_combo.addItem("Todas", "")

        self._element_combo = self._labeled_combo("🌪", "Elemento")
        self._element_combo.addItem("Todos", "")
        for el in ELEMENT_OPTIONS:
            if el:
                self._element_combo.addItem(el, el)

        # Populated from the live category folder tree (any depth) via
        # _refresh_category_filter_combo, called from _reload_categories —
        # left just with a placeholder item until the first _reload().
        self._category_filter_combo = self._labeled_combo("🏷", "Tipo")
        self._category_filter_combo.addItem("Todos", "")

        self._level_combo = self._labeled_combo("⭐", "Nível")
        self._level_combo.addItem("Todos", "")
        for lo, hi, band_label in _LEVEL_BANDS:
            self._level_combo.addItem(band_label, (lo, hi))

        for combo in (self._tier_combo, self._region_combo, self._element_combo,
                      self._category_filter_combo, self._level_combo):
            col_box = QVBoxLayout()
            col_box.setSpacing(2)
            col_box.addWidget(combo._caption_widget)
            col_box.addWidget(combo)
            filters.addLayout(col_box)
        col.addLayout(filters)

        # ── Row 2: Ordenar por + Grade/Lista toggle ──
        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_col = QVBoxLayout()
        sort_col.setSpacing(2)
        sort_caption = QLabel("Ordenar por")
        sort_caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        self._sort_combo = QComboBox()
        self._sort_combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 10px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; min-width: 130px; }}
            QComboBox QAbstractItemView {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_DIM}; }}
        """)
        for key, label in _SORT_OPTIONS:
            self._sort_combo.addItem(label, key)
        self._sort_combo.currentIndexChanged.connect(lambda _i: self._apply_filters())
        sort_col.addWidget(sort_caption)
        sort_col.addWidget(self._sort_combo)
        sort_row.addLayout(sort_col)
        sort_row.addStretch()

        self._view_mode = "grade"
        self._grade_btn = QToolButton()
        self._grade_btn.setText("▦ Grade")
        self._list_btn = QToolButton()
        self._list_btn.setText("☰ Lista")
        for btn, mode in ((self._grade_btn, "grade"), (self._list_btn, "lista")):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, m=mode: self._set_view_mode(m))
        self._grade_btn.setChecked(True)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        toggle_row.addWidget(self._grade_btn)
        toggle_row.addWidget(self._list_btn)
        self._refresh_view_toggle_style()
        sort_row.addLayout(toggle_row)
        col.addLayout(sort_row)

        result_row = QHBoxLayout()
        self._result_label = QLabel("")
        self._result_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        result_row.addWidget(self._result_label)
        result_row.addStretch()
        col.addLayout(result_row)

        def _make_scroll(widget: QWidget) -> QScrollArea:
            s = QScrollArea()
            s.setWidgetResizable(True)
            s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            s.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")
            s.setWidget(widget)
            return s

        # Grade and Lista each keep their own persistent QScrollArea — a
        # QStackedWidget just swaps which is *visible*, so toggling views
        # never hands a live widget to Qt's ownership-transferring
        # QScrollArea.setWidget() (which deletes whatever was set before).
        grid_widget = QWidget()
        self._grid_layout = FlowLayout(grid_widget, spacing=8)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(_make_scroll(grid_widget))
        self._view_stack.addWidget(_make_scroll(self._list_widget))
        col.addWidget(self._view_stack, 1)
        return col

    def _refresh_view_toggle_style(self):
        for btn, active in ((self._grade_btn, self._view_mode == "grade"), (self._list_btn, self._view_mode == "lista")):
            if active:
                btn.setStyleSheet(f"""
                    QToolButton {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
                        padding: 6px 12px; font-size: 10px; font-weight: bold; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                        padding: 6px 12px; font-size: 10px; }}
                    QToolButton:hover {{ background: rgba(255,255,255,0.1); }}
                """)
        self._grade_btn.setStyleSheet(self._grade_btn.styleSheet() + "QToolButton { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }")
        self._list_btn.setStyleSheet(self._list_btn.styleSheet() + "QToolButton { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }")

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        self._grade_btn.setChecked(mode == "grade")
        self._list_btn.setChecked(mode == "lista")
        self._refresh_view_toggle_style()
        self._view_stack.setCurrentIndex(0 if mode == "grade" else 1)
        self._apply_filters()

    def _apply_filters(self):
        if not self._ui_ready:
            return
        search = self._search_edit.text().strip().lower()
        tier = self._tier_combo.currentData() or ""
        region_id = self._region_combo.currentData() or ""
        element = self._element_combo.currentData() or ""
        category = self._category_filter_combo.currentData() or ""
        # The combo only lists root folders now (see
        # _refresh_category_filter_combo) — picking one should still match
        # every mob nested anywhere under it, not just ones filed directly
        # at the root.
        category_ids = self._descendant_ids(category) if category else set()
        level_band = self._level_combo.currentData() or None

        def matches(m: dict) -> bool:
            if self._active_filter == "favoritos" and not m.get("favorite"):
                return False
            # Browsing inside a folder (see _navigate_into) restricts to
            # mobs filed directly under it — like a file explorer only
            # showing a directory's own files, not everything nested below.
            if self._current_dir_id is not None and m.get("category") != self._current_dir_id:
                return False
            if search and search not in (m.get("name") or "").lower():
                return False
            if tier and int(m.get("tier", 1) or 1) != tier:
                return False
            if region_id and m.get("zone_id") != region_id:
                return False
            if element and m.get("element") != element:
                return False
            if category and m.get("category") not in category_ids:
                return False
            if level_band:
                lo, hi = level_band
                if not (lo <= int(m.get("level", 1) or 1) <= hi):
                    return False
            return True

        filtered = [m for m in self._mobs if matches(m)]
        sort_key = self._sort_combo.currentData() or "name_asc"
        if sort_key == "name_asc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower())
        elif sort_key == "name_desc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower(), reverse=True)
        elif sort_key == "level_asc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1))
        elif sort_key == "level_desc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1), reverse=True)
        elif sort_key == "tier_desc":
            filtered.sort(key=lambda m: int(m.get("tier", 1) or 1), reverse=True)

        self._result_label.setText(f"Mostrando {len(filtered)} de {len(self._mobs)} mobs")
        self._rebuild_grid(filtered)
        logger.info("Filtros aplicados: %d de %d mob(s) visíveis", len(filtered), len(self._mobs))

    def _rebuild_grid(self, mobs: list[dict]):
        # hide() immediately, on top of deleteLater() — deleteLater() only
        # schedules destruction for whenever the event loop next processes
        # deferred deletes (which, under rapid-fire rebuilds like typing in
        # the search box, can lag behind), so an un-hidden old card would
        # keep rendering at its stale position, overlapping the freshly
        # laid out ones.
        for layout in (self._grid_layout, self._list_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()

        zones = dict(self._zones_provider())
        target = self._grid_layout if self._view_mode == "grade" else self._list_layout
        for m in mobs:
            if self._view_mode == "grade":
                card = MobCard(m["id"])
                card.set_data(
                    m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
                    m.get("rarity", "normal"), m.get("element", ""), zones.get(m.get("zone_id", ""), ""),
                    bool(m.get("favorite", 0)),
                )
            else:
                card = self._build_list_row(m, zones)
            card.set_selected(m["id"] == self._selected_id)
            card.selected.connect(self._on_card_selected)
            card.favorite_toggled.connect(self._on_favorite_toggled)
            card.duplicate_requested.connect(self._on_duplicate)
            card.delete_requested.connect(self._on_delete)
            target.addWidget(card)
            # A freshly reparented widget doesn't reliably report
            # isVisible()==True the instant addWidget() returns — Qt shows
            # it implicitly, but not necessarily before the synchronous
            # activate() call below runs. FlowLayout._do_layout skips
            # anything not (yet) visible, so without this explicit show()
            # the most-recently-added card could be left at Qt's default
            # (0,0) geometry, overlapping everything else.
            card.show()
        if self._view_mode == "lista":
            self._list_layout.addStretch()

        # FlowLayout.addItem() (unlike built-in layouts) never calls
        # invalidate() itself, so newly added cards can sit un-positioned —
        # stacked at whatever default geometry Qt gives a freshly-parented
        # widget — until something unrelated happens to trigger a relayout.
        # Force it now instead of leaving it to chance.
        self._grid_layout.invalidate()
        self._grid_layout.activate()

    def _build_list_row(self, m: dict, zones: dict) -> MobCard:
        """Reuses MobCard's signals/behavior but a full-width horizontal
        layout instead of the fixed-size grid tile — the "Lista" view."""
        from src.layouts.panels.mobs.mob_card import MobListRow
        row = MobListRow(m["id"])
        row.set_data(
            m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
            m.get("rarity", "normal"), m.get("element", ""), zones.get(m.get("zone_id", ""), ""),
            bool(m.get("favorite", 0)),
        )
        return row

    def _mob_by_id(self, mob_id: str) -> dict | None:
        return next((m for m in self._mobs if m["id"] == mob_id), None)

    def _on_card_selected(self, mob_id: str):
        self._selected_id = mob_id
        for layout in (self._grid_layout, self._list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if w is not None and hasattr(w, "mob_id"):
                    w.set_selected(w.mob_id == mob_id)
        mob = self._mob_by_id(mob_id)
        if mob:
            self._edit_panel.load(mob)
            self._edit_panel.set_assets(self._uow.mob_assets.get_by_mob(mob_id) if self._uow else [])
        logger.info("Mob selecionado: id=%s", mob_id)

    def _on_asset_add(self, mob_id: str, fields: dict):
        if not self._uow:
            return
        self._uow.mob_assets.create(mob_id=mob_id, **fields)
        self._edit_panel.set_assets(self._uow.mob_assets.get_by_mob(mob_id))

    def _on_asset_delete(self, mob_id: str, asset_id: str):
        if not self._uow:
            return
        self._uow.mob_assets.delete(asset_id)
        self._edit_panel.set_assets(self._uow.mob_assets.get_by_mob(mob_id))
