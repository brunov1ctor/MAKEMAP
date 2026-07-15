"""2. Explorer (painel) + 2.1 Filtros Rápidos (painel separado)."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Metrics, Typography
from src.components.collapsible_panel import CollapsiblePanel
from src.layouts.panels.brush_panel import FlowLayout


# ─── Filter Chip ───────────────────────────────────────────────────────────

class _FilterChip(QFrame):
    filter_toggled = Signal(str, bool)

    def __init__(self, icon: str, label: str, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._checked = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 8, 2)
        layout.setSpacing(4)

        self._box = QLabel("✓")
        self._box.setFixedSize(16, 16)
        self._box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_box_style()
        layout.addWidget(self._box)

        lbl = QLabel(f"{icon} {label}")
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px;
            color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        layout.addWidget(lbl)

    def _update_box_style(self):
        if self._checked:
            self._box.setStyleSheet(f"""
                background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
                border-radius: 3px; color: #ffffff; font-size: 10px; font-weight: bold;
            """)
            self._box.setText("✓")
        else:
            self._box.setStyleSheet(f"""
                background: transparent; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 3px; color: transparent; font-size: 10px;
            """)
            self._box.setText("")

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._update_box_style()
        self.filter_toggled.emit(self._key, self._checked)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        self._checked = checked
        self._update_box_style()


# ─── 2.1 Filter Panel ─────────────────────────────────────────────────────

class FilterPanel(CollapsiblePanel):
    """2.1 Filtros Rápidos — painel colapsável com chips."""

    filter_toggled = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(title="Filtros Rápidos", icon="⚡", parent=parent, radius=10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Toggle all button no header
        self._toggle_all = QToolButton()
        self._toggle_all.setText("Todos")
        self._toggle_all.setFixedHeight(18)
        self._toggle_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_all.setStyleSheet(f"""
            QToolButton {{
                border: none; font-size: 8px; color: {Colors.ACCENT};
                padding: 2px 6px; border-radius: 4px; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.ACCENT_DIM}; }}
        """)
        # Inserir antes da seta no header
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, self._toggle_all)

        # Chips in flow layout
        flow = FlowLayout(spacing=2)

        categories = [
            ("👹", "Mobs", "Mobs"), ("🧙", "NPCs", "NPCs"),
            ("📜", "Quests", "Quests"), ("⚔", "Itens", "Itens"),
            ("💀", "Bosses", "Bosses"), ("⚡", "Eventos", "Eventos"),
            ("💎", "Recursos", "Recursos"), ("🌿", "Vegetação", "Vegetação"),
            ("⛏", "Minérios", "Minérios"), ("🏴", "PvP", "PvP"),
        ]

        self._chips = []
        for icon, label, key in categories:
            chip = _FilterChip(icon, label, key)
            chip.filter_toggled.connect(self.filter_toggled.emit)
            flow.addWidget(chip)
            self._chips.append(chip)

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent; border: none;")
        grid_widget.setLayout(flow)
        self.content_layout.addWidget(grid_widget)

        self._toggle_all.clicked.connect(self._on_toggle_all)

    def _on_toggle_all(self):
        all_checked = all(c.isChecked() for c in self._chips)
        for chip in self._chips:
            chip.setChecked(not all_checked)


# ─── Explorer Toolbar ──────────────────────────────────────────────────────

class ExplorerToolbar(QFrame):
    """Barra vertical de ferramentas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(Metrics.TOOLBAR_WIDTH)
        self.setStyleSheet(f"""
            ExplorerToolbar {{
                background: {Colors.GLASS_BG_STRONG};
                border-right: 1px solid {Colors.BORDER_SUBTLE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(4)

        actions = [
            ("👑", "Criar Reino"), ("🗺", "Nova Região"),
            ("📥", "Importar"), ("📤", "Exportar"),
            ("⭐", "Favoritos"), ("🔗", "Conexões"), ("📂", "Organizar"),
        ]

        for icon, tip in actions:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; border-radius: 6px;
                    font-size: 13px; color: {Colors.TEXT_MUTED}; background: transparent;
                }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            """)
            layout.addWidget(btn)

        layout.addStretch()

        self.btn_expand = QToolButton()
        self.btn_expand.setText("⊞")
        self.btn_expand.setToolTip("Expandir Tudo")
        self.btn_expand.setFixedSize(28, 28)
        self.btn_expand.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 6px; font-size: 13px; color: {Colors.TEXT_MUTED}; }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        layout.addWidget(self.btn_expand)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setText("⊟")
        self.btn_collapse.setToolTip("Recolher Tudo")
        self.btn_collapse.setFixedSize(28, 28)
        self.btn_collapse.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 6px; font-size: 13px; color: {Colors.TEXT_MUTED}; }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        layout.addWidget(self.btn_collapse)


# ─── 2. Explorer Panel ─────────────────────────────────────────────────────

class ExplorerPanel(CollapsiblePanel):
    """2. Explorer — toolbar + busca + árvore + contador."""

    region_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(title="Explorer", icon="🌍", parent=parent, radius=12)

        # Alterar título para tamanho maior
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)

        # Counter no header
        self.counter_label = QLabel("0 elementos")
        self.counter_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
            background: rgba(10,16,30,0.5); border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 10px; padding: 2px 8px;
        """)
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, self.counter_label)

        # Conteúdo principal com toolbar lateral
        body = QWidget()
        body.setStyleSheet("background: transparent; border: none;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Toolbar vertical
        self.toolbar = ExplorerToolbar()
        body_layout.addWidget(self.toolbar)

        # Conteúdo direito
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 4, 4, 4)
        content_layout.setSpacing(8)

        # Busca
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Buscar região...")
        self.search.setFixedHeight(30)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(10,16,30,0.7);
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 8px; padding: 0 12px;
                font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        content_layout.addWidget(self.search)

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
                font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_SECONDARY}; outline: none;
            }}
            QTreeWidget::item {{ padding: 3px 4px; border-radius: 6px; margin: 1px 0; }}
            QTreeWidget::item:hover {{ background: {Colors.PANEL_HOVER}; }}
            QTreeWidget::item:selected {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; }}
            QTreeWidget::branch {{ background: transparent; border: none; }}
        """)
        self._populate_placeholder()
        content_layout.addWidget(self.tree, 1)

        # Botão Nova Região
        add_btn = QToolButton()
        add_btn.setText("+ Nova Região")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QToolButton {{
                color: {Colors.ACCENT}; font-size: {Typography.SIZE_XS}px;
                font-weight: {Typography.WEIGHT_BOLD};
                border: 1px dashed {Colors.ACCENT}; border-radius: 8px;
                padding: 6px; background: {Colors.ACCENT_DIM};
            }}
            QToolButton:hover {{ background: {Colors.ACCENT_GLOW}; border-style: solid; }}
        """)
        content_layout.addWidget(add_btn)

        body_layout.addWidget(content, 1)
        self.content_layout.addWidget(body)

        # Connections
        self.toolbar.btn_expand.clicked.connect(self.tree.expandAll)
        self.toolbar.btn_collapse.clicked.connect(self.tree.collapseAll)
        self._update_counter()

    def _delete_item(self, item: QTreeWidgetItem):
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
        self._update_counter()

    def _make_item_widget(self, item: QTreeWidgetItem, text: str, is_parent: bool = False, level: int = 0):
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(w)
        indent = level * 16
        row.setContentsMargins(indent, 0, 4, 0)
        row.setSpacing(4)

        if is_parent:
            arrow = QToolButton()
            arrow.setText("▼")
            arrow.setFixedSize(16, 16)
            arrow.setCursor(Qt.CursorShape.PointingHandCursor)
            arrow.setStyleSheet(f"""
                QToolButton {{
                    border: none; font-size: 8px;
                    color: {Colors.TEXT_MUTED}; background: transparent;
                }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            """)
            def toggle_expand(checked, it=item, btn=arrow):
                if it.isExpanded():
                    it.setExpanded(False)
                    btn.setText("▶")
                else:
                    it.setExpanded(True)
                    btn.setText("▼")
            arrow.clicked.connect(toggle_expand)
            row.addWidget(arrow)
        else:
            connector = QLabel("└")
            connector.setFixedWidth(12)
            connector.setStyleSheet(f"""
                font-size: 10px; color: rgba(255,255,255,0.2);
                background: transparent; border: none;
            """)
            row.addWidget(connector)

        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        row.addWidget(lbl, 1)

        btn_x = QToolButton()
        btn_x.setText("✕")
        btn_x.setFixedSize(18, 18)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 9px; font-size: 10px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        btn_x.clicked.connect(lambda: self._delete_item(item))
        row.addWidget(btn_x)

        return w

    def _populate_placeholder(self):
        data = {
            "👑 Reino da Luz": [
                ("🌲", "Floresta do Amanhecer", "Lv 1-10"),
                ("🏔", "Vale do Eco", "Lv 10-20"),
                ("🏰", "Cidade de Eldoria", "Lv 15-25"),
            ],
            "👑 Reino das Sombras": [
                ("🌿", "Pântano das Almas", "Lv 20-30"),
                ("🏯", "Fortaleza Negra", "Lv 30-40"),
            ],
            "👑 Reino do Fogo": [
                ("🌋", "Montanhas Ardentes", "Lv 40-50"),
                ("🏜", "Deserto de Cinzas", "Lv 50-60"),
            ],
            "👑 Reino da Água": [
                ("🏖", "Costa Esmeralda", "Lv 60-70"),
                ("🏝", "Ilhas Flutuantes", "Lv 70-80"),
            ],
        }
        for kingdom, regions in data.items():
            k_item = QTreeWidgetItem(self.tree)
            k_item.setExpanded(True)
            self.tree.setItemWidget(k_item, 0, self._make_item_widget(k_item, kingdom, is_parent=True, level=0))
            for icon, name, level in regions:
                child = QTreeWidgetItem(k_item)
                self.tree.setItemWidget(child, 0, self._make_item_widget(child, f"{icon} {name}  [{level}]", level=1))

    def _update_counter(self):
        count = 0
        def _count(item):
            nonlocal count
            count += 1
            for i in range(item.childCount()):
                _count(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            _count(self.tree.topLevelItem(i))
        self.counter_label.setText(f"{count} elementos")
