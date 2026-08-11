"""LoreEditorPanel — a coluna direita do painel Lore: cabeçalho (título
grande + ID + menu), Título/Categoria/Autor, Tags, Resumo e Conteúdo (rich
text). Ao contrário de QuestPropertiesPanel (uma barra lateral estreita com
3 cartões colapsáveis), esse é um único cartão ocupando a coluna inteira —
a imagem de referência do painel Lore mostra um único formulário, não vários
cartões empilhados.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QFrame, QSizePolicy, QToolButton, QMenu, QPushButton,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, combo_qss
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.shared.rich_text_editor import RichTextEditor
from src.layouts.panels.lore.constants import (
    _combo, _no_wheel, panel_frame_style, hrule, json_list,
    LORE_CATEGORIES, CATEGORY_LABELS,
)

_INPUT_STYLE = f"""
    QLineEdit, QTextEdit {{
        background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
        border-radius: 5px; padding: 5px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 11px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {Colors.ACCENT}; }}
    {combo_qss(padding="5px 8px", font_size=11)}
"""


class _TagChip(QFrame):
    removed = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text
        self.setStyleSheet(
            f"QFrame {{ background: rgba(79,195,247,0.12); border: 1px solid {Colors.ACCENT_DIM}; "
            f"border-radius: 9px; }} QLabel {{ background: transparent; border: none; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 4, 2)
        row.setSpacing(4)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 9px; font-weight: bold;")
        row.addWidget(lbl)
        close = QToolButton()
        close.setText("✕")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(14, 14)
        close.setStyleSheet(f"QToolButton {{ border: none; background: transparent; color: {Colors.ACCENT}; font-size: 8px; }}")
        close.clicked.connect(lambda: self.removed.emit(self._text))
        row.addWidget(close)

    def text(self) -> str:
        return self._text


def _field(label_text: str, widget: QWidget) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(3)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
    col.addWidget(lbl)
    col.addWidget(widget)
    return col


class LoreEditorPanel(QFrame):
    """Editor de uma entrada de Lore — sempre visível quando algo está
    selecionado na lista; desabilitado (set_empty) quando nada está."""

    changed = Signal()
    duplicate_requested = Signal()
    delete_requested = Signal()
    mention_clicked = Signal(str, str)  # entity_type, entity_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._loading = False
        self._tags: list[str] = []
        self._preview = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)

        outer.addLayout(self._build_header())
        outer.addWidget(hrule())
        outer.addLayout(self._build_fields())
        outer.addWidget(self._build_tags_section())
        outer.addLayout(_field("Resumo", self._build_summary()))
        outer.addLayout(self._build_content_section(), 1)

        for w in (self._title, self._category, self._author, self._summary):
            self._track(w)
        self._rich_text.changed.connect(self._on_field_changed)
        self._rich_text.mention_clicked.connect(self.mention_clicked.emit)

        self.set_empty()

    def set_mention_catalog(self, entries: list[dict]):
        self._rich_text.set_mention_catalog(entries)

    # ── cabeçalho ──

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        top = QHBoxLayout()
        self._heading = QLabel("NENHUM ELEMENTO")
        self._heading.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 18pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._heading.setWordWrap(True)
        top.addWidget(self._heading, 1)

        self._id_lbl = QLabel("")
        self._id_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        top.addWidget(self._id_lbl, 0, Qt.AlignmentFlag.AlignTop)

        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋮")
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 14px; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        self._menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("Duplicar", self.duplicate_requested.emit)
        menu.addAction("Excluir", self.delete_requested.emit)
        self._menu_btn.setMenu(menu)
        top.addWidget(self._menu_btn, 0, Qt.AlignmentFlag.AlignTop)
        col.addLayout(top)

        actions = QHBoxLayout()
        actions.addStretch()
        self._preview_btn = QPushButton("👁 Visualizar")
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.setCheckable(True)
        self._preview_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 6px 12px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
            QPushButton:checked {{ background: {Colors.ACCENT_DIM}; border-color: {Colors.ACCENT}; color: {Colors.ACCENT}; }}
        """)
        self._preview_btn.clicked.connect(self._on_toggle_preview)
        actions.addWidget(self._preview_btn)

        self._save_btn = QPushButton("💾 Salvar")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        # Salvar aqui é só um atalho manual pro autosave debounced que já
        # roda em background (ver panel.py) — força o timer a disparar já.
        self._save_btn.clicked.connect(self._on_field_changed)
        actions.addWidget(self._save_btn)
        col.addLayout(actions)
        return col

    def _build_fields(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self._title = QLineEdit()
        self._title.setPlaceholderText("Título da entrada")
        self._title.textChanged.connect(self._on_title_changed)
        row.addLayout(_field("Título", self._title), 2)

        self._category = _combo(CATEGORY_LABELS)
        _no_wheel(self._category)
        row.addLayout(_field("Categoria", self._category), 1)

        self._author = QLineEdit()
        self._author.setPlaceholderText("Autor")
        row.addLayout(_field("Autor", self._author), 1)
        return row

    def _build_tags_section(self) -> QWidget:
        section = QWidget()
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lbl = QLabel("Tags")
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        lay.addWidget(lbl)

        # _tag_input vive dentro do _tags_flow (inline com os chips),
        # não como widget separado no lay — _rebuild_tags o reposiciona
        # ao final dos chips a cada mudança.
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("+ Adicionar tag...")
        self._tag_input.setFixedWidth(150)
        self._tag_input.returnPressed.connect(self._on_add_tag)

        self._tags_holder = QWidget()
        self._tags_holder.setStyleSheet("background: transparent;")
        self._tags_flow = FlowLayout(self._tags_holder, spacing=4)
        self._tags_flow.addWidget(self._tag_input)
        lay.addWidget(self._tags_holder)
        return section

    def _build_summary(self) -> QTextEdit:
        self._summary = QTextEdit()
        self._summary.setFixedHeight(56)
        self._summary.setPlaceholderText("Um resumo curto desta entrada...")
        _no_wheel(self._summary)
        return self._summary

    def _build_content_section(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)
        lbl = QLabel("Conteúdo")
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        col.addWidget(lbl)
        self._rich_text = RichTextEditor()
        col.addWidget(self._rich_text, 1)
        return col

    # ── comportamento ──

    def _track(self, widget):
        for signal_name in ("textChanged", "currentTextChanged"):
            signal = getattr(widget, signal_name, None)
            if signal is not None:
                signal.connect(self._on_field_changed)
                break

    def _on_field_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    def _on_title_changed(self, text: str):
        self._heading.setText((text or "Nova Entrada").upper())
        self._on_field_changed()

    def _on_toggle_preview(self, checked: bool):
        self._preview = checked
        self._rich_text.set_preview_mode(checked)
        self._preview_btn.setText("✏ Editar" if checked else "👁 Visualizar")

    def _on_add_tag(self):
        text = self._tag_input.text().strip()
        self._tag_input.clear()
        if not text or text in self._tags:
            return
        self._tags.append(text)
        self._rebuild_tags()
        self._on_field_changed()

    def _on_remove_tag(self, text: str):
        self._tags = [t for t in self._tags if t != text]
        self._rebuild_tags()
        self._on_field_changed()

    def _rebuild_tags(self):
        # self._tag_input is a persistent widget re-added at the end of
        # every rebuild (not a per-tag chip) — deleteLater()'ing it here
        # like the chips below destroys the one QLineEdit instance the
        # class keeps reusing, so the very next rebuild's addWidget() below
        # (or the one after, once the deferred delete actually runs) hits a
        # RuntimeError: "already deleted" on it.
        while self._tags_flow.count():
            item = self._tags_flow.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._tag_input:
                widget.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag)
            chip.removed.connect(self._on_remove_tag)
            self._tags_flow.addWidget(chip)
        self._tags_flow.addWidget(self._tag_input)

    # ── API pública ──

    def set_id_label(self, code: str):
        self._id_lbl.setText(f"ID: {code}" if code else "")

    def set_empty(self):
        self._loading = True
        try:
            self._title.clear()
            self._category.setCurrentIndex(0)
            self._author.clear()
            self._tags = []
            self._rebuild_tags()
            self._summary.clear()
            self._rich_text.clear()
            self._heading.setText("NENHUM ELEMENTO")
            self._id_lbl.setText("")
        finally:
            self._loading = False
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._loading = True
        try:
            title = record.get("title") or ""
            self._title.setText(title)
            self._heading.setText((title or "Nova Entrada").upper())
            category = record.get("category") or ""
            idx = self._category.findText(category)
            self._category.setCurrentIndex(idx if idx >= 0 else 0)
            self._author.setText(record.get("author") or "")
            self._tags = list(json_list(record.get("tags_json")))
            self._rebuild_tags()
            self._summary.setPlainText(record.get("summary") or "")
            self._rich_text.set_html(record.get("content_html") or "")
            self.set_id_label(record.get("code") or "")
        finally:
            self._loading = False

    def collect(self) -> dict:
        return {
            "title": self._title.text().strip() or "Nova Entrada",
            "category": self._category.currentText(),
            "author": self._author.text().strip(),
            "tags_json": json.dumps(self._tags, ensure_ascii=False),
            "summary": self._summary.toPlainText(),
            "content_html": self._rich_text.to_html(),
        }
