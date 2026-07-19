"""RegionCategorySection — collapsible group of RegionCards under one zone
category (Residencial/Comercial/... or a custom one).

A new lightweight class rather than reusing assets/card.py's CategorySection
— that one is tightly bound to filesystem folders (mkdir/rglob on a Path)
and carries asset/sound-specific extra headers. Only its collapse/arrow
header mechanics are mirrored here, not its content-population logic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.layouts.panels.region.region_card import RegionCard


class RegionCategorySection(QFrame):
    """Collapsible header + list of RegionCards for one zone category."""

    add_requested = Signal(str)        # category_key
    delete_requested = Signal(object)  # self
    card_selected = Signal(str)
    card_deleted = Signal(str)
    card_renamed = Signal(str, str)
    card_locate_requested = Signal(str)
    card_stars_changed = Signal(str, int)

    def __init__(self, category_key: str, icon: str, label: str, color: QColor, parent=None):
        super().__init__(parent)
        self.category_key = category_key
        self.label = label
        self.color = color
        self._expanded = True
        self._cards: dict[str, RegionCard] = {}
        self.setStyleSheet("background: transparent;")

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.02); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        self._header.mousePressEvent = lambda e: self._toggle()

        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(4)

        self._arrow = QLabel("▼")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px; background: transparent; border: none;")
        h_lay.addWidget(self._arrow)

        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background: {color.name()}; border-radius: 2px; border: 1px solid rgba(255,255,255,0.2);")
        h_lay.addWidget(swatch)

        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        h_lay.addWidget(ic)

        self._title_label = QLabel(label)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        h_lay.addWidget(self._title_label)

        self._count_lbl = QLabel("(0)")
        self._count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        h_lay.addWidget(self._count_lbl)
        h_lay.addStretch()

        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(18, 18)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Nova região nesta categoria")
        add_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; "
            f"color: {Colors.ACCENT}; font-size: 12px; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_btn.clicked.connect(lambda: self.add_requested.emit(self.category_key))
        h_lay.addWidget(add_btn)

        self._del_btn = QToolButton()
        self._del_btn.setText("🗑")
        self._del_btn.setFixedSize(18, 18)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setToolTip("Excluir categoria")
        self._del_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        h_lay.addWidget(self._del_btn)

        main.addWidget(self._header)

        # Content
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(8, 6, 8, 6)
        self._content_lay.setSpacing(4)
        main.addWidget(self._content)

        self._update_delete_visibility()

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")

    def add_card(self, region_id: str, name: str, color: QColor, stars: int = 0) -> RegionCard:
        card = RegionCard(region_id, name, color, stars)
        card.selected.connect(self.card_selected.emit)
        card.deleted.connect(self.card_deleted.emit)
        card.renamed.connect(self.card_renamed.emit)
        card.locate_requested.connect(self.card_locate_requested.emit)
        card.stars_changed.connect(self.card_stars_changed.emit)
        self._content_lay.addWidget(card)
        self._cards[region_id] = card
        self._update_count()
        return card

    def remove_card(self, region_id: str):
        card = self._cards.pop(region_id, None)
        if card:
            self._content_lay.removeWidget(card)
            card.deleteLater()
            self._update_count()

    def get_card(self, region_id: str) -> RegionCard | None:
        return self._cards.get(region_id)

    def all_cards(self):
        return list(self._cards.values())

    def card_count(self) -> int:
        return len(self._cards)

    def rename(self, new_label: str):
        self.label = new_label
        self._title_label.setText(new_label)

    def _update_count(self):
        self._count_lbl.setText(f"({len(self._cards)})")
        self._update_delete_visibility()

    def _update_delete_visibility(self):
        self._del_btn.setVisible(len(self._cards) == 0)
