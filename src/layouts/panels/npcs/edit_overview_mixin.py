"""OverviewSectionMixin — "Informações Gerais" (portrait, Nome/Título/Tipo/
Categoria/Facção/Região/Sub-região/Nível/Vida/Mana, Descrição). Mixed into
NPCEditPanel (see npc_edit_panel.py) — operates on self.* attributes
NPCEditPanel owns; not meant to be instantiated on its own.

"Categoria" (npcs.category, the real folder-tree column populated from
npc_categories — Mercadores/Hostis/Aliados/Figurante by default, see
npcs/categories.py) now has its own combo here, same as Mobs' template —
an earlier version of this file deliberately left it out (category
assignment via the sidebar/grid only), but that made it impossible to see
or change an NPC's category from its own edit form at all. "Tipo" is a
separate, unrelated field (the plain npc_type column — Mercador/Guardião/
Civil/... — an NPC's role/profession, not its category) and stays exactly
as it was.

"Posição no Mundo" (X/Y/Z) used to be its own second section builder here —
it now lives inside ExtrasSectionMixin's "Informações Extras" instead (see
edit_extras_mixin.py), folded in alongside Configurações Adicionais.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QWidget, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.mobs.edit_helpers import _spin, _hr, _stat_row
from src.layouts.panels.mobs.edit_widgets import _DropImageButton

logger = logging.getLogger("MAKEMAP")

NPC_TYPE_OPTIONS = ["Mercador", "Guardião", "Civil", "Hostil", "Aliado"]
STATUS_OPTIONS = ["Ativo", "Inativo"]
DEFAULT_FACTION_OPTIONS = ["Neutro", "Vila", "Guarda Real", "Bandidos", "Mercadores"]


class OverviewSectionMixin:
    """Informações Gerais — portrait next to a card of general fields, then
    Descrição as its own card. Same visual language as Mob's
    OverviewSectionMixin (borderless bold values inside #infoCard), just a
    smaller field set since NPCs have no drops/abilities/combat stats."""

    _THUMB_MAX_W = 220
    _THUMB_MAX_H = 320
    _THUMB_DEFAULT_H = 200

    def _build_overview_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome do NPC")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 6px 10px; color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        outer.addWidget(self._name_edit)

        id_row = QHBoxLayout()
        id_row.setSpacing(8)
        self._id_label = QLabel("")
        self._id_label.setTextFormat(Qt.TextFormat.RichText)
        self._id_label.setStyleSheet(
            f"font-size: 10px; font-weight: bold; background: transparent; color: {Colors.TEXT_PRIMARY}; border: none;"
        )
        id_row.addWidget(self._id_label)
        self._type_badge = QLabel("")
        self._type_badge.setStyleSheet(
            f"font-size: 11px; font-weight: bold; border-radius: 8px; padding: 4px 12px; "
            f"background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY};"
        )
        id_row.addWidget(self._type_badge)
        id_row.addStretch()
        outer.addLayout(id_row)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        thumb_col = QVBoxLayout()
        thumb_col.setSpacing(4)
        self._thumb = _DropImageButton()
        self._thumb.setFixedSize(self._THUMB_MAX_W, self._THUMB_DEFAULT_H)
        self._thumb.setIconSize(self._thumb.size())
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.setToolTip("Clique ou arraste uma imagem")
        self._thumb_pixmap = None
        self._image_path = ""
        self._thumb.clicked.connect(self._on_pick_image)
        self._thumb.image_dropped.connect(self._on_image_dropped)
        thumb_col.addWidget(self._thumb)
        thumb_hint = QLabel("Clique ou arraste uma imagem")
        thumb_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        thumb_col.addWidget(thumb_hint)
        top_row.addLayout(thumb_col)

        info_card = QFrame()
        info_card.setObjectName("infoCard")
        info_card.setStyleSheet(f"""
            QFrame#infoCard {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
            QFrame#infoCard QComboBox, QFrame#infoCard QSpinBox, QFrame#infoCard QLineEdit {{
                border: none; background: transparent; padding: 0;
                font-size: 14px; font-weight: bold; color: {Colors.TEXT_PRIMARY};
            }}
            QFrame#infoCard QComboBox::drop-down {{ width: 0; border: none; }}
            QFrame#infoCard QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
        """)
        info_lay = QVBoxLayout(info_card)
        info_lay.setContentsMargins(14, 12, 14, 12)
        info_lay.setSpacing(8)

        info_title = QLabel("Informações Gerais")
        info_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        info_lay.addWidget(info_title)
        info_lay.addWidget(_hr())

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Ex: Ferreiro da Vila")
        # Free text, not a fixed-options combo — an NPC's role/profession
        # is too open-ended for a short preset list (unlike Categoria,
        # which really is a closed set of folders).
        self._npc_type_edit = QLineEdit()
        self._npc_type_edit.setPlaceholderText("Ex: Mercador")
        self._npc_type_edit.textChanged.connect(self._refresh_type_badge)
        info_lay.addLayout(_stat_row([
            ("Título", self._title_edit), ("Tipo", self._npc_type_edit),
        ]))
        info_lay.addWidget(_hr())

        # Populated by set_category_options() from the live category folder
        # tree (NPCsPanel._reload_categories) — not built statically here
        # since folders are user-created/persisted, not a fixed list. See
        # this mixin's own docstring for why this exists (vs. "Tipo" above).
        self._category_combo = QComboBox()
        self._level_spin = _spin(1, 999, 1)
        info_lay.addLayout(_stat_row([
            ("Categoria", self._category_combo), ("Nível", self._level_spin),
        ]))
        info_lay.addWidget(_hr())

        self._faction_combo = QComboBox()
        self._faction_combo.setEditable(True)
        self._faction_combo.addItems(DEFAULT_FACTION_OPTIONS)
        self._status_combo = QComboBox()
        self._status_combo.addItems(STATUS_OPTIONS)
        info_lay.addLayout(_stat_row([
            ("Facção", self._faction_combo), ("Status", self._status_combo),
        ]))
        info_lay.addWidget(_hr())

        self._zone_combo = QComboBox()
        self._zone_combo.addItem("Sem região", "")
        self._subcategory_edit = QLineEdit()
        self._subcategory_edit.setPlaceholderText("Opcional")
        info_lay.addLayout(_stat_row([
            ("Região", self._zone_combo), ("Sub-região", self._subcategory_edit),
        ]))
        info_lay.addWidget(_hr())

        self._health_spin = _spin(0, 9_999_999, 100)
        self._mana_spin = _spin(0, 999999, 50)
        info_lay.addLayout(_stat_row([
            ("Vida", self._health_spin), ("Mana", self._mana_spin),
        ]))

        top_row.addWidget(info_card, 1)
        outer.addLayout(top_row)
        self._refresh_thumb()

        desc_card = QFrame()
        desc_card.setObjectName("descCard")
        desc_card.setStyleSheet(f"""
            QFrame#descCard {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        desc_lay = QVBoxLayout(desc_card)
        desc_lay.setContentsMargins(14, 10, 14, 10)
        desc_lay.setSpacing(6)
        desc_title = QLabel("Descrição")
        desc_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        desc_lay.addWidget(desc_title)
        desc_lay.addWidget(_hr())
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição...")
        self._desc_edit.setFixedHeight(56)
        self._desc_edit.setStyleSheet(f"""
            QTextEdit {{ border: none; background: transparent; color: {Colors.TEXT_SECONDARY}; font-size: 11px; padding: 0; }}
        """)
        desc_lay.addWidget(self._desc_edit)
        outer.addWidget(desc_card)

        outer.addStretch()
        return w

    def _refresh_type_badge(self):
        self._type_badge.setText(f"🧙 {self._npc_type_edit.text().strip() or NPC_TYPE_OPTIONS[0]}")

    def _refresh_thumb(self):
        if self._thumb_pixmap is not None:
            ratio = self._thumb_pixmap.width() / self._thumb_pixmap.height()
            w = self._THUMB_MAX_W
            h = round(w / ratio)
            if h > self._THUMB_MAX_H:
                h = self._THUMB_MAX_H
                w = round(h * ratio)
            self._thumb.setFixedSize(w, h)
            self._thumb.setIconSize(self._thumb.size())
            self._thumb.set_cover_pixmap(self._thumb_pixmap)
            self._thumb.setText("")
            self._thumb.setStyleSheet("""
                QToolButton { border-radius: 8px; border: 1px solid rgba(255,255,255,0.15); }
            """)
        else:
            self._thumb.setFixedSize(self._THUMB_MAX_W, self._THUMB_DEFAULT_H)
            self._thumb.setIconSize(self._thumb.size())
            self._thumb.set_cover_pixmap(None)
            self._thumb.setText("🧙")
            self._thumb.setStyleSheet(f"""
                QToolButton {{ border-radius: 8px; border: 1px dashed {Colors.BORDER_SUBTLE};
                background: rgba(255,255,255,0.05); font-size: 48px; color: {Colors.TEXT_MUTED}; }}
            """)

    def _on_pick_image(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Selecionar Imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        self._set_image_path(path)

    def _on_image_dropped(self, path: str):
        self._set_image_path(path)

    def _set_image_path(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._image_path = path
        self._thumb_pixmap = pixmap
        self._refresh_thumb()
        self._mark_dirty()
        logger.info("Editor: imagem selecionada para npc %s: %s", self._npc_id, path)

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

    def set_category_options(self, categories: list[dict]):
        """Repopulates the Categoria combo from the live category folder
        tree (NPCsPanel._reload_categories) — indented by depth so the
        hierarchy still reads even as a flat dropdown list. Called on every
        reload and every category CRUD, mirroring MobEditPanel's own
        set_category_options / NPCsPanel._refresh_category_filter_combo's
        tree-walk."""
        current = self._category_combo.currentData()
        self._category_combo.blockSignals(True)
        self._category_combo.clear()

        by_parent: dict[str | None, list[dict]] = {}
        for c in categories:
            by_parent.setdefault(c.get("parent_id"), []).append(c)

        def add_level(parent_id, depth):
            siblings = sorted(by_parent.get(parent_id, []), key=lambda c: (c.get("sort_order") or 0, c["name"]))
            for c in siblings:
                prefix = ("    " * depth) + ("↳ " if depth else "")
                self._category_combo.addItem(f"{prefix}{c.get('icon') or '🧙'} {c['name']}", c["id"])
                add_level(c["id"], depth + 1)

        add_level(None, 0)
        idx = self._category_combo.findData(current)
        self._category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._category_combo.blockSignals(False)
