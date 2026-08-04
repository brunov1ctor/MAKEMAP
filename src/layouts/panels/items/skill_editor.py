"""SkillEditor — the EDITOR DE HABILIDADE center column.

Composed like a flag: the icon is a fixed "canto" block in the top-left,
sem crop (a imagem inteira aparece, redimensionada pra caber), com só a
Identidade (nome/preview/nível/tier/recarga) ao lado dele — do tamanho da
própria identidade, sem sobrar espaço vazio abaixo do ícone. Da seção
Requisitos & Mecânica em diante (Custo, Dano, Tags, texto livre), o
conteúdo usa a largura toda do painel em grids de 3-4 colunas, cada seção
com uma legenda. Não há mais abas: a antiga pill tab-bar/QStackedWidget foi
removida a pedido do usuário, que achava a navegação por abas pouco
amigável pra um formulário que cabe inteiro numa coluna scrollável. Real DB
columns (name, category, rarity, level, cooldown, mana_cost, element, code,
icon) plus a `stats` JSON blob for the rest — Tags included, see
SKILL_TAG_TYPES.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QCompleter, QGridLayout, QFileDialog, QToolButton,
    QPushButton, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.items.constants import (
    _spin, _dspin, _no_wheel, _section_label, _INPUT_STYLE, SKILL_FLAGS,
    DAMAGE_TYPES, ELEMENT_OPTIONS,
    skill_tier_options, skill_tier_color, skill_tier_label,
    skill_tag_type_options, skill_tag_type_label, skill_tag_type_color,
)
from src.layouts.panels.items.editor_base import (
    SquareCheck, IconButton, editor_frame,
)


class _TagChip(QWidget):
    """One "Debuff: Queimadura"-style pill in the Tags section's FlowLayout —
    colored by its type (see SKILL_TAG_TYPES), with a "✕" to remove. Purely
    descriptive metadata for the designer (e.g. so "Incinerar" can note it
    hits harder if the target already carries a "Queimadura" debuff) — the
    editor has no game engine to interpret any synergy between skills."""

    remove_requested = Signal(str)  # this chip's tag_id

    def __init__(self, tag_id: str, tag_type: str, label: str, parent=None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("tagChip")
        color = skill_tag_type_color(tag_type)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 4, 3)
        lay.setSpacing(4)
        self.setStyleSheet(f"""
            #tagChip {{ background: {color}26; border: 1px solid {color}77; border-radius: 10px; }}
        """)
        text = QLabel(f"{skill_tag_type_label(tag_type)}: {label}" if label else skill_tag_type_label(tag_type))
        text.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(text)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(14, 14)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Remover tag")
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {color}; font-size: 9px; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        close_btn.clicked.connect(lambda: self.remove_requested.emit(self.tag_id))
        lay.addWidget(close_btn)


class SkillEditor(QWidget):
    changed = Signal()
    image_changed = Signal(str)

    def __init__(self, skills_provider=None, items_provider=None, parent=None):
        """`skills_provider` fica disponível para futuras necessidades do
        editor — a Árvore de Habilidades agora cria/conecta nós direto no
        próprio canvas (ver skill_tree/canvas.py), não mais a partir daqui.
        `items_provider` alimenta "Arma Requerida" com os itens de categoria
        Arma realmente cadastrados no Editor de Item (ver
        _refresh_req_arma_options), em vez de uma lista fixa."""
        super().__init__(parent)
        self._items_provider = items_provider or (lambda: [])
        # The app-wide stylesheet (build_stylesheet(), applied once at
        # QApplication level) styles QComboBox popups dark everywhere else,
        # but a combo built deep inside this scroll area's nested layouts
        # can still pop up with Qt's unstyled default (a plain white list)
        # the first time it's opened — applying the same rule locally (same
        # fix entity_list.py/MobEditPanel already use) guarantees it. The
        # leading "background: transparent; border: none;" is required —
        # calling setStyleSheet() on a plain QWidget switches it to
        # style-sheet-driven background painting, and without an explicit
        # transparent rule for the widget itself it'd paint an OPAQUE
        # background behind editor_frame()'s rounded glass card, peeking
        # out as square corners around the card's border-radius.
        self.setStyleSheet("background: transparent; border: none;" + _INPUT_STYLE)
        self._loading = True
        self._record: dict = {}
        self._skills_provider = skills_provider or (lambda: [])
        self._flag_switches: dict[str, SquareCheck] = {}
        self._tags: list[dict] = []  # [{"id", "type", "label"}, ...] — see _build_tags_section

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        frame, content, title_row = editor_frame("Editor de Habilidade")
        self._id_label = QLabel("ID: —")
        self._id_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        title_row.addWidget(self._id_label)
        outer.addWidget(frame)

        self._empty_hint = QLabel("Selecione uma habilidade ou clique em “+ Nova Habilidade”.")
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self._empty_hint)

        # Body in a scroll area — a full form scrolls internally instead of
        # forcing its column/row larger.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 5px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(10)
        self._scroll.setWidget(self._body)
        content.addWidget(self._scroll, 1)

        self._build_top_row(body)
        self._build_requisitos_mecanica(body)
        self._build_custo(body)
        self._build_dano(body)
        self._build_tags_section(body)
        self._build_text_section(body)
        body.addStretch()

        self._update_preview()
        self._scroll.setVisible(False)
        self._loading = False

    # ── layout: canto (ícone) + identidade, depois seções em largura total ──

    def _build_top_row(self, body: QVBoxLayout):
        """Canto: só o ícone + identidade (nome/preview/nível/tier/recarga)
        ficam ao lado dele — do tamanho da própria identidade, sem "puxar"
        uma coluna estreita pelo resto do painel. Da seção Requisitos em
        diante o conteúdo usa a largura toda (ver _build_requisitos_mecanica/
        _build_custo/_build_dano), em vez de sobrar vazio abaixo do ícone."""
        row = QHBoxLayout()
        row.setSpacing(12)

        self._icon_btn = IconButton("✨", size=(110, 110), crop=False)
        self._icon_btn.clicked.connect(self._on_pick_image)
        self._icon_btn.image_dropped.connect(self._on_image_set)
        self._icon_btn.setToolTip("Clique ou arraste uma imagem")
        row.addWidget(self._icon_btn, alignment=Qt.AlignmentFlag.AlignTop)

        identity_col = QVBoxLayout()
        identity_col.setSpacing(8)
        self._build_identity(identity_col)
        row.addLayout(identity_col, 1)
        body.addLayout(row)

    def _section(self, container, title: str, cols: int = 2) -> QGridLayout:
        container.addWidget(_section_label(title))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        container.addLayout(grid)
        return grid

    def _build_identity(self, right_col: QVBoxLayout):
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome da habilidade")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ background: transparent; border: none; border-bottom: 1px solid {Colors.BORDER_SUBTLE};
                color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: bold; padding: 2px 0; }}
            QLineEdit:focus {{ border-bottom: 1px solid {Colors.ACCENT}; }}
        """)
        self._name_edit.textEdited.connect(self._emit_changed)
        right_col.addWidget(self._name_edit)

        # Selo de pré-visualização — mesma cor do anel do node na Árvore
        # (skill_tier_color), atualizado a cada mudança de nome/tier/nível
        # via _update_preview(), pra dar uma ideia de como a habilidade vai
        # aparecer no canvas sem precisar sair do editor pra conferir.
        self._preview_label = QLabel()
        self._preview_label.setStyleSheet("font-size: 9px; font-weight: bold; padding: 2px 8px; border-radius: 8px;")
        right_col.addWidget(self._preview_label, alignment=Qt.AlignmentFlag.AlignLeft)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._level_spin = self._num(_no_wheel(_spin(1, 999, 1)))
        grid.addLayout(self._labeled("Nível", self._level_spin), 0, 0)

        # "Tier" no lugar de "Raridade" — raridade é escala de loot (comum/
        # raro/épico...), não faz sentido numa habilidade; tier de
        # progressão (Inicial → Lendário) sim. Ainda grava na coluna
        # `rarity` do banco (mesmas chaves), só muda o rótulo/UI aqui e na
        # lista (ver skill_tier_label/skill_tier_color).
        self._tier_combo = QComboBox()
        for key, label in skill_tier_options():
            self._tier_combo.addItem(label, key)
        _no_wheel(self._tier_combo)
        self._tier_combo.currentIndexChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Tier", self._tier_combo), 0, 1)

        self._cooldown = self._num(_no_wheel(_dspin(0, 9999, 0.0, " s")))
        grid.addLayout(self._labeled("Recarga", self._cooldown), 1, 0, 1, 2)
        right_col.addLayout(grid)

    def _build_requisitos_mecanica(self, body: QVBoxLayout):
        # 4 colunas — largura total do painel, não mais espremido na coluna
        # ao lado do ícone — então Nível Req./Arma Requerida cabem numa
        # linha só e os 5 toggles quase cabem numa linha só também.
        grid = self._section(body, "Requisitos & Mecânica", cols=4)
        self._req_nivel = self._num(_no_wheel(_spin(0, 999, 1)))
        grid.addLayout(self._labeled("Nível Req.", self._req_nivel), 0, 0)

        # Editável + QCompleter em vez de uma lista fixa de tipos de arma —
        # busca TODOS os itens de fato cadastrados no Editor de Item (ver
        # _refresh_req_arma_options), não só categoria "Arma": o requisito
        # pode ser uma armadura, um consumível etc., não só uma arma — e
        # filtra a lista conforme o usuário digita, tipo autocomplete/ajax.
        self._req_arma = QComboBox()
        self._req_arma.setEditable(True)
        self._req_arma.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        req_arma_completer = QCompleter(self._req_arma.model(), self._req_arma)
        req_arma_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        req_arma_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        req_arma_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._req_arma.setCompleter(req_arma_completer)
        _no_wheel(self._req_arma)
        self._req_arma.currentTextChanged.connect(self._emit_changed)
        self._refresh_req_arma_options()
        grid.addLayout(self._labeled("Item Requerido", self._req_arma), 0, 1, 1, 3)

        # Os 5 numa linha só (não mais um grid 4 col + sobra) — checkbox
        # quadrado simples com "v" desenhado quando ativo, em vez do
        # ToggleSwitch em pílula, que fica mais difícil de escanear rápido
        # quando são vários lado a lado.
        toggles_row = QHBoxLayout()
        toggles_row.setSpacing(16)
        for key, label, default in SKILL_FLAGS:
            cb = SquareCheck(default)
            cb.toggled.connect(self._emit_changed)
            self._flag_switches[key] = cb
            pair = QHBoxLayout()
            pair.setSpacing(5)
            pair.addWidget(cb)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
            pair.addWidget(lbl)
            toggles_row.addLayout(pair)
        toggles_row.addStretch()
        grid.addLayout(toggles_row, 1, 0, 1, 4)

    def _refresh_req_arma_options(self):
        """Repopula "Item Requerido" com TODOS os itens realmente
        cadastrados no Editor de Item — não só categoria "Arma": uma
        habilidade pode exigir uma armadura ou consumível específico tanto
        quanto uma arma, então a lista não filtra por item_type — mais
        "Qualquer"/"Desarmado" que não são itens de verdade. Preserva o
        texto atual (mesmo que o item tenha sido removido do catálogo desde
        então, o campo é editável e aceita texto livre)."""
        current = self._req_arma.currentText()
        item_names = sorted({
            (it.get("name") or "").strip()
            for it in (self._items_provider() or [])
            if (it.get("name") or "").strip()
        })
        self._req_arma.blockSignals(True)
        self._req_arma.clear()
        self._req_arma.addItem("Qualquer")
        self._req_arma.addItem("Desarmado")
        self._req_arma.addItems(item_names)
        self._req_arma.setCurrentText(current)
        self._req_arma.blockSignals(False)

    def showEvent(self, event):
        """Reconfere os itens de "Item Requerido" toda vez que o editor
        aparece — cobre o caso de o usuário cadastrar um item novo no
        Editor de Item e voltar pra Habilidades sem trocar de habilidade
        selecionada (o que também dispararia load(), mas esse evento não)."""
        super().showEvent(event)
        if hasattr(self, "_req_arma"):
            self._refresh_req_arma_options()

    def _build_custo(self, body: QVBoxLayout):
        grid = self._section(body, "Custo", cols=4)
        self._mana = self._num(_no_wheel(_spin(0, 99999, 0)))
        self._stamina = self._num(_no_wheel(_spin(0, 99999, 0)))
        self._recurso = QComboBox()
        self._recurso.addItems(["Mana", "Stamina", "Fúria", "Energia", "Nenhum"])
        _no_wheel(self._recurso)
        self._recurso.currentTextChanged.connect(self._emit_changed)
        self._cargas = self._num(_no_wheel(_spin(0, 99, 0)))
        grid.addLayout(self._labeled("Custo de Mana", self._mana), 0, 0)
        grid.addLayout(self._labeled("Custo de Stamina", self._stamina), 0, 1)
        grid.addLayout(self._labeled("Recurso Principal", self._recurso), 0, 2)
        grid.addLayout(self._labeled("Cargas", self._cargas), 0, 3)

        self._alcance = self._num(_no_wheel(_dspin(0, 999, 0.0, " m")))
        self._area = self._num(_no_wheel(_dspin(0, 999, 0.0, " m")))
        self._duracao = self._num(_no_wheel(_dspin(0, 999, 0.0, " s")))
        self._cast_time = self._num(_no_wheel(_dspin(0, 999, 0.0, " s")))
        grid.addLayout(self._labeled("Alcance", self._alcance), 1, 0)
        grid.addLayout(self._labeled("Área de Efeito", self._area), 1, 1)
        grid.addLayout(self._labeled("Duração", self._duracao), 1, 2)
        grid.addLayout(self._labeled("Tempo de Conjuração", self._cast_time), 1, 3)

    def _build_dano(self, body: QVBoxLayout):
        grid = self._section(body, "Dano", cols=3)
        self._dmg_type = QComboBox()
        self._dmg_type.addItems(DAMAGE_TYPES)
        _no_wheel(self._dmg_type)
        self._dmg_type.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Tipo de Dano", self._dmg_type), 0, 0)
        self._element = QComboBox()
        self._element.addItems(ELEMENT_OPTIONS)
        _no_wheel(self._element)
        self._element.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Elemento", self._element), 0, 1)

        # Rank Máximo — até que rank essa habilidade pode ser evoluída na
        # Árvore de Habilidades (o node lá herda esse teto, ver
        # skill_tree/canvas.py._ensure_node/refresh_node_metadata). Mudar aqui
        # reconstrói a tabela "Dano por Rank" abaixo pra ter uma linha por
        # rank de 1 até esse valor.
        self._rank_max_spin = _no_wheel(_spin(1, 10, 5))
        self._rank_max_spin.valueChanged.connect(self._on_rank_max_changed)
        grid.addLayout(self._labeled("Rank Máximo", self._rank_max_spin), 0, 2)

        rank_header = QHBoxLayout()
        rank_header.setSpacing(6)
        rank_spacer = QLabel("")
        rank_spacer.setFixedWidth(46)
        rank_header.addWidget(rank_spacer)
        for text in ("Dano Base", "Escalonamento"):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
            rank_header.addWidget(lbl, 1)
        grid.addLayout(rank_header, 1, 0, 1, 3)

        self._rank_rows_widget = QWidget()
        self._rank_rows_layout = QVBoxLayout(self._rank_rows_widget)
        self._rank_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rank_rows_layout.setSpacing(3)
        grid.addWidget(self._rank_rows_widget, 2, 0, 1, 3)
        self._rank_spin_rows: list[tuple] = []
        self._rebuild_rank_rows(self._rank_max_spin.value())

    def _on_rank_max_changed(self, value: int):
        self._rebuild_rank_rows(value)
        self._emit_changed()

    def _rebuild_rank_rows(self, count: int):
        """(Re)builds one [Dano Base | Escalonamento] row per rank, 1..count
        — preserves values already typed for ranks that still exist when
        Rank Máximo changes (growing/shrinking the table)."""
        existing = [(db.value(), esc.value()) for db, esc in self._rank_spin_rows]
        while self._rank_rows_layout.count():
            item = self._rank_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rank_spin_rows = []
        for i in range(count):
            row = QHBoxLayout()
            row.setSpacing(6)
            rank_lbl = QLabel(f"Rank {i + 1}")
            rank_lbl.setFixedWidth(46)
            rank_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
            row.addWidget(rank_lbl)
            dano_spin = _no_wheel(_dspin(0, 99999, 0.0))
            dano_spin.valueChanged.connect(self._emit_changed)
            esc_spin = _no_wheel(_dspin(0, 100, 0.0, " %"))
            esc_spin.valueChanged.connect(self._emit_changed)
            if i < len(existing):
                dano_spin.setValue(existing[i][0])
                esc_spin.setValue(existing[i][1])
            row.addWidget(dano_spin, 1)
            row.addWidget(esc_spin, 1)
            wrapper = QWidget()
            wrapper.setLayout(row)
            self._rank_rows_layout.addWidget(wrapper)
            self._rank_spin_rows.append((dano_spin, esc_spin))

    # ── largura total: Tags e texto livre ──

    def _build_tags_section(self, body: QVBoxLayout):
        """Tags de efeito (Buff/Debuff/Bônus/...) — puro metadado pro
        designer classificar o que a habilidade aplica (ex.: Debuff
        "Queimadura"), pra anotar sinergias como "Incinerar causa mais dano
        se o alvo já tiver Queimadura" sem nenhuma estrutura de synergy de
        verdade rodando por trás (ver SKILL_TAG_TYPES). Fica em largura
        total porque os chips precisam de espaço pra quebrar linha."""
        body.addWidget(_section_label("Tags"))
        col = QVBoxLayout()
        col.setSpacing(6)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self._tag_type_combo = QComboBox()
        for key, label in skill_tag_type_options():
            self._tag_type_combo.addItem(label, key)
        _no_wheel(self._tag_type_combo)
        add_row.addWidget(self._tag_type_combo)
        self._tag_label_edit = QLineEdit()
        self._tag_label_edit.setPlaceholderText("Ex.: Queimadura...")
        self._tag_label_edit.returnPressed.connect(self._on_add_tag)
        add_row.addWidget(self._tag_label_edit, 1)
        add_btn = QPushButton("+ Adicionar")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 5px; padding: 4px 10px; font-size: 9px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        add_btn.clicked.connect(self._on_add_tag)
        add_row.addWidget(add_btn)
        col.addLayout(add_row)

        self._tags_container = QWidget()
        self._tags_flow = FlowLayout(self._tags_container, spacing=6)
        col.addWidget(self._tags_container)
        body.addLayout(col)

    def _on_add_tag(self):
        label = self._tag_label_edit.text().strip()
        tag_type = self._tag_type_combo.currentData()
        if not label:
            return
        self._tags.append({"id": str(uuid.uuid4()), "type": tag_type, "label": label})
        self._tag_label_edit.clear()
        self._refresh_tags_display()
        self._emit_changed()

    def _on_remove_tag(self, tag_id: str):
        self._tags = [t for t in self._tags if t.get("id") != tag_id]
        self._refresh_tags_display()
        self._emit_changed()

    def _refresh_tags_display(self):
        while self._tags_flow.count():
            item = self._tags_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag["id"], tag.get("type", "buff"), tag.get("label", ""))
            chip.remove_requested.connect(self._on_remove_tag)
            self._tags_flow.addWidget(chip)

    def _build_text_section(self, body: QVBoxLayout):
        """Descrição e Notas lado a lado, em largura total e com altura
        reduzida — texto livre é o que se consulta por último ao revisar
        uma habilidade, por isso fica no final do painel."""
        row = QHBoxLayout()
        row.setSpacing(10)
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição da habilidade...")
        self._desc_edit.setFixedHeight(44)
        self._desc_edit.textChanged.connect(self._emit_changed)
        row.addLayout(self._labeled("Descrição", self._desc_edit), 1)

        self._notas = QTextEdit()
        self._notas.setPlaceholderText("Notas de design, animação, efeitos...")
        self._notas.setFixedHeight(44)
        self._notas.textChanged.connect(self._emit_changed)
        row.addLayout(self._labeled("Notas", self._notas), 1)
        body.addLayout(row)

    # ── helpers ──

    def _labeled(self, label: str, widget) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        cap = QLabel(label)
        cap.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        col.addWidget(cap)
        if isinstance(widget, (QHBoxLayout, QVBoxLayout)):
            col.addLayout(widget)
        else:
            col.addWidget(widget)
        return col

    def _num(self, widget):
        widget.valueChanged.connect(self._emit_changed)
        return widget

    def _update_preview(self):
        """Selo "● Tier · Nível N" colorido pelo tier atual — mesma cor que
        o node correspondente usa no canvas da Árvore (skill_tier_color)."""
        tier_key = self._tier_combo.currentData() or "common"
        color = skill_tier_color(tier_key)
        level = self._level_spin.value()
        self._preview_label.setText(f"●  {skill_tier_label(tier_key)}  ·  Nível {level}")
        self._preview_label.setStyleSheet(f"""
            font-size: 9px; font-weight: bold; padding: 2px 8px; border-radius: 8px;
            color: {color}; background: {color}22; border: 1px solid {color}77;
        """)

    def _emit_changed(self, *args):
        self._update_preview()
        if not self._loading:
            self.changed.emit()

    def _on_pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher ícone", "", "Imagens (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self._on_image_set(path)

    def _on_image_set(self, path: str):
        self._icon_btn.set_image(path)
        self._record["image_path"] = path
        self.image_changed.emit(path)
        self._emit_changed()

    def set_empty(self):
        self._scroll.setVisible(False)
        self._empty_hint.setVisible(True)
        self._id_label.setText("ID: —")

    def load(self, record: dict):
        self._loading = True
        self._record = dict(record)
        stats = self._parse_stats(record.get("stats"))

        self._empty_hint.setVisible(False)
        self._scroll.setVisible(True)
        self._id_label.setText(f"ID: {record.get('code') or '—'}")
        self._name_edit.setText(record.get("name", ""))
        self._icon_btn.set_image(record.get("image_path") or "")

        tier_idx = self._tier_combo.findData(record.get("rarity") or "common")
        self._tier_combo.setCurrentIndex(tier_idx if tier_idx >= 0 else 0)
        self._level_spin.setValue(int(record.get("level") or 1))
        self._cooldown.setValue(float(record.get("cooldown") or 0))
        self._desc_edit.setPlainText(record.get("description", ""))

        self._mana.setValue(int(record.get("mana_cost") or 0))
        self._stamina.setValue(int(stats.get("stamina", 0)))
        self._alcance.setValue(float(stats.get("alcance", 0)))
        self._area.setValue(float(stats.get("area", 0)))
        self._duracao.setValue(float(stats.get("duracao", 0)))
        self._cast_time.setValue(float(stats.get("cast_time", 0)))
        for key, _label, default in SKILL_FLAGS:
            self._flag_switches[key].setChecked(bool(stats.get(key, default)))

        self._dmg_type.setCurrentText(stats.get("dmg_type", DAMAGE_TYPES[0]))
        self._element.setCurrentText(record.get("element") or ELEMENT_OPTIONS[0])

        rank_max = max(1, min(10, int(stats.get("rank_max") or 5)))
        self._rank_max_spin.blockSignals(True)
        self._rank_max_spin.setValue(rank_max)
        self._rank_max_spin.blockSignals(False)
        self._rebuild_rank_rows(rank_max)
        rank_damage = stats.get("rank_damage") or []
        for i, (dano_spin, esc_spin) in enumerate(self._rank_spin_rows):
            entry = rank_damage[i] if i < len(rank_damage) else {}
            dano_spin.setValue(float(entry.get("dano_base", 0)))
            esc_spin.setValue(float(entry.get("escalonamento", 0)))

        self._req_nivel.setValue(int(stats.get("req_nivel", record.get("level") or 1)))
        self._refresh_req_arma_options()
        self._req_arma.setCurrentText(stats.get("req_arma", "Qualquer"))
        self._recurso.setCurrentText(stats.get("recurso", "Mana"))
        self._cargas.setValue(int(stats.get("cargas", 0)))
        self._notas.setPlainText(stats.get("notas", ""))

        self._tags = list(stats.get("tags") or [])
        self._refresh_tags_display()

        self._update_preview()
        self._loading = False

    def collect(self) -> dict:
        stats = {
            "stamina": self._stamina.value(),
            "alcance": self._alcance.value(),
            "area": self._area.value(),
            "duracao": self._duracao.value(),
            "cast_time": self._cast_time.value(),
            "dmg_type": self._dmg_type.currentText(),
            "req_nivel": self._req_nivel.value(),
            "req_arma": self._req_arma.currentText(),
            "recurso": self._recurso.currentText(),
            "cargas": self._cargas.value(),
            "notas": self._notas.toPlainText().strip(),
            "tags": self._tags,
            "rank_max": self._rank_max_spin.value(),
            "rank_damage": [
                {"dano_base": dano_spin.value(), "escalonamento": esc_spin.value()}
                for dano_spin, esc_spin in self._rank_spin_rows
            ],
        }
        for key, _label, _default in SKILL_FLAGS:
            stats[key] = self._flag_switches[key].isChecked()
        return {
            "name": self._name_edit.text().strip() or "Nova Habilidade",
            "description": self._desc_edit.toPlainText().strip(),
            "rarity": self._tier_combo.currentData() or "common",
            "level": self._level_spin.value(),
            "cooldown": self._cooldown.value(),
            "mana_cost": self._mana.value(),
            "element": self._element.currentText(),
            "image_path": self._record.get("image_path", ""),
            "stats": json.dumps(stats, ensure_ascii=False),
        }

    @staticmethod
    def _parse_stats(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
