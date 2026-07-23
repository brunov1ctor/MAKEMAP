"""OverviewSectionMixin — Visão Geral (Nome, ID+Raridade, portrait,
Informações Gerais card, Descrição). Mixed into MobEditPanel (see
mob_edit_panel.py) — operates on self.* attributes MobEditPanel owns; not
meant to be instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QToolButton, QWidget, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import RARITY_DEFS, TIPO_OPTIONS
from src.layouts.panels.mobs.edit_helpers import _combo, _spin, _hr, _stat_row
from src.layouts.panels.mobs.edit_widgets import _DropImageButton

logger = logging.getLogger("MAKEMAP")


class OverviewSectionMixin:
    """Visão Geral — matches the reference profile-card layout: the
    editable Nome field at the top, then an ID + Raridade badge row,
    then a big portrait next to an "Informações Gerais" card (Nível/
    Tipo/Tier, Categoria/Subcategoria, Ambiente/Região — label above
    value, thin dividers between columns and between rows, no visible
    input borders), then Descrição as its own full-width card. The
    panel's own header (see MobEditPanel._build_ui) just mirrors this
    Nome field as a plain read-only title — it's not a separate/
    duplicate value, load()/set_empty() set both from the same source.
    Status, Elemento and the Raridade *selector* (the badge here is just
    a readout of it) live in Atributos instead — none of the three
    appear in the reference card."""

    def _build_overview_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome do mob")
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
        self._id_label.setStyleSheet(f"""
            font-size: 10px; font-weight: bold; background: rgba(255,255,255,0.05); color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 4px 10px;
        """)
        id_row.addWidget(self._id_label)
        self._rarity_badge = QLabel("")
        self._rarity_badge.setStyleSheet("font-size: 11px; font-weight: bold; border-radius: 8px; padding: 4px 12px;")
        id_row.addWidget(self._rarity_badge)
        id_row.addStretch()
        outer.addLayout(id_row)

        # ─── Portrait + "Informações Gerais" card, side by side ───
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        thumb_col = QVBoxLayout()
        thumb_col.setSpacing(4)
        self._thumb = _DropImageButton()
        self._thumb.setFixedSize(220, 200)
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

        # QComboBox/QSpinBox/QLineEdit here are overridden borderless/
        # bold/larger — the reference shows plain typography, not boxed
        # form inputs, even though these stay fully editable. Scoped to
        # #infoCard (not a bare "QFrame" selector) so it doesn't also
        # repaint the _hr() dividers nested inside, which are QFrame too.
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

        self._level_spin = _spin(1, 999, 1)
        self._tipo_combo = _combo(TIPO_OPTIONS)
        self._tier_spin = _spin(1, 10, 1)
        info_lay.addLayout(_stat_row([
            ("Nível", self._level_spin), ("Tipo", self._tipo_combo), ("Tier", self._tier_spin),
        ]))
        info_lay.addWidget(_hr())

        # Populated by set_category_options() from the live category
        # folder tree (MobsPanel._reload_categories) — not built statically
        # here since folders are user-created/persisted, not a fixed list.
        self._category_combo = QComboBox()
        self._subcategory_edit = QLineEdit()
        self._subcategory_edit.setPlaceholderText("Opcional")
        info_lay.addLayout(_stat_row([
            ("Categoria", self._category_combo), ("Subcategoria", self._subcategory_edit),
        ]))
        info_lay.addWidget(_hr())

        self._ambiente_edit = QLineEdit()
        self._ambiente_edit.setPlaceholderText("Ex: Pântano Sombrio")
        self._zone_combo = QComboBox()
        self._zone_combo.addItem("Sem região", "")
        info_lay.addLayout(_stat_row([
            ("Ambiente", self._ambiente_edit), ("Região", self._zone_combo),
        ]))

        top_row.addWidget(info_card, 1)
        outer.addLayout(top_row)
        self._refresh_thumb()

        # ─── Descrição — its own full-width card, same borderless
        # textedit treatment as the fields above. ───
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

    def _refresh_rarity_badge(self):
        key = next((k for k, _c, label in RARITY_DEFS if label == self._rarity_combo.currentText()), "normal")
        color = next((c for k, c, _l in RARITY_DEFS if k == key), "#9AA5B1")
        self._rarity_badge.setText(f"🔥 {self._rarity_combo.currentText()}")
        self._rarity_badge.setStyleSheet(
            f"font-size: 11px; font-weight: bold; border-radius: 8px; padding: 4px 12px; "
            f"background: {color}33; color: {color};"
        )

    def _refresh_thumb(self):
        if self._thumb_pixmap is not None:
            # QIcon on a QToolButton letterboxes to fit — scaling
            # KeepAspectRatioByExpanding then cropping to the button's own
            # size first (cover-fit) makes the image actually fill the
            # whole portrait area instead of floating small with padding
            # around it whenever its aspect ratio doesn't match the button.
            btn_size = self._thumb.size()
            scaled = self._thumb_pixmap.scaled(
                btn_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - btn_size.width()) // 2
            y = (scaled.height() - btn_size.height()) // 2
            cropped = scaled.copy(x, y, btn_size.width(), btn_size.height())
            self._thumb.setIcon(QIcon(cropped))
            self._thumb.setText("")
            self._thumb.setStyleSheet("""
                QToolButton { border-radius: 8px; border: 1px solid rgba(255,255,255,0.15); }
            """)
        else:
            self._thumb.setIcon(QIcon())
            self._thumb.setText("👹")
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
        logger.info("Editor: imagem selecionada para mob %s: %s", self._mob_id, path)

    def set_category_options(self, categories: list[dict]):
        """Repopulates the Categoria combo from the live category folder
        tree (MobsPanel._reload_categories) — indented by depth so the
        hierarchy still reads even as a flat dropdown list. Called on
        every reload and every category CRUD, mirroring
        MobsPanel._refresh_category_filter_combo's own tree-walk."""
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
                self._category_combo.addItem(f"{prefix}{c.get('icon') or '📁'} {c['name']}", c["id"])
                add_level(c["id"], depth + 1)

        add_level(None, 0)
        idx = self._category_combo.findData(current)
        self._category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._category_combo.blockSignals(False)

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
