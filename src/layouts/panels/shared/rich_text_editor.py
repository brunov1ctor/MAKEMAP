"""RichTextEditor — a QTextEdit with a real formatting toolbar (bold/italic/
underline/strike, lists, alignment, link, image, code block, quote, table,
undo/redo), first built for the Lore panel's "Conteúdo" field. No such
widget existed anywhere in the app before — every other multi-line field
(Descrição/Notas/Scripts/...) is a plain QTextEdit with no formatting at
all. Everything here is implemented on top of Qt's own rich-text stack
(QTextCursor/QTextCharFormat/QTextDocument) — no third-party dependency.
"""

from __future__ import annotations

import base64

from PySide6.QtCore import QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QTextCharFormat, QTextCursor,
    QTextDocument, QTextListFormat, QTextTableFormat,
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from src.styles.tokens import Colors, combo_qss
from src.layouts.panel_manager import paint_glass_panel

_MENTION_PREFIX = "mention://"

_BLOCK_STYLES = ["Normal", "Título 1", "Título 2", "Título 3", "Citação"]
_HEADING_SIZES = {"Título 1": 20, "Título 2": 16, "Título 3": 13}

_TOOLBAR_BTN_STYLE = f"""
    QToolButton {{
        background: transparent; border: none; border-radius: 4px;
        color: {Colors.TEXT_SECONDARY}; font-size: 11px; padding: 4px 7px;
    }}
    QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
    QToolButton:checked {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; }}
"""

_COMBO_STYLE = combo_qss(padding="3px 8px")


def _sep() -> QWidget:
    line = QWidget()
    line.setFixedWidth(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE};")
    return line


class _MentionPopup(QWidget):
    """Popup de autocomplete do '@' — estilo Teams/Slack:
    - Não rouba o foco do editor (WA_ShowWithoutActivating)
    - Campo de busca próprio dentro do popup
    - Navegação por teclado (cima/baixo/enter/esc)
    - Fecha ao clicar fora"""

    picked = Signal(dict)
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # não rouba foco
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Campo de busca interno — recebe o foco e o texto digitado após '@'
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar...")
        self._search.setFixedHeight(26)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.08); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 2px 8px;
                color: {Colors.TEXT_PRIMARY}; font-size: 11px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._search.textChanged.connect(self._on_search_changed)
        self._search.installEventFilter(self)
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.setFixedWidth(260)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none;
                color: {Colors.TEXT_PRIMARY}; font-size: 11px; outline: none; }}
            QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}
            QListWidget::item:selected {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT}; }}
        """)
        self._list.itemClicked.connect(lambda item: self.picked.emit(item.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self._list)

        self._all_entries: list[dict] = []

    def paintEvent(self, event):
        paint_glass_panel(self, radius=10)

    def eventFilter(self, obj, event):
        """Intercepta teclas no campo de busca para navegar a lista."""
        from PySide6.QtCore import QEvent
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                entry = self.confirm()
                if entry:
                    self.picked.emit(entry)
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def set_entries(self, entries: list[dict]):
        self._all_entries = entries
        self._apply_filter(self._search.text())

    def _on_search_changed(self, text: str):
        self._apply_filter(text)

    def _apply_filter(self, query: str):
        self._list.clear()
        q = query.strip().lower()
        filtered = [e for e in self._all_entries if not q or q in (e.get("name") or "").lower()][:20]
        for entry in filtered:
            item = QListWidgetItem(f"{entry.get('icon', '')}  {entry.get('name', '')}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._list.addItem(item)
        if filtered:
            self._list.setCurrentRow(0)
        row_h = self._list.sizeHintForRow(0) if filtered else 28
        list_h = min(200, row_h * max(1, len(filtered)) + 8)
        self.setFixedSize(272, list_h + self._search.height() + 20)

    def _move_selection(self, delta: int):
        row = self._list.currentRow()
        self._list.setCurrentRow(max(0, min(self._list.count() - 1, row + delta)))

    # mantido para compatibilidade com _handle_mention_popup_key
    def move_selection(self, delta: int):
        self._move_selection(delta)

    def confirm(self) -> dict | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def focus_search(self):
        """Dá foco ao campo de busca interno."""
        self._search.setFocus()
        self._search.clear()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()


class _MentionTextEdit(QTextEdit):
    """QTextEdit that reports "@" keypresses and clicks on a
    `mention://type/id` anchor back to its owning RichTextEditor — kept as
    a real subclass (not a monkeypatch) since it needs to intercept
    keyPressEvent to drive the popup's keyboard navigation."""

    mention_clicked = Signal(str, str)  # entity_type, entity_id

    def __init__(self, owner: "RichTextEditor", parent=None):
        super().__init__(parent)
        self._owner = owner

    def keyPressEvent(self, event):
        if self._owner._handle_mention_popup_key(event):
            return
        if self._owner._mention_popup_open():
            # Enquanto o popup está aberto, backspace e caracteres imprimíveis
            # vão para o campo de busca do popup, não para o editor.
            key = event.key()
            if key == Qt.Key.Key_Backspace or (event.text() and event.text().isprintable()):
                self._owner._forward_key_to_popup(event)
                return
        super().keyPressEvent(event)
        if event.text() == "@":
            self._owner._open_mention_popup()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # A bare click on a mention always jumps to that entity's own
            # panel — same as clicking a link. Cursor placement right at
            # its edges still works fine (anchorAt only matches within the
            # mention's own text span), so editing around it isn't blocked.
            anchor = self.anchorAt(event.position().toPoint())
            if anchor.startswith(_MENTION_PREFIX):
                entity_type, entity_id = anchor[len(_MENTION_PREFIX):].split("/", 1)
                self.mention_clicked.emit(entity_type, entity_id)
                return
        super().mousePressEvent(event)


class RichTextEditor(QWidget):
    """Toolbar + QTextEdit. `to_html()`/`set_html()` for persistence,
    `changed` fires on every edit (debounce it same as any other field —
    see the panel's own autosave timer)."""

    changed = Signal()
    mention_clicked = Signal(str, str)  # entity_type, entity_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._catalog: list[dict] = []
        self._mention_popup: _MentionPopup | None = None
        self._mention_anchor_pos: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._toolbar_row = QHBoxLayout()
        self._toolbar_row.setSpacing(2)
        outer.addLayout(self._toolbar_row)

        self._body = _MentionTextEdit(owner=self)
        self._body.setAcceptRichText(True)
        self._body.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 10px; color: {Colors.TEXT_PRIMARY}; font-size: 12px;
            }}
            QTextEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._body.textChanged.connect(self.changed.emit)
        self._body.currentCharFormatChanged.connect(self._sync_toggle_buttons)
        self._body.mention_clicked.connect(self.mention_clicked.emit)
        outer.addWidget(self._body, 1)

        self._build_toolbar()

    # ── toolbar construction ──

    def _build_toolbar(self):
        self._block_combo = QComboBox()
        self._block_combo.addItems(_BLOCK_STYLES)
        self._block_combo.setStyleSheet(_COMBO_STYLE)
        self._block_combo.setFixedWidth(90)
        self._block_combo.activated.connect(self._on_block_style)
        self._toolbar_row.addWidget(self._block_combo)
        self._toolbar_row.addWidget(_sep())

        self._bold_btn = self._add_toggle("B", "Negrito", self._toggle_bold)
        self._italic_btn = self._add_toggle("I", "Itálico", self._toggle_italic)
        self._underline_btn = self._add_toggle("U", "Sublinhado", self._toggle_underline)
        self._strike_btn = self._add_toggle("S", "Tachado", self._toggle_strike)
        self._toolbar_row.addWidget(_sep())

        self._add_action("≡•", "Lista com marcadores", lambda: self._apply_list(QTextListFormat.Style.ListDisc))
        self._add_action("≡1.", "Lista numerada", lambda: self._apply_list(QTextListFormat.Style.ListDecimal))
        self._toolbar_row.addWidget(_sep())

        self._add_action("⯇", "Alinhar à esquerda", lambda: self._body.setAlignment(Qt.AlignmentFlag.AlignLeft))
        self._add_action("≣", "Centralizar", lambda: self._body.setAlignment(Qt.AlignmentFlag.AlignHCenter))
        self._add_action("⯈", "Alinhar à direita", lambda: self._body.setAlignment(Qt.AlignmentFlag.AlignRight))
        self._toolbar_row.addWidget(_sep())

        self._add_action("🔗", "Link", self._insert_link)
        self._add_action("🖼", "Imagem", self._insert_image)
        self._add_action("</>", "Bloco de código", self._insert_code_block)
        self._add_action("❝", "Citação", self._insert_quote)
        self._add_action("▦", "Tabela", self._insert_table)
        self._toolbar_row.addWidget(_sep())

        self._undo_btn = self._add_action("↶", "Desfazer", self._body.undo)
        self._redo_btn = self._add_action("↷", "Refazer", self._body.redo)
        self._undo_btn.setEnabled(False)
        self._redo_btn.setEnabled(False)
        self._body.undoAvailable.connect(self._undo_btn.setEnabled)
        self._body.redoAvailable.connect(self._redo_btn.setEnabled)

        self._toolbar_row.addStretch()

    def _add_action(self, glyph: str, tooltip: str, slot) -> QToolButton:
        btn = QToolButton()
        btn.setText(glyph)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(_TOOLBAR_BTN_STYLE)
        btn.clicked.connect(slot)
        self._toolbar_row.addWidget(btn)
        return btn

    def _add_toggle(self, glyph: str, tooltip: str, slot) -> QToolButton:
        btn = self._add_action(glyph, tooltip, slot)
        btn.setCheckable(True)
        return btn

    # ── formatting actions ──

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        is_bold = int(self._body.fontWeight()) > int(QFont.Weight.Normal)
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self._body.mergeCurrentCharFormat(fmt)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._body.fontItalic())
        self._body.mergeCurrentCharFormat(fmt)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._body.fontUnderline())
        self._body.mergeCurrentCharFormat(fmt)

    def _toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self._body.currentCharFormat().fontStrikeOut())
        self._body.mergeCurrentCharFormat(fmt)

    def _sync_toggle_buttons(self, fmt: QTextCharFormat):
        # Reflects the format AT THE CURSOR (or of the current selection's
        # start) in the toolbar's pressed state — same idea any WYSIWYG
        # editor uses so the buttons show what you'd get if you typed now.
        self._bold_btn.setChecked(int(fmt.fontWeight()) > int(QFont.Weight.Normal))
        self._italic_btn.setChecked(fmt.fontItalic())
        self._underline_btn.setChecked(fmt.fontUnderline())
        self._strike_btn.setChecked(fmt.fontStrikeOut())

    def _on_block_style(self, index: int):
        style = _BLOCK_STYLES[index]
        cursor = self._body.textCursor()
        if style == "Citação":
            self._insert_quote()
            return
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if style in _HEADING_SIZES else QFont.Weight.Normal)
        fmt.setFontPointSize(_HEADING_SIZES.get(style, 12))
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(fmt)
        self._body.mergeCurrentCharFormat(fmt)

    def _apply_list(self, style: QTextListFormat.Style):
        cursor = self._body.textCursor()
        list_fmt = QTextListFormat()
        list_fmt.setStyle(style)
        cursor.createList(list_fmt)

    def _insert_link(self):
        cursor = self._body.textCursor()
        default_text = cursor.selectedText() or "link"
        url, ok = QInputDialog.getText(self, "Link", "URL:")
        if not ok or not url:
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QColor(Colors.ACCENT))
        fmt.setFontUnderline(True)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            cursor.insertText(default_text, fmt)

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            return
        # Embedded as a base64 data: URI (not a resource keyed by the local
        # file path) so content_html stays fully self-contained — it still
        # renders correctly even if the original file gets moved/deleted or
        # the project opens on a different machine.
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        b64 = base64.b64encode(bytes(buffer.data())).decode("ascii")
        url = f"data:image/png;base64,{b64}"
        self._body.document().addResource(QTextDocument.ResourceType.ImageResource, url, image)
        self._body.textCursor().insertImage(url)

    def _insert_code_block(self):
        cursor = self._body.textCursor()
        text = cursor.selectedText() or "código"
        cursor.insertHtml(
            f"<pre style='font-family:Consolas,monospace; background:rgba(255,255,255,0.08); "
            f"padding:8px; border-radius:4px; color:{Colors.TEXT_PRIMARY};'>{text}</pre>"
        )

    def _insert_quote(self):
        cursor = self._body.textCursor()
        text = cursor.selectedText() or "citação"
        cursor.insertHtml(
            f"<blockquote style='border-left:3px solid {Colors.ACCENT}; margin-left:0; "
            f"padding-left:12px; color:{Colors.TEXT_SECONDARY}; font-style:italic;'>{text}</blockquote>"
        )

    def _insert_table(self):
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setBorderBrush(QColor(Colors.BORDER))
        fmt.setCellPadding(4)
        self._body.textCursor().insertTable(2, 2, fmt)

    # ── "@" mentions ──

    def set_mention_catalog(self, entries: list[dict]):
        """`entries`: [{"type", "id", "name", "icon"}, ...] — built by
        whoever owns this editor (it has the UnitOfWork; this widget stays
        entity-agnostic), e.g. LorePanel combining mobs/npcs/items/skills/
        quests/dungeons into one flat searchable list."""
        self._catalog = entries

    def _mention_popup_open(self) -> bool:
        return self._mention_popup is not None

    def _open_mention_popup(self):
        # Registra a posição do '@' para substituir ao confirmar
        self._mention_anchor_pos = self._body.textCursor().position() - 1
        popup = _MentionPopup(self)
        popup.set_entries(self._catalog)
        popup.picked.connect(self._commit_mention)
        popup.closed.connect(self._on_mention_popup_closed)
        self._mention_popup = popup
        self._position_mention_popup()
        popup.show()
        popup.focus_search()  # foco vai para o campo de busca interno

    def _forward_key_to_popup(self, event):
        """Repassa teclas de caractere digitadas no editor para o campo de
        busca do popup — backspace apaga o último char da busca, qualquer
        outro caractere imprimível é acrescentado."""
        if not self._mention_popup:
            return
        search = self._mention_popup._search
        key = event.key()
        if key == Qt.Key.Key_Backspace:
            text = search.text()
            search.setText(text[:-1])
        elif event.text() and event.text().isprintable():
            search.setText(search.text() + event.text())

    def _position_mention_popup(self):
        if not self._mention_popup:
            return
        self._mention_popup.move(self._body.mapToGlobal(self._body.cursorRect().bottomLeft()))

    def _handle_mention_popup_key(self, event) -> bool:
        """Called from _MentionTextEdit.keyPressEvent BEFORE the normal Qt
        handling — returning True means "consumed, don't edit the text"."""
        if not self._mention_popup_open():
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._close_mention_popup()
            return True
        if key == Qt.Key.Key_Down:
            self._mention_popup.move_selection(1)
            return True
        if key == Qt.Key.Key_Up:
            self._mention_popup.move_selection(-1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            entry = self._mention_popup.confirm()
            if entry:
                self._commit_mention(entry)
            else:
                self._close_mention_popup()
            return True
        return False

    def _commit_mention(self, entry: dict):
        if self._mention_anchor_pos is None:
            return
        cursor = self._body.textCursor()
        # Seleciona do '@' até a posição atual do cursor no editor
        cursor.setPosition(self._mention_anchor_pos)
        cursor.setPosition(self._body.textCursor().position(), QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(f"{_MENTION_PREFIX}{entry['type']}/{entry['id']}")
        fmt.setForeground(QColor(Colors.ACCENT))
        fmt.setFontUnderline(True)
        fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(entry.get("name", ""), fmt)
        # Reseta o formato para o que vier depois
        cursor.insertText(" ", QTextCharFormat())
        self._body.setTextCursor(cursor)
        self._body.setFocus()  # devolve foco ao editor
        self._close_mention_popup()

    def _on_mention_popup_closed(self):
        self._mention_popup = None
        self._mention_anchor_pos = None

    def _close_mention_popup(self):
        popup = self._mention_popup
        if popup:
            popup.hide()  # triggers hideEvent -> closed -> _on_mention_popup_closed (clears self._mention_popup)
            popup.deleteLater()

    # ── read-only / preview toggle ──

    def set_preview_mode(self, preview: bool):
        """"Visualizar" — read-only, toolbar hidden, so you can see exactly
        how the formatted text reads without risking an accidental edit."""
        self._body.setReadOnly(preview)
        for i in range(self._toolbar_row.count()):
            item = self._toolbar_row.itemAt(i)
            if item.widget():
                item.widget().setVisible(not preview)

    # ── API pública ──

    def to_html(self) -> str:
        return self._body.toHtml()

    def set_html(self, html: str):
        self._body.blockSignals(True)
        self._body.setHtml(html or "")
        self._body.blockSignals(False)

    def clear(self):
        self.set_html("")
