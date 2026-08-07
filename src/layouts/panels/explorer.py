"""2. Explorer (painel) — árvore derivada e ressincronizada automaticamente
a partir do que existe de fato no mapa (ver ExplorerSyncMediator). O
painel em si só sabe renderizar uma lista de ExplorerNode e emitir cliques;
toda a lógica de "o que existe / o que é uma región" mora no mediator.
"""

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget,
    QGraphicsOpacityEffect, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve

from src.styles.tokens import Colors, Typography
from src.components.collapsible_panel import CollapsiblePanel
from src.engines.map.explorer_model import ExplorerNode

_NODE_ROLE = Qt.ItemDataRole.UserRole


# ─── 2. Explorer Panel ─────────────────────────────────────────────────────

class ExplorerPanel(CollapsiblePanel):
    """2. Explorer — busca + árvore auto-sincronizada + contador."""

    node_activated = Signal(dict)  # payload de um ExplorerNode não-categoria (ex.: scene_pos)
    node_hovered = Signal(dict, bool)  # (payload, hovered) — mouse enter/leave de uma linha não-categoria

    def __init__(self, parent=None):
        super().__init__(title="Explorer", icon="🌍", parent=parent, radius=12)

        self._all_roots: list[ExplorerNode] = []
        self._collapsed_categories: set[str] = set()
        self._selected_ids: set[int] = set()
        self._pulse_animations: list[QPropertyAnimation] = []
        self._hovered_payload: dict | None = None

        # Título maior
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)

        # Counter no header
        self.counter_label = QLabel("0 elementos")
        self.counter_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};
            background: rgba(10,16,30,0.5); border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 10px; padding: 2px 8px;
        """)
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, self.counter_label)

        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(8)

        # Busca + expandir/recolher tudo
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Buscar no mapa...")
        self.search.setFixedHeight(30)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(10,16,30,0.7);
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 8px; padding: 0 12px;
                font-size: {Typography.SIZE_SM}px; color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self.search.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search, 1)

        btn_style = f"""
            QToolButton {{
                border: none; border-radius: 6px; font-size: 13px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; border-radius: 8px;
                padding: 6px 10px; font-size: 11px;
            }}
        """

        self.btn_expand = QToolButton()
        self.btn_expand.setText("⊞")
        self.btn_expand.setToolTip("Expandir Tudo")
        self.btn_expand.setFixedSize(28, 28)
        self.btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_expand.setStyleSheet(btn_style)
        self.btn_expand.clicked.connect(self._expand_all)
        search_row.addWidget(self.btn_expand)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setText("⊟")
        self.btn_collapse.setToolTip("Recolher Tudo")
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.setStyleSheet(btn_style)
        self.btn_collapse.clicked.connect(self._collapse_all)
        search_row.addWidget(self.btn_collapse)

        content_layout.addLayout(search_row)

        # Árvore
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: transparent; border: none;
                font-size: {Typography.SIZE_SM}px; color: {Colors.TEXT_SECONDARY}; outline: none;
            }}
            QTreeWidget::item {{ padding: 4px 4px; border-radius: 6px; margin: 1px 0; }}
            QTreeWidget::item:hover {{ background: {Colors.PANEL_HOVER}; }}
            QTreeWidget::item:selected {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; }}
            QTreeWidget::branch {{ background: transparent; border: none; }}
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        content_layout.addWidget(self.tree, 1)

        self.content_layout.addWidget(content)
        self._update_counter(0)

    # ─── API pública (chamada por ExplorerSyncMediator) ────────────────

    def set_tree(self, roots: list[ExplorerNode]):
        """Substitui a árvore inteira pelos `roots` — chamado a cada rebuild
        do ExplorerSyncMediator. Preserva busca e estado expandir/recolher."""
        self._all_roots = roots
        self._render(self._filtered_roots(self.search.text()))

    def set_selected_ids(self, ids: set[int]):
        """Atualiza quais itens de cena estão selecionados e re-renderiza
        apenas o estado de destaque/pulso, sem reconstruir a árvore toda."""
        self._selected_ids = ids
        self._render(self._filtered_roots(self.search.text()))

    # ─── Busca ───────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._render(self._filtered_roots(text))

    def _filtered_roots(self, query: str) -> list[ExplorerNode]:
        query = query.strip().lower()
        if not query:
            return self._all_roots

        def _filter_node(node: ExplorerNode) -> ExplorerNode | None:
            """Return a copy of node with only matching descendants, or None."""
            if node.children:
                kept = [r for c in node.children for r in [_filter_node(c)] if r is not None]
                if kept:
                    return ExplorerNode(
                        id=node.id, kind=node.kind, label=node.label,
                        thumbnail=node.thumbnail, icon_glyph=node.icon_glyph,
                        children=kept, payload=node.payload,
                    )
            if query in node.label.lower():
                return node
            return None

        filtered = []
        for category in self._all_roots:
            kept = [r for c in category.children for r in [_filter_node(c)] if r is not None]
            if kept:
                filtered.append(ExplorerNode(
                    id=category.id, kind=category.kind, label=category.label,
                    icon_glyph=category.icon_glyph, children=kept,
                ))
        return filtered

    # ─── Expandir/Recolher ───────────────────────────────────────────────

    def _expand_all(self):
        self._collapsed_categories.clear()
        self.tree.expandAll()

    def _collapse_all(self):
        self._collapsed_categories = {self.tree.topLevelItem(i).data(0, _NODE_ROLE).id
                                       for i in range(self.tree.topLevelItemCount())}
        self.tree.collapseAll()

    # ─── Clique ──────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int):
        node: ExplorerNode = item.data(0, _NODE_ROLE)
        if node is None or node.kind == "category":
            return
        self.node_activated.emit(node.payload)

    # ─── Render ──────────────────────────────────────────────────────────

    def _render(self, roots: list[ExplorerNode]):
        for anim in self._pulse_animations:
            anim.stop()
        self._pulse_animations.clear()

        if self._hovered_payload is not None:
            self.node_hovered.emit(self._hovered_payload, False)
            self._hovered_payload = None

        self.tree.clear()
        total_leaves = 0
        selected_item: QTreeWidgetItem | None = None

        def _add_children(parent_qt: QTreeWidgetItem, nodes: list[ExplorerNode], level: int):
            nonlocal total_leaves, selected_item
            for node in nodes:
                is_parent = bool(node.children)
                qt_item = QTreeWidgetItem(parent_qt)
                qt_item.setData(0, _NODE_ROLE, node)
                w, lbl = self._make_item_widget(node, level=level, is_parent=is_parent,
                                                tree_item=qt_item if is_parent else None)
                self.tree.setItemWidget(qt_item, 0, w)
                if is_parent:
                    has_selected_gc = _add_children(qt_item, node.children, level + 1)
                    qt_item.setExpanded(has_selected_gc or node.id not in self._collapsed_categories)
                    if has_selected_gc and selected_item is None:
                        pass  # selected_item already set deeper
                else:
                    total_leaves += 1
                    if node.selected:
                        self._start_pulse(lbl)
                        selected_item = qt_item
            return any(
                (n.selected or (n.children and _has_selected(n)))
                for n in nodes
            )

        def _has_selected(node: ExplorerNode) -> bool:
            if node.selected:
                return True
            return any(_has_selected(c) for c in node.children)

        for category in roots:
            k_item = QTreeWidgetItem(self.tree)
            k_item.setData(0, _NODE_ROLE, category)
            k_widget, _ = self._make_item_widget(category, level=0, is_parent=True, tree_item=k_item)
            self.tree.setItemWidget(k_item, 0, k_widget)
            has_sel = _add_children(k_item, category.children, level=1)
            k_item.setExpanded(has_sel or category.id not in self._collapsed_categories)

        self._update_counter(total_leaves)
        if selected_item is not None:
            self.tree.scrollToItem(selected_item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _start_pulse(self, widget: QWidget):
        """Efeito pulsante de opacidade no widget do item selecionado."""
        fx = QGraphicsOpacityEffect(widget)
        fx.setOpacity(1.0)
        widget.setGraphicsEffect(fx)

        anim = QPropertyAnimation(fx, b"opacity", widget)
        anim.setDuration(900)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._pulse_animations.append(anim)

    def _make_item_widget(self, node: ExplorerNode, level: int, is_parent: bool,
                          tree_item: QTreeWidgetItem | None = None) -> tuple[QWidget, QLabel]:
        is_selected = node.selected and not is_parent

        w = QWidget()
        if is_selected:
            w.setStyleSheet(
                f"background: {Colors.ACCENT_DIM}; border-left: 3px solid {Colors.ACCENT};"
                f"border-radius: 4px;"
            )
        else:
            w.setStyleSheet("background: transparent; border: none;")

        row = QHBoxLayout(w)
        indent = level * 16
        row.setContentsMargins(indent, 0, 4, 0)
        row.setSpacing(6)

        if is_parent:
            arrow = QToolButton()
            arrow.setText("▼" if node.id not in self._collapsed_categories else "▶")
            arrow.setFixedSize(16, 16)
            arrow.setCursor(Qt.CursorShape.PointingHandCursor)
            arrow.setStyleSheet(f"""
                QToolButton {{
                    border: none; font-size: 8px;
                    color: {Colors.TEXT_MUTED}; background: transparent;
                }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            """)

            def toggle_expand(checked=False, node_id=node.id, btn=arrow, ti=tree_item):
                item = ti if ti is not None else self._top_level_item_for(node_id)
                if item is None:
                    return
                expanded = not item.isExpanded()
                item.setExpanded(expanded)
                btn.setText("▼" if expanded else "▶")
                if expanded:
                    self._collapsed_categories.discard(node_id)
                else:
                    self._collapsed_categories.add(node_id)
            arrow.clicked.connect(toggle_expand)
            row.addWidget(arrow)
        else:
            connector = QLabel("└")
            connector.setFixedWidth(12)
            connector.setStyleSheet("font-size: 10px; color: rgba(255,255,255,0.2); background: transparent; border: none;")
            row.addWidget(connector)

        thumb = QLabel()
        thumb.setFixedSize(20, 20)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if node.thumbnail is not None and not node.thumbnail.isNull():
            thumb.setPixmap(node.thumbnail.scaled(
                20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            thumb.setText(node.icon_glyph or "•")
            thumb.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        row.addWidget(thumb)

        label_text = node.label
        if node.kind == "category":
            label_text = f"{node.label} ({len(node.children)})"

        text_color = Colors.ACCENT if is_selected else (Colors.TEXT_PRIMARY if is_parent else Colors.TEXT_SECONDARY)
        font_weight = Typography.WEIGHT_BOLD if (is_selected or is_parent) else Typography.WEIGHT_NORMAL

        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {font_weight}; color: {text_color};
            background: transparent; border: none;
        """)
        row.addWidget(lbl, 1)

        if not is_parent:
            payload = node.payload

            def enter_event(event, payload=payload):
                self._hovered_payload = payload
                self.node_hovered.emit(payload, True)

            def leave_event(event, payload=payload):
                if self._hovered_payload is payload:
                    self._hovered_payload = None
                self.node_hovered.emit(payload, False)

            w.enterEvent = enter_event
            w.leaveEvent = leave_event

        return w, lbl

    def _top_level_item_for(self, node_id: str) -> QTreeWidgetItem | None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            node: ExplorerNode = item.data(0, _NODE_ROLE)
            if node is not None and node.id == node_id:
                return item
        return None

    def _update_counter(self, count: int):
        self.counter_label.setText(f"{count} elementos")
