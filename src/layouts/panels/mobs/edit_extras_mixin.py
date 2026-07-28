"""ExtrasSectionMixin — Informações Extras (Drops Principais linked to the
Item catalog, Habilidades structured list, Assets/mob_assets, Spawn,
Animações, Notas). Mixed into MobEditPanel (see mob_edit_panel.py) —
operates on self.* attributes MobEditPanel owns; not meant to be
instantiated on its own.
"""

from __future__ import annotations

import json
import logging
import os

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QWidget, QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import EFFECT_OPTIONS
from src.layouts.panels.mobs.edit_helpers import (
    _combo, _spin, _dspin, _section_label, _field_row, _extra_header_row, _hr,
)
from src.layouts.panels.mobs.edit_widgets import (
    _DropTile, _AbilityTile, _AssetCard, _AssetDropScrollArea, _CatalogPickerDialog,
)
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.shared.import_export_helpers import normalize_name

logger = logging.getLogger("MAKEMAP")

# Drops stays a fixed single-row strip (it scrolls horizontally, so its
# height never depends on entry count). Habilidades/Assets instead grow
# with their content (see _resize_scroll_to_content) between these two
# bounds — tall enough to show one full-width card without feeling empty,
# capped so a mob with a dozen abilities doesn't push Spawn/Notas off
# screen; beyond the cap the area scrolls internally, same as before.
_CARD_AREA_HEIGHT = 160
_CARD_AREA_MIN_H = 96
_CARD_AREA_MAX_H = 340


class ExtrasSectionMixin:
    """Informações Extras — Drops Principais (linked to the Item
    catalog), Habilidades (structured list), Assets (map-stamp files
    for this mob, see mob_assets/migration 8), Spawn (respawn/patrol/
    efeitos — Região itself lives in Visão Geral), and the remaining
    free-text Animações / Notas do Designer."""

    def _build_extra_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        # ─── Drops Principais — top tiles reference real Item rows (see
        # set_items_catalog); "+ Novo Item" opens a popup with the full
        # catalog as a card grid (see _on_open_drop_picker) instead of
        # keeping that search grid always inline. ───
        outer.addLayout(_extra_header_row("DROPS PRINCIPAIS", "+ Novo Item", self._on_open_drop_picker))
        outer.addWidget(_hr())
        # A horizontally-scrolling QScrollArea + QHBoxLayout, NOT a
        # FlowLayout — FlowLayout relies on heightForWidth to report its
        # own height, which only reaches the parent reliably when it's
        # the *direct* layout of a QScrollArea's widget (that's how the
        # main mob grid uses it, see MobsPanel._build_center). Nested
        # several QVBoxLayouts + collapsible sections + an ancestor
        # QScrollArea deep inside this panel, that height never
        # propagated back up — new tiles rendered but got clipped to
        # whatever height the container happened to have before they
        # existed. A fixed-height scroll strip sidesteps the whole
        # problem: height is constant, only width scrolls.
        self._drops_scroll = QScrollArea()
        self._drops_scroll.setWidgetResizable(True)
        self._drops_scroll.setFixedHeight(_CARD_AREA_HEIGHT)
        self._drops_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._drops_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._drops_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:horizontal {{ height: 4px; background: transparent; }}
            QScrollBar::handle:horizontal {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-width: 20px; }}
        """)
        drops_tiles_widget = QWidget()
        self._drops_row = QHBoxLayout(drops_tiles_widget)
        self._drops_row.setContentsMargins(0, 0, 0, 0)
        self._drops_row.setSpacing(8)
        self._drops_row.addStretch()
        self._drops_scroll.setWidget(drops_tiles_widget)
        outer.addWidget(self._drops_scroll)

        # Shown instead of the (otherwise empty, still-160px-tall) strip
        # above when this mob has no drops yet — without it that fixed
        # height reads as a blank gap between the header and Taxa/Qtd.
        self._drops_empty_lbl = QLabel("Nenhum drop adicionado ainda.")
        self._drops_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(self._drops_empty_lbl)

        ver_todos_row = QHBoxLayout()
        ver_todos_row.addStretch()
        self._drops_ver_todos_btn = QPushButton("")
        self._drops_ver_todos_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drops_ver_todos_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_SECONDARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 14px; padding: 6px 16px; font-size: 10px; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        self._drops_ver_todos_btn.clicked.connect(self._on_toggle_drops_expanded)
        ver_todos_row.addWidget(self._drops_ver_todos_btn)
        ver_todos_row.addStretch()
        outer.addLayout(ver_todos_row)

        # ─── Habilidades — the linked-cards list (already on this mob)
        # stays as-is; "+ Vincular Habilidade" opens the same popup pattern
        # as Drops above, over the real Skill catalog instead of a
        # QComboBox (see _on_open_ability_picker). ───
        outer.addLayout(_extra_header_row("HABILIDADES", "+ Vincular Habilidade", self._on_open_ability_picker))
        outer.addWidget(_hr())
        self._abilities_scroll = QScrollArea()
        self._abilities_scroll.setWidgetResizable(True)
        self._abilities_scroll.setFixedHeight(_CARD_AREA_MIN_H)
        self._abilities_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._abilities_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        self._abilities_widget = QWidget()
        # FlowLayout, not QVBoxLayout — same square-tile grid as Drops
        # Principais instead of a stacked list of wide cards (see
        # _AbilityTile), so multiple habilidades wrap across the available
        # width instead of always taking one full row each.
        self._abilities_container = FlowLayout(self._abilities_widget, spacing=10)
        self._abilities_container.setContentsMargins(0, 0, 0, 0)
        self._abilities_scroll.setWidget(self._abilities_widget)
        outer.addWidget(self._abilities_scroll)

        # Shown instead of the linked-cards scroll area when this mob has
        # no habilidades yet — otherwise that area's own min height still
        # reserves space, reading as a blank gap before the search grid.
        self._abilities_empty_lbl = QLabel("Nenhuma habilidade vinculada ainda.")
        self._abilities_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(self._abilities_empty_lbl)

        # ─── Assets — stamp files for this mob (see mob_assets/migration
        # 8); persisted immediately on add/remove via
        # asset_add_requested/asset_delete_requested rather than waiting
        # for Salvar Alterações, same as category CRUD elsewhere in this
        # panel — it's a separate table, not a column on this mob row. ───
        outer.addLayout(_extra_header_row("ASSETS", "+ Novo Asset", self._on_new_asset_clicked))
        outer.addWidget(_hr())
        assets_filter_row = QHBoxLayout()
        assets_filter_row.setSpacing(6)
        self._asset_search_edit = QLineEdit()
        self._asset_search_edit.setPlaceholderText("🔍 Buscar asset...")
        self._asset_search_edit.textChanged.connect(lambda _t: self._refresh_assets_display())
        assets_filter_row.addWidget(self._asset_search_edit, 1)
        self._asset_type_filter = QComboBox()
        self._asset_type_filter.addItem("Tipo: Todos", "")
        self._asset_type_filter.addItem("Modelo 3D", "Modelo 3D")
        self._asset_type_filter.addItem("Imagem", "Imagem")
        self._asset_type_filter.addItem("Arquivo", "Arquivo")
        self._asset_type_filter.currentIndexChanged.connect(lambda _i: self._refresh_assets_display())
        assets_filter_row.addWidget(self._asset_type_filter)
        outer.addLayout(assets_filter_row)
        # Accepts files dragged straight from Explorer/Finder — same idea
        # as the Visão Geral portrait's own drag-and-drop, just multi-file
        # and covering 3D models/textures too (see _AssetDropScrollArea).
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

        # ─── Spawn — Efeitos moved in here as a compact dropdown (was its
        # own free-text section) to match the reference layout. ───
        outer.addLayout(_extra_header_row("SPAWN", "", None))
        outer.addWidget(_hr())
        self._respawn_spin = _spin(0, 999999, 60)
        self._respawn_spin.setSuffix(" s")
        self._patrol_spin = _dspin(0, 99999, 10, " m")
        self._effect_combo = _combo(EFFECT_OPTIONS)
        spawn_row = QHBoxLayout()
        spawn_row.setSpacing(10)
        spawn_row.addLayout(_field_row("Tempo de Respawn", self._respawn_spin))
        spawn_row.addLayout(_field_row("Raio de Patrulha", self._patrol_spin))
        spawn_row.addLayout(_field_row("Efeitos", self._effect_combo))
        outer.addLayout(spawn_row)
        self._spawn_notes = QTextEdit()
        self._spawn_notes.setPlaceholderText("Condições de spawn, pontos de invocação, frequência...")
        self._spawn_notes.setFixedHeight(48)
        outer.addWidget(self._spawn_notes)

        outer.addWidget(_section_label("ANIMAÇÕES"))
        self._animation_notes = QTextEdit()
        self._animation_notes.setPlaceholderText("Animações: idle, ataque, morte, referências de sprite/arquivo...")
        self._animation_notes.setFixedHeight(48)
        outer.addWidget(self._animation_notes)

        outer.addWidget(_section_label("NOTAS DO DESIGNER"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(48)
        outer.addWidget(self._notes_edit)

        outer.addStretch()
        return w

    def _resize_scroll_to_content(self, scroll_area: QScrollArea, content_widget: QWidget):
        """Grows `scroll_area` to fit `content_widget`'s current cards, up
        to _CARD_AREA_MAX_H — beyond that it keeps a fixed height and lets
        the QScrollArea's own scrollbar take over. Setting a fixed height
        computed from the content's real sizeHint (rather than relying on
        heightForWidth to bubble up through the ancestor layouts) sidesteps
        the propagation dead-end noted below on _CARD_AREA_HEIGHT."""
        content_widget.adjustSize()
        content_h = content_widget.sizeHint().height()
        scroll_area.setFixedHeight(max(_CARD_AREA_MIN_H, min(content_h, _CARD_AREA_MAX_H)))

    # ─── Drops Principais ───

    def set_items_catalog(self, items: list[dict]):
        """Populates the drop-add picker from the real Item catalog
        (self._uow.items) — called on every MobsPanel._reload(), mirroring
        set_category_options/set_zone_options."""
        self._items_catalog = items
        self._refresh_drops_display()  # catalog names/icons may have changed

    def _refresh_drops_display(self):
        # index 0 is skipped — that's the trailing addStretch() set up in
        # _build_extra_section, which stays put so tiles left-align in the
        # scroll strip instead of centering/spreading out.
        while self._drops_row.count() > 1:
            item = self._drops_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        catalog_by_id = {it["id"]: it for it in self._items_catalog}
        ordered = sorted(self._drops, key=lambda d: d.get("rate", 0), reverse=True)
        visible = ordered if self._drops_expanded else ordered[:5]
        for entry in visible:
            item = catalog_by_id.get(entry.get("item_id"), {"id": entry.get("item_id", "")})
            tile = _DropTile(item, entry.get("rate", 0), entry.get("qty", 1))
            tile.remove_requested.connect(self._on_remove_drop)
            self._drops_row.insertWidget(self._drops_row.count() - 1, tile)

        total = len(self._drops)
        self._drops_scroll.setVisible(total > 0)
        self._drops_empty_lbl.setVisible(total == 0)
        if total > 5:
            self._drops_ver_todos_btn.setVisible(True)
            self._drops_ver_todos_btn.setText("Ver menos ←" if self._drops_expanded else f"Ver todos ({total}) →")
        else:
            self._drops_ver_todos_btn.setVisible(False)

    def _on_toggle_drops_expanded(self):
        self._drops_expanded = not self._drops_expanded
        self._refresh_drops_display()

    def _on_pick_drop_item(self, item_id: str):
        if not item_id:
            return
        item = next((it for it in self._items_catalog if it.get("id") == item_id), None)
        stats = self._parse_stats(item.get("stats")) if item else {}
        self._drops.append({
            "item_id": item_id,
            "rate": float(stats.get("drop_rate", 10.0)),
            "qty": int(stats.get("drop_qty", 1)),
        })
        self._refresh_drops_display()
        self._mark_dirty()
        logger.info("Editor: drop adicionado (mob=%s, item=%s)", self._mob_id, item_id)

    def _on_open_drop_picker(self):
        # Scrolls "Drops Principais" to the top of the sections viewport
        # first — the picker below centers itself on that viewport, and
        # without this it'd center on wherever the scroll happened to be
        # (usually still showing Visão Geral above), landing the card over
        # unrelated content instead of the section the user just clicked in.
        self._sections_scroll.ensureWidgetVisible(self._drops_scroll, 0, 0)
        dlg = _CatalogPickerDialog("Adicionar Drop", "Buscar Item", self._items_catalog, parent=self._sections_scroll.viewport())
        dlg.exec()
        if dlg.picked_id:
            self._on_pick_drop_item(dlg.picked_id)

    @staticmethod
    def _parse_stats(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _on_remove_drop(self, item_id: str):
        for i, d in enumerate(self._drops):
            if d.get("item_id") == item_id:
                del self._drops[i]
                break
        self._refresh_drops_display()
        self._mark_dirty()
        logger.info("Editor: drop removido (mob=%s, item=%s)", self._mob_id, item_id)

    # ─── Habilidades ───

    def set_skills_catalog(self, skills: list[dict]):
        """Populates the ability picker from the real Skill catalog
        (self._uow.skills) — called on every MobsPanel._reload(), mirroring
        set_items_catalog above."""
        self._skills_catalog = skills
        self._refresh_abilities_display()  # catalog names/icons/images may have changed

    def _resolve_ability(self, entry: dict) -> tuple[dict, bool]:
        """(display dict, unlinked) for one self._abilities entry — either
        the live skill row (skill_id resolves against the catalog), a
        "removed from catalog" placeholder (skill_id set but no longer in
        self._skills_catalog), or a legacy unmatched record (see
        _migrate_legacy_ability)."""
        skill_id = entry.get("skill_id")
        if skill_id:
            catalog_by_id = {s["id"]: s for s in self._skills_catalog}
            skill = catalog_by_id.get(skill_id)
            if skill:
                return skill, False
            return {"id": skill_id}, True
        return {
            "id": "",
            "name": entry.get("legacy_name", ""),
            "description": entry.get("legacy_description", ""),
            "rarity": entry.get("legacy_rarity", "common"),
        }, True

    def _refresh_abilities_display(self):
        while self._abilities_container.count():
            item = self._abilities_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, entry in enumerate(self._abilities):
            skill, unlinked = self._resolve_ability(entry)
            tile = _AbilityTile(i, skill, unlinked=unlinked)
            tile.remove_requested.connect(self._on_remove_ability)
            self._abilities_container.addWidget(tile)
        has_abilities = bool(self._abilities)
        self._abilities_scroll.setVisible(has_abilities)
        self._abilities_empty_lbl.setVisible(not has_abilities)
        if has_abilities:
            self._resize_scroll_to_content(self._abilities_scroll, self._abilities_widget)

    def _on_remove_ability(self, index: int):
        del self._abilities[index]
        self._refresh_abilities_display()
        self._mark_dirty()
        logger.info("Editor: habilidade removida (mob=%s, índice=%s)", self._mob_id, index)

    def _on_pick_ability(self, skill_id: str):
        if not skill_id:
            return
        entry = {"skill_id": skill_id}
        if self._ability_editing_index is None:
            self._abilities.append(entry)
        else:
            self._abilities[self._ability_editing_index] = entry
            self._ability_editing_index = None
        self._refresh_abilities_display()
        self._mark_dirty()
        logger.info("Editor: habilidade adicionada (mob=%s): skill_id=%s", self._mob_id, skill_id)

    def _on_open_ability_picker(self):
        # See the matching comment in _on_open_drop_picker.
        self._sections_scroll.ensureWidgetVisible(self._abilities_scroll, 0, 0)
        dlg = _CatalogPickerDialog("Vincular Habilidade", "Buscar Habilidade", self._skills_catalog, parent=self._sections_scroll.viewport())
        dlg.exec()
        if dlg.picked_id:
            self._on_pick_ability(dlg.picked_id)
        else:
            self._ability_editing_index = None  # cancelou uma edição em andamento

    def _migrate_legacy_ability(self, entry: dict) -> dict:
        """Best-effort migration of pre-catalog-link entries
        ({"name","description","rarity"}, no skill_id) — matched by
        normalized name against the live skills catalog. No match keeps
        the old text as an unlinked legacy record instead of dropping it;
        it converts to the new {"skill_id"} shape the next time the
        designer re-selects and re-saves it."""
        if entry.get("skill_id"):
            return entry
        legacy_name = normalize_name(entry.get("name", ""))
        match = next(
            (s for s in self._skills_catalog if normalize_name(s.get("name", "")) == legacy_name),
            None,
        ) if legacy_name else None
        if match:
            return {"skill_id": match["id"]}
        return {
            "legacy_name": entry.get("name", ""),
            "legacy_description": entry.get("description", ""),
            "legacy_rarity": entry.get("rarity", "common"),
        }

    # ─── Assets ───

    def set_assets(self, assets: list[dict]):
        """mob_assets rows for the currently loaded mob — fetched and
        pushed in by MobsPanel (a separate table, not part of the mob
        dict `load()` receives), refreshed after every add/remove."""
        self._assets = assets
        self._refresh_assets_display()

    def _refresh_assets_display(self):
        while self._assets_container.count():
            item = self._assets_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self._asset_search_edit.text().strip().lower()
        type_filter = self._asset_type_filter.currentData() or ""
        for asset in self._assets:
            if query and query not in (asset.get("name") or "").lower():
                continue
            if type_filter and asset.get("asset_type") != type_filter:
                continue
            card = _AssetCard(asset)
            card.delete_requested.connect(self._on_delete_asset)
            self._assets_container.addWidget(card)
        self._assets_container.addStretch()
        self._resize_scroll_to_content(self._assets_scroll, self._assets_widget)

    def _on_new_asset_clicked(self):
        if not self._mob_id:
            return
        self._ensure_mob_saved()
        path, _filter = QFileDialog.getOpenFileName(
            self, "Selecionar Asset", "",
            "Assets (*.fbx *.obj *.gltf *.glb *.png *.jpg *.jpeg *.webp);;Todos os arquivos (*.*)",
        )
        if not path:
            return
        self._add_asset_from_path(path)

    def _on_assets_dropped(self, paths: list[str]):
        """Files dragged straight onto the Assets list (see
        _AssetDropScrollArea) — same import as "+ Novo Asset", just
        skipping the file dialog and accepting several at once."""
        if not self._mob_id or not paths:
            return
        self._ensure_mob_saved()
        for path in paths:
            self._add_asset_from_path(path)

    def _ensure_mob_saved(self):
        if self._creating:
            # mob_assets.mob_id is a NOT NULL FK to mobs.id — this mob is
            # still just an in-memory draft (see MobCrudMixin._on_new_mob),
            # with no row in `mobs` yet, so inserting an asset now would
            # crash with a FOREIGN KEY constraint failure. Auto-save first,
            # exactly what "Salvar Alterações" does, so the asset always
            # has a real mob row to attach to.
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
        logger.info("Editor: asset adicionado (mob=%s): '%s'", self._mob_id, fields["name"])
        self.asset_add_requested.emit(self._mob_id, fields)

    def _on_delete_asset(self, asset_id: str):
        if not self._mob_id:
            return
        logger.info("Editor: asset removido (mob=%s): id=%s", self._mob_id, asset_id)
        self.asset_delete_requested.emit(self._mob_id, asset_id)
