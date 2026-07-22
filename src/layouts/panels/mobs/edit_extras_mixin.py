"""ExtrasSectionMixin — Informações Extras (Drops Principais linked to the
Item catalog, Habilidades structured list, Assets/mob_assets, Spawn,
Animações, Notas). Mixed into MobEditPanel (see mob_edit_panel.py) —
operates on self.* attributes MobEditPanel owns; not meant to be
instantiated on its own.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QToolButton, QWidget, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import ITEM_RARITY_DEFS, EFFECT_OPTIONS
from src.layouts.panels.mobs.edit_helpers import (
    _combo, _spin, _dspin, _section_label, _field_row, _extra_header_row, _hr,
)
from src.layouts.panels.mobs.edit_widgets import _DropTile, _AbilityCard, _AssetCard

logger = logging.getLogger("MAKEMAP")


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
        # set_items_catalog); no header-row "+" here since the add
        # control is its own row below, next to rate/qty. ───
        outer.addLayout(_extra_header_row("DROPS PRINCIPAIS", "", None))
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
        from PySide6.QtWidgets import QScrollArea
        drops_scroll = QScrollArea()
        drops_scroll.setWidgetResizable(True)
        drops_scroll.setFixedHeight(_DropTile.SIZE + 32)
        drops_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        drops_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        drops_scroll.setStyleSheet(f"""
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
        drops_scroll.setWidget(drops_tiles_widget)
        outer.addWidget(drops_scroll)

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

        add_drop_row = QHBoxLayout()
        add_drop_row.setSpacing(6)
        self._drop_item_combo = QComboBox()
        self._drop_rate_spin = _dspin(0, 100, 10, " %")
        self._drop_rate_spin.setDecimals(1)
        self._drop_rate_spin.setMaximumWidth(70)
        self._drop_qty_spin = _spin(1, 9999, 1)
        self._drop_qty_spin.setMaximumWidth(56)
        add_drop_btn = QToolButton()
        add_drop_btn.setText("+")
        add_drop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_drop_btn.setToolTip("Adicionar drop")
        add_drop_btn.setStyleSheet(f"""
            QToolButton {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; border: none;
                border-radius: 4px; padding: 3px 10px; font-size: 12px; font-weight: bold; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        add_drop_btn.clicked.connect(self._on_add_drop)
        add_drop_row.addWidget(self._drop_item_combo, 1)
        add_drop_row.addWidget(self._drop_rate_spin)
        add_drop_row.addWidget(self._drop_qty_spin)
        add_drop_row.addWidget(add_drop_btn)
        outer.addLayout(add_drop_row)

        # ─── Habilidades — structured list; the inline editor (add AND
        # edit, see _ability_editing_index) stays hidden until needed
        # instead of popping a separate window, same reasoning as every
        # other inline editor in this app (_InlineNameEdit etc). ───
        outer.addLayout(_extra_header_row("HABILIDADES", "+ Nova Habilidade", self._on_new_ability_clicked))
        self._abilities_container = QVBoxLayout()
        self._abilities_container.setSpacing(6)
        outer.addLayout(self._abilities_container)
        self._ability_editor = self._build_ability_editor()
        self._ability_editor.setVisible(False)
        outer.addWidget(self._ability_editor)

        # ─── Assets — stamp files for this mob (see mob_assets/migration
        # 8); persisted immediately on add/remove via
        # asset_add_requested/asset_delete_requested rather than waiting
        # for Salvar Alterações, same as category CRUD elsewhere in this
        # panel — it's a separate table, not a column on this mob row. ───
        outer.addLayout(_extra_header_row("ASSETS", "+ Novo Asset", self._on_new_asset_clicked))
        self._assets_container = QVBoxLayout()
        self._assets_container.setSpacing(6)
        outer.addLayout(self._assets_container)

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

    def _build_ability_editor(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.ACCENT}; border-radius: 8px; }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        self._ability_name_edit = QLineEdit()
        self._ability_name_edit.setPlaceholderText("Nome da habilidade")
        lay.addLayout(_field_row("Nome", self._ability_name_edit))

        lay.addWidget(QLabel("Descrição"))
        self._ability_desc_edit = QTextEdit()
        self._ability_desc_edit.setPlaceholderText("Descrição...")
        self._ability_desc_edit.setFixedHeight(40)
        lay.addWidget(self._ability_desc_edit)

        self._ability_rarity_combo = _combo([label for _k, _c, label in ITEM_RARITY_DEFS])
        lay.addLayout(_field_row("Raridade", self._ability_rarity_combo))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY}; border: none;
                border-radius: 6px; padding: 5px 12px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        cancel_btn.clicked.connect(self._on_cancel_ability_edit)
        save_btn = QPushButton("Salvar")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        save_btn.clicked.connect(self._on_save_ability)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)
        return frame

    # ─── Drops Principais ───

    def set_items_catalog(self, items: list[dict]):
        """Populates the drop-add picker from the real Item catalog
        (self._uow.items) — called on every MobsPanel._reload(), mirroring
        set_category_options/set_zone_options."""
        self._items_catalog = items
        current = self._drop_item_combo.currentData()
        self._drop_item_combo.blockSignals(True)
        self._drop_item_combo.clear()
        for it in sorted(items, key=lambda i: (i.get("name") or "").lower()):
            self._drop_item_combo.addItem(f"{it.get('icon') or '🎁'} {it.get('name', '')}", it["id"])
        idx = self._drop_item_combo.findData(current)
        self._drop_item_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._drop_item_combo.blockSignals(False)
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
        if total > 5:
            self._drops_ver_todos_btn.setVisible(True)
            self._drops_ver_todos_btn.setText("Ver menos ←" if self._drops_expanded else f"Ver todos ({total}) →")
        else:
            self._drops_ver_todos_btn.setVisible(False)

    def _on_toggle_drops_expanded(self):
        self._drops_expanded = not self._drops_expanded
        self._refresh_drops_display()

    def _on_add_drop(self):
        item_id = self._drop_item_combo.currentData()
        if not item_id:
            return
        self._drops.append({
            "item_id": item_id,
            "rate": self._drop_rate_spin.value(),
            "qty": self._drop_qty_spin.value(),
        })
        self._refresh_drops_display()
        self._mark_dirty()
        logger.info("Editor: drop adicionado (mob=%s, item=%s)", self._mob_id, item_id)

    def _on_remove_drop(self, item_id: str):
        for i, d in enumerate(self._drops):
            if d.get("item_id") == item_id:
                del self._drops[i]
                break
        self._refresh_drops_display()
        self._mark_dirty()
        logger.info("Editor: drop removido (mob=%s, item=%s)", self._mob_id, item_id)

    # ─── Habilidades ───

    def _refresh_abilities_display(self):
        while self._abilities_container.count():
            item = self._abilities_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, ability in enumerate(self._abilities):
            card = _AbilityCard(i, ability)
            card.edit_requested.connect(self._on_edit_ability)
            card.remove_requested.connect(self._on_remove_ability)
            self._abilities_container.addWidget(card)

    def _on_new_ability_clicked(self):
        self._ability_editing_index = None
        self._ability_name_edit.clear()
        self._ability_desc_edit.clear()
        self._ability_rarity_combo.setCurrentIndex(0)
        self._ability_editor.setVisible(True)

    def _on_edit_ability(self, index: int):
        ability = self._abilities[index]
        self._ability_editing_index = index
        self._ability_name_edit.setText(ability.get("name", ""))
        self._ability_desc_edit.setPlainText(ability.get("description", ""))
        from src.layouts.panels.mobs.categories import item_rarity_label as _irl
        self._ability_rarity_combo.setCurrentText(_irl(ability.get("rarity", "common")))
        self._ability_editor.setVisible(True)

    def _on_remove_ability(self, index: int):
        del self._abilities[index]
        self._refresh_abilities_display()
        self._mark_dirty()
        logger.info("Editor: habilidade removida (mob=%s, índice=%s)", self._mob_id, index)

    def _on_save_ability(self):
        name = self._ability_name_edit.text().strip()
        if not name:
            return
        rarity_key = next(
            (k for k, _c, label in ITEM_RARITY_DEFS if label == self._ability_rarity_combo.currentText()),
            "common",
        )
        entry = {"name": name, "description": self._ability_desc_edit.toPlainText().strip(), "rarity": rarity_key}
        if self._ability_editing_index is None:
            self._abilities.append(entry)
        else:
            self._abilities[self._ability_editing_index] = entry
        self._ability_editor.setVisible(False)
        self._refresh_abilities_display()
        self._mark_dirty()
        logger.info("Editor: habilidade salva (mob=%s, índice=%s): '%s'", self._mob_id, self._ability_editing_index, name)

    def _on_cancel_ability_edit(self):
        self._ability_editor.setVisible(False)

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
        for asset in self._assets:
            card = _AssetCard(asset)
            card.delete_requested.connect(self._on_delete_asset)
            self._assets_container.addWidget(card)

    def _on_new_asset_clicked(self):
        if not self._mob_id:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "Selecionar Asset", "",
            "Assets (*.fbx *.obj *.gltf *.glb *.png *.jpg *.jpeg *.webp);;Todos os arquivos (*.*)",
        )
        if not path:
            return
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
