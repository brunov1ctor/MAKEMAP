"""GridFilterMixin — the center card grid/list, its filter row, and card
selection. Mixed into NPCsPanel (see panel.py) — operates on self.*
attributes NPCsPanel owns; not meant to be instantiated on its own.

Mirrors src/layouts/panels/mobs/panel_grid_mixin.py, adapted to npcs'
own columns: no tier/element (mob-specific combat fields), replaced with
Tipo (npc_type) and Status (ativo/inativo) filters instead.
"""

from __future__ import annotations

import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QToolButton, QScrollArea, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors, combo_qss
from src.services.project_assets import import_asset, resolve_asset_path
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.npcs.categories import NPC_TYPE_OPTIONS, STATUS_OPTIONS
from src.layouts.panels.npcs.npc_card import NPCCard
from src.layouts.panels.npcs.panel_helpers import _LEVEL_BANDS, _SORT_OPTIONS

logger = logging.getLogger("MAKEMAP")


class GridFilterMixin:
    """Search + Região/Tipo/Categoria/Status/Nível filters, Ordenar por +
    Grade/Lista toggle, and the resulting card grid/list."""

    def _labeled_combo(self, icon: str, caption: str) -> QComboBox:
        combo = QComboBox()
        combo.setStyleSheet(combo_qss(radius=6, padding="4px 6px") + "QComboBox { min-width: 84px; }")
        combo.currentIndexChanged.connect(lambda _i: self._apply_filters())
        combo._caption_widget = QLabel(f"{icon} {caption}")
        combo._caption_widget.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        return combo

    def _build_center(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Pesquisar npcs...")
        self._search_edit.textChanged.connect(self._apply_filters)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 6px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 11px; }}
        """)
        filters.addWidget(self._search_edit, 1)

        self._region_combo = self._labeled_combo("🗺", "Região")
        self._region_combo.addItem("Todas", "")

        self._npc_type_combo = self._labeled_combo("🎭", "Tipo")
        self._npc_type_combo.addItem("Todos", "")
        for t in NPC_TYPE_OPTIONS:
            self._npc_type_combo.addItem(t, t)

        # Populated from the live category folder tree (any depth) via
        # _refresh_category_filter_combo, called from _reload_categories.
        self._category_filter_combo = self._labeled_combo("📁", "Categoria")
        self._category_filter_combo.addItem("Todos", "")

        self._status_combo = self._labeled_combo("⚡", "Status")
        self._status_combo.addItem("Todos", "")
        for s in STATUS_OPTIONS:
            self._status_combo.addItem(s, s.lower())

        self._level_combo = self._labeled_combo("⭐", "Nível")
        self._level_combo.addItem("Todos", "")
        for lo, hi, band_label in _LEVEL_BANDS:
            self._level_combo.addItem(band_label, (lo, hi))

        for combo in (self._region_combo, self._npc_type_combo,
                      self._category_filter_combo, self._status_combo, self._level_combo):
            col_box = QVBoxLayout()
            col_box.setSpacing(2)
            col_box.addWidget(combo._caption_widget)
            col_box.addWidget(combo)
            filters.addLayout(col_box)
        col.addLayout(filters)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_col = QVBoxLayout()
        sort_col.setSpacing(2)
        sort_caption = QLabel("Ordenar por")
        sort_caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        self._sort_combo = QComboBox()
        self._sort_combo.setStyleSheet(combo_qss(radius=6, padding="4px 10px") + "QComboBox { min-width: 130px; }")
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
        region_id = self._region_combo.currentData() or ""
        npc_type = self._npc_type_combo.currentData() or ""
        category = self._category_filter_combo.currentData() or ""
        category_ids = self._descendant_ids(category) if category else set()
        status = self._status_combo.currentData() or ""
        level_band = self._level_combo.currentData() or None

        def matches(m: dict) -> bool:
            if search and search not in (m.get("name") or "").lower():
                return False
            if region_id and m.get("zone_id") != region_id:
                return False
            if npc_type and m.get("npc_type") != npc_type:
                return False
            if category and m.get("category") not in category_ids:
                return False
            if status and (m.get("status") or "ativo") != status:
                return False
            if level_band:
                lo, hi = level_band
                if not (lo <= int(m.get("level", 1) or 1) <= hi):
                    return False
            return True

        filtered = [m for m in self._npcs if matches(m)]
        sort_key = self._sort_combo.currentData() or "name_asc"
        if sort_key == "name_asc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower())
        elif sort_key == "name_desc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower(), reverse=True)
        elif sort_key == "level_asc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1))
        elif sort_key == "level_desc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1), reverse=True)

        self._result_label.setText(f"Mostrando {len(filtered)} de {len(self._npcs)} npcs")
        self._rebuild_grid(filtered)
        logger.info("Filtros aplicados: %d de %d npc(s) visíveis", len(filtered), len(self._npcs))

    def _rebuild_grid(self, npcs: list[dict]):
        for layout in (self._grid_layout, self._list_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()

        zones = dict(self._zones_provider())
        target = self._grid_layout if self._view_mode == "grade" else self._list_layout
        for m in npcs:
            zone_id = m.get("zone_id", "")
            zone_image = self._zone_thumbnail_provider(zone_id) if zone_id else None
            if self._view_mode == "grade":
                card = NPCCard(m["id"])
                card.set_data(
                    m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
                    m.get("npc_type", ""), zones.get(zone_id, ""),
                    bool(m.get("favorite", 0)), resolve_asset_path(self._project_dir, m.get("image_path", "")),
                    zone_image=zone_image,
                )
            else:
                card = self._build_list_row(m, zones, zone_image)
            card.set_selected(m["id"] == self._selected_id)
            card.selected.connect(self._on_card_selected)
            card.favorite_toggled.connect(self._on_favorite_toggled)
            card.duplicate_requested.connect(self._on_duplicate)
            card.delete_requested.connect(self._on_delete)
            target.addWidget(card)
            card.show()
        if self._view_mode == "lista":
            self._list_layout.addStretch()

        self._grid_layout.invalidate()
        self._grid_layout.activate()

    def _build_list_row(self, m: dict, zones: dict, zone_image=None) -> NPCCard:
        from src.layouts.panels.npcs.npc_card import NPCListRow
        row = NPCListRow(m["id"])
        row.set_data(
            m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
            m.get("npc_type", ""), zones.get(m.get("zone_id", ""), ""),
            bool(m.get("favorite", 0)), resolve_asset_path(self._project_dir, m.get("image_path", "")),
            zone_image=zone_image,
        )
        return row

    def _npc_by_id(self, npc_id: str) -> dict | None:
        return next((m for m in self._npcs if m["id"] == npc_id), None)

    def _on_card_selected(self, npc_id: str):
        self._selected_id = npc_id
        for layout in (self._grid_layout, self._list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if w is not None and hasattr(w, "npc_id"):
                    w.set_selected(w.npc_id == npc_id)
        npc = self._npc_by_id(npc_id)
        if npc:
            display = dict(npc)
            display["image_path"] = resolve_asset_path(self._project_dir, npc.get("image_path", ""))
            self._edit_panel.load(display)
            self._refresh_assets_display(npc_id)
        logger.info("NPC selecionado: id=%s", npc_id)

    def _refresh_assets_display(self, npc_id: str):
        assets = self._uow.npc_assets.get_by_npc(npc_id) if self._uow else []
        resolved = []
        for asset in assets:
            display = dict(asset)
            display["file_path"] = resolve_asset_path(self._project_dir, asset.get("file_path", ""))
            resolved.append(display)
        self._edit_panel.set_assets(resolved)

    def _on_asset_add(self, npc_id: str, fields: dict):
        if not self._uow:
            return
        asset_id = str(uuid.uuid4())
        if fields.get("file_path"):
            fields["file_path"] = import_asset(
                self._project_dir, fields["file_path"], "assets/npc_assets", asset_id)
        self._uow.npc_assets.create(id=asset_id, npc_id=npc_id, **fields)
        self._refresh_assets_display(npc_id)

    def _on_asset_delete(self, npc_id: str, asset_id: str):
        if not self._uow:
            return
        self._uow.npc_assets.delete(asset_id)
        self._refresh_assets_display(npc_id)
