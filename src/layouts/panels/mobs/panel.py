"""MobsPanel — fullscreen module screen: stat bar, category sidebar,
filterable card grid, and a detail/edit panel on the right.

Fed directly by UnitOfWork.mobs (no extra mediator layer, unlike
Região/Terrain which sit on top of live canvas objects) — a mob here is
just a database row, so this panel talks to the repository straight away
and re-renders its in-memory `_mobs` cache after every change.
"""

from __future__ import annotations

import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QToolButton, QPushButton, QFrame, QScrollArea, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.mobs.categories import (
    CATEGORY_DEFS, SMART_FILTERS, RARITY_DEFS, ELEMENT_OPTIONS,
    category_label, rarity_label, rarity_color,
)
from src.layouts.panels.mobs.mob_card import MobCard
from src.layouts.panels.mobs.mob_edit_panel import MobEditPanel
from src.layouts.panels.mobs.donut_chart import DonutChart

logger = logging.getLogger("MAKEMAP")

_LEVEL_BANDS = [
    (1, 10, "1-10"), (11, 20, "11-20"), (21, 30, "21-30"),
    (31, 40, "31-40"), (41, 50, "41-50"), (51, 9999, "51+"),
]
_SORT_OPTIONS = [
    ("name_asc", "Nome (A-Z)"), ("name_desc", "Nome (Z-A)"),
    ("level_asc", "Nível (crescente)"), ("level_desc", "Nível (decrescente)"),
    ("tier_desc", "Tier (maior primeiro)"),
]


def _stat_chip(icon: str, value: str, label: str) -> QFrame:
    chip = QFrame()
    chip.setStyleSheet(f"""
        QFrame {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
    """)
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(6)
    icon_lbl = QLabel(icon)
    icon_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
    lay.addWidget(icon_lbl)
    col = QVBoxLayout()
    col.setSpacing(0)
    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
    label_lbl = QLabel(label)
    label_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
    col.addWidget(value_lbl)
    col.addWidget(label_lbl)
    lay.addLayout(col)
    chip._value_label = value_lbl
    return chip


class _SidebarRow(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        self._label = QLabel(label)
        self._label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(self._label, 1)
        self._count = QLabel("0")
        self._count.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        lay.addWidget(self._count)
        self._refresh_style()

    def set_count(self, n: int):
        self._count.setText(str(n))

    def set_selected(self, sel: bool):
        self._selected = sel
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"QFrame {{ background: {Colors.ACCENT_DIM}; border-radius: 6px; }}")
            self._label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        else:
            self.setStyleSheet("QFrame { background: transparent; border-radius: 6px; }"
                                "QFrame:hover { background: rgba(255,255,255,0.06); }")
            self._label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class MobsPanel(QWidget):
    """Fullscreen Mobs module — replaces the empty-state placeholder."""

    closed = Signal()

    def __init__(self, uow, zones_provider=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._zones_provider = zones_provider or (lambda: [])
        self._mobs: list[dict] = []
        self._sidebar_rows: dict[str, _SidebarRow] = {}
        self._active_filter = "todos"
        self._selected_id = ""
        self._custom_categories: dict[str, str] = {}
        self._ui_ready = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._build_ui()
        self._ui_ready = True
        self._reload()

    # ─── UI construction ───

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 16)
        outer.setSpacing(8)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("👹")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("MOBS")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Gerencie todas as criaturas e inimigos do seu mundo.")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        new_btn = QPushButton("+ Novo Mob")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 8px 14px; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self._on_new_mob)
        header.addWidget(new_btn)

        def _secondary_btn(text: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 6px; padding: 8px 14px; font-size: 11px; font-weight: bold; }}
                QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
            """)
            return btn

        import_btn = _secondary_btn("📥 Importar")
        import_btn.clicked.connect(self._on_import)
        header.addWidget(import_btn)

        export_btn = _secondary_btn("📤 Exportar")
        export_btn.clicked.connect(self._on_export)
        header.addWidget(export_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none; font-size: 14px; border-radius: 14px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        # ── Stat chips ──
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(8)
        self._stat_chips: dict[str, QFrame] = {}
        for key, icon_c, label in [
            ("total", "📊", "Total de Mobs"), ("boss", "👑", "Chefes (Boss)"),
            ("elite", "💠", "Elite"), ("normal", "🔰", "Normais"),
            ("elements", "🌪", "Elementos diferentes"), ("drops", "🎁", "Drops cadastrados"),
            ("zones", "🗺", "Regiões utilizadas"),
        ]:
            chip = _stat_chip(icon_c, "0", label)
            self._stat_chips[key] = chip
            self._stats_row.addWidget(chip)
        self._stats_row.addStretch()
        outer.addLayout(self._stats_row)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        outer.addWidget(sep)

        # ── Body: sidebar | center | edit panel ──
        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_left_column())
        body.addLayout(self._build_center(), 1)
        self._edit_panel = MobEditPanel()
        self._edit_panel.setFixedWidth(MobEditPanel.PANEL_WIDTH)
        self._edit_panel.save_requested.connect(self._on_save)
        self._edit_panel.cancel_requested.connect(self._on_cancel_edit)
        self._edit_panel.duplicate_requested.connect(self._on_duplicate)
        self._edit_panel.delete_requested.connect(self._on_delete)
        self._edit_panel.test_requested.connect(self._on_test)
        self._edit_panel.generate_loot_requested.connect(self._on_generate_loot)
        self._edit_panel.locate_requested.connect(self._on_locate)
        body.addWidget(self._edit_panel)
        outer.addLayout(body, 1)

    def _build_left_column(self) -> QWidget:
        """Categories and Resumo Rápido as two independent, visibly
        separate cards stacked in the left column — NOT one nested inside
        the other, which used to make Resumo Rápido read as part of the
        same panel as the category list."""
        container = QWidget()
        container.setFixedWidth(190)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(self._build_sidebar(), 1)
        outer.addWidget(self._build_summary_card())
        return container

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.03); border-radius: 8px; }}")
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        cat_title = QLabel("CATEGORIAS")
        cat_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        title_row.addWidget(cat_title)
        title_row.addStretch()
        new_cat_btn = QPushButton("+ Nova categoria")
        new_cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_cat_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.ACCENT}; border: none; font-size: 9px; font-weight: bold; padding: 0; }}
            QPushButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        new_cat_btn.clicked.connect(self._on_new_category)
        title_row.addWidget(new_cat_btn)
        lay.addLayout(title_row)

        self._category_search = QLineEdit()
        self._category_search.setPlaceholderText("🔍 Buscar categoria...")
        self._category_search.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
        """)
        self._category_search.textChanged.connect(self._filter_sidebar_rows)
        lay.addWidget(self._category_search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                              "QScrollArea > QWidget > QWidget { background: transparent; }")
        rows_widget = QWidget()
        rows_lay = QVBoxLayout(rows_widget)
        rows_lay.setContentsMargins(0, 0, 0, 0)
        rows_lay.setSpacing(2)

        for key, icon_c, label in SMART_FILTERS:
            row = _SidebarRow(key, icon_c, label)
            row.clicked.connect(self._on_filter_selected)
            self._sidebar_rows[key] = row
            rows_lay.addWidget(row)

        cat_sep = QFrame()
        cat_sep.setFixedHeight(1)
        cat_sep.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        rows_lay.addWidget(cat_sep)

        for key, icon_c, label in CATEGORY_DEFS:
            row = _SidebarRow(key, icon_c, label)
            row.clicked.connect(self._on_filter_selected)
            self._sidebar_rows[key] = row
            rows_lay.addWidget(row)

        self._custom_cat_sep = QFrame()
        self._custom_cat_sep.setFixedHeight(1)
        self._custom_cat_sep.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        self._custom_cat_sep.setVisible(False)
        rows_lay.addWidget(self._custom_cat_sep)

        self._rows_layout = rows_lay
        rows_lay.addStretch()
        scroll.setWidget(rows_widget)
        lay.addWidget(scroll, 1)

        self._sidebar_rows["todos"].set_selected(True)
        return sidebar

    def _build_summary_card(self) -> QFrame:
        """"Resumo Rápido" — its own independent bordered card, a sibling
        of the category list (not nested inside it)."""
        summary_card = QFrame()
        summary_card.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        summary_lay = QVBoxLayout(summary_card)
        summary_lay.setContentsMargins(10, 8, 10, 8)
        summary_lay.setSpacing(6)

        summary_label = QLabel("RESUMO RÁPIDO")
        summary_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        summary_lay.addWidget(summary_label)

        self._donut = DonutChart()
        donut_row = QHBoxLayout()
        donut_row.addStretch()
        donut_row.addWidget(self._donut)
        donut_row.addStretch()
        summary_lay.addLayout(donut_row)

        self._summary_grid = QGridLayout()
        self._summary_grid.setSpacing(4)
        summary_lay.addLayout(self._summary_grid)
        return summary_card

    def _labeled_combo(self, icon: str, caption: str) -> QComboBox:
        """A small "ICON CAPTION" label stacked above a combo box — matches
        the Tier/Região/Elemento/Tipo/Nível filter columns in the mock."""
        combo = QComboBox()
        combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; min-width: 84px; }}
            QComboBox QAbstractItemView {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_DIM}; }}
        """)
        combo.currentIndexChanged.connect(lambda _i: self._apply_filters())
        combo._caption_widget = QLabel(f"{icon} {caption}")
        combo._caption_widget.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        return combo

    def _build_center(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        # ── Row 1: search + Tier/Região/Elemento/Tipo/Nível ──
        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Pesquisar mobs...")
        self._search_edit.textChanged.connect(self._apply_filters)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 6px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 11px; }}
        """)
        filters.addWidget(self._search_edit, 1)

        self._tier_combo = self._labeled_combo("🛡", "Tier")
        self._tier_combo.addItem("Todos", "")
        for t in range(1, 11):
            self._tier_combo.addItem(str(t), t)

        self._region_combo = self._labeled_combo("🗺", "Região")
        self._region_combo.addItem("Todas", "")

        self._element_combo = self._labeled_combo("🌪", "Elemento")
        self._element_combo.addItem("Todos", "")
        for el in ELEMENT_OPTIONS:
            if el:
                self._element_combo.addItem(el, el)

        self._category_filter_combo = self._labeled_combo("🏷", "Tipo")
        self._category_filter_combo.addItem("Todos", "")
        for key, _icon, label in CATEGORY_DEFS:
            self._category_filter_combo.addItem(label, key)

        self._level_combo = self._labeled_combo("⭐", "Nível")
        self._level_combo.addItem("Todos", "")
        for lo, hi, band_label in _LEVEL_BANDS:
            self._level_combo.addItem(band_label, (lo, hi))

        for combo in (self._tier_combo, self._region_combo, self._element_combo,
                      self._category_filter_combo, self._level_combo):
            col_box = QVBoxLayout()
            col_box.setSpacing(2)
            col_box.addWidget(combo._caption_widget)
            col_box.addWidget(combo)
            filters.addLayout(col_box)
        col.addLayout(filters)

        # ── Row 2: Ordenar por + Grade/Lista toggle ──
        sort_row = QHBoxLayout()
        sort_row.setSpacing(8)
        sort_col = QVBoxLayout()
        sort_col.setSpacing(2)
        sort_caption = QLabel("Ordenar por")
        sort_caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        self._sort_combo = QComboBox()
        self._sort_combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 10px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; min-width: 130px; }}
            QComboBox QAbstractItemView {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_DIM}; }}
        """)
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

        # Grade and Lista each keep their own persistent QScrollArea — a
        # QStackedWidget just swaps which is *visible*, so toggling views
        # never hands a live widget to Qt's ownership-transferring
        # QScrollArea.setWidget() (which deletes whatever was set before).
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

    # ─── Data loading ───

    def _reload(self):
        self._mobs = self._uow.mobs.get_all() if self._uow else []
        self._region_combo.blockSignals(True)
        current = self._region_combo.currentData()
        self._region_combo.clear()
        self._region_combo.addItem("Todas as Regiões", "")
        for zid, name in self._zones_provider():
            self._region_combo.addItem(name, zid)
        idx = self._region_combo.findData(current)
        self._region_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._region_combo.blockSignals(False)
        self._edit_panel.set_zone_options(self._zones_provider())
        self._recompute_stats()
        self._apply_filters()

    def _recompute_stats(self):
        total = len(self._mobs)
        boss = sum(1 for m in self._mobs if m.get("rarity") == "boss")
        elite = sum(1 for m in self._mobs if m.get("rarity") == "elite")
        normal = total - boss - elite
        elements = len({m.get("element") for m in self._mobs if m.get("element")})
        drops = 0
        for m in self._mobs:
            import json
            try:
                drops += len(json.loads(m.get("drops_json") or "[]"))
            except (ValueError, TypeError):
                pass
        zones_used = len({m.get("zone_id") for m in self._mobs if m.get("zone_id")})

        values = {"total": total, "boss": boss, "elite": elite, "normal": normal,
                  "elements": elements, "drops": drops, "zones": zones_used}
        for key, chip in self._stat_chips.items():
            chip._value_label.setText(f"{values.get(key, 0):,}".replace(",", "."))

        for key, row in self._sidebar_rows.items():
            if key == "todos":
                row.set_count(total)
            elif key == "favoritos":
                row.set_count(sum(1 for m in self._mobs if m.get("favorite")))
            elif key == "chefes":
                row.set_count(boss)
            elif key == "elite":
                row.set_count(elite)
            else:
                row.set_count(sum(1 for m in self._mobs if m.get("category") == key))

        # Resumo rápido — donut + 2-column legend, counts by rarity
        counts = {key: sum(1 for m in self._mobs if m.get("rarity") == key) for key, _c, _l in RARITY_DEFS}
        self._donut.set_data([(counts[key], color) for key, color, _l in RARITY_DEFS], total)

        while self._summary_grid.count():
            item = self._summary_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (key, color, label) in enumerate(RARITY_DEFS):
            count = counts[key]
            pct = 100 * count / total if total else 0
            pct_text = f"{pct:.0f}%" if pct >= 1 or pct == 0 else "+1%"

            row = QHBoxLayout()
            row.setSpacing(4)
            square = QLabel()
            square.setFixedSize(8, 8)
            square.setStyleSheet(f"background: {color}; border-radius: 2px;")
            row.addWidget(square)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 8px; background: transparent; border: none;")
            row.addWidget(lbl, 1)
            pct_lbl = QLabel(pct_text)
            pct_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
            row.addWidget(pct_lbl)

            cell = QWidget()
            cell.setLayout(row)
            self._summary_grid.addWidget(cell, i // 2, i % 2)

    # ─── Filtering ───

    def _filter_sidebar_rows(self, text: str):
        text = text.strip().lower()
        for key, row in self._sidebar_rows.items():
            if key in ("todos", "favoritos", "chefes", "elite"):
                continue
            row.setVisible(text in row._label.text().lower())

    def _on_filter_selected(self, key: str):
        self._active_filter = key
        for k, row in self._sidebar_rows.items():
            row.set_selected(k == key)
        self._apply_filters()

    def _on_new_category(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nova Categoria", "Nome da categoria:")
        name = name.strip()
        if not ok or not name:
            return
        key = name.lower().replace(" ", "_")
        if key in self._sidebar_rows:
            return
        self._custom_categories[key] = name
        self._custom_cat_sep.setVisible(True)
        row = _SidebarRow(key, "📌", name)
        row.clicked.connect(self._on_filter_selected)
        self._sidebar_rows[key] = row
        idx = self._rows_layout.indexOf(self._custom_cat_sep) + 1
        self._rows_layout.insertWidget(idx, row)
        self._edit_panel.add_custom_category(key, name)
        self._category_filter_combo.addItem(name, key)

    def _apply_filters(self):
        if not self._ui_ready:
            return
        search = self._search_edit.text().strip().lower()
        tier = self._tier_combo.currentData() or ""
        region_id = self._region_combo.currentData() or ""
        element = self._element_combo.currentData() or ""
        category = self._category_filter_combo.currentData() or ""
        level_band = self._level_combo.currentData() or None

        def matches(m: dict) -> bool:
            if self._active_filter == "favoritos" and not m.get("favorite"):
                return False
            elif self._active_filter == "chefes" and m.get("rarity") != "boss":
                return False
            elif self._active_filter == "elite" and m.get("rarity") != "elite":
                return False
            elif self._active_filter not in ("todos", "favoritos", "chefes", "elite") and m.get("category") != self._active_filter:
                return False
            if search and search not in (m.get("name") or "").lower():
                return False
            if tier and int(m.get("tier", 1) or 1) != tier:
                return False
            if region_id and m.get("zone_id") != region_id:
                return False
            if element and m.get("element") != element:
                return False
            if category and m.get("category") != category:
                return False
            if level_band:
                lo, hi = level_band
                if not (lo <= int(m.get("level", 1) or 1) <= hi):
                    return False
            return True

        filtered = [m for m in self._mobs if matches(m)]
        sort_key = self._sort_combo.currentData() or "name_asc"
        if sort_key == "name_asc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower())
        elif sort_key == "name_desc":
            filtered.sort(key=lambda m: (m.get("name") or "").lower(), reverse=True)
        elif sort_key == "level_asc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1))
        elif sort_key == "level_desc":
            filtered.sort(key=lambda m: int(m.get("level", 1) or 1), reverse=True)
        elif sort_key == "tier_desc":
            filtered.sort(key=lambda m: int(m.get("tier", 1) or 1), reverse=True)

        self._result_label.setText(f"Mostrando {len(filtered)} de {len(self._mobs)} mobs")
        self._rebuild_grid(filtered)

    def _rebuild_grid(self, mobs: list[dict]):
        # hide() immediately, on top of deleteLater() — deleteLater() only
        # schedules destruction for whenever the event loop next processes
        # deferred deletes (which, under rapid-fire rebuilds like typing in
        # the search box, can lag behind), so an un-hidden old card would
        # keep rendering at its stale position, overlapping the freshly
        # laid out ones.
        for layout in (self._grid_layout, self._list_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()

        zones = dict(self._zones_provider())
        target = self._grid_layout if self._view_mode == "grade" else self._list_layout
        for m in mobs:
            if self._view_mode == "grade":
                card = MobCard(m["id"])
                card.set_data(
                    m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
                    m.get("rarity", "normal"), m.get("element", ""), zones.get(m.get("zone_id", ""), ""),
                    bool(m.get("favorite", 0)),
                )
            else:
                card = self._build_list_row(m, zones)
            card.set_selected(m["id"] == self._selected_id)
            card.selected.connect(self._on_card_selected)
            card.favorite_toggled.connect(self._on_favorite_toggled)
            card.duplicate_requested.connect(self._on_duplicate)
            card.delete_requested.connect(self._on_delete)
            target.addWidget(card)
            # A freshly reparented widget doesn't reliably report
            # isVisible()==True the instant addWidget() returns — Qt shows
            # it implicitly, but not necessarily before the synchronous
            # activate() call below runs. FlowLayout._do_layout skips
            # anything not (yet) visible, so without this explicit show()
            # the most-recently-added card could be left at Qt's default
            # (0,0) geometry, overlapping everything else.
            card.show()
        if self._view_mode == "lista":
            self._list_layout.addStretch()

        # FlowLayout.addItem() (unlike built-in layouts) never calls
        # invalidate() itself, so newly added cards can sit un-positioned —
        # stacked at whatever default geometry Qt gives a freshly-parented
        # widget — until something unrelated happens to trigger a relayout.
        # Force it now instead of leaving it to chance.
        self._grid_layout.invalidate()
        self._grid_layout.activate()

    def _build_list_row(self, m: dict, zones: dict) -> MobCard:
        """Reuses MobCard's signals/behavior but a full-width horizontal
        layout instead of the fixed-size grid tile — the "Lista" view."""
        from src.layouts.panels.mobs.mob_card import MobListRow
        row = MobListRow(m["id"])
        row.set_data(
            m.get("name", ""), int(m.get("level", 1) or 1), m.get("category", "outros"),
            m.get("rarity", "normal"), m.get("element", ""), zones.get(m.get("zone_id", ""), ""),
            bool(m.get("favorite", 0)),
        )
        return row

    # ─── Card / edit-panel interactions ───

    def _mob_by_id(self, mob_id: str) -> dict | None:
        return next((m for m in self._mobs if m["id"] == mob_id), None)

    def _on_card_selected(self, mob_id: str):
        self._selected_id = mob_id
        for layout in (self._grid_layout, self._list_layout):
            for i in range(layout.count()):
                w = layout.itemAt(i).widget()
                if w is not None and hasattr(w, "mob_id"):
                    w.set_selected(w.mob_id == mob_id)
        mob = self._mob_by_id(mob_id)
        if mob:
            self._edit_panel.load(mob)

    def _on_export(self):
        import json
        from PySide6.QtWidgets import QFileDialog
        path, _filter = QFileDialog.getSaveFileName(self, "Exportar Mobs", "mobs.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._mobs, f, ensure_ascii=False, indent=2)
        logger.info("Exportados %d mobs para %s", len(self._mobs), path)

    def _on_import(self):
        import json
        from PySide6.QtWidgets import QFileDialog
        path, _filter = QFileDialog.getOpenFileName(self, "Importar Mobs", "", "JSON (*.json)")
        if not path or not self._uow:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning("Arquivo de importação inválido: esperada uma lista de mobs.")
            return
        known_columns = set(self._mobs[0].keys()) if self._mobs else None
        imported = 0
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            fields = {k: v for k, v in entry.items()
                      if k not in ("id", "created_at", "updated_at") and (known_columns is None or k in known_columns)}
            self._uow.mobs.create(**fields)
            imported += 1
        logger.info("Importados %d mobs de %s", imported, path)
        self._reload()

    def _on_new_mob(self):
        if not self._uow:
            return
        mob_id = str(uuid.uuid4())
        name = f"Novo Mob {len(self._mobs) + 1}"
        self._uow.mobs.create(id=mob_id, name=name)
        self._reload()
        self._on_card_selected(mob_id)

    def _on_save(self, values: dict):
        if not self._uow or not values.get("id"):
            return
        mob_id = values.pop("id")
        self._uow.mobs.update(mob_id, **values)
        self._selected_id = mob_id
        self._reload()
        self._on_card_selected(mob_id)

    def _on_cancel_edit(self):
        self._selected_id = ""
        self._edit_panel.set_empty(True)
        self._apply_filters()

    def _on_duplicate(self, mob_id: str):
        mob = self._mob_by_id(mob_id)
        if not mob or not self._uow:
            return
        new_mob = dict(mob)
        new_mob.pop("id", None)
        new_mob.pop("created_at", None)
        new_mob.pop("updated_at", None)
        new_mob["name"] = f"{mob.get('name', 'Mob')} (Cópia)"
        new_id = self._uow.mobs.create(**new_mob)
        self._reload()
        self._on_card_selected(new_id)

    def _on_delete(self, mob_id: str):
        if not self._uow:
            return
        self._uow.mobs.delete(mob_id)
        if self._selected_id == mob_id:
            self._selected_id = ""
            self._edit_panel.set_empty(True)
        self._reload()

    def _on_favorite_toggled(self, mob_id: str, favorite: bool):
        if self._uow:
            self._uow.mobs.update(mob_id, favorite=int(favorite))
        for m in self._mobs:
            if m["id"] == mob_id:
                m["favorite"] = int(favorite)
        self._recompute_stats()

    def _on_test(self, mob_id: str):
        mob = self._mob_by_id(mob_id)
        if mob:
            logger.info("Testando mob no jogo: %s", mob.get("name"))

    def _on_generate_loot(self, mob_id: str):
        import json
        mob = self._mob_by_id(mob_id)
        if not mob or not self._uow:
            return
        try:
            drops = json.loads(mob.get("drops_json") or "[]")
        except (ValueError, TypeError):
            drops = []
        drops.append({"name": f"Item Gerado {len(drops) + 1}", "rate": 10.0, "qty": 1})
        self._uow.mobs.update(mob_id, drops_json=json.dumps(drops))
        logger.info("Loot gerado para %s", mob.get("name"))
        self._reload()
        self._on_card_selected(mob_id)

    def _on_locate(self, mob_id: str):
        mob = self._mob_by_id(mob_id)
        if not mob:
            return
        if not mob.get("position_x") and not mob.get("position_y"):
            logger.info("Mob '%s' ainda não possui posição definida no mapa.", mob.get("name"))
            return
        self.closed.emit()

    # ─── Paint ───

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(14, 22, 42, 230))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.drawPath(path)
        p.end()
