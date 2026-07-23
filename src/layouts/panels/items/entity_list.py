"""EntityListColumn — the left column shared by ITENS and HABILIDADES.

A self-contained list panel: title + "+ Novo …" button, a search box, up
to two filter combos, a 6-column table (icon+Nome / Categoria / Raridade /
Nível / ID / excluir) and a pagination footer. It's data-agnostic — the
owning panel pushes in plain row dicts via set_rows() and reacts to
`selected` / `new_requested` / `delete_requested`. Filtering/paging happen
in here so typing in the search box or flipping a page never round-trips
through the panel.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QToolButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QColor, QDrag

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_label, item_rarity_color
from src.layouts.panels.items.constants import (
    _INPUT_STYLE, _no_wheel, sub_header, panel_frame_style,
)


class _DragTable(QTableWidget):
    """A list table whose rows can be dragged out carrying the row id under
    a custom MIME format — used so a HABILIDADES row can be dropped onto the
    skill-tree canvas to spawn a node for it."""

    def __init__(self, rows: int, cols: int, drag_format: str, parent=None):
        super().__init__(rows, cols, parent)
        self._drag_format = drag_format
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, actions):
        items = self.selectedItems()
        if not items:
            return
        row_id = self.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if not row_id:
            return
        mime = QMimeData()
        mime.setData(self._drag_format, str(row_id).encode("utf-8"))
        mime.setText(str(row_id))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class EntityListColumn(QFrame):
    """Reusable list column for Itens and Habilidades alike."""

    selected = Signal(str)         # row id
    new_requested = Signal()
    import_requested = Signal()
    json_apply = Signal(str)       # raw JSON text from the { } JSON editor
    delete_requested = Signal(str)  # row id

    PAGE_SIZE = 50

    def __init__(
        self,
        title: str,
        new_label: str,
        filters: list[tuple[str, list[str]]] | None = None,
        drag_format: str | None = None,
        parent=None,
    ):
        """`filters` is [(placeholder, options), ...] — up to two combos
        rendered next to the search box (e.g. Categoria / Raridade). The
        first option of each is the "all" sentinel and is never filtered on.
        `drag_format`, if set, makes rows draggable carrying the row id under
        that MIME type (skill list → skill-tree canvas).
        """
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(240)

        self._rows: list[dict] = []
        self._filtered: list[dict] = []
        self._page = 0
        self._selected_id: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # ── Header: title + New button + { } JSON ──
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(sub_header(title))
        header.addStretch()
        new_btn = QPushButton(new_label)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 5px 12px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self.new_requested.emit)
        header.addWidget(new_btn)

        # Same "{ } JSON" affordance as config's Parallax section — a toggle
        # that reveals an inline bulk editor to paste/create many records at
        # once, right beside the "+ Novo …" button.
        json_btn = QToolButton()
        json_btn.setText("{ } JSON")
        json_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        json_btn.setToolTip("Criar vários registros de uma vez em JSON")
        json_btn.setStyleSheet(
            f"QToolButton {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE}; "
            f"padding: 5px 8px; color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold; border-radius: 6px; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}"
        )
        json_btn.clicked.connect(self._toggle_json)
        header.addWidget(json_btn)
        outer.addLayout(header)

        # ── Inline JSON bulk editor (collapsed by default) ──
        self._json_widget = QFrame()
        self._json_widget.setStyleSheet(
            f"QFrame {{ background: rgba(0,0,0,0.15); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        jl = QVBoxLayout(self._json_widget)
        jl.setContentsMargins(8, 6, 8, 6)
        jl.setSpacing(5)
        self._json_hint = QLabel("Cole uma lista JSON para criar vários de uma vez.")
        self._json_hint.setWordWrap(True)
        self._json_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        jl.addWidget(self._json_hint)
        from PySide6.QtWidgets import QTextEdit
        self._json_edit = QTextEdit()
        self._json_edit.setFixedHeight(110)
        self._json_edit.setStyleSheet(
            f"QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; font-family: Consolas, monospace; "
            f"background: rgba(0,0,0,0.25); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 4px; }}"
        )
        jl.addWidget(self._json_edit)
        self._json_error = QLabel("")
        self._json_error.setWordWrap(True)
        self._json_error.setStyleSheet(f"color: {Colors.ERROR}; font-size: 8pt; background: transparent; border: none;")
        self._json_error.hide()
        jl.addWidget(self._json_error)
        jbtns = QHBoxLayout()
        jbtns.addStretch()
        cancel = QToolButton()
        cancel.setText("Cancelar")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 10px; font-size: 8pt; "
            f"color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.08); }}"
        )
        cancel.clicked.connect(self._toggle_json)
        jbtns.addWidget(cancel)
        apply_btn = QToolButton()
        apply_btn.setText("Aplicar")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 12px; font-size: 8pt; font-weight: bold; "
            f"color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        apply_btn.clicked.connect(lambda: self.json_apply.emit(self._json_edit.toPlainText()))
        jbtns.addWidget(apply_btn)
        jl.addLayout(jbtns)
        self._json_widget.hide()
        outer.addWidget(self._json_widget)

        # ── Search + filters ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText(f"🔍  Buscar {title.lower()}...")
        self._search.setFixedHeight(28)
        self._search.textChanged.connect(self._on_filters_changed)
        self._search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        filter_row.addWidget(self._search, 2)

        self._filter_combos: list[QComboBox] = []
        for placeholder, options in (filters or []):
            combo = QComboBox()
            combo.addItem(placeholder)
            combo.addItems(options)
            combo.setFixedHeight(28)
            _no_wheel(combo)
            combo.currentIndexChanged.connect(self._on_filters_changed)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            filter_row.addWidget(combo, 1)
            self._filter_combos.append(combo)
        outer.addLayout(filter_row)

        # ── Table ──
        if drag_format:
            self._table = _DragTable(0, 6, drag_format)
        else:
            self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["Nome", "Categoria", "Raridade", "Nível", "ID", ""])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setCursor(Qt.CursorShape.PointingHandCursor)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(30)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(5, 26)
        hh.setHighlightSections(False)
        self._table.setStyleSheet(f"""
            QTableWidget {{ background: transparent; border: none; color: {Colors.TEXT_PRIMARY};
                font-size: 10px; gridline-color: transparent; }}
            QTableWidget::item {{ padding: 2px 6px; border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}
            QTableWidget::item:selected {{ background: {Colors.ACCENT_DIM}; color: {Colors.TEXT_PRIMARY}; }}
            QHeaderView::section {{ background: transparent; color: {Colors.TEXT_MUTED};
                border: none; border-bottom: 1px solid {Colors.BORDER}; padding: 4px 6px;
                font-size: 9px; font-weight: bold; }}
            QScrollBar:vertical {{ width: 5px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        outer.addWidget(self._table, 1)

        # ── Footer: total + pagination ──
        footer = QHBoxLayout()
        footer.setSpacing(4)
        self._total_lbl = QLabel("Total: 0")
        self._total_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        footer.addWidget(self._total_lbl)
        footer.addStretch()
        self._pager = QHBoxLayout()
        self._pager.setSpacing(3)
        footer.addLayout(self._pager)
        outer.addLayout(footer)

    # ── Public API ──

    def set_rows(self, rows: list[dict]):
        """`rows` are dicts with id, name, category, rarity, level, code,
        icon. Keeps the current selection highlighted if it still exists."""
        self._rows = rows
        self._apply_filters(keep_page=True)

    def select(self, row_id: str):
        self._selected_id = row_id or ""
        self._highlight_selected()

    def current_id(self) -> str:
        return self._selected_id

    # ── JSON bulk editor ──

    def set_json_template(self, text: str):
        """Placeholder/example JSON shown the first time the editor opens."""
        self._json_template = text

    def _toggle_json(self):
        showing = not self._json_widget.isVisible()
        if showing and not self._json_edit.toPlainText().strip():
            self._json_edit.setPlainText(getattr(self, "_json_template", ""))
        self._json_error.hide()
        self._json_widget.setVisible(showing)

    def json_show_error(self, message: str):
        self._json_error.setText(message)
        self._json_error.setVisible(bool(message))

    def json_close(self):
        self._json_edit.clear()
        self._json_error.hide()
        self._json_widget.hide()

    # ── Filtering / paging ──

    def _on_filters_changed(self):
        self._page = 0
        self._apply_filters()

    def _apply_filters(self, keep_page: bool = False):
        query = self._search.text().strip().lower()
        active_filters: list[tuple[int, str]] = []
        # combo 0 → Categoria, combo 1 → Raridade — same order the owning
        # panel passed them in.
        filter_keys = ["category", "rarity"]
        for i, combo in enumerate(self._filter_combos):
            if combo.currentIndex() > 0 and i < len(filter_keys):
                active_filters.append((i, combo.currentText()))

        def matches(row: dict) -> bool:
            if query and query not in (row.get("name", "").lower() + " " + row.get("code", "").lower()):
                return False
            for i, value in active_filters:
                key = filter_keys[i]
                if key == "rarity":
                    if item_rarity_label(row.get("rarity", "")) != value:
                        return False
                else:
                    if value not in (row.get(key, "") or ""):
                        return False
            return True

        self._filtered = [r for r in self._rows if matches(r)]
        max_page = max(0, (len(self._filtered) - 1) // self.PAGE_SIZE)
        if not keep_page:
            self._page = 0
        self._page = min(self._page, max_page)
        self._render_page()

    def _render_page(self):
        start = self._page * self.PAGE_SIZE
        page_rows = self._filtered[start:start + self.PAGE_SIZE]

        self._table.blockSignals(True)
        self._table.setRowCount(len(page_rows))
        for r, row in enumerate(page_rows):
            icon = row.get("icon") or "📦"
            name_item = QTableWidgetItem(f"{icon}  {row.get('name', '')}")
            name_item.setData(Qt.ItemDataRole.UserRole, row.get("id", ""))
            self._table.setItem(r, 0, name_item)
            self._table.setItem(r, 1, QTableWidgetItem(row.get("category", "") or "—"))

            rarity_key = row.get("rarity", "")
            rarity_item = QTableWidgetItem(item_rarity_label(rarity_key))
            rarity_item.setForeground(QColor(item_rarity_color(rarity_key)))
            self._table.setItem(r, 2, rarity_item)

            level_item = QTableWidgetItem(str(row.get("level", "") if row.get("level") is not None else ""))
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(r, 3, level_item)

            code_item = QTableWidgetItem(row.get("code", "") or "")
            # TEXT_MUTED (40% branco) contra o fundo quase preto do painel
            # compõe pra um cinza bem escuro — lia como "preto" de tão
            # baixo contraste. TEXT_SECONDARY continua discreto (mais
            # apagado que Nome) mas de verdade legível.
            code_item.setForeground(QColor(Colors.TEXT_SECONDARY))
            self._table.setItem(r, 4, code_item)

            row_id = row.get("id", "")
            delete_btn = QToolButton()
            delete_btn.setText("✕")
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.setToolTip("Excluir")
            delete_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 10px; }}
                QToolButton:hover {{ color: {Colors.ERROR}; }}
            """)
            delete_btn.clicked.connect(lambda _=False, rid=row_id: self.delete_requested.emit(rid))
            self._table.setCellWidget(r, 5, delete_btn)
        self._table.blockSignals(False)

        self._total_lbl.setText(f"Total: {len(self._filtered)}")
        self._highlight_selected()
        self._rebuild_pager()

    def _highlight_selected(self):
        self._table.blockSignals(True)
        self._table.clearSelection()
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == self._selected_id:
                self._table.selectRow(r)
                break
        self._table.blockSignals(False)

    def _on_selection_changed(self):
        items = self._table.selectedItems()
        if not items:
            return
        row_id = self._table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if row_id and row_id != self._selected_id:
            self._selected_id = row_id
            self.selected.emit(row_id)

    def _rebuild_pager(self):
        while self._pager.count():
            w = self._pager.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        total_pages = max(1, (len(self._filtered) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if total_pages <= 1:
            return

        def nav_btn(text: str, target: int, enabled: bool, active: bool = False) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setEnabled(enabled)
            bg = Colors.ACCENT if active else "rgba(255,255,255,0.05)"
            fg = "#08131F" if active else Colors.TEXT_SECONDARY
            b.setStyleSheet(f"""
                QToolButton {{ background: {bg}; color: {fg}; border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: bold; min-width: 16px; }}
                QToolButton:hover:enabled {{ background: {Colors.PANEL_HOVER}; }}
                QToolButton:disabled {{ color: {Colors.TEXT_DISABLED}; }}
            """)
            b.clicked.connect(lambda: self._goto_page(target))
            return b

        self._pager.addWidget(nav_btn("«", self._page - 1, self._page > 0))
        # Windowed page numbers around the current page, with an ellipsis to
        # the last page — same shape as the reference (1 2 3 … 10).
        pages = self._page_window(self._page, total_pages)
        for p in pages:
            if p == -1:
                dots = QLabel("…")
                dots.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
                self._pager.addWidget(dots)
            else:
                self._pager.addWidget(nav_btn(str(p + 1), p, True, active=(p == self._page)))
        self._pager.addWidget(nav_btn("»", self._page + 1, self._page < total_pages - 1))

    @staticmethod
    def _page_window(current: int, total: int) -> list[int]:
        if total <= 5:
            return list(range(total))
        pages = {0, total - 1, current, current - 1, current + 1}
        pages = sorted(p for p in pages if 0 <= p < total)
        out: list[int] = []
        prev = None
        for p in pages:
            if prev is not None and p - prev > 1:
                out.append(-1)  # ellipsis
            out.append(p)
            prev = p
        return out

    def _goto_page(self, page: int):
        total_pages = max(1, (len(self._filtered) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._page = max(0, min(page, total_pages - 1))
        self._render_page()
