"""SkillEditor — the EDITOR DE HABILIDADE center column.

Same shape as ItemEditor (header / meta / tabbed form) but with the skill
vocabulary. The header packs the icon beside a compact grid (Nível, Tier,
Recarga, Requisitos, Mecânica) instead of spreading those across their own
tabs — Requisitos/Mecânica used to be whole tabs for just 2-5 fields each,
which read as mostly empty space; folding them beside the image compacts
the panel instead. Remaining tabs: Propriedades (mana/stamina/alcance/área/
durações), Dano (incl. Rank Máximo + dano por rank), Recursos, Tags (buff/
debuff/bônus...) and Outros. Real DB columns (name, category, rarity,
level, cooldown, mana_cost, element, code, icon) plus a `stats` JSON blob
for the rest — Tags included, see SKILL_TAG_TYPES.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QGridLayout, QStackedWidget, QFileDialog, QToolButton,
    QPushButton, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panels.items.constants import (
    _spin, _dspin, _no_wheel, _INPUT_STYLE, SKILL_FLAGS,
    DAMAGE_TYPES, ELEMENT_OPTIONS,
    skill_tier_options,
    skill_tag_type_options, skill_tag_type_label, skill_tag_type_color,
)
from src.layouts.panels.items.editor_base import (
    ToggleSwitch, EditorTabBar, IconButton, editor_frame, toggle_row,
)


class _TagChip(QWidget):
    """One "Debuff: Queimadura"-style pill in the Tags tab's FlowLayout —
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
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {color}; font-size: 9px; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        close_btn.clicked.connect(lambda: self.remove_requested.emit(self.tag_id))
        lay.addWidget(close_btn)


class SkillEditor(QWidget):
    changed = Signal()
    image_changed = Signal(str)

    def __init__(self, skills_provider=None, parent=None):
        """`skills_provider` fica disponível para futuras necessidades do
        editor — a Árvore de Habilidades agora cria/conecta nós direto no
        próprio canvas (ver skill_tree/canvas.py), não mais a partir daqui."""
        super().__init__(parent)
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
        self._flag_switches: dict[str, ToggleSwitch] = {}
        self._tags: list[dict] = []  # [{"id", "type", "label"}, ...] — see _build_tags_tab

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

        # Body in a scroll area — same reasoning as ItemEditor: a full form
        # scrolls internally instead of forcing its column/row larger.
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
        body.setSpacing(8)
        self._scroll.setWidget(self._body)
        content.addWidget(self._scroll, 1)

        self._build_header(body)
        self._build_tabs(body)
        body.addStretch()

        self._scroll.setVisible(False)
        self._loading = False

    def _build_header(self, body: QVBoxLayout):
        """Ícone à esquerda; à direita, o nome em cima e, logo abaixo, um
        grid compacto com tudo que antes vivia espalhado em Nível/Tier/
        Recarga (o antigo _build_meta) + as abas Requisitos e Mecânica
        inteiras — ambas só tinham 2-5 campos e liam como abas quase vazias
        sozinhas; ao lado da imagem elas ocupam o espaço que já sobra ali."""
        row = QHBoxLayout()
        row.setSpacing(12)
        icon_col = QVBoxLayout()
        icon_col.setSpacing(4)
        self._icon_btn = IconButton("✨")
        self._icon_btn.clicked.connect(self._on_pick_image)
        self._icon_btn.image_dropped.connect(self._on_image_set)
        self._icon_btn.setToolTip("Clique ou arraste uma imagem")
        icon_col.addWidget(self._icon_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        icon_col.addStretch()
        row.addLayout(icon_col)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome da habilidade")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ background: transparent; border: none; border-bottom: 1px solid {Colors.BORDER_SUBTLE};
                color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: bold; padding: 2px 0; }}
            QLineEdit:focus {{ border-bottom: 1px solid {Colors.ACCENT}; }}
        """)
        self._name_edit.textEdited.connect(self._emit_changed)
        right_col.addWidget(self._name_edit)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # "Categoria" saiu — a Árvore de Habilidades agora agrupa por guia,
        # criada e nomeada direto no canvas da árvore (ver skill_tree/canvas.py),
        # que já cumpre esse papel sem precisar de um campo redundante aqui.
        self._level_spin = _spin(1, 999, 1)
        self._level_spin.valueChanged.connect(self._emit_changed)
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

        self._cooldown = _dspin(0, 9999, 0.0, " s")
        self._cooldown.valueChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Recarga", self._cooldown), 1, 0)

        # Requisitos (2 campos) direto aqui — não é mais uma aba própria.
        self._req_nivel = self._num(_spin(0, 999, 1))
        grid.addLayout(self._labeled("Nível Req.", self._req_nivel), 1, 1)

        self._req_arma = QComboBox()
        self._req_arma.addItems(["Qualquer", "Espada", "Machado", "Arco", "Cajado", "Adaga", "Desarmado"])
        _no_wheel(self._req_arma)
        self._req_arma.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Arma Requerida", self._req_arma), 2, 0, 1, 2)

        # Mecânica (5 toggles) direto aqui também — não é mais uma aba
        # própria, 2 por linha pra caber no espaço da coluna.
        for i, (key, label, default) in enumerate(SKILL_FLAGS):
            sw = ToggleSwitch(default)
            sw.toggled.connect(self._emit_changed)
            self._flag_switches[key] = sw
            grid.addLayout(toggle_row(label, sw), 3 + i // 2, i % 2)

        right_col.addLayout(grid)
        row.addLayout(right_col, 1)
        body.addLayout(row)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição da habilidade...")
        self._desc_edit.setFixedHeight(48)
        self._desc_edit.textChanged.connect(self._emit_changed)
        body.addLayout(self._labeled("Descrição", self._desc_edit))

    def _build_tabs(self, body: QVBoxLayout):
        self._tab_bar = EditorTabBar(["Propriedades", "Dano", "Recursos", "Tags", "Outros"])
        self._tab_bar.tab_changed.connect(lambda i: self._stack.setCurrentIndex(i))
        body.addWidget(self._tab_bar)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_props_tab())
        self._stack.addWidget(self._build_damage_tab())
        self._stack.addWidget(self._build_resources_tab())
        self._stack.addWidget(self._build_tags_tab())
        self._stack.addWidget(self._build_other_tab())
        body.addWidget(self._stack, 1)

    def _build_props_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._mana = self._num(_spin(0, 99999, 0))
        self._stamina = self._num(_spin(0, 99999, 0))
        self._alcance = self._num(_dspin(0, 999, 0.0, " m"))
        grid.addLayout(self._labeled("Custo de Mana", self._mana), 0, 0)
        grid.addLayout(self._labeled("Custo de Stamina", self._stamina), 1, 0)
        grid.addLayout(self._labeled("Alcance", self._alcance), 2, 0)
        self._area = self._num(_dspin(0, 999, 0.0, " m"))
        self._duracao = self._num(_dspin(0, 999, 0.0, " s"))
        self._cast_time = self._num(_dspin(0, 999, 0.0, " s"))
        grid.addLayout(self._labeled("Área de Efeito", self._area), 0, 1)
        grid.addLayout(self._labeled("Duração", self._duracao), 1, 1)
        grid.addLayout(self._labeled("Tempo de Conjuração", self._cast_time), 2, 1)
        return page

    def _build_damage_tab(self) -> QWidget:
        page, grid = self._form_page()
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
        self._rank_max_spin = _spin(1, 10, 5)
        self._rank_max_spin.valueChanged.connect(self._on_rank_max_changed)
        grid.addLayout(self._labeled("Rank Máximo", self._rank_max_spin), 1, 0, 1, 2)

        rank_header = QHBoxLayout()
        rank_header.setSpacing(6)
        rank_spacer = QLabel("")
        rank_spacer.setFixedWidth(46)
        rank_header.addWidget(rank_spacer)
        for text in ("Dano Base", "Escalonamento"):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
            rank_header.addWidget(lbl, 1)
        grid.addLayout(rank_header, 2, 0, 1, 2)

        self._rank_rows_widget = QWidget()
        self._rank_rows_layout = QVBoxLayout(self._rank_rows_widget)
        self._rank_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rank_rows_layout.setSpacing(3)
        grid.addWidget(self._rank_rows_widget, 3, 0, 1, 2)
        self._rank_spin_rows: list[tuple] = []
        self._rebuild_rank_rows(self._rank_max_spin.value())
        return page

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
            dano_spin = _dspin(0, 99999, 0.0)
            dano_spin.valueChanged.connect(self._emit_changed)
            esc_spin = _dspin(0, 100, 0.0, " %")
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

    def _build_resources_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._recurso = QComboBox()
        self._recurso.addItems(["Mana", "Stamina", "Fúria", "Energia", "Nenhum"])
        _no_wheel(self._recurso)
        self._recurso.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Recurso Principal", self._recurso), 0, 0)
        self._cargas = self._num(_spin(0, 99, 0))
        grid.addLayout(self._labeled("Cargas", self._cargas), 0, 1)
        return page

    def _build_tags_tab(self) -> QWidget:
        """Tags de efeito (Buff/Debuff/Bônus/...) — puro metadado pro
        designer classificar o que a habilidade aplica (ex.: Debuff
        "Queimadura"), pra anotar sinergias como "Incinerar causa mais dano
        se o alvo já tiver Queimadura" sem nenhuma estrutura de synergy de
        verdade rodando por trás (ver SKILL_TAG_TYPES)."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(2, 4, 2, 4)
        col.setSpacing(8)

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

        hint = QLabel("Documentação livre pra sinergias — ex.: Debuff \"Queimadura\" numa habilidade que causa dano ao longo do tempo, pra outra (\"Incinerar\") anotar que causa mais dano se o alvo já tiver essa tag.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        col.addWidget(hint)

        self._tags_container = QWidget()
        self._tags_flow = FlowLayout(self._tags_container, spacing=6)
        col.addWidget(self._tags_container)
        col.addStretch()
        return page

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

    def _build_other_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._notas = QTextEdit()
        self._notas.setPlaceholderText("Notas de design, animação, efeitos...")
        self._notas.setFixedHeight(70)
        self._notas.textChanged.connect(self._emit_changed)
        col = self._labeled("Notas", self._notas)
        grid.addLayout(col, 0, 0, 1, 2)
        return page

    # ── helpers (mirror ItemEditor) ──

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

    def _form_page(self) -> tuple[QWidget, QGridLayout]:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(2, 4, 2, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        return page, grid

    def _num(self, widget):
        widget.valueChanged.connect(self._emit_changed)
        return widget

    def _emit_changed(self, *args):
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
        self._req_arma.setCurrentText(stats.get("req_arma", "Qualquer"))
        self._recurso.setCurrentText(stats.get("recurso", "Mana"))
        self._cargas.setValue(int(stats.get("cargas", 0)))
        self._notas.setPlainText(stats.get("notas", ""))

        self._tags = list(stats.get("tags") or [])
        self._refresh_tags_display()

        self._tab_bar.set_current(0)
        self._stack.setCurrentIndex(0)
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
