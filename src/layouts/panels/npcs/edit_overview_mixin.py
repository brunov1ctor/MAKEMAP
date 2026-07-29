"""OverviewSectionMixin — "Informações Gerais" (portrait, Nome/Título/Tipo/
Facção/Região/Sub-região/Nível/Vida/Mana, Descrição) plus a second small
section builder for "Posição no Mundo" (X/Y/Z). Mixed into NPCEditPanel (see
npc_edit_panel.py) — operates on self.* attributes NPCEditPanel owns; not
meant to be instantiated on its own.

Deviation from the Mob template: NPCs don't get a category-folder combo here
— npcs.category (the folder-tree column, same free-text/no-FK pattern as
mobs.category) is owned by the NPCsPanel sidebar explorer being built
separately, not by this edit form. "Tipo" instead binds straight to the
plain npc_type column via a fixed-options combo, so this file never needs to
import the (concurrently-authored) npcs/categories.py.
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
from src.layouts.panels.mobs.edit_helpers import _spin, _dspin, _hr, _stat_row, _field_row
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
        self._npc_type_combo = QComboBox()
        self._npc_type_combo.addItems(NPC_TYPE_OPTIONS)
        self._npc_type_combo.currentIndexChanged.connect(self._refresh_type_badge)
        info_lay.addLayout(_stat_row([
            ("Título", self._title_edit), ("Tipo", self._npc_type_combo),
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

        self._level_spin = _spin(1, 999, 1)
        self._level_min_spin = _spin(1, 999, 1)
        self._level_max_spin = _spin(1, 999, 1)
        info_lay.addLayout(_stat_row([
            ("Nível", self._level_spin),
        ]))
        lvl_range_row = QHBoxLayout()
        lvl_range_row.setSpacing(6)
        lvl_range_row.addLayout(_field_row("Nível recomendado (min)", self._level_min_spin))
        lvl_range_row.addLayout(_field_row("Nível recomendado (max)", self._level_max_spin))
        info_lay.addLayout(lvl_range_row)
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

    def _build_position_section(self) -> QWidget:
        """Posição no Mundo — X/Y/Z, split out as its own collapsible
        section (see NPCEditPanel._build_ui) so it doesn't crowd the
        Informações Gerais card with world-placement fields that are mostly
        set by the Spawn tool on the canvas, not typed by hand."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(8)

        self._pos_x_spin = _dspin(-999999.0, 999999.0, 0.0)
        self._pos_y_spin = _dspin(-999999.0, 999999.0, 0.0)
        self._pos_z_spin = _dspin(-999999.0, 999999.0, 0.0)
        for spin_w in (self._pos_x_spin, self._pos_y_spin, self._pos_z_spin):
            spin_w.setDecimals(2)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addLayout(_field_row("X", self._pos_x_spin))
        row.addLayout(_field_row("Y", self._pos_y_spin))
        row.addLayout(_field_row("Z", self._pos_z_spin))
        outer.addLayout(row)
        outer.addStretch()
        return w

    def _refresh_type_badge(self):
        self._type_badge.setText(f"🧙 {self._npc_type_combo.currentText()}")

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
