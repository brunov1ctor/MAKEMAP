"""Region Settings Panel — CRUD of zone cards grouped by (customizable)
category, Cities-Skylines-style. Mirrors TerrainSettingsPanel's shell.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QWidget, QScrollArea, QLineEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.region.category_section import RegionCategorySection
from src.engines.map.zones import ZONE_TYPES


class RegionSettingsPanel(QFrame):
    """Side panel for Região (zone) CRUD, cards grouped by category."""

    PANEL_WIDTH = 300

    # Palette for auto-colored custom categories — translucent (alpha 90)
    # to match ZONE_TYPES' built-in colors; not TerrainSettingsPanel's
    # opaque _PALETTE, which isn't right for a ground-tint fill.
    _CUSTOM_PALETTE = [
        QColor(230, 120, 170, 90), QColor(120, 200, 220, 90), QColor(200, 150, 90, 90),
        QColor(160, 210, 90, 90), QColor(210, 90, 90, 90), QColor(150, 150, 220, 90),
        QColor(90, 180, 160, 90), QColor(220, 170, 60, 90),
    ]

    region_add_requested = Signal(str)      # category_key
    region_renamed = Signal(str, str)       # region_id, new_name
    region_removed = Signal(str)            # region_id
    region_selected = Signal(str)           # region_id
    region_locate_requested = Signal(str)   # region_id
    region_stars_changed = Signal(str, int)
    close_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._categories: dict[str, dict] = {}   # key -> {"label","color","section"}
        self._card_index: dict[str, str] = {}    # region_id -> category_key
        self._selected_id = ""
        self._custom_color_idx = 0
        self._new_category_row = None
        self._notice_row = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("🏙")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Região")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        add_cat_btn = QToolButton()
        add_cat_btn.setText("+ Categoria")
        add_cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_cat_btn.setStyleSheet(f"""
            QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; padding: 3px 8px;
                color: {Colors.ACCENT}; font-size: 10px; font-weight: bold; border-radius: 4px; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        add_cat_btn.clicked.connect(self._add_category)
        header.addWidget(add_cat_btn)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        layout.addWidget(self._sep())

        # ─── Category sections ───
        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(6)
        layout.addLayout(self._list_layout)
        self._list_layout.addStretch()

        for key, icon_ch, label, color in ZONE_TYPES:
            self._create_category_section(key, icon_ch, label, color)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    # ─── Category management ───

    def _create_category_section(self, key: str, icon: str, label: str, color: QColor) -> dict:
        section = RegionCategorySection(key, icon, label, color)
        section.add_requested.connect(self.region_add_requested.emit)
        section.delete_requested.connect(self._on_delete_category)
        section.card_selected.connect(self._on_card_selected)
        section.card_deleted.connect(self._on_card_deleted)
        section.card_renamed.connect(self.region_renamed.emit)
        section.card_locate_requested.connect(self.region_locate_requested.emit)
        section.card_stars_changed.connect(self.region_stars_changed.emit)
        self._list_layout.insertWidget(self._list_layout.count() - 1, section)
        entry = {"label": label, "color": color, "section": section}
        self._categories[key] = entry
        self.content_changed.emit()
        return entry

    def _next_custom_color(self) -> QColor:
        color = self._CUSTOM_PALETTE[self._custom_color_idx % len(self._CUSTOM_PALETTE)]
        self._custom_color_idx += 1
        return color

    def _add_category(self):
        """Inline dashed-row creation, no native dialog — same pattern as
        AssetSoundManager._add_category/_add_style (assets/panel.py)."""
        if self._new_category_row is not None:
            self._new_category_row.findChild(QLineEdit).setFocus()
            return

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.03); border: 1px dashed {Colors.ACCENT};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("Nome da categoria...")
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        row_lay.addWidget(edit, 1)

        confirm_btn = QToolButton()
        confirm_btn.setText("✓")
        confirm_btn.setFixedSize(22, 22)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        row_lay.addWidget(confirm_btn)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        row_lay.addWidget(cancel_btn)

        confirm_btn.clicked.connect(lambda: self._confirm_new_category(edit.text()))
        cancel_btn.clicked.connect(self._close_new_category_row)
        edit.returnPressed.connect(lambda: self._confirm_new_category(edit.text()))

        self._list_layout.insertWidget(0, row)
        self._new_category_row = row
        edit.setFocus()

    def _close_new_category_row(self):
        if self._new_category_row is not None:
            self._list_layout.removeWidget(self._new_category_row)
            self._new_category_row.deleteLater()
            self._new_category_row = None

    def _confirm_new_category(self, name: str):
        name = name.strip()
        self._close_new_category_row()
        if not name:
            return
        key = name.lower().replace(" ", "_")
        if key in self._categories:
            self._show_inline_notice(f"A categoria '{name}' já existe.")
            return
        self._create_category_section(key, "📁", name, self._next_custom_color())

    def _on_delete_category(self, section: RegionCategorySection):
        if section.card_count() > 0:
            self._show_inline_notice(
                f"A categoria '{section.label}' possui {section.card_count()} região(ões). "
                "Remova-as antes de excluir a categoria."
            )
            return
        key = section.category_key
        self._list_layout.removeWidget(section)
        section.deleteLater()
        self._categories.pop(key, None)
        self.content_changed.emit()

    def _close_inline_notice(self):
        if self._notice_row is not None:
            self._list_layout.removeWidget(self._notice_row)
            self._notice_row.deleteLater()
            self._notice_row = None

    def _show_inline_notice(self, message: str, on_confirm=None):
        self._close_inline_notice()
        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(239,83,80,0.10); border: 1px solid {Colors.ERROR};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 8, 8, 8)
        row_lay.setSpacing(8)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; border: none;")
        row_lay.addWidget(lbl, 1)

        if on_confirm:
            confirm_btn = QToolButton()
            confirm_btn.setText("Excluir")
            confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            confirm_btn.setStyleSheet(f"""
                QToolButton {{ border: none; border-radius: 4px; padding: 3px 10px; font-size: 9pt;
                    color: white; background: {Colors.ERROR}; }}
                QToolButton:hover {{ background: #ff6b66; }}
            """)
            def _confirm():
                self._close_inline_notice()
                on_confirm()
            confirm_btn.clicked.connect(_confirm)
            row_lay.addWidget(confirm_btn)

        dismiss_btn = QToolButton()
        dismiss_btn.setText("Cancelar" if on_confirm else "✕")
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; padding: 3px 8px; font-size: 9pt;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.08); }}
        """)
        dismiss_btn.clicked.connect(self._close_inline_notice)
        row_lay.addWidget(dismiss_btn)

        self._list_layout.insertWidget(0, row)
        self._notice_row = row

    # ─── Public API (called by RegionMediator once a polygon is finalized) ───

    def add_region_card(self, region_id: str, name: str, category_key: str, stars: int = 0,
                         category_label: str | None = None, category_color: QColor | None = None):
        entry = self._categories.get(category_key)
        if entry is None:
            # Category vanished (deleted) between "+ Novo" and the polygon
            # being finalized — re-create it from the mediator's snapshot
            # so the finished zone still has a home instead of being lost.
            color = category_color or self._next_custom_color()
            entry = self._create_category_section(
                category_key, "📁", category_label or category_key.capitalize(), color
            )
        entry["section"].add_card(region_id, name, entry["color"], stars)
        self._card_index[region_id] = category_key

    def category_info(self, category_key: str) -> tuple[str, QColor] | None:
        entry = self._categories.get(category_key)
        return (entry["label"], entry["color"]) if entry else None

    def category_count(self, category_key: str) -> int:
        entry = self._categories.get(category_key)
        return entry["section"].card_count() if entry else 0

    # ─── Card signal handlers ───

    def _on_card_selected(self, region_id: str):
        self._selected_id = region_id
        for entry in self._categories.values():
            for card in entry["section"].all_cards():
                card.set_selected(card.region_id == region_id)
        self.region_selected.emit(region_id)

    def _on_card_deleted(self, region_id: str):
        category_key = self._card_index.pop(region_id, None)
        entry = self._categories.get(category_key) if category_key else None
        if entry:
            entry["section"].remove_card(region_id)
        if self._selected_id == region_id:
            self._selected_id = ""
        self.region_removed.emit(region_id)

    def paintEvent(self, event):
        paint_glass_panel(self)
