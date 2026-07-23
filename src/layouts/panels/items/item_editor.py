"""ItemEditor — the EDITOR DE ITEM center column.

A header (icon / name / friendly ID), the Categoria·Raridade·Prioridade
row, a description box, then a tabbed form (Propriedades / Mecânica / Dano /
Requisitos) and a tags row. Real DB columns (name, item_type, subcategory,
rarity, level_req, code, icon, image_path) plus everything else in a `stats`
JSON blob — collect() returns exactly what ItemRepository.update() wants.

Field edits emit `changed`; the owning panel debounces + persists. `_loading`
guards against emitting while load() is populating the widgets.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QGridLayout, QStackedWidget,
    QScrollArea, QToolButton, QPushButton, QFrame, QFileDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_label
from src.layouts.panels.items.constants import (
    _spin, _dspin, _no_wheel, ITEM_CATEGORIES, ITEM_CATEGORY_NAMES,
    DAMAGE_TYPES, ELEMENT_OPTIONS, ALLOWED_CLASSES, ITEM_FLAGS, rarity_options,
)
from src.layouts.panels.items.editor_base import (
    ToggleSwitch, EditorTabBar, IconButton, editor_frame, toggle_row,
)


class ItemEditor(QWidget):
    changed = Signal()
    image_changed = Signal(str)   # local image path (also stored via changed)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True
        self._record: dict = {}
        self._tags: list[str] = []
        self._flag_switches: dict[str, ToggleSwitch] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        frame, content, title_row = editor_frame("Editor de Item")
        self._id_label = QLabel("ID: —")
        self._id_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        title_row.addWidget(self._id_label)
        outer.addWidget(frame)

        self._empty_hint = QLabel("Selecione um item na lista ou clique em “+ Novo Item”.")
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self._empty_hint)

        # Body lives in a scroll area so a fully-populated editor never
        # forces its column/row to grow and steal space from the other five
        # panels ("brigam por espaço") — the fields scroll internally instead.
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
        self._build_tags(body)
        body.addStretch()

        self._scroll.setVisible(False)
        self._loading = False

    # ── construction ──

    def _build_header(self, body: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(12)
        icon_col = QVBoxLayout()
        icon_col.setSpacing(4)
        self._icon_btn = IconButton("🗡")
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
        self._name_edit.setPlaceholderText("Nome do item")
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

        self._cat_combo = QComboBox()
        self._cat_combo.addItems(ITEM_CATEGORY_NAMES)
        _no_wheel(self._cat_combo)
        self._cat_combo.currentTextChanged.connect(self._on_category_changed)
        self._sub_combo = QComboBox()
        _no_wheel(self._sub_combo)
        self._sub_combo.currentTextChanged.connect(self._emit_changed)
        cat_row = QHBoxLayout()
        cat_row.setSpacing(4)
        cat_row.addWidget(self._cat_combo, 1)
        cat_row.addWidget(self._sub_combo, 1)
        grid.addLayout(self._labeled("Categoria", cat_row), 0, 0)

        self._priority_spin = _spin(0, 999, 0)
        self._priority_spin.valueChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Prioridade", self._priority_spin), 0, 1)

        self._rarity_combo = QComboBox()
        for key, label in rarity_options():
            self._rarity_combo.addItem(label, key)
        _no_wheel(self._rarity_combo)
        self._rarity_combo.currentIndexChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Raridade", self._rarity_combo), 1, 0)

        self._level_spin = _spin(1, 999, 1)
        self._level_spin.valueChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Nível", self._level_spin), 1, 1)
        body.addLayout(grid)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Descrição do item...")
        self._desc_edit.setFixedHeight(48)
        self._desc_edit.textChanged.connect(self._emit_changed)
        body.addLayout(self._labeled("Descrição", self._desc_edit))

    def _build_tabs(self, body: QVBoxLayout):
        self._tab_bar = EditorTabBar(["Propriedades", "Mecânica", "Dano", "Requisitos"])
        self._tab_bar.tab_changed.connect(lambda i: self._stack.setCurrentIndex(i))
        body.addWidget(self._tab_bar)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_props_tab())
        self._stack.addWidget(self._build_mechanics_tab())
        self._stack.addWidget(self._build_damage_tab())
        self._stack.addWidget(self._build_requirements_tab())
        body.addWidget(self._stack, 1)

    def _build_props_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._peso = self._num(_dspin(0, 9999, 0.0, " kg"))
        self._valor = self._num(_spin(0, 9_999_999, 0))
        self._stack_max = self._num(_spin(1, 9999, 1))
        self._durabilidade = self._num(_spin(0, 9999, 100))
        self._nivel_min = self._num(_spin(0, 999, 1))
        grid.addLayout(self._labeled("Peso", self._peso), 0, 0)
        grid.addLayout(self._labeled("Valor de Venda", self._valor), 1, 0)
        grid.addLayout(self._labeled("Stack Máximo", self._stack_max), 2, 0)
        grid.addLayout(self._labeled("Durabilidade", self._durabilidade), 3, 0)
        grid.addLayout(self._labeled("Nível Mínimo", self._nivel_min), 4, 0)

        self._classe = QComboBox()
        self._classe.addItems(ALLOWED_CLASSES)
        _no_wheel(self._classe)
        self._classe.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Classe Permitida", self._classe), 0, 1)
        for i, (key, label, default) in enumerate(ITEM_FLAGS):
            sw = ToggleSwitch(default)
            sw.toggled.connect(self._emit_changed)
            self._flag_switches[key] = sw
            grid.addLayout(toggle_row(label, sw), i + 1, 1)
        return page

    def _build_mechanics_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._uso = QComboBox()
        self._uso.addItems(["Passivo", "Ativo", "Equipável", "Arremessável"])
        _no_wheel(self._uso)
        self._uso.currentTextChanged.connect(self._emit_changed)
        grid.addLayout(self._labeled("Tipo de Uso", self._uso), 0, 0)
        self._cooldown_item = self._num(_dspin(0, 9999, 0.0, " s"))
        grid.addLayout(self._labeled("Tempo de Recarga", self._cooldown_item), 1, 0)
        self._efeito_uso = QLineEdit()
        self._efeito_uso.textEdited.connect(self._emit_changed)
        grid.addLayout(self._labeled("Efeito ao Usar", self._efeito_uso), 0, 1)
        self._consumivel = ToggleSwitch(False)
        self._consumivel.toggled.connect(self._emit_changed)
        self._flag_switches["consumable"] = self._consumivel
        grid.addLayout(toggle_row("Consumível", self._consumivel), 1, 1)
        return page

    def _build_damage_tab(self) -> QWidget:
        page, grid = self._form_page()
        self._attack = self._num(_dspin(0, 99999, 0.0))
        self._atk_speed = self._num(_dspin(0, 100, 1.0))
        self._crit = self._num(_dspin(0, 100, 0.0, " %"))
        self._range = self._num(_dspin(0, 999, 0.0, " m"))
        grid.addLayout(self._labeled("Ataque", self._attack), 0, 0)
        grid.addLayout(self._labeled("Vel. de Ataque", self._atk_speed), 1, 0)
        grid.addLayout(self._labeled("Crítico", self._crit), 2, 0)
        grid.addLayout(self._labeled("Alcance", self._range), 3, 0)
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
        self._req_forca = self._num(_spin(0, 999, 0))
        self._req_destreza = self._num(_spin(0, 999, 0))
        self._req_inteligencia = self._num(_spin(0, 999, 0))
        grid.addLayout(self._labeled("Força", self._req_forca), 0, 0)
        grid.addLayout(self._labeled("Destreza", self._req_destreza), 1, 0)
        grid.addLayout(self._labeled("Inteligência", self._req_inteligencia), 2, 0)
        self._req_reputacao = QLineEdit()
        self._req_reputacao.textEdited.connect(self._emit_changed)
        grid.addLayout(self._labeled("Reputação", self._req_reputacao), 0, 1)
        return page

    def _build_tags(self, body: QVBoxLayout):
        row = QHBoxLayout()
        row.setSpacing(6)
        tags_lbl = QLabel("Tags")
        tags_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        row.addWidget(tags_lbl)
        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(4)
        row.addLayout(self._tags_row)
        row.addStretch()
        add_tag = QToolButton()
        add_tag.setText("+")
        add_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        add_tag.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.ACCENT};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; font-size: 11px; font-weight: bold;
                min-width: 20px; min-height: 18px; }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; }}
        """)
        add_tag.clicked.connect(self._on_add_tag)
        row.addWidget(add_tag)
        body.addLayout(row)

    # ── field helpers ──

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
        """Wire a spin/dspin's valueChanged to _emit_changed and return it."""
        widget.valueChanged.connect(self._emit_changed)
        return widget

    # ── data flow ──

    def _on_category_changed(self, category: str):
        current_sub = self._sub_combo.currentText()
        self._sub_combo.blockSignals(True)
        self._sub_combo.clear()
        self._sub_combo.addItems(ITEM_CATEGORIES.get(category, []))
        if current_sub in ITEM_CATEGORIES.get(category, []):
            self._sub_combo.setCurrentText(current_sub)
        self._sub_combo.blockSignals(False)
        self._emit_changed()

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
        """Shared by the file dialog and drag-and-drop onto the icon."""
        self._icon_btn.set_image(path)
        self._record["image_path"] = path
        self.image_changed.emit(path)
        self._emit_changed()

    def _on_add_tag(self):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Nova tag", "Tag:")
        if ok and text.strip():
            self._tags.append(text.strip())
            self._refresh_tags()
            self._emit_changed()

    def _refresh_tags(self):
        while self._tags_row.count():
            w = self._tags_row.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for tag in self._tags:
            chip = QToolButton()
            chip.setText(f"{tag}  ✕")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(f"""
                QToolButton {{ background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                    border: none; border-radius: 4px; padding: 1px 6px; font-size: 9px; }}
                QToolButton:hover {{ background: rgba(239,83,80,0.25); color: {Colors.ERROR}; }}
            """)
            chip.clicked.connect(lambda _=False, t=tag: self._remove_tag(t))
            self._tags_row.addWidget(chip)

    def _remove_tag(self, tag: str):
        if tag in self._tags:
            self._tags.remove(tag)
            self._refresh_tags()
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

        category = record.get("item_type") or "Arma"
        if category not in ITEM_CATEGORY_NAMES:
            category = "Outro"
        self._cat_combo.setCurrentText(category)
        self._sub_combo.blockSignals(True)
        self._sub_combo.clear()
        self._sub_combo.addItems(ITEM_CATEGORIES.get(category, []))
        self._sub_combo.setCurrentText(record.get("subcategory") or "")
        self._sub_combo.blockSignals(False)

        rarity = record.get("rarity") or "common"
        idx = self._rarity_combo.findData(rarity)
        self._rarity_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._level_spin.setValue(int(record.get("level_req") or 1))
        self._priority_spin.setValue(int(stats.get("priority", 0)))
        self._desc_edit.setPlainText(record.get("description", ""))

        self._peso.setValue(float(stats.get("peso", 0)))
        self._valor.setValue(int(stats.get("valor", 0)))
        self._stack_max.setValue(int(stats.get("stack_max", 1)))
        self._durabilidade.setValue(int(stats.get("durabilidade", 100)))
        self._nivel_min.setValue(int(stats.get("nivel_min", record.get("level_req") or 1)))
        self._classe.setCurrentText(stats.get("classe", "Todas"))
        for key, _label, default in ITEM_FLAGS:
            self._flag_switches[key].setChecked(bool(stats.get(key, default)))
        self._consumivel.setChecked(bool(stats.get("consumable", False)))

        self._uso.setCurrentText(stats.get("uso", "Passivo"))
        self._cooldown_item.setValue(float(stats.get("cooldown", 0)))
        self._efeito_uso.setText(stats.get("efeito_uso", ""))

        self._attack.setValue(float(stats.get("attack", 0)))
        self._atk_speed.setValue(float(stats.get("atk_speed", 1.0)))
        self._crit.setValue(float(stats.get("crit", 0)))
        self._range.setValue(float(stats.get("range", 0)))
        self._dmg_type.setCurrentText(stats.get("dmg_type", DAMAGE_TYPES[0]))
        self._element.setCurrentText(stats.get("element", ELEMENT_OPTIONS[0]))

        self._req_forca.setValue(int(stats.get("req_forca", 0)))
        self._req_destreza.setValue(int(stats.get("req_destreza", 0)))
        self._req_inteligencia.setValue(int(stats.get("req_inteligencia", 0)))
        self._req_reputacao.setText(stats.get("req_reputacao", ""))

        self._tags = list(stats.get("tags", []))
        self._refresh_tags()
        self._tab_bar.set_current(0)
        self._stack.setCurrentIndex(0)
        self._loading = False

    def collect(self) -> dict:
        """DB-column dict for ItemRepository.update() — id is excluded (the
        panel already knows it)."""
        stats = {
            "priority": self._priority_spin.value(),
            "peso": self._peso.value(),
            "valor": self._valor.value(),
            "stack_max": self._stack_max.value(),
            "durabilidade": self._durabilidade.value(),
            "nivel_min": self._nivel_min.value(),
            "classe": self._classe.currentText(),
            "uso": self._uso.currentText(),
            "cooldown": self._cooldown_item.value(),
            "efeito_uso": self._efeito_uso.text().strip(),
            "attack": self._attack.value(),
            "atk_speed": self._atk_speed.value(),
            "crit": self._crit.value(),
            "range": self._range.value(),
            "dmg_type": self._dmg_type.currentText(),
            "element": self._element.currentText(),
            "req_forca": self._req_forca.value(),
            "req_destreza": self._req_destreza.value(),
            "req_inteligencia": self._req_inteligencia.value(),
            "req_reputacao": self._req_reputacao.text().strip(),
            "tags": self._tags,
        }
        for key, _label, _default in ITEM_FLAGS:
            stats[key] = self._flag_switches[key].isChecked()
        stats["consumable"] = self._consumivel.isChecked()
        return {
            "name": self._name_edit.text().strip() or "Novo Item",
            "description": self._desc_edit.toPlainText().strip(),
            "item_type": self._cat_combo.currentText(),
            "subcategory": self._sub_combo.currentText(),
            "rarity": self._rarity_combo.currentData() or "common",
            "level_req": self._level_spin.value(),
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
