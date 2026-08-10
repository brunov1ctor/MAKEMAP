"""ExtrasSectionMixin — "Informações Extras": Posição no Mundo (X/Y/Z),
Configurações Adicionais, Notas, Itens
Fornecidos (linked to the Item catalog, mirroring Mobs' Drops Principais —
what this NPC can supply/sell instead of combat loot), and the Assets list
(npc_assets — stamp images the Spawn tool will later pick from, see
mob_assets/migration 8 for the original pattern this mirrors). Mixed into
NPCEditPanel (see npc_edit_panel.py) — operates on self.* attributes
NPCEditPanel owns; not meant to be instantiated on its own.

Simplified vs the Mob template: no Habilidades catalog-linking UI — npcs
has no abilities_json column.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QWidget, QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.edit_helpers import (
    _dspin, _section_label, _extra_header_row, _field_row, _hr, _checkbox,
)
from src.layouts.panels.mobs.edit_widgets import (
    _AssetCard, _AssetDropScrollArea, _DropTile, _CatalogPickerDialog,
)

logger = logging.getLogger("MAKEMAP")

_CARD_AREA_MIN_H = 96
_CARD_AREA_MAX_H = 340
# See mobs/edit_extras_mixin.py's own identical constant for why this is
# tile height (_DropTile, 93px total) + a small breathing-room margin.
_ITEMS_CARD_AREA_HEIGHT = 104


class ExtrasSectionMixin:
    """Informações Extras — Posição no Mundo, visibility checkboxes, Notas,
    Itens Fornecidos, Assets."""

    def _build_extra_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        # ─── Posição no Mundo — used to be its own top-level collapsible
        # section; folded in here instead since it's mostly set by the
        # Spawn tool on the canvas, not hand-typed, same reasoning that
        # already applies to everything else in Informações Extras. ───
        outer.addWidget(_section_label("POSIÇÃO NO MUNDO"))
        outer.addWidget(_hr())
        self._pos_x_spin = _dspin(-999999.0, 999999.0, 0.0)
        self._pos_y_spin = _dspin(-999999.0, 999999.0, 0.0)
        self._pos_z_spin = _dspin(-999999.0, 999999.0, 0.0)
        for spin_w in (self._pos_x_spin, self._pos_y_spin, self._pos_z_spin):
            spin_w.setDecimals(2)
        pos_row = QHBoxLayout()
        pos_row.setSpacing(10)
        pos_row.addLayout(_field_row("X", self._pos_x_spin))
        pos_row.addLayout(_field_row("Y", self._pos_y_spin))
        pos_row.addLayout(_field_row("Z", self._pos_z_spin))
        outer.addLayout(pos_row)

        outer.addWidget(_section_label("CONFIGURAÇÕES ADICIONAIS"))
        outer.addWidget(_hr())
        self._shows_quest_icon_check = _checkbox("Mostra ícone de missão")
        self._uses_animations_check = _checkbox("Usa animações")
        checks_row1 = QHBoxLayout()
        checks_row1.setSpacing(14)
        checks_row1.addWidget(self._shows_quest_icon_check)
        checks_row1.addWidget(self._uses_animations_check)
        outer.addLayout(checks_row1)

        outer.addWidget(_section_label("NOTAS DO DESIGNER"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(48)
        outer.addWidget(self._notes_edit)

        # ─── Itens Fornecidos — top tiles reference real Item rows (see
        # set_items_catalog), exact same _DropTile mechanism as Mobs' Drops
        # Principais — just representing what this NPC can supply/sell
        # instead of combat loot. "+ Novo Item" opens a popup with the full
        # catalog as a card grid, same as Mobs. Placed right above Assets. ───
        outer.addLayout(_extra_header_row("ITENS FORNECIDOS", "+ Novo Item", self._on_open_provided_item_picker))
        outer.addWidget(_hr())
        self._provided_items_scroll = QScrollArea()
        self._provided_items_scroll.setWidgetResizable(True)
        self._provided_items_scroll.setFixedHeight(_ITEMS_CARD_AREA_HEIGHT)
        self._provided_items_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._provided_items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._provided_items_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:horizontal {{ height: 4px; background: transparent; }}
            QScrollBar::handle:horizontal {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-width: 20px; }}
        """)
        provided_items_tiles_widget = QWidget()
        self._provided_items_row = QHBoxLayout(provided_items_tiles_widget)
        self._provided_items_row.setContentsMargins(0, 0, 0, 0)
        self._provided_items_row.setSpacing(8)
        self._provided_items_row.addStretch()
        self._provided_items_scroll.setWidget(provided_items_tiles_widget)
        outer.addWidget(self._provided_items_scroll)

        self._provided_items_empty_lbl = QLabel("Nenhum item fornecido ainda.")
        self._provided_items_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(self._provided_items_empty_lbl)

        provided_items_ver_todos_row = QHBoxLayout()
        provided_items_ver_todos_row.addStretch()
        self._provided_items_ver_todos_btn = QPushButton("")
        self._provided_items_ver_todos_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._provided_items_ver_todos_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_SECONDARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 14px; padding: 6px 16px; font-size: 10px; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        self._provided_items_ver_todos_btn.clicked.connect(self._on_toggle_provided_items_expanded)
        provided_items_ver_todos_row.addWidget(self._provided_items_ver_todos_btn)
        provided_items_ver_todos_row.addStretch()
        outer.addLayout(provided_items_ver_todos_row)

        # ─── Assets — stamp files for this NPC (npc_assets, mirrors
        # mob_assets); persisted immediately on add/remove via
        # asset_add_requested/asset_delete_requested rather than waiting for
        # Salvar Alterações — it's a separate table, not a column on this
        # npc row. ───
        outer.addLayout(_extra_header_row("ASSETS", "+ Novo Asset", self._on_new_asset_clicked))
        outer.addWidget(_hr())
        self._asset_search_edit = QLineEdit()
        self._asset_search_edit.setPlaceholderText("🔍 Buscar asset...")
        self._asset_search_edit.textChanged.connect(lambda _t: self._refresh_assets_display())
        outer.addWidget(self._asset_search_edit)
        self._assets_scroll = _AssetDropScrollArea()
        self._assets_scroll.setWidgetResizable(True)
        self._assets_scroll.setFixedHeight(_CARD_AREA_MIN_H)
        self._assets_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._assets_scroll.set_base_style(f"""
            QScrollArea {{ background: transparent; border: 1px solid transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        self._assets_scroll.files_dropped.connect(self._on_assets_dropped)
        self._assets_widget = QWidget()
        self._assets_container = QVBoxLayout(self._assets_widget)
        self._assets_container.setContentsMargins(0, 0, 0, 0)
        self._assets_container.setSpacing(6)
        self._assets_scroll.setWidget(self._assets_widget)
        outer.addWidget(self._assets_scroll)

        outer.addStretch()
        return w

    # ─── Itens Fornecidos — mirrors Mobs' Drops Principais exactly (see
    # mobs/edit_extras_mixin.py's own versions of every method below), just
    # renamed/repurposed: what this NPC can supply/sell instead of combat
    # loot from a kill. Persisted as npcs.provides_items_json (migration 31),
    # same {"item_id","rate","qty"} shape as mobs.drops_json. ───

    def set_items_catalog(self, items: list[dict]):
        """Populates the item-add picker from the real Item catalog
        (self._uow.items) — called on every NPCsPanel._reload(), mirroring
        set_zone_options/set_category_options."""
        self._items_catalog = items
        self._refresh_provided_items_display()  # catalog names/icons may have changed

    def _refresh_provided_items_display(self):
        # index 0 is skipped — that's the trailing addStretch() set up in
        # _build_extra_section, which stays put so tiles left-align in the
        # scroll strip instead of centering/spreading out.
        while self._provided_items_row.count() > 1:
            item = self._provided_items_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        catalog_by_id = {it["id"]: it for it in self._items_catalog}
        ordered = sorted(self._provided_items, key=lambda d: d.get("rate", 0), reverse=True)
        visible = ordered if self._provided_items_expanded else ordered[:5]
        for entry in visible:
            item = catalog_by_id.get(entry.get("item_id"), {"id": entry.get("item_id", "")})
            tile = _DropTile(item, entry.get("rate", 0), entry.get("qty", 1))
            tile.remove_requested.connect(self._on_remove_provided_item)
            tile.open_requested.connect(self.item_open_requested.emit)
            self._provided_items_row.insertWidget(self._provided_items_row.count() - 1, tile)

        total = len(self._provided_items)
        self._provided_items_scroll.setVisible(total > 0)
        self._provided_items_empty_lbl.setVisible(total == 0)
        if total > 5:
            self._provided_items_ver_todos_btn.setVisible(True)
            self._provided_items_ver_todos_btn.setText(
                "Ver menos ←" if self._provided_items_expanded else f"Ver todos ({total}) →"
            )
        else:
            self._provided_items_ver_todos_btn.setVisible(False)

    def _on_toggle_provided_items_expanded(self):
        self._provided_items_expanded = not self._provided_items_expanded
        self._refresh_provided_items_display()

    def _on_pick_provided_item(self, item_id: str):
        if not item_id:
            return
        self._provided_items.append({"item_id": item_id, "rate": 10.0, "qty": 1})
        self._refresh_provided_items_display()
        self._mark_dirty()
        logger.info("Editor: item fornecido adicionado (npc=%s, item=%s)", self._npc_id, item_id)

    def _on_open_provided_item_picker(self):
        # Scrolls "Itens Fornecidos" to the top of the sections viewport
        # first — the picker below centers itself on that viewport, and
        # without this it'd center on wherever the scroll happened to be,
        # landing the card over unrelated content instead of the section
        # the user just clicked in.
        self._sections_scroll.ensureWidgetVisible(self._provided_items_scroll, 0, 0)
        dlg = _CatalogPickerDialog("Adicionar Item", "Buscar Item", self._items_catalog, parent=self._sections_scroll.viewport())
        dlg.exec()
        if dlg.picked_id:
            self._on_pick_provided_item(dlg.picked_id)

    def _on_remove_provided_item(self, item_id: str):
        for i, d in enumerate(self._provided_items):
            if d.get("item_id") == item_id:
                del self._provided_items[i]
                break
        self._refresh_provided_items_display()
        self._mark_dirty()
        logger.info("Editor: item fornecido removido (npc=%s, item=%s)", self._npc_id, item_id)

    def _resize_scroll_to_content(self, scroll_area: QScrollArea, content_widget: QWidget):
        content_widget.adjustSize()
        content_h = content_widget.sizeHint().height()
        scroll_area.setFixedHeight(max(_CARD_AREA_MIN_H, min(content_h, _CARD_AREA_MAX_H)))

    # ─── Assets ───

    def set_assets(self, assets: list[dict]):
        """npc_assets rows for the currently loaded NPC — fetched and
        pushed in by NPCsPanel (a separate table, not part of the npc dict
        `load()` receives), refreshed after every add/remove."""
        self._assets = assets
        self._refresh_assets_display()

    def _refresh_assets_display(self):
        while self._assets_container.count():
            item = self._assets_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self._asset_search_edit.text().strip().lower()
        for asset in self._assets:
            if query and query not in (asset.get("name") or "").lower():
                continue
            card = _AssetCard(asset)
            card.delete_requested.connect(self._on_delete_asset)
            self._assets_container.addWidget(card)
        self._assets_container.addStretch()
        self._resize_scroll_to_content(self._assets_scroll, self._assets_widget)

    def _on_new_asset_clicked(self):
        if not self._npc_id:
            return
        self._ensure_npc_saved()
        path, _filter = QFileDialog.getOpenFileName(
            self, "Selecionar Asset", "",
            "Assets (*.fbx *.obj *.gltf *.glb *.png *.jpg *.jpeg *.webp);;Todos os arquivos (*.*)",
        )
        if not path:
            return
        self._add_asset_from_path(path)

    def _on_assets_dropped(self, paths: list[str]):
        if not self._npc_id or not paths:
            return
        self._ensure_npc_saved()
        for path in paths:
            self._add_asset_from_path(path)

    def _ensure_npc_saved(self):
        if self._creating:
            # npc_assets.npc_id is a NOT NULL FK to npcs.id — this NPC is
            # still just an in-memory draft, with no row in `npcs` yet, so
            # inserting an asset now would crash with a FOREIGN KEY
            # constraint failure. Auto-save first, exactly what "Salvar
            # Alterações" does, so the asset always has a real npc row to
            # attach to.
            self.save_requested.emit(self.collect_values())

    def _add_asset_from_path(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        asset_type = {
            ".fbx": "Modelo 3D", ".obj": "Modelo 3D", ".gltf": "Modelo 3D", ".glb": "Modelo 3D",
            ".png": "Imagem", ".jpg": "Imagem", ".jpeg": "Imagem", ".webp": "Imagem",
        }.get(ext, "Arquivo")
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        fields = {
            "name": os.path.basename(path),
            "asset_type": asset_type,
            "file_path": path,
            "file_size": size,
            "rarity": "common",
        }
        logger.info("Editor: asset adicionado (npc=%s): '%s'", self._npc_id, fields["name"])
        self.asset_add_requested.emit(self._npc_id, fields)

    def _on_delete_asset(self, asset_id: str):
        if not self._npc_id:
            return
        logger.info("Editor: asset removido (npc=%s): id=%s", self._npc_id, asset_id)
        self.asset_delete_requested.emit(self._npc_id, asset_id)
