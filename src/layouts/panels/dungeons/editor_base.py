"""SectionEditor — a base dos dois painéis de detalhes da tela.

A referência desenhava "Geral / Progresso / Produção" e "Geral / Layout /
Encontros / Chefes" como abas; aqui cada uma dessas divisões é uma seção
recolhível empilhada numa coluna rolável. Vantagem prática: dá para ver
custo e requisito ao mesmo tempo, e o painel continua legível em qualquer
largura sem a barra de abas espremer.

O cabeçalho (miniatura + nome + subtítulo) e o rodapé (Salvar/Reverter)
ficam fixos; só a pilha de seções rola.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panels.items.editor_base import IconButton
from src.layouts.panels.dungeons.constants import (
    _INPUT_STYLE, panel_frame_style, sub_header, caption, hrule,
)


class SectionEditor(QFrame):
    """Cabeçalho + pilha de seções + rodapé. Subclasses montam as seções."""

    changed = Signal()           # algum campo foi editado (auto-save debounced)
    save_requested = Signal()
    revert_requested = Signal()
    image_changed = Signal(str)  # nova imagem escolhida/arrastada na miniatura

    THUMB = (150, 84)

    def __init__(self, title: str, fallback_icon: str = "🏰", parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(260)
        self._fallback_icon = fallback_icon
        self._sections: list[CollapsibleSection] = []
        # Guarda os sinais dos campos enquanto um registro está sendo
        # carregado — sem isso, preencher os widgets dispararia changed a
        # cada setValue e regravaria o registro recém-lido por cima.
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)
        outer.addWidget(sub_header(title))

        # ── Cabeçalho: miniatura + nome/subtítulo/estado ──
        header = QHBoxLayout()
        header.setSpacing(10)
        self._thumb = IconButton(fallback_icon, size=self.THUMB)
        self._thumb.setToolTip("Clique ou arraste uma imagem")
        self._thumb.clicked.connect(self._on_pick_image)
        self._thumb.image_dropped.connect(self._on_image_picked)
        header.addWidget(self._thumb)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_lbl = QLabel("—")
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._sub_lbl = QLabel("")
        self._sub_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        self._desc_lbl = QLabel("")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        self._state_lbl = QLabel("")
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._state_lbl.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        info.addWidget(self._name_lbl)
        info.addWidget(self._sub_lbl)
        info.addWidget(self._desc_lbl)
        info.addWidget(self._state_lbl)
        header.addLayout(info, 1)
        outer.addLayout(header)
        outer.addWidget(hrule())
        self.set_thumbnail("")

        # ── Coluna rolável de seções ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self._column = QVBoxLayout(holder)
        self._column.setContentsMargins(0, 4, 4, 4)
        self._column.setSpacing(6)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
        self._holder = holder

        # ── Rodapé ──
        footer = QHBoxLayout()
        footer.setSpacing(8)
        save = QPushButton("Salvar Alterações")
        save.setFixedHeight(28)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 0 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        save.clicked.connect(self.save_requested.emit)
        revert = QPushButton("Reverter")
        revert.setFixedHeight(28)
        revert.setCursor(Qt.CursorShape.PointingHandCursor)
        revert.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 0 14px;
                font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        revert.clicked.connect(self.revert_requested.emit)
        footer.addWidget(save, 1)
        footer.addWidget(revert, 1)
        outer.addLayout(footer)

    # ── Montagem das seções (usado pelas subclasses) ──

    def add_section(self, title: str, expanded: bool = False) -> CollapsibleSection:
        section = CollapsibleSection(title, expanded=expanded)
        self._column.addWidget(section)
        self._sections.append(section)
        return section

    def finish_sections(self):
        """Chamar depois da última seção — sem o stretch final o layout
        estica as seções para preencher a sobra de altura."""
        self._column.addStretch()

    def track(self, *widgets):
        """Liga os sinais de edição desses widgets ao `changed` do editor,
        respeitando o guarda de carregamento."""
        for widget in widgets:
            for signal_name in ("valueChanged", "currentTextChanged", "textChanged", "toggled"):
                signal = getattr(widget, signal_name, None)
                if signal is not None:
                    signal.connect(self._on_field_changed)
                    break
        return widgets[0] if len(widgets) == 1 else widgets

    def _on_field_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    # ── Cabeçalho ──

    def set_header(self, name: str, subtitle: str = "", description: str = "", state: str = ""):
        self._name_lbl.setText(name or "—")
        self._sub_lbl.setText(subtitle)
        self._desc_lbl.setText(description)
        self._state_lbl.setText(state)

    def set_thumbnail(self, path: str):
        self._thumb.set_image(path or "")

    def _on_pick_image(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if path:
            self._on_image_picked(path)

    def _on_image_picked(self, path: str):
        """Compartilhado pelo clique (file dialog) e pelo arrastar-e-soltar
        do IconButton — a miniatura já se atualiza sozinha (o próprio
        IconButton chama set_image no dropEvent); só falta avisar o editor
        dono para persistir."""
        self._thumb.set_image(path)
        self.image_changed.emit(path)
        self._on_field_changed()

    # ── Utilitários de layout para as seções ──

    @staticmethod
    def grid(pairs: list[tuple[str, QWidget]], columns: int = 1) -> QGridLayout:
        """Rótulo à esquerda, campo à direita, em `columns` pares por linha."""
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(5)
        for i, (label_text, widget) in enumerate(pairs):
            row, col = divmod(i, columns)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(lbl, row, col * 2)
            layout.addWidget(widget, row, col * 2 + 1)
            layout.setColumnStretch(col * 2 + 1, 1)
        return layout

    @staticmethod
    def stat_grid(pairs: list[tuple[str, QLabel]], columns: int = 2) -> QGridLayout:
        """Legenda pequena acima do valor — usado nas seções só de leitura
        (Informações Adicionais, Produção estimada)."""
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(6)
        for i, (label_text, widget) in enumerate(pairs):
            row, col = divmod(i, columns)
            cell = QVBoxLayout()
            cell.setSpacing(1)
            cell.addWidget(caption(label_text))
            cell.addWidget(widget)
            layout.addLayout(cell, row, col)
            layout.setColumnStretch(col, 1)
        return layout
