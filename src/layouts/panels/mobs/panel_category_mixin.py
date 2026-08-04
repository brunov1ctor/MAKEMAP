"""CategoryExplorerMixin — the CATEGORIAS sidebar/explorer: folder tree
navigation, search, create/rename/delete. Mixed into MobsPanel (see
panel.py) — operates on self.* attributes MobsPanel owns; not meant to be
instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QToolButton, QPushButton, QFrame, QScrollArea, QStackedWidget, QSplitter,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.components.live_splitter import LiveSplitter
from src.layouts.panels.mobs.categories import set_category_lookup
from src.layouts.panels.mobs.panel_widgets import _SidebarRow
from src.layouts.panels.mobs.category_edit_panel import CategoryEditPanel

logger = logging.getLogger("MAKEMAP")


class CategoryExplorerMixin:
    """CATEGORIAS box: "CATEGORIAS" title alone, then one combined row
    (back/forward + search + "+ Nova categoria"), then a single continuous
    list of folder rows for the current directory — clicking one just
    replaces that same list in place (see _refresh_explorer/
    _navigate_into) rather than opening anything separate below it."""

    def _build_left_column(self) -> QWidget:
        """Categories and Resumo Rápido as two independent, visibly
        separate cards stacked in the left column — NOT one nested inside
        the other, which used to make Resumo Rápido read as part of the
        same panel as the category list. The two live in their own
        vertical QSplitter (same click-and-drag-a-handle interaction as
        the left|center|right _body_splitter in panel.py) instead of a
        plain QVBoxLayout with fixed stretch factors — CATEGORIAS starts
        at roughly 2/3 of the column's height and Resumo Rápido 1/3 (see
        setSizes below), but the user can now drag the handle between them
        to any split they want, the same way they already can between the
        sidebar/grid/edit-panel columns. The category list's own internal
        QScrollArea still stretches to fill whatever height it ends up
        with, scrolling internally if there isn't room for every row.

        The whole column is itself a 2-page QStackedWidget (self._left_
        stack): page 0 is this browse view, page 1 is CategoryEditPanel —
        creating/editing a category folder swaps this LEFT column, not the
        right-hand MobEditPanel slot, since a category isn't a mob and
        belongs with the explorer it's edited from (see
        _open_category_editor)."""
        container = QWidget()
        self._left_container = container
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        browse_splitter = LiveSplitter(Qt.Orientation.Vertical)
        browse_splitter.setChildrenCollapsible(False)
        browse_splitter.setHandleWidth(10)
        browse_splitter.addWidget(self._build_sidebar())
        browse_splitter.addWidget(self._build_summary_card())
        browse_splitter.setStretchFactor(0, 2)
        browse_splitter.setStretchFactor(1, 1)
        # Large relative values, not real pixels — Qt scales these down
        # proportionally against whatever height is actually available at
        # layout time, same trick _apply_responsive_layout already relies
        # on for the horizontal splitter's initial sizes.
        browse_splitter.setSizes([2000, 1000])
        browse_widget = browse_splitter

        self._category_edit_panel = CategoryEditPanel()
        self._category_edit_panel.save_requested.connect(self._on_category_editor_save)
        self._category_edit_panel.delete_requested.connect(self._on_category_editor_delete)
        self._category_edit_panel.close_requested.connect(self._on_category_editor_close)

        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(browse_widget)
        self._left_stack.addWidget(self._category_edit_panel)
        outer.addWidget(self._left_stack)
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
                QToolTip {{
                    background-color: {Colors.BG_ELEVATED};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 8px;
                    padding: 6px 10px;
                    font-size: 11px;
                }}
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

        # "+ Nova categoria" opens the full CategoryEditPanel in the right
        # column (see _open_category_editor) instead of swapping itself for
        # an inline text field — the old single-name-field flow couldn't
        # set an icon/border/image, only ever created rows with the
        # hardcoded '🐾' icon.
        self._new_cat_btn = QPushButton("+ Nova categoria")
        self._new_cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_cat_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.ACCENT}; border: none; font-size: 9px; font-weight: bold; padding: 0; }}
            QPushButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        self._new_cat_btn.clicked.connect(lambda: self._open_category_editor(None))
        controls_row.addWidget(self._new_cat_btn)
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
                row = _SidebarRow(
                    cat["id"], cat.get("icon") or "🐾", cat["name"], show_menu=True,
                    border_color=cat.get("border_color") or "", image_path=cat.get("image_path") or "",
                )
                row.set_count(sum(1 for m in self._mobs if m.get("category") in self._descendant_ids(cat["id"])))
                row.clicked.connect(self._navigate_into)
                row.rename_confirmed.connect(self._on_rename_category)
                row.delete_requested.connect(self._on_delete_category)
                row.edit_requested.connect(self._on_edit_category_requested)
                row.reorder_requested.connect(self._reorder_categories)
                self._folders_layout.addWidget(row)
        else:
            # Makes an empty directory (or a search with no matches)
            # unambiguous — otherwise navigating into one looks identical
            # to nothing having happened at all.
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

    def _open_category_editor(self, category: dict | None):
        """Opens CategoryEditPanel in the left column (see _build_left_
        column's self._left_stack) — `category=None`
        creates a new subfolder inside whichever directory is currently
        open in the explorer (self._current_dir_id, None meaning the
        root), matching "ao clicar no card, Nova categoria cria dentro do
        diretório selecionado". A non-None dict edits that category
        in-place (see _on_edit_category_requested)."""
        parent_id = category["parent_id"] if category else self._current_dir_id
        self._category_edit_panel.load(category, parent_id)
        self._left_stack.setCurrentIndex(1)
        self._category_edit_panel.focus_name()

    def _on_edit_category_requested(self, key: str):
        if not self._uow:
            return
        cat = self._uow.mob_categories.get(key)
        if cat:
            self._open_category_editor(cat)

    def _on_category_editor_close(self):
        self._left_stack.setCurrentIndex(0)

    def _on_category_editor_save(self, data: dict):
        if not self._uow:
            return
        fields = dict(
            name=data["name"], icon=data["icon"], border_color=data["border_color"],
            image_path=data["image_path"], image_border_color=data["image_border_color"],
            tag_text_color=data["tag_text_color"],
        )
        if data["id"]:
            self._uow.mob_categories.update(data["id"], **fields)
            logger.info("Categoria atualizada: id=%s nome='%s'", data["id"], data["name"])
        else:
            cat_id = self._uow.mob_categories.create(parent_id=data["parent_id"], **fields)
            logger.info("Categoria criada: id=%s nome='%s' pai=%s", cat_id, data["name"], data["parent_id"])
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        # A leftover search filter that doesn't match the new/renamed
        # category would otherwise hide it right after saving — looking
        # exactly like it silently failed. Clearing it (which itself
        # triggers _refresh_explorer via textChanged) guarantees it's
        # actually visible.
        if self._category_search.text():
            self._category_search.clear()
        # _reload_categories() only refreshes the lookup category_badge_
        # color/category_image_border_color read from — the mob grid's
        # MobCard widgets computed their border/tag colors once, at the
        # time they were built, and don't re-poll that lookup on their
        # own. Rebuilding the grid now (same call the search/filter boxes
        # already trigger on every change) is what makes every mob card in
        # this category pick up the new color immediately, without the
        # user having to open and re-save each mob individually.
        self._apply_filters()
        self._left_stack.setCurrentIndex(0)

    def _on_category_editor_delete(self, key: str):
        if self._on_delete_category(key):
            self._left_stack.setCurrentIndex(0)

    def _reorder_categories(self, source_id: str, target_id: str):
        """Drops `source_id`'s row onto `target_id`'s — only makes sense
        between siblings of the currently open folder (both rows are only
        ever rendered together when they share a parent, see
        _refresh_explorer), so no cross-folder guard is needed here."""
        if not self._uow:
            return
        siblings = self._uow.mob_categories.get_children(self._current_dir_id)
        ids = [c["id"] for c in siblings]
        if source_id not in ids or target_id not in ids:
            return
        ids.remove(source_id)
        ids.insert(ids.index(target_id), source_id)
        for i, cat_id in enumerate(ids):
            self._uow.mob_categories.update(cat_id, sort_order=i)
        self._reload_categories()
        logger.info("Categorias reordenadas em dir=%s: %s", self._current_dir_id, ids)

    def _on_rename_category(self, key: str, new_name: str):
        if not self._uow:
            return
        self._uow.mob_categories.update(key, name=new_name)
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        # The grid's rarity chip text is category_label(category) — a
        # rename needs the same grid rebuild as a color change (see
        # _on_category_editor_save) or every mob card keeps showing the
        # old name on its tag until something else happens to rebuild it.
        self._apply_filters()
        logger.info("Categoria renomeada: id=%s novo_nome='%s'", key, new_name)

    def _on_delete_category(self, key: str) -> bool:
        """Deletes immediately — no native QMessageBox confirmation dialog
        (that used to pop a separate OS window outside the app; the "are
        you sure" step now lives in-panel instead, as CategoryEditPanel's
        delete button arming itself on first click — see
        _DeleteConfirmButton in category_edit_panel.py — and the sidebar
        ⋮ menu's quick delete matching region_card.py's existing
        no-confirm precedent). Still returns a bool (always True once
        self._uow exists) so _on_category_editor_delete's call site keeps
        working unchanged."""
        if not self._uow:
            return False
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
        return True
