"""RecordListColumn — a coluna esquerda usada pelas duas metades da tela
(LISTA DE CONSTRUÇÕES e LISTA DE DUNGEONS).

Diferente da EntityListColumn de Itens (uma tabela de 5 colunas), aqui cada
registro é um card: miniatura/emoji + nome + subtítulo, com a bolinha de
status à direita. O último card é sempre o "+ Novo", como na referência.
Filtragem e busca acontecem aqui dentro, então digitar não passa pelo painel
dono da lista.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QFrame, QScrollArea, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    _INPUT_STYLE, _no_wheel, panel_frame_style, sub_header, status_dot,
)

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


class _RecordCard(QFrame):
    """Uma linha da lista. `record` traz id/name/subtitle/icon/image/status.

    Aceita uma imagem arrastada do Explorer/Finder direto sobre o card
    (mesma ideia do IconButton dos editores) — emite `image_dropped` com o
    caminho local; quem é dono da lista decide onde persistir."""

    clicked = Signal(str)
    image_dropped = Signal(str, str)  # record id, caminho local
    delete_requested = Signal(str)

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self._id = record.get("id", "")
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAcceptDrops(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 10, 6)
        row.setSpacing(8)

        self._thumb = QLabel()
        self._thumb.setFixedSize(38, 38)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback_icon = record.get("icon") or "🏰"
        self._set_thumb_image(record.get("image") or "")
        row.addWidget(self._thumb)

        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(record.get("name") or "—")
        name.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        subtitle = QLabel(record.get("subtitle") or "")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        # Sem isso, um nome/subtítulo comprido teria minimumSizeHint igual
        # ao texto inteiro (QLabel sem word-wrap não elide) — numa coluna
        # estreita isso empurra os itens de tamanho fixo à direita (bolinha
        # de status, botão ✕) para fora da área visível do card em vez de
        # ceder espaço. QSizePolicy.Ignored faz o rótulo abrir mão do
        # próprio texto na hora de disputar espaço; ele só corta visualmente
        # (sem "…"), mas os botões fixos nunca mais somem.
        for lbl in (name, subtitle):
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        col.addWidget(name)
        col.addWidget(subtitle)
        row.addLayout(col, 1)

        if record.get("status"):
            row.addWidget(status_dot(record["status"]))

        delete_btn = QToolButton()
        delete_btn.setText("✕")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFixedSize(18, 18)
        delete_btn.setToolTip("Excluir")
        delete_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self._id))
        row.addWidget(delete_btn)

        self.set_selected(False)

    def _set_thumb_image(self, path: str):
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            self._thumb.setText(self._fallback_icon)
            self._thumb.setStyleSheet(
                f"background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE}; "
                f"border-radius: 8px; font-size: 18px;"
            )
        else:
            self._thumb.setText("")
            self._thumb.setPixmap(pixmap.scaled(
                38, 38, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation))
            self._thumb.setStyleSheet(f"border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px;")

    def record_id(self) -> str:
        return self._id

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self, drop: bool = False):
        if drop:
            border, bg = Colors.ACCENT, "rgba(79,195,247,0.15)"
        elif self._selected:
            border, bg = Colors.ACCENT, "rgba(79,195,247,0.12)"
        else:
            border, bg = Colors.BORDER_SUBTLE, "rgba(255,255,255,0.03)"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}"
            f"QFrame:hover {{ border-color: {Colors.ACCENT}; }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(event)

    # ── drag & drop ──

    def _accepted_path(self, mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(_IMAGE_EXTS):
                return path
        return None

    def dragEnterEvent(self, event):
        if self._accepted_path(event.mimeData()):
            self._refresh_style(drop=True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._refresh_style()

    def dropEvent(self, event):
        path = self._accepted_path(event.mimeData())
        self._refresh_style()
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        self._set_thumb_image(path)
        self.image_dropped.emit(self._id, path)


class _NewCard(QFrame):
    """O card "+ Novo …" fixo no fim da lista."""

    clicked = Signal()

    def __init__(self, title: str, hint: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.02); border: 1px dashed {Colors.BORDER}; "
            f"border-radius: 8px; }}"
            f"QFrame:hover {{ border-color: {Colors.ACCENT}; background: rgba(79,195,247,0.08); }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 10, 6)
        row.setSpacing(8)
        plus = QLabel("+")
        plus.setFixedSize(38, 38)
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 20px; font-weight: bold;")
        row.addWidget(plus)
        col = QVBoxLayout()
        col.setSpacing(1)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        sub = QLabel(hint)
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px;")
        col.addWidget(lbl)
        col.addWidget(sub)
        row.addLayout(col, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class RecordListColumn(QFrame):
    """Lista de cards com busca, filtros e o card de criação no fim."""

    selected = Signal(str)
    new_requested = Signal()
    image_dropped = Signal(str, str)  # record id, caminho local
    delete_requested = Signal(str)

    def __init__(
        self,
        title: str,
        search_hint: str,
        new_title: str,
        new_hint: str,
        filters: list[tuple[str, list[str], str]] | None = None,
        parent=None,
    ):
        """`filters` é [(placeholder, opções, chave do registro), ...] — os
        combos ficam abaixo da busca e filtram por igualdade naquela chave.
        A primeira opção de cada combo é o "todos" e nunca filtra."""
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Piso real: miniatura(38) + bolinha de status(~14) + botão ✕(18) +
        # espaçamentos/margens do card e da coluna (~44) + um mínimo de
        # espaço legível pro nome (~70) — abaixo disso o botão de excluir
        # fica sem onde desenhar mesmo com o QSizePolicy.Ignored do texto.
        self.setMinimumWidth(210)

        self._records: list[dict] = []
        self._cards: list[_RecordCard] = []
        self._selected_id = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(7)
        outer.addWidget(sub_header(title))

        self._search = QLineEdit()
        self._search.setPlaceholderText(f"🔍  {search_hint}")
        self._search.setFixedHeight(26)
        self._search.textChanged.connect(self._rebuild)
        outer.addWidget(self._search)

        self._filters: list[tuple[QComboBox, str]] = []
        if filters:
            frow = QHBoxLayout()
            frow.setSpacing(6)
            for placeholder, options, key in filters:
                combo = QComboBox()
                combo.addItem(placeholder)
                combo.addItems(options)
                combo.setFixedHeight(26)
                _no_wheel(combo)
                combo.currentIndexChanged.connect(self._rebuild)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                frow.addWidget(combo, 1)
                self._filters.append((combo, key))
            outer.addLayout(frow)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 5px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, 4, 0)
        self._list.setSpacing(6)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        self._new_card = _NewCard(new_title, new_hint)
        self._new_card.clicked.connect(self.new_requested.emit)

        self._empty = QLabel("Nenhum registro corresponde à busca.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")

    # ── API pública ──

    def set_records(self, records: list[dict]):
        self._records = records
        self._rebuild()

    def select(self, record_id: str):
        self._selected_id = record_id or ""
        for card in self._cards:
            card.set_selected(card.record_id() == self._selected_id)

    def current_id(self) -> str:
        return self._selected_id

    # ── interno ──

    def _matches(self, record: dict) -> bool:
        query = self._search.text().strip().lower()
        if query:
            haystack = f"{record.get('name', '')} {record.get('subtitle', '')} {record.get('code', '')}".lower()
            if query not in haystack:
                return False
        for combo, key in self._filters:
            if combo.currentIndex() > 0 and (record.get(key) or "") != combo.currentText():
                return False
        return True

    def _rebuild(self):
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget in (self._new_card, self._empty):
                # Reaproveitados a cada rebuild — só desanexar, não destruir.
                widget.setParent(None)
            elif widget is not None:
                widget.deleteLater()

        self._cards = []
        visible = [r for r in self._records if self._matches(r)]
        for record in visible:
            card = _RecordCard(record)
            card.clicked.connect(self._on_card_clicked)
            card.image_dropped.connect(self.image_dropped.emit)
            card.delete_requested.connect(self.delete_requested.emit)
            card.set_selected(card.record_id() == self._selected_id)
            self._list.addWidget(card)
            self._cards.append(card)

        if not visible:
            self._list.addWidget(self._empty)
            self._empty.show()

        self._list.addWidget(self._new_card)
        self._new_card.show()
        # Sem o stretch final o QVBoxLayout estica os cards para ocupar a
        # sobra de altura em vez de deixá-la em branco.
        self._list.addStretch()

    def _on_card_clicked(self, record_id: str):
        self.select(record_id)
        self.selected.emit(record_id)
