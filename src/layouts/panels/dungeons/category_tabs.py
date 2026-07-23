"""CategoryTabBar — fileira de abas editáveis (criar/renomear/excluir) para
o filtro de Categoria (Construções) / Tipo (Dungeons), substituindo o
dropdown de lista fixa que existia antes.

Achatada, sem hierarquia — ao contrário do explorador de pastas de Mobs
(CategoryExplorerMixin), aqui não há aninhamento, só uma linha de pills.
Reaproveita _InlineNameEdit (mobs/panel_widgets.py) para o "+ criar" inline,
mesma ideia que "+ Nova categoria" de Mobs já usa.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy, QToolButton
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.mobs.panel_widgets import _InlineNameEdit

# Sentinela de "Todas" — nunca colide com um nome de categoria real.
ALL_KEY = ""


class _Pill(QWidget):
    """Uma aba clicável. `editable=False` (a pill "Todas") não abre menu de
    contexto nem pode ser renomeada/excluída."""

    clicked = Signal(str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)

    def __init__(self, key: str, icon: str, label: str, editable: bool, parent=None):
        super().__init__(parent)
        self._key = key
        self._selected = False
        self.setObjectName("catPill")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(10, 4, 10, 4)
        self._row.setSpacing(4)
        self._label = QLabel(f"{icon} {label}".strip())
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._row.addWidget(self._label)

        self._rename_edit: _InlineNameEdit | None = None
        self._close_btn: QToolButton | None = None
        if editable:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._open_menu)
            # Um "✕" sempre visível — o menu de contexto (clique direito)
            # sozinho não é descoberto por ninguém; excluir precisa de um
            # alvo de clique óbvio, igual ⋮ nas pastas de Mobs.
            self._close_btn = QToolButton()
            self._close_btn.setText("✕")
            self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._close_btn.setFixedSize(14, 14)
            self._close_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 9px; }}
                QToolButton:hover {{ color: {Colors.ERROR}; }}
            """)
            self._close_btn.clicked.connect(lambda: self.delete_requested.emit(self._key))
            self._row.addWidget(self._close_btn)

        self._refresh_style()

    def key(self) -> str:
        return self._key

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        # Estilo de aba de navegador: cantos arredondados só em cima, sem
        # fundo em bolha — a aba ativa "gruda" na barrinha de destaque
        # (border-bottom colorida) em vez de virar um chip isolado.
        if self._selected:
            self.setStyleSheet(f"""
                QWidget#catPill {{ background: rgba(79,195,247,0.10);
                    border: none; border-bottom: 2px solid {Colors.ACCENT};
                    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
                QLabel {{ color: {Colors.ACCENT}; font-size: 9px; font-weight: bold; background: transparent; border: none; }}
            """)
        else:
            self.setStyleSheet(f"""
                QWidget#catPill {{ background: transparent;
                    border: none; border-bottom: 2px solid transparent;
                    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
                QWidget#catPill:hover {{ background: rgba(255,255,255,0.05); }}
                QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 9px; font-weight: bold; background: transparent; border: none; }}
            """)

    def _open_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("✏ Renomear", self._begin_rename)
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self._key))
        menu.exec(self.mapToGlobal(pos))

    def _begin_rename(self):
        if self._rename_edit is None:
            self._rename_edit = _InlineNameEdit(self)
            self._rename_edit.setFixedWidth(110)
            self._rename_edit.setStyleSheet(f"""
                QLineEdit {{ background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                    border-radius: 4px; padding: 0 4px; color: {Colors.TEXT_PRIMARY}; font-size: 9px; }}
            """)
            self._rename_edit.confirmed.connect(self._confirm_rename)
            self._rename_edit.cancelled.connect(self._cancel_rename)
            self._row.insertWidget(0, self._rename_edit)
            self._rename_edit.setVisible(False)
        self._rename_edit.setText(self._label.text().split(" ", 1)[-1])
        self._label.setVisible(False)
        self._rename_edit.setVisible(True)
        self._rename_edit.setFocus()
        self._rename_edit.selectAll()

    def _confirm_rename(self):
        new_name = self._rename_edit.text().strip()
        self._rename_edit.setVisible(False)
        self._label.setVisible(True)
        if new_name and new_name != self._key:
            self.rename_requested.emit(self._key, new_name)

    def _cancel_rename(self):
        self._rename_edit.setVisible(False)
        self._label.setVisible(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


class CategoryTabBar(QWidget):
    """Fileira horizontal e rolável de abas + pill "+ criar" no fim."""

    selected = Signal(str)              # "" = Todas
    create_requested = Signal(str)      # nome da nova categoria
    rename_requested = Signal(str, str)  # nome antigo, nome novo
    delete_requested = Signal(str)      # nome

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._current = ALL_KEY
        self._pills: list[_Pill] = []

        # A linha de baixo é a "base" da faixa de abas — igual à borda que
        # separa uma barra de abas de navegador do conteúdo abaixo; a aba
        # selecionada não tem essa borda (ela funde com a barrinha de
        # destaque desenhada em cada _Pill), só as inativas mostram a base.
        self.setStyleSheet(f"border-bottom: 1px solid {Colors.BORDER_SUBTLE};")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(30)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # AsNeeded, não AlwaysOff: com o scroll desligado e
        # widgetResizable=True, o Qt força a fileira de abas a caber no
        # viewport comprimindo cada pill abaixo do tamanho natural (mesmo
        # bug do card da lista) em vez de aparar com rolagem — igual a
        # abas demais num navegador, o certo é rolar, não espremer.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._row = QHBoxLayout(holder)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(2)
        scroll.setWidget(holder)
        outer.addWidget(scroll)

        self._all_pill = _Pill(ALL_KEY, "", "Todas", editable=False)
        self._all_pill.clicked.connect(self._on_pill_clicked)
        self._all_pill.set_selected(True)
        self._row.addWidget(self._all_pill)
        self._pills.append(self._all_pill)

        self._add_edit = _InlineNameEdit()
        self._add_edit.setPlaceholderText("Nova categoria...")
        self._add_edit.setFixedWidth(110)
        self._add_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.ACCENT};
                border-radius: 12px; padding: 3px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 9px; }}
        """)
        self._add_edit.setVisible(False)
        self._add_edit.confirmed.connect(self._confirm_add)
        self._add_edit.cancelled.connect(self._cancel_add)

        self._add_pill = _Pill("__add__", "", "+", editable=False)
        self._add_pill.clicked.connect(self._begin_add)

    # ── API pública ──

    def set_categories(self, categories: list[dict]):
        """`categories` — dicts com id/name/icon, já ordenados."""
        while self._row.count():
            self._row.takeAt(0)
        for pill in self._pills[1:]:
            pill.deleteLater()
        self._pills = [self._all_pill]
        self._row.addWidget(self._all_pill)

        for cat in categories:
            pill = _Pill(cat["name"], cat.get("icon") or "", cat["name"], editable=True)
            pill.clicked.connect(self._on_pill_clicked)
            pill.rename_requested.connect(self._on_rename)
            pill.delete_requested.connect(self.delete_requested.emit)
            pill.set_selected(cat["name"] == self._current)
            self._row.addWidget(pill)
            self._pills.append(pill)

        self._row.addWidget(self._add_edit)
        self._row.addWidget(self._add_pill)
        self._row.addStretch()
        self._all_pill.set_selected(self._current == ALL_KEY)

    def current(self) -> str:
        return self._current

    # ── interno ──

    def _on_pill_clicked(self, key: str):
        self._current = key
        for pill in self._pills:
            pill.set_selected(pill.key() == key)
        self.selected.emit(key)

    def _begin_add(self):
        self._add_pill.setVisible(False)
        self._add_edit.clear()
        self._add_edit.setVisible(True)
        self._add_edit.setFocus()

    def _confirm_add(self):
        name = self._add_edit.text().strip()
        self._add_edit.setVisible(False)
        self._add_pill.setVisible(True)
        if name:
            self.create_requested.emit(name)

    def _cancel_add(self):
        self._add_edit.setVisible(False)
        self._add_pill.setVisible(True)

    def _on_rename(self, old_name: str, new_name: str):
        self.rename_requested.emit(old_name, new_name)
