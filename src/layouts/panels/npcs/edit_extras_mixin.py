"""ExtrasSectionMixin — "⚙ Configurações Adicionais" (map-visibility
checkboxes), free-text Notas, and the Assets list (npc_assets — stamp
images the Spawn tool will later pick from, see mob_assets/migration 8 for
the original pattern this mirrors). Mixed into NPCEditPanel (see
npc_edit_panel.py) — operates on self.* attributes NPCEditPanel owns; not
meant to be instantiated on its own.

Simplified vs the Mob template: no Drops/Habilidades catalog-linking UI —
npcs has no drops_json/abilities_json columns.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QCheckBox, QWidget, QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.edit_helpers import _section_label, _extra_header_row, _hr
from src.layouts.panels.mobs.edit_widgets import _AssetCard, _AssetDropScrollArea

logger = logging.getLogger("MAKEMAP")

_CARD_AREA_MIN_H = 96
_CARD_AREA_MAX_H = 340


class ExtrasSectionMixin:
    """Configurações Adicionais — visibility checkboxes, Notas, Assets."""

    def _build_extra_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        outer.addWidget(_section_label("CONFIGURAÇÕES ADICIONAIS"))
        outer.addWidget(_hr())
        self._visible_on_map_check = QCheckBox("Visível no mapa")
        self._shows_on_minimap_check = QCheckBox("Aparece no minimapa")
        self._shows_quest_icon_check = QCheckBox("Mostra ícone de missão")
        self._uses_animations_check = QCheckBox("Usa animações")
        checks_row1 = QHBoxLayout()
        checks_row1.setSpacing(14)
        checks_row1.addWidget(self._visible_on_map_check)
        checks_row1.addWidget(self._shows_on_minimap_check)
        outer.addLayout(checks_row1)
        checks_row2 = QHBoxLayout()
        checks_row2.setSpacing(14)
        checks_row2.addWidget(self._shows_quest_icon_check)
        checks_row2.addWidget(self._uses_animations_check)
        outer.addLayout(checks_row2)

        outer.addWidget(_section_label("NOTAS DO DESIGNER"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(48)
        outer.addWidget(self._notes_edit)

        # ─── Assets — stamp files for this NPC (npc_assets, mirrors
        # mob_assets); persisted immediately on add/remove via
        # asset_add_requested/asset_delete_requested rather than waiting for
        # Salvar Alterações — it's a separate table, not a column on this
        # npc row. ───
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
