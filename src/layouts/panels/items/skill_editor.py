"""SkillEditor — the EDITOR DE HABILIDADE center column.

Same shape as ItemEditor (header / meta / tabbed form) but with the skill
vocabulary: Categoria·Raridade·Nível·Tempo de Recarga up top, then
Propriedades (mana/stamina/alcance/área/durações), Mecânica (the five
behavior toggles), Dano, Requisitos, Recursos and Outros. Real DB columns
(name, category, rarity, level, cooldown, mana_cost, element, code, icon)
plus a `stats` JSON blob for the rest.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QGridLayout, QStackedWidget, QPushButton, QFileDialog,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.items.constants import (
    _spin, _dspin, _no_wheel, SKILL_FLAGS,
    DAMAGE_TYPES, ELEMENT_OPTIONS, rarity_options,
)
from src.layouts.panels.items.editor_base import (
    ToggleSwitch, EditorTabBar, IconButton, editor_frame, toggle_row,
)


class SkillEditor(QWidget):
    changed = Signal()
    image_changed = Signal(str)

    def __init__(self, skills_provider=None, parent=None):
        """`skills_provider` devolve o catálogo de habilidades — popula o
        combo "Evoluir de:", que substituiu o "+ Nó" manual da árvore
        (mesma ideia do "Desbloqueada por" das Construções)."""
        super().__init__(parent)
        self._loading = True
        self._record: dict = {}
        self._skills_provider = skills_provider or (lambda: [])
        self._flag_switches: dict[str, ToggleSwitch] = {}

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
        self._build_meta(body)
        self._build_tabs(body)
        body.addStretch()

        self._scroll.setVisible(False)
        self._loading = False

    def _build_header(self, body: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(12)
        icon_col = QVBoxLayout()
        icon_col.setSpacing(4)
        self._icon_btn = IconButton("✨")
        self._icon_btn.clicked.connect(self._on_pick_image)
        self._icon_btn.image_dropped.connect(self._on_image_set)
        self._icon_btn.setToolTip("Clique ou arraste uma imagem")
        icon_col.addWidget(self._icon_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        change_btn = QPushButton("Alterar Ícone")
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 3px 6px; font-size: 9px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        change_btn.clicked.connect(self._on_pick_image)
        icon_col.addWidget(change_btn)
        row.addLayout(icon_col)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addStretch()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome da habilidade")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ background: transparent; border: none; border-bottom: 1px solid {Colors.BORDER_SUBTLE};
                color: {Colors.TEXT_PRIMARY}; font-size: 16px; font-weight: bold; padding: 2px 0; }}
            QLineEdit:focus {{ border-bottom: 1px solid {Colors.ACCENT}; }}
        """)
        self._name_edit.textEdited.connect(self._emit_changed)
        name_col.addWidget(self._name_edit)
        name_col.addStretch()
        row.addLayout(name_col, 1)
        body.addLayout(row)

    def _build_meta(self, body: QVBoxLayout):
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        # "Categoria" saiu — a Árvore de Habilidades agora agrupa por guia
        # (nomeada abaixo, via "Evoluir de: → Nenhuma (raiz)"), que já
        # cumpre esse papel sem precisar de um segundo campo redundante.
        self._level_spin = _spin(1, 999, 1)
        self._level_spin.valueChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Nível", self._level_spin), 0, 0)

        self._rarity_combo = QComboBox()
        for key, label in rarity_options():
            self._rarity_combo.addItem(label, key)
        _no_wheel(self._rarity_combo)
        self._rarity_combo.currentIndexChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Raridade", self._rarity_combo), 0, 1)

        self._cooldown = _dspin(0, 9999, 0.0, " s")
        self._cooldown.valueChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Tempo de Recarga", self._cooldown), 1, 0, 1, 2)

        # Define o pré-requisito desta habilidade na Árvore de Habilidades —
        # escolher aqui cria (ou reaproveita) o nó dela e o do pré-requisito
        # na guia ativa da árvore, com a conexão entre os dois. Escolher
        # "— Nenhuma (raiz) —" revela o campo de nome logo abaixo: nomear
        # ali cria uma guia nova (ou renomeia a atual) pra essa habilidade
        # começar sozinha, sem pai.
        self._evolves_from = QComboBox()
        _no_wheel(self._evolves_from)
        self._evolves_from.currentIndexChanged.connect(self._on_evolves_from_changed)
        grid.addLayout(self._labeled("Evoluir de", self._evolves_from), 2, 0, 1, 2)

        self._new_tab_name = QLineEdit()
        self._new_tab_name.setPlaceholderText("Nome da guia na Árvore de Habilidades…")
        self._new_tab_name.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.ACCENT};
                border-radius: 5px; padding: 3px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
        """)
        self._new_tab_name.textEdited.connect(self._emit_changed)
        self._new_tab_wrap = QWidget()
        new_tab_col = self._labeled("Nova guia", self._new_tab_name)
        new_tab_col.setContentsMargins(0, 0, 0, 0)
        self._new_tab_wrap.setLayout(new_tab_col)
        self._new_tab_wrap.hide()
        grid.addWidget(self._new_tab_wrap, 3, 0, 1, 2)
        body.addLayout(grid)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição da habilidade...")
        self._desc_edit.setFixedHeight(48)
        self._desc_edit.textChanged.connect(self._emit_changed)
        body.addLayout(self._labeled("Descrição", self._desc_edit))

    def _build_tabs(self, body: QVBoxLayout):
        self._tab_bar = EditorTabBar(["Propriedades", "Mecânica", "Dano", "Requisitos", "Recursos", "Outros"])
        self._tab_bar.tab_changed.connect(lambda i: self._stack.setCurrentIndex(i))
        body.addWidget(self._tab_bar)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_props_tab())
        self._stack.addWidget(self._build_mechanics_tab())
        self._stack.addWidget(self._build_damage_tab())
        self._stack.addWidget(self._build_requirements_tab())
        self._stack.addWidget(self._build_resources_tab())
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

    def _build_mechanics_tab(self) -> QWidget:
        page, grid = self._form_page()
        for i, (key, label, default) in enumerate(SKILL_FLAGS):
            sw = ToggleSwitch(default)
            sw.toggled.connect(self._emit_changed)
            self._flag_switches[key] = sw
            grid.addLayout(toggle_row(label, sw), i % 3, i // 3)
        return page

    def _build_damage_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._dano_base = self._num(_dspin(0, 99999, 0.0))
        self._escalonamento = self._num(_dspin(0, 100, 0.0, " %"))
        grid.addLayout(self._labeled("Dano Base", self._dano_base), 0, 0)
        grid.addLayout(self._labeled("Escalonamento", self._escalonamento), 1, 0)
        self._dmg_type = QComboBox()
        self._dmg_type.addItems(DAMAGE_TYPES)
        _no_wheel(self._dmg_type)
        self._dmg_type.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Tipo de Dano", self._dmg_type), 0, 1)
        self._element = QComboBox()
        self._element.addItems(ELEMENT_OPTIONS)
        _no_wheel(self._element)
        self._element.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Elemento", self._element), 1, 1)
        return page

    def _build_requirements_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._req_nivel = self._num(_spin(0, 999, 1))
        grid.addLayout(self._labeled("Nível Requerido", self._req_nivel), 0, 0)
        self._req_arma = QComboBox()
        self._req_arma.addItems(["Qualquer", "Espada", "Machado", "Arco", "Cajado", "Adaga", "Desarmado"])
        _no_wheel(self._req_arma)
        self._req_arma.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Arma Requerida", self._req_arma), 0, 1)
        return page

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

    def _on_evolves_from_changed(self, index: int):
        self._new_tab_wrap.setVisible(index == 0)
        self._emit_changed()

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

    def refresh_evolves_from_options(self):
        """Repopula "Evoluir de:" com o catálogo atual, excluindo a própria
        habilidade (evita um ciclo direto A evolui de A). Chamado sempre que
        a lista de habilidades muda."""
        current = self._evolves_from.currentData()
        self._evolves_from.blockSignals(True)
        self._evolves_from.clear()
        self._evolves_from.addItem("— Nenhuma (raiz) —", "")
        for sk in self._skills_provider() or []:
            if sk.get("id") != self._record.get("id"):
                self._evolves_from.addItem(f"{sk.get('icon') or '✨'}  {sk.get('name', '—')}", sk.get("id"))
        index = self._evolves_from.findData(current)
        self._evolves_from.setCurrentIndex(index if index >= 0 else 0)
        self._evolves_from.blockSignals(False)

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

        rarity = record.get("rarity") or "common"
        idx = self._rarity_combo.findData(rarity)
        self._rarity_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._level_spin.setValue(int(record.get("level") or 1))
        self._cooldown.setValue(float(record.get("cooldown") or 0))
        self._desc_edit.setPlainText(record.get("description", ""))
        self.refresh_evolves_from_options()
        index = self._evolves_from.findData(record.get("evolves_from") or "")
        self._evolves_from.setCurrentIndex(index if index >= 0 else 0)
        self._new_tab_name.clear()
        self._new_tab_wrap.setVisible(self._evolves_from.currentIndex() == 0)

        self._mana.setValue(int(record.get("mana_cost") or 0))
        self._stamina.setValue(int(stats.get("stamina", 0)))
        self._alcance.setValue(float(stats.get("alcance", 0)))
        self._area.setValue(float(stats.get("area", 0)))
        self._duracao.setValue(float(stats.get("duracao", 0)))
        self._cast_time.setValue(float(stats.get("cast_time", 0)))
        for key, _label, default in SKILL_FLAGS:
            self._flag_switches[key].setChecked(bool(stats.get(key, default)))

        self._dano_base.setValue(float(stats.get("dano_base", 0)))
        self._escalonamento.setValue(float(stats.get("escalonamento", 0)))
        self._dmg_type.setCurrentText(stats.get("dmg_type", DAMAGE_TYPES[0]))
        self._element.setCurrentText(record.get("element") or ELEMENT_OPTIONS[0])

        self._req_nivel.setValue(int(stats.get("req_nivel", record.get("level") or 1)))
        self._req_arma.setCurrentText(stats.get("req_arma", "Qualquer"))
        self._recurso.setCurrentText(stats.get("recurso", "Mana"))
        self._cargas.setValue(int(stats.get("cargas", 0)))
        self._notas.setPlainText(stats.get("notas", ""))

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
            "dano_base": self._dano_base.value(),
            "escalonamento": self._escalonamento.value(),
            "dmg_type": self._dmg_type.currentText(),
            "req_nivel": self._req_nivel.value(),
            "req_arma": self._req_arma.currentText(),
            "recurso": self._recurso.currentText(),
            "cargas": self._cargas.value(),
            "notas": self._notas.toPlainText().strip(),
        }
        for key, _label, _default in SKILL_FLAGS:
            stats[key] = self._flag_switches[key].isChecked()
        return {
            "name": self._name_edit.text().strip() or "Nova Habilidade",
            "description": self._desc_edit.toPlainText().strip(),
            "rarity": self._rarity_combo.currentData() or "common",
            "level": self._level_spin.value(),
            "cooldown": self._cooldown.value(),
            "mana_cost": self._mana.value(),
            "element": self._element.currentText(),
            "image_path": self._record.get("image_path", ""),
            "evolves_from": self._evolves_from.currentData() or None,
            # Chave transiente — não é coluna do banco, o painel usa e
            # descarta antes de salvar (ver ItemsSkillsPanel._save_skill).
            "_new_tab_name": self._new_tab_name.text().strip() if self._new_tab_wrap.isVisible() else "",
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
