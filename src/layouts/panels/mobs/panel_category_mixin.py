"""CategoryExplorerMixin — the CATEGORIAS sidebar/explorer: folder tree
navigation, search, create/rename/delete. Mixed into MobsPanel (see
panel.py) — operates on self.* attributes MobsPanel owns; not meant to be
instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QToolButton, QPushButton, QFrame, QScrollArea, QMessageBox,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import SMART_FILTERS, set_category_lookup
from src.layouts.panels.mobs.panel_widgets import _SidebarRow, _InlineNameEdit

logger = logging.getLogger("MAKEMAP")


class CategoryExplorerMixin:
    """CATEGORIAS box: the SMART_FILTERS (Todos/Favoritos) stay plain
    pinned rows since they aren't part of the folder tree — matching the
    reference: "CATEGORIAS" title alone, then one combined row (back/
    forward + search + "+ Nova categoria"), then a single continuous list
    — smart filters first, folder rows for the current directory right
    after with no separator between them, since clicking a folder row
    just replaces that same list in place (see _refresh_explorer/
    _navigate_into) rather than opening anything separate below it."""

    def _build_left_column(self) -> QWidget:
        """Categories and Resumo Rápido as two independent, visibly
        separate cards stacked in the left column — NOT one nested inside
        the other, which used to make Resumo Rápido read as part of the
        same panel as the category list. CATEGORIAS defaults to 2/3 of the
        column's height and Resumo Rápido 1/3 — plain stretch factors, so
        both actually respond as the window/column resizes (a fixed
        content-based height was tried here and didn't — it only reacted
        to rows being added/removed, never to the window itself changing
        size). The category list's own internal QScrollArea also stretches
        to fill whatever the box ends up with, and scrolls internally
        if there isn't room for every row."""
        container = QWidget()
        self._left_container = container
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(self._build_sidebar(), 2)
        outer.addWidget(self._build_summary_card(), 1)
        return container

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.03); border-radius: 8px; }}")
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        cat_title = QLabel("CATEGORIAS")
        cat_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(cat_title)

        def _nav_btn(text: str, tooltip: str, slot) -> QToolButton:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_SECONDARY}; font-size: 11px; padding: 2px 4px; }}
                QToolButton:hover:!disabled {{ color: {Colors.TEXT_PRIMARY}; }}
                QToolButton:disabled {{ color: {Colors.BORDER_SUBTLE}; }}
            """)
            btn.clicked.connect(slot)
            return btn

        controls_row = QHBoxLayout()
        controls_row.setSpacing(4)
        self._nav_back_btn = _nav_btn("◀", "Voltar", self._on_nav_back)
        self._nav_forward_btn = _nav_btn("▶", "Avançar", self._on_nav_forward)
        controls_row.addWidget(self._nav_back_btn)
        controls_row.addWidget(self._nav_forward_btn)

        self._category_search = QLineEdit()
        self._category_search.setPlaceholderText("🔍 Buscar categoria...")
        self._category_search.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 4px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
        """)
        self._category_search.textChanged.connect(lambda _t: self._refresh_explorer())
        controls_row.addWidget(self._category_search, 1)

        # "+ Nova categoria" swaps itself for an inline text field in the
        # same spot (see _on_new_category_clicked/_confirm_new_category/
        # _cancel_new_category) instead of popping a separate QInputDialog
        # window — Enter confirms, Escape or clicking away cancels.
        self._new_cat_btn = QPushButton("+ Nova categoria")
        self._new_cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_cat_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.ACCENT}; border: none; font-size: 9px; font-weight: bold; padding: 0; }}
            QPushButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        self._new_cat_btn.clicked.connect(self._on_new_category_clicked)
        controls_row.addWidget(self._new_cat_btn)

        self._new_cat_edit = _InlineNameEdit()
        self._new_cat_edit.setPlaceholderText("Nome da categoria...")
        self._new_cat_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.ACCENT};
                border-radius: 6px; padding: 4px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
        """)
        self._new_cat_edit.setVisible(False)
        self._new_cat_edit.confirmed.connect(self._confirm_new_category)
        self._new_cat_edit.cancelled.connect(self._cancel_new_category)
        controls_row.addWidget(self._new_cat_edit, 1)

        # An explicit confirm button beside the field — Enter already
        # confirms, but a visible click target means it isn't the only way.
        self._new_cat_confirm_btn = QToolButton()
        self._new_cat_confirm_btn.setText("✓")
        self._new_cat_confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_cat_confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        self._new_cat_confirm_btn.setVisible(False)
        self._new_cat_confirm_btn.clicked.connect(self._confirm_new_category)
        controls_row.addWidget(self._new_cat_confirm_btn)
        lay.addLayout(controls_row)

        # Breadcrumb — hidden entirely at the root (see _refresh_explorer),
        # so it doesn't add a row the reference image doesn't show; it
        # only appears once you've actually navigated into a folder.
        self._breadcrumb_container = QWidget()
        self._breadcrumb_row = QHBoxLayout(self._breadcrumb_container)
        self._breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        self._breadcrumb_row.setSpacing(2)
        lay.addWidget(self._breadcrumb_container)
        self._breadcrumb_container.setVisible(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                              "QScrollArea > QWidget > QWidget { background: transparent; }")
        self._folders_list_widget = QWidget()
        self._folders_layout = QVBoxLayout(self._folders_list_widget)
        self._folders_layout.setContentsMargins(0, 0, 0, 0)
        self._folders_layout.setSpacing(2)

        # Smart filters are added once here and never touched again —
        # _refresh_explorer only clears/rebuilds what comes after them
        # (see self._folder_rows_start_index), so they stay put at the
        # top of the same list the folder rows appear directly beneath.
        for key, icon_c, label in SMART_FILTERS:
            row = _SidebarRow(key, icon_c, label)
            row.clicked.connect(self._on_filter_selected)
            self._sidebar_rows[key] = row
            self._folders_layout.addWidget(row)
        self._sidebar_rows["todos"].set_selected(True)
        self._folder_rows_start_index = self._folders_layout.count()

        scroll.setWidget(self._folders_list_widget)
        self._folders_scroll = scroll
        # Stretches to fill whatever's left in the sidebar box (see
        # _build_left_column's 2:1 split) — scrolls internally instead of
        # growing past that if there are more rows than fit.
        lay.addWidget(scroll, 1)

        return sidebar

    def _breadcrumb_button(self, label: str, target_id: str | None) -> QToolButton:
        is_current = target_id == self._current_dir_id
        btn = QToolButton()
        btn.setText(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        color = Colors.ACCENT if is_current else Colors.TEXT_SECONDARY
        weight = "bold" if is_current else "normal"
        btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {color};
                font-size: 9px; font-weight: {weight}; padding: 0 2px; }}
            QToolButton:hover {{ color: {Colors.ACCENT}; }}
        """)
        btn.clicked.connect(lambda _c=False, tid=target_id: self._navigate_into(tid))
        return btn

    def _descendant_ids(self, folder_id: str) -> set[str]:
        """`folder_id` plus every id nested under it, any depth — used to
        count mobs recursively for a folder card's badge."""
        ids = {folder_id}
        stack = [folder_id]
        while stack:
            current = stack.pop()
            for child in self._uow.mob_categories.get_children(current):
                if child["id"] not in ids:
                    ids.add(child["id"])
                    stack.append(child["id"])
        return ids

    def _refresh_explorer(self):
        """Rebuilds the breadcrumb + folder rows for self._current_dir_id
        — called on navigation, category CRUD, and every _reload()."""
        if not self._uow or not hasattr(self, "_breadcrumb_row"):
            return

        while self._breadcrumb_row.count():
            item = self._breadcrumb_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        path = self._uow.mob_categories.get_path(self._current_dir_id)
        # Hidden entirely at the root — see _build_sidebar — so it only
        # takes up space once there's an actual path to show.
        self._breadcrumb_container.setVisible(bool(path))
        if path:
            self._breadcrumb_row.addWidget(self._breadcrumb_button("🏠", None))
            for cat in path:
                sep = QLabel("›")
                sep.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
                self._breadcrumb_row.addWidget(sep)
                self._breadcrumb_row.addWidget(self._breadcrumb_button(cat["name"], cat["id"]))
            self._breadcrumb_row.addStretch()

        self._nav_back_btn.setEnabled(self._nav_index > 0)
        self._nav_forward_btn.setEnabled(self._nav_index < len(self._nav_history) - 1)

        # Only the folder rows get cleared/rebuilt — the smart filters
        # above them (added once in _build_sidebar) stay put, so this
        # never touches self._sidebar_rows.
        while self._folders_layout.count() > self._folder_rows_start_index:
            item = self._folders_layout.takeAt(self._folder_rows_start_index)
            if item.widget():
                item.widget().deleteLater()
        search = self._category_search.text().strip().lower()
        children = [
            cat for cat in self._uow.mob_categories.get_children(self._current_dir_id)
            if not search or search in cat["name"].lower()
        ]
        if children:
            for cat in children:
                row = _SidebarRow(cat["id"], cat.get("icon") or "📁", cat["name"], show_menu=True)
                row.set_count(sum(1 for m in self._mobs if m.get("category") in self._descendant_ids(cat["id"])))
                row.clicked.connect(self._navigate_into)
                row.rename_confirmed.connect(self._on_rename_category)
                row.delete_requested.connect(self._on_delete_category)
                self._folders_layout.addWidget(row)
        else:
            # Makes an empty directory (or a search with no matches)
            # unambiguous — otherwise navigating into one looks identical
            # to nothing having happened at all, since the smart filters
            # above are the only thing left on screen either way.
            empty_lbl = QLabel("Nenhuma categoria encontrada." if search else "Nenhuma subcategoria aqui ainda.")
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-style: italic; "
                                     f"background: transparent; border: none; padding: 6px 8px;")
            self._folders_layout.addWidget(empty_lbl)

        # Without this, a QVBoxLayout with no stretch item distributes any
        # leftover height (there's plenty once the box gets its 2/3 share
        # of the column, see _build_left_column) EQUALLY across every row
        # instead of leaving it as blank space below the last one — every
        # row (pinned smart filters included) was rendering ~110px tall
        # instead of its natural ~30px, so only 2 fit on screen before
        # needing to scroll for the rest.
        self._folders_layout.addStretch()
        logger.info("Explorer atualizado: dir=%s, %d subpasta(s)", self._current_dir_id, len(children))

    def _navigate_into(self, folder_id: str | None):
        logger.info("Explorer: clique recebido (folder_id=%s, atual=%s)", folder_id, self._current_dir_id)
        if folder_id == self._current_dir_id:
            return
        self._nav_history = self._nav_history[:self._nav_index + 1] + [folder_id]
        self._nav_index += 1
        self._current_dir_id = folder_id
        self._refresh_explorer()
        self._apply_filters()

    def _on_nav_back(self):
        if self._nav_index > 0:
            self._nav_index -= 1
            self._current_dir_id = self._nav_history[self._nav_index]
            self._refresh_explorer()
            self._apply_filters()
            logger.info("Navegação (voltar): dir=%s", self._current_dir_id)

    def _on_nav_forward(self):
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_index += 1
            self._current_dir_id = self._nav_history[self._nav_index]
            self._refresh_explorer()
            self._apply_filters()
            logger.info("Navegação (avançar): dir=%s", self._current_dir_id)

    def _reload_categories(self) -> list[dict]:
        """Fetches the whole category tree (any depth) fresh from the DB
        and pushes it everywhere it's consumed: the icon/label lookup
        MobCard reads from, the "Tipo" filter combo, the explorer, and
        (cached on self._all_categories) Resumo Rápido's legend."""
        if not self._uow:
            return []
        all_categories = self._uow.mob_categories.get_all()
        self._all_categories = all_categories
        set_category_lookup(all_categories)
        self._refresh_category_filter_combo(all_categories)
        self._refresh_explorer()
        logger.info("Categorias recarregadas: %d no total", len(all_categories))
        return all_categories

    def _refresh_category_filter_combo(self, categories: list[dict]):
        """Top-level folders only — showing every nested subfolder here
        too (as it did before) got cluttered fast, and drilling into a
        specific subfolder already has its own dedicated UI: the explorer
        itself. Selecting a root entry here matches that folder AND
        everything nested under it (see _apply_filters), not just mobs
        filed directly at the root."""
        current = self._category_filter_combo.currentData()
        self._category_filter_combo.blockSignals(True)
        self._category_filter_combo.clear()
        self._category_filter_combo.addItem("Todos", "")

        roots = sorted(
            (c for c in categories if c.get("parent_id") is None),
            key=lambda c: (c.get("sort_order") or 0, c["name"]),
        )
        for c in roots:
            self._category_filter_combo.addItem(f"{c.get('icon') or '📁'} {c['name']}", c["id"])

        idx = self._category_filter_combo.findData(current)
        self._category_filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._category_filter_combo.blockSignals(False)

    def _on_filter_selected(self, key: str):
        self._active_filter = key
        for k, row in self._sidebar_rows.items():
            row.set_selected(k == key)
        if key == "todos" and self._current_dir_id is not None:
            # "Todos" means show every mob — reset folder browsing back to
            # the root too, instead of silently staying scoped to whatever
            # directory happened to be open.
            self._current_dir_id = None
            self._nav_history = [None]
            self._nav_index = 0
            self._refresh_explorer()
        self._apply_filters()
        logger.info("Filtro de categoria selecionado: %s", key)

    def _on_new_category_clicked(self):
        self._new_cat_btn.setVisible(False)
        self._new_cat_edit.clear()
        self._new_cat_edit.setVisible(True)
        self._new_cat_confirm_btn.setVisible(True)
        self._new_cat_edit.setFocus()

    def _cancel_new_category(self):
        self._new_cat_edit.setVisible(False)
        self._new_cat_confirm_btn.setVisible(False)
        self._new_cat_btn.setVisible(True)

    def _confirm_new_category(self):
        """Creates a new subfolder inside whichever directory is currently
        open in the explorer (self._current_dir_id, None meaning the
        root) — matches "ao clicar no card, Nova categoria cria dentro do
        diretório selecionado"."""
        name = self._new_cat_edit.text().strip()
        self._new_cat_edit.setVisible(False)
        self._new_cat_confirm_btn.setVisible(False)
        self._new_cat_btn.setVisible(True)
        if not name or not self._uow:
            return
        cat_id = self._uow.mob_categories.create(parent_id=self._current_dir_id, name=name, icon="📁")
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        # A leftover search filter that doesn't match the new category's
        # name would otherwise hide it right after creating it — looking
        # exactly like it silently failed. Clearing it (which itself
        # triggers _refresh_explorer via textChanged) guarantees the new
        # folder is actually visible.
        if self._category_search.text():
            self._category_search.clear()
        logger.info("Categoria criada: id=%s nome='%s' pai=%s", cat_id, name, self._current_dir_id)

    def _on_rename_category(self, key: str, new_name: str):
        if not self._uow:
            return
        self._uow.mob_categories.update(key, name=new_name)
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        logger.info("Categoria renomeada: id=%s novo_nome='%s'", key, new_name)

    def _on_delete_category(self, key: str):
        if not self._uow:
            return
        cat = self._uow.mob_categories.get(key)
        name = cat["name"] if cat else key
        reply = QMessageBox.question(
            self, "Excluir categoria",
            f'Excluir "{name}"? Isso também exclui todas as subcategorias dentro dela, se houver.\n\n'
            "Mobs já atribuídos a ela não são apagados — só ficam sem essa categoria.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        before = len(self._all_categories)
        self._uow.mob_categories.delete(key)
        if self._current_dir_id is not None and not self._uow.mob_categories.get(self._current_dir_id):
            # Was browsing the deleted folder (or one of its now-cascaded
            # subfolders) — back to the root instead of a dead end.
            self._current_dir_id = None
            self._nav_history = [None]
            self._nav_index = 0
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        self._apply_filters()
        logger.info("Categoria excluída: id=%s (cascata: %d)", key, before - len(categories))
