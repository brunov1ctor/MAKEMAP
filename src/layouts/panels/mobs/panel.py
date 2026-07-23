"""MobsPanel — fullscreen module screen: stat bar, category sidebar,
filterable card grid, and a detail/edit panel on the right.

Fed directly by UnitOfWork.mobs (no extra mediator layer, unlike
Região/Terrain which sit on top of live canvas objects) — a mob here is
just a database row, so this panel talks to the repository straight away
and re-renders its in-memory `_mobs` cache after every change.

This is the "shell" module for MobsPanel — most of the actual behavior
lives in 5 mixins, one per concern area, each in its own file:
- CategoryExplorerMixin (panel_category_mixin.py) — the CATEGORIAS sidebar
- GridFilterMixin (panel_grid_mixin.py) — center card grid + filters
- MobDataMixin (panel_data_mixin.py) — data reload + Resumo Rápido stats
- ImportExportMixin (panel_import_export_mixin.py) — Importar/Exportar
- MobCrudMixin (panel_crud_mixin.py) — create/save/duplicate/delete a mob
This file keeps only what's genuinely top-level: __init__, the overall
QSplitter layout assembly, and window-resize handling. See panel_widgets.py
for the standalone widget classes and panel_helpers.py for pure constants/
functions used across the mixins.
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
from src.layouts.panels.mobs.mob_edit_panel import MobEditPanel
from src.layouts.panels.mobs.panel_helpers import _stat_chip
from src.layouts.panels.mobs.panel_category_mixin import CategoryExplorerMixin
from src.layouts.panels.mobs.panel_grid_mixin import GridFilterMixin
from src.layouts.panels.mobs.panel_data_mixin import MobDataMixin
from src.layouts.panels.mobs.panel_import_export_mixin import ImportExportMixin
from src.layouts.panels.mobs.panel_crud_mixin import MobCrudMixin

logger = logging.getLogger("MAKEMAP")


class MobsPanel(
    CategoryExplorerMixin, GridFilterMixin, MobDataMixin,
    ImportExportMixin, MobCrudMixin, QWidget,
):
    """Fullscreen Mobs module — replaces the empty-state placeholder."""

    closed = Signal()

    # Left column / center grid / edit panel now live in a draggable
    # QSplitter (see _build_ui) instead of a plain QHBoxLayout, so the user
    # can resize the three by hand. _LEFT_RATIO/_MIN_W/_MAX_W below only
    # decide the *initial* left-column width (recomputed on every window
    # resize) — the moment the user drags a splitter handle
    # (_on_splitter_moved), that ratio-based sizing stops being applied so
    # a subsequent window resize doesn't silently override their choice.
    # Ratio is tuned to land close to the original fixed 190px at this
    # panel's typical ~1568px content width; min/max keep it usable at the
    # extremes. 264px is the real floor already — the "CATEGORIAS" label +
    # "+ Nova categoria" button share one row that can't compress past
    # their own text width (confirmed via minimumSizeHint()); MIN_W just
    # documents that intent; the actual clamp always defers to the live
    # minimumSizeHint() below in case that row's content changes later.
    #
    # The edit panel (right column) keeps its own floor — MobEditPanel's
    # minimumWidth stays PANEL_WIDTH (520px) because its fields were
    # hand-tuned to fit exactly that with nothing scrolling — the splitter
    # just refuses to drag it any narrower, same as it refuses to shrink
    # the left column below its own minimumSizeHint.
    _LEFT_RATIO = 0.15
    _LEFT_MIN_W = 264
    _LEFT_MAX_W = 320

    def __init__(self, uow, zones_provider=None, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._zones_provider = zones_provider or (lambda: [])
        self._mobs: list[dict] = []
        self._selected_id = ""
        # Category folder explorer state — mirrors a simple browser history
        # (list + index) so back/forward can revisit without recomputing
        # anything: None means the tree's root, non-None is a mob_categories.id.
        self._current_dir_id: str | None = None
        self._nav_history: list[str | None] = [None]
        self._nav_index = 0
        self._ui_ready = False
        self._splitter_user_adjusted = False  # set once the user drags a handle — see _on_splitter_moved
        self._auto_splitter_positions: dict[int, int] = {}  # expected handle positions from our own setSizes() — see _on_splitter_moved
        self._all_categories: list[dict] = []  # cached by _reload_categories — used by _recompute_stats for Resumo Rápido
        # None = showing the normal mob edit panel; "import" or
        # "export_json"/"export_csv" = the right panel is showing the drop
        # zone or a format's template editor instead (see _toggle_import_mode/
        # _on_export_choice/_close_tools_mode).
        self._tools_mode: str | None = None
        self._template_fmt: str | None = None  # which format _template_edit currently holds
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._build_ui()
        self._ui_ready = True
        self._reload()
        self._apply_responsive_layout()
        # Open the panel with a blank draft already staged in the edit
        # column instead of the "Nenhum mob selecionado" empty state — same
        # draft _on_new_mob() prepares on click, just fired once up front so
        # the user doesn't have to click "+ Novo Mob" for the common case of
        # opening the panel to create something.
        self._on_new_mob()

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

        def _menu_btn(text: str, items: list[tuple[str, str]], on_pick) -> QToolButton:
            """A secondary-style button whose click opens a menu of format
            choices instead of firing a single action — `items` is
            [(fmt_key, label), ...], `on_pick(fmt_key)` runs when one is
            chosen. Used for Importar/Exportar so the format (JSON/CSV/
            Excel) is picked explicitly on the panel itself, not left to
            the file dialog's own filter dropdown."""
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

        # Importar is a plain toggle now — no per-format menu, since the
        # drop zone it opens (see _DropZone) figures the format out from
        # whichever file gets dragged in.
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

        # Exportar keeps its format menu — JSON/CSV open an editable
        # template in the right panel (see _on_export_choice), Excel opens
        # the save dialog directly and writes a template .xlsx file (no
        # panel takeover, since a spreadsheet isn't something to edit as
        # plain text here).
        export_btn = _menu_btn("📤 Exportar", [
            ("json", "Exportar como JSON"), ("csv", "Exportar como CSV"), ("xlsx", "Exportar como Excel (.xlsx)"),
        ], self._on_export_choice)
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

        # ── Body: sidebar | center | edit panel, resizable by hand ──
        # A QSplitter instead of a plain QHBoxLayout so the user can drag
        # the boundary between any two columns — each widget's own
        # minimumSizeHint (or explicit minimumWidth, for the edit panel)
        # is still the floor the splitter won't cross either way.
        self._body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._body_splitter.setChildrenCollapsible(False)
        self._body_splitter.setHandleWidth(10)
        self._body_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        center_widget = QWidget()
        center_widget.setLayout(self._build_center())

        self._edit_panel = MobEditPanel()
        self._edit_panel.save_requested.connect(self._on_save)
        self._edit_panel.rename_requested.connect(self._on_rename)
        self._edit_panel.delete_requested.connect(self._on_delete)
        self._edit_panel.asset_add_requested.connect(self._on_asset_add)
        self._edit_panel.asset_delete_requested.connect(self._on_asset_delete)

        # The right column is a stack: the normal mob edit panel, or (while
        # Importar/Exportar-as-template is active) the tools panel taking
        # its place — same slot in the splitter either way, so the column
        # width/handle position doesn't jump when switching between them.
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

    # Below this many pixels of actual handle movement, a splitterMoved
    # signal is treated as noise (an accidental nudge while dragging
    # something else nearby, or a stray click) rather than a deliberate
    # resize — mirrors the same drag-vs-click threshold used for the
    # compass's move/rotate drags. Without this, one accidental 1-2px
    # bump would permanently disable the auto-fit-to-window logic for the
    # rest of the session, which reads exactly like "panels stopped
    # resizing" the next time the window/monitor changes size.
    _SPLITTER_NUDGE_THRESHOLD = 6

    def _on_splitter_moved(self, pos: int, index: int):
        expected = self._auto_splitter_positions.get(index)
        if expected is not None and abs(pos - expected) < self._SPLITTER_NUDGE_THRESHOLD:
            return
        # A real, deliberate drag — stop overriding column widths from
        # here on, or every future window resize would silently snap the
        # split back to the ratio-based default and undo their choice.
        self._splitter_user_adjusted = True

    def _apply_responsive_layout(self):
        total_w = self.width()
        if total_w <= 0 or not hasattr(self, "_left_container"):
            return
        # No minimumHeight floor on the summary card here anymore — it used
        # to pin one so the legend could never overlap the donut, but that
        # meant Resumo Rápido competed for space with the sidebar instead
        # of the two sharing it 2:1 as intended. _SummaryCard now protects
        # against the overlap itself (hides the legend below a safe
        # height), so this method no longer needs to.
        if not self._splitter_user_adjusted:
            # Same never-below-natural-minimum floor as the summary card
            # above — the search box + "+ Nova categoria" button up top
            # aren't inside the sidebar's internal scroll area, so they
            # can't compress past their own content width without
            # clipping/overlapping.
            content_min_w = self._left_container.minimumSizeHint().width()
            ratio_w = round(total_w * self._LEFT_RATIO)
            left_w = max(content_min_w, min(self._LEFT_MAX_W, max(self._LEFT_MIN_W, ratio_w)))
            # Edit panel starts at its own natural (sizeHint) width — not
            # squeezed down to its bare minimumSizeHint — with only the
            # center card grid absorbing whatever's left over, UNLESS
            # that would crush center below a usable floor of its own —
            # on a narrow monitor the edit panel gives up its preferred
            # width (down to its own hard minimum) before center is
            # allowed to shrink past that, so a small window degrades by
            # narrowing the edit panel first instead of squeezing the
            # mob grid into an unusable sliver.
            center_min_w = 220
            right_w = self._edit_panel.sizeHint().width()
            if total_w - left_w - right_w < center_min_w:
                right_w = max(self._edit_panel.minimumWidth(), total_w - left_w - center_min_w)
            center_w = max(1, total_w - left_w - right_w)
            sizes = [left_w, center_w, right_w]
            self._body_splitter.setSizes(sizes)
            # Remember the positions setSizes() actually produced (handle
            # position = cumulative sum up to it) so _on_splitter_moved
            # can tell a real drag apart from Qt's own splitterMoved noise.
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
