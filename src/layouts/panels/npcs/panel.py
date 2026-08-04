"""NPCsPanel — fullscreen module screen: stat bar, category sidebar,
filterable card grid, and a detail/edit panel on the right.

Mirrors src/layouts/panels/mobs/panel.py exactly in structure — most of the
actual behavior lives in 5 mixins, one per concern area, each in its own
file:
- CategoryExplorerMixin (panel_category_mixin.py) — the CATEGORIAS sidebar
- GridFilterMixin (panel_grid_mixin.py) — center card grid + filters
- NPCDataMixin (panel_data_mixin.py) — data reload + Resumo Rápido stats
- ImportExportMixin (panel_import_export_mixin.py) — Importar/Exportar
- NPCCrudMixin (panel_crud_mixin.py) — create/save/duplicate/delete an npc
This file keeps only what's genuinely top-level: __init__, the overall
QSplitter layout assembly, and window-resize handling.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QPushButton,
    QFrame, QSizePolicy, QStackedWidget, QSplitter, QMenu,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.components.live_splitter import LiveSplitter
from src.layouts.panels.npcs.npc_edit_panel import NPCEditPanel
from src.layouts.panels.npcs.panel_helpers import _stat_chip
from src.layouts.panels.npcs.panel_category_mixin import CategoryExplorerMixin
from src.layouts.panels.npcs.panel_grid_mixin import GridFilterMixin
from src.layouts.panels.npcs.panel_data_mixin import NPCDataMixin
from src.layouts.panels.npcs.panel_import_export_mixin import ImportExportMixin
from src.layouts.panels.npcs.panel_crud_mixin import NPCCrudMixin

logger = logging.getLogger("MAKEMAP")


class NPCsPanel(
    CategoryExplorerMixin, GridFilterMixin, NPCDataMixin,
    ImportExportMixin, NPCCrudMixin, QWidget,
):
    """Fullscreen NPCs module — replaces the empty-state placeholder."""

    closed = Signal()
    item_open_requested = Signal(str)  # item_id — bubbled from NPCEditPanel tile click

    # See MobsPanel's own docstring for the reasoning behind these — the
    # same tuned ratio/floor/ceiling applies here unchanged.
    _LEFT_RATIO = 0.15
    _LEFT_MIN_W = 264
    _LEFT_MAX_W = 320

    def __init__(self, uow, zones_provider=None, zone_thumbnail_provider=None, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._zones_provider = zones_provider or (lambda: [])
        self._zone_thumbnail_provider = zone_thumbnail_provider or (lambda _zone_id, size=24: None)
        self._npcs: list[dict] = []
        self._selected_id = ""
        self._current_dir_id: str | None = None
        self._nav_history: list[str | None] = [None]
        self._nav_index = 0
        self._ui_ready = False
        self._splitter_user_adjusted = False
        self._auto_splitter_positions: dict[int, int] = {}
        self._all_categories: list[dict] = []
        self._tools_mode: str | None = None
        self._template_fmt: str | None = None
        self._staged_image_folder: str | None = None
        self._staged_image_files: dict[str, str] = {}
        self._staged_asset_folder: str | None = None
        self._staged_asset_files: dict[str, str] = {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._build_ui()
        self._ui_ready = True
        self._reload()
        self._apply_responsive_layout()
        self._on_new_npc()

    # ─── UI construction ───

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 16)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("🧙")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("NPCS")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Gerencie todos os personagens não-jogáveis do seu mundo.")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        new_btn = QPushButton("+ Novo NPC")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 8px 14px; font-size: 11px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self._on_new_npc)
        header.addWidget(new_btn)

        def _menu_btn(text: str, items: list[tuple[str, str]], on_pick) -> QToolButton:
            btn = QToolButton()
            btn.setText(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            btn.setStyleSheet(f"""
                QToolButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 6px; padding: 8px 14px; font-size: 11px; font-weight: bold; }}
                QToolButton:hover {{ background: rgba(255,255,255,0.12); }}
                QToolButton::menu-indicator {{ subcontrol-position: right center; subcontrol-origin: padding; right: 6px; }}
            """)
            menu = QMenu(btn)
            menu.setStyleSheet(f"""
                QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; }}
                QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
            """)
            for fmt_key, label in items:
                menu.addAction(label, lambda k=fmt_key: on_pick(k))
            btn.setMenu(menu)
            return btn

        self._import_btn = QToolButton()
        self._import_btn.setText("📥 Importar")
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 8px 14px; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        self._import_btn.clicked.connect(self._toggle_import_mode)
        header.addWidget(self._import_btn)

        export_btn = _menu_btn("📤 Exportar", [
            ("json", "Exportar como JSON"), ("csv", "Exportar como CSV"), ("xlsx", "Exportar como Excel (.xlsx)"),
        ], self._on_export_choice)
        header.addWidget(export_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none; font-size: 14px; border-radius: 14px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(8)
        self._stat_chips: dict[str, QFrame] = {}
        for key, icon_c, label in [
            ("total", "📊", "Total de NPCs"), ("ativos", "✅", "Ativos"),
            ("inativos", "⛔", "Inativos"), ("tipos", "🎭", "Tipos diferentes"),
            ("faccoes", "🛡", "Facções diferentes"), ("favoritos", "⭐", "Favoritos"),
            ("zonas", "🗺", "Regiões utilizadas"),
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

        self._body_splitter = LiveSplitter(Qt.Orientation.Horizontal)
        self._body_splitter.setChildrenCollapsible(False)
        self._body_splitter.setHandleWidth(10)

        center_widget = QWidget()
        center_widget.setLayout(self._build_center())

        self._edit_panel = NPCEditPanel()
        self._edit_panel.save_requested.connect(self._on_save)
        self._edit_panel.rename_requested.connect(self._on_rename)
        self._edit_panel.delete_requested.connect(self._on_delete)
        self._edit_panel.asset_add_requested.connect(self._on_asset_add)
        self._edit_panel.asset_delete_requested.connect(self._on_asset_delete)
        self._edit_panel.item_open_requested.connect(self.item_open_requested.emit)

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._edit_panel)
        self._right_stack.addWidget(self._build_tools_panel())

        self._body_splitter.addWidget(self._build_left_column())
        self._body_splitter.addWidget(center_widget)
        self._body_splitter.addWidget(self._right_stack)
        self._body_splitter.setStretchFactor(0, 0)
        self._body_splitter.setStretchFactor(1, 1)
        self._body_splitter.setStretchFactor(2, 0)
        self._body_splitter.splitterMoved.connect(self._on_splitter_moved)
        outer.addWidget(self._body_splitter, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    _SPLITTER_NUDGE_THRESHOLD = 6

    def _on_splitter_moved(self, pos: int, index: int):
        expected = self._auto_splitter_positions.get(index)
        if expected is not None and abs(pos - expected) < self._SPLITTER_NUDGE_THRESHOLD:
            return
        self._splitter_user_adjusted = True

    def _apply_responsive_layout(self):
        total_w = self.width()
        if total_w <= 0 or not hasattr(self, "_left_container"):
            return
        if not self._splitter_user_adjusted:
            content_min_w = self._left_container.minimumSizeHint().width()
            ratio_w = round(total_w * self._LEFT_RATIO)
            left_w = max(content_min_w, min(self._LEFT_MAX_W, max(self._LEFT_MIN_W, ratio_w)))
            center_min_w = 220
            right_w = self._edit_panel.sizeHint().width()
            if total_w - left_w - right_w < center_min_w:
                right_w = max(self._edit_panel.minimumWidth(), total_w - left_w - center_min_w)
            center_w = max(1, total_w - left_w - right_w)
            sizes = [left_w, center_w, right_w]
            self._body_splitter.setSizes(sizes)
            actual = self._body_splitter.sizes()
            cumulative = 0
            self._auto_splitter_positions = {}
            for i in range(len(actual) - 1):
                cumulative += actual[i]
                self._auto_splitter_positions[i] = cumulative

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
