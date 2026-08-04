"""ContentTabBar — fileira horizontal e estática de abas de conteúdo (Fluxo/
Geral/Objetivos/.../Notas) no meio do painel de Quests.

Visualmente é a mesma "aba de navegador" de CategoryTabBar (dungeons/
category_tabs.py) — borda inferior colorida na aba ativa, sem fundo em
bolha — mas sem criar/renomear/excluir: essa fileira é uma lista fixa de
seções do editor, não uma categoria editável pelo usuário.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QScrollArea, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors


class _TabPill(QWidget):
    clicked = Signal(str)

    def __init__(self, key: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._selected = False
        self.setObjectName("contentTabPill")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(4)
        text = QLabel(f"{icon}  {label}".strip())
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(text)
        self._refresh_style()

    def key(self) -> str:
        return self._key

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QWidget#contentTabPill {{ background: rgba(79,195,247,0.10);
                    border: none; border-bottom: 2px solid {Colors.ACCENT};
                    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
                QLabel {{ color: {Colors.ACCENT}; font-size: 10px; font-weight: bold; background: transparent; border: none; }}
            """)
        else:
            self.setStyleSheet(f"""
                QWidget#contentTabPill {{ background: transparent;
                    border: none; border-bottom: 2px solid transparent;
                    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
                QWidget#contentTabPill:hover {{ background: rgba(255,255,255,0.05); }}
                QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold; background: transparent; border: none; }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


class ContentTabBar(QWidget):
    """`tabs` é [(key, icon, label), ...], ordem de exibição."""

    selected = Signal(str)

    def __init__(self, tabs: list[tuple[str, str, str]], parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"border-bottom: 1px solid {Colors.BORDER_SUBTLE};")
        self._pills: list[_TabPill] = []
        self._current = tabs[0][0] if tabs else ""

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(32)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        for key, icon, label in tabs:
            pill = _TabPill(key, icon, label)
            pill.clicked.connect(self._on_pill_clicked)
            pill.set_selected(key == self._current)
            row.addWidget(pill)
            self._pills.append(pill)
        row.addStretch()

        scroll.setWidget(holder)
        outer.addWidget(scroll)

    def current(self) -> str:
        return self._current

    def _on_pill_clicked(self, key: str):
        self._current = key
        for pill in self._pills:
            pill.set_selected(pill.key() == key)
        self.selected.emit(key)
