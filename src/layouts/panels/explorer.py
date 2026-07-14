"""2. Explorer (painel) + 2.1 Filtros Rápidos (painel separado)."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget, QScrollArea,
    QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Metrics, Typography


# ─── Glass Paint Helper ────────────────────────────────────────────────────

def _paint_glass(widget, event, radius=12):
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = widget.width(), widget.height()
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.fillPath(path, QColor(11, 25, 41, 200))
    grad = QLinearGradient(0, 0, 0, h * 0.25)
    grad.setColorAt(0.0, QColor(255, 255, 255, 10))
    grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(grad))
    p.setPen(QPen(QColor(255, 255, 255, 30), 1))
    p.drawPath(path)
    p.end()


# ─── Filter Chip ───────────────────────────────────────────────────────────

class _FilterChip(QToolButton):
    filter_toggled = Signal(str, bool)

    def __init__(self, icon: str, label: str, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self.setText(f"{icon} {label}")
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setFixedHeight(26)
        self.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 13px;
                font-size: {Typography.SIZE_XXS}px;
                color: {Colors.TEXT_SECONDARY};
                padding: 3px 10px;
                background: transparent;
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER};
                border-color: {Colors.BORDER_HOVER};
            }}
            QToolButton:checked {{
                color: {Colors.ACCENT};
                background: {Colors.ACCENT_DIM};
                border-color: {Colors.ACCENT};
            }}
        """)
        self.toggled.connect(lambda checked: self.filter_toggled.emit(self._key, checked))


# ─── 2.1 Filter Panel (painel independente) ───────────────────────────────

class FilterPanel(QFrame):
    """2.1 Filtros Rápidos — painel independente com chips."""

    filter_toggled = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("⚡ Filtros Rápidos")
        header.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_MUTED}; background: transparent; border: none;
        """)
        header_row.addWidget(header)
        header_row.addStretch()

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
        header_row.addWidget(self._toggle_all)
        layout.addLayout(header_row)

        # Chips
        grid = QGridLayout()
        grid.setSpacing(4)

        categories = [
            ("👹", "Mobs", "Mobs"), ("🧙", "NPCs", "NPCs"),
            ("📜", "Quests", "Quests"), ("⚔", "Itens", "Itens"),
            ("💀", "Bosses", "Bosses"), ("⚡", "Eventos", "Eventos"),
            ("💎", "Recursos", "Recursos"), ("🌿", "Vegetação", "Vegetação"),
            ("⛏", "Minérios", "Minérios"), ("🏴", "PvP", "PvP"),
        ]

        self._chips = []
        for i, (icon, label, key) in enumerate(categories):
            chip = _FilterChip(icon, label, key)
            chip.filter_toggled.connect(self.filter_toggled.emit)
            grid.addWidget(chip, i // 2, i % 2)
            self._chips.append(chip)

        layout.addLayout(grid)
        self._toggle_all.clicked.connect(self._on_toggle_all)

    def _on_toggle_all(self):
        all_checked = all(c.isChecked() for c in self._chips)
        for chip in self._chips:
            chip.setChecked(not all_checked)

    def paintEvent(self, event):
        _paint_glass(self, event, radius=10)


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

class ExplorerPanel(QFrame):
    """2. Explorer — toolbar + busca + árvore + contador."""

    region_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar vertical
        self.toolbar = ExplorerToolbar()
        main_layout.addWidget(self.toolbar)

        # Conteúdo
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 8)
        content_layout.setSpacing(8)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("🌍 Explorer")
        title.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        header_row.addWidget(title)
        header_row.addStretch()

        self.counter_label = QLabel("0 elementos")
        self.counter_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
            background: rgba(10,16,30,0.5); border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 10px; padding: 2px 8px;
        """)
        header_row.addWidget(self.counter_label)
        content_layout.addLayout(header_row)

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

        main_layout.addWidget(content, 1)

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

    def paintEvent(self, event):
        _paint_glass(self, event, radius=12)

    def _make_item_widget(self, item: QTreeWidgetItem, text: str, is_parent: bool = False, level: int = 0):
        """Cria widget com indentação + triângulo (se pai) + texto + botão X."""
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
            # Linha de conexão para filhos
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
