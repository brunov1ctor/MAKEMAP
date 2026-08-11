"""QuestPropertiesPanel — a coluna direita, sempre visível independente da
aba de conteúdo ativa (Fluxo/Geral/Objetivos/...). Três cartões separados
(mesmo estilo "subpanel" com moldura própria usado no resto do app), não um
painel único contínuo:

1. "Propriedades da Quest" — imagem, Nome/Título/Tipo/Região/Nível/Tags/
   Descrição curta.
2. "Configurações" — os toggles (repetível, tempo limite, ...).
3. "Recompensas" — EXP/Gold/Reputação + itens, com o mesmo picker de
   catálogo buscável que Mobs usa em Drops Principais/Habilidades
   (ver mobs/edit_widgets._CatalogPickerDialog) em vez de um menu simples.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QTextEdit, QFrame, QScrollArea, QSizePolicy, QCheckBox, QToolButton,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, combo_qss
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panels.items.editor_base import IconButton
from src.layouts.panels.mobs.edit_widgets import _CatalogPickerDialog
from src.layouts.panels.quests.constants import (
    _combo, _spin, _no_wheel, _section_label, panel_frame_style, sub_header,
    hrule, json_list, json_obj, QUEST_TYPES, PRIORITIES,
)

_CHECKBOX_STYLE = f"""
    QCheckBox {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; spacing: 6px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px; border-radius: 3px;
        border: 1px solid {Colors.BORDER}; background: {Colors.BG_ELEVATED};
    }}
    QCheckBox::indicator:checked {{ background: {Colors.ACCENT}; border-color: {Colors.ACCENT}; }}
"""


def _toggle_row(label_text: str) -> tuple[QHBoxLayout, QCheckBox]:
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
    box = QCheckBox()
    box.setStyleSheet(_CHECKBOX_STYLE)
    row.addWidget(lbl, 1)
    row.addWidget(box)
    return row, box


def _card(title: str, expanded: bool = True) -> tuple[QFrame, QVBoxLayout, CollapsibleSection]:
    """Cartão colapsável — clicar no cabeçalho recolhe/expande o conteúdo.
    Os 3 cartões (Propriedades/Configurações/Recompensas) começam todos
    abertos; o painel inteiro fica desabilitado (via set_empty()) enquanto
    nenhuma quest está selecionada, o que também bloqueia o clique no
    cabeçalho — então um cartão que iniciasse fechado não daria pra reabrir
    nesse estado."""
    frame = QFrame()
    frame.setObjectName("subpanel")
    frame.setStyleSheet(panel_frame_style())
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(6, 6, 6, 6)
    outer.setSpacing(0)
    section = CollapsibleSection(title, expanded=expanded)
    outer.addWidget(section)
    return frame, section.content_layout, section


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


class _RewardItemRow(QFrame):
    removed = Signal(str)

    def __init__(self, item_id: str, name: str, qty: int, parent=None):
        super().__init__(parent)
        self._item_id = item_id
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 6, 5)
        row.setSpacing(6)
        icon = QLabel("🎁")
        icon.setStyleSheet("font-size: 13px;")
        row.addWidget(icon)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px;")
        row.addWidget(name_lbl, 1)
        qty_lbl = QLabel("×")
        qty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px;")
        row.addWidget(qty_lbl)
        self._qty = _spin(1, 9999, qty or 1)
        self._qty.setFixedWidth(50)
        _no_wheel(self._qty)
        row.addWidget(self._qty)
        close = QToolButton()
        close.setText("✕")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(16, 16)
        close.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 9px; }} "
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        close.clicked.connect(lambda: self.removed.emit(self._item_id))
        row.addWidget(close)

    def item_id(self) -> str:
        return self._item_id

    def qty(self) -> int:
        return self._qty.value()

    def qty_changed_connect(self, slot):
        self._qty.valueChanged.connect(slot)


class QuestPropertiesPanel(QFrame):
    """Coluna direita persistente — visível independente da aba de conteúdo
    ativa no meio do painel (Fluxo/Geral/Objetivos/...)."""

    changed = Signal()
    image_changed = Signal(str)

    THUMB = (150, 96)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self._input_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(260)

        self._loading = False
        self._tags: list[str] = []
        self._image = ""
        self._reward_items: list[dict] = []  # [{"item_id":.., "name":..}]
        self._items_catalog: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(10)

        column.addWidget(self._build_properties_card())
        column.addWidget(self._build_settings_card())
        column.addWidget(self._build_rewards_card())
        column.addStretch()

        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        for w in (self._name, self._title, self._type, self._region,
                  self._level_min, self._level_max, self._description,
                  self._repeatable, self._time_limit, self._fail_on_abandon,
                  self._auto_accept, self._hide_on_map, self._priority,
                  self._reward_exp, self._reward_gold, self._reward_rep):
            self._track(w)

        self.set_empty()

    # ── cartão 1: Propriedades da Quest ──

    def _build_properties_card(self) -> QFrame:
        frame, lay, _section = _card("Propriedades da Quest")

        self._thumb = IconButton("🗺", size=self.THUMB, crop=True)
        self._thumb.setToolTip("Clique ou arraste uma imagem")
        self._thumb.clicked.connect(self._on_pick_image)
        self._thumb.image_dropped.connect(self._on_image_picked)
        thumb_row = QHBoxLayout()
        thumb_row.addStretch()
        thumb_row.addWidget(self._thumb)
        thumb_row.addStretch()
        lay.addLayout(thumb_row)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Nome da quest")
        self._title = QLineEdit()
        self._title.setPlaceholderText("Título/subtítulo")
        self._type = _combo(QUEST_TYPES)
        _no_wheel(self._type)
        self._region = _combo([])
        _no_wheel(self._region)
        self._level_min = _spin(1, 999, 1)
        self._level_max = _spin(1, 999, 1)
        _no_wheel(self._level_min)
        _no_wheel(self._level_max)

        lay.addLayout(self._field("Nome", self._name))
        lay.addLayout(self._field("Título", self._title))
        lay.addLayout(self._field("Tipo", self._type))
        lay.addLayout(self._field("Região", self._region))

        level_row = QHBoxLayout()
        level_lbl = QLabel("Nível recomendado")
        level_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        level_row.addWidget(level_lbl)
        level_row.addWidget(self._level_min, 1)
        dash = QLabel("—")
        dash.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent; border: none;")
        level_row.addWidget(dash)
        level_row.addWidget(self._level_max, 1)
        lay.addLayout(level_row)

        lay.addWidget(_section_label("Tags"))
        # _tag_input vive dentro do _tags_flow (inline com os chips), mesmo
        # padrão do painel de Lore — não como widget separado no lay.
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("+ Adicionar tag...")
        self._tag_input.setFixedWidth(150)
        self._tag_input.returnPressed.connect(self._on_add_tag)

        self._tags_holder = QWidget()
        self._tags_holder.setStyleSheet("background: transparent;")
        from src.layouts.panels.brush.flow_layout import FlowLayout
        self._tags_flow = FlowLayout(self._tags_holder, spacing=4)
        self._tags_flow.addWidget(self._tag_input)
        lay.addWidget(self._tags_holder)

        lay.addWidget(_section_label("Descrição curta"))
        self._description = QTextEdit()
        self._description.setFixedHeight(64)
        self._description.setPlaceholderText("Um resumo curto da missão...")
        # QTextEdit is a QAbstractScrollArea — it swallows every wheel event
        # for its own internal scrolling by default, even when the text fits
        # and there's nothing to scroll, instead of letting it bubble up to
        # the panel's outer QScrollArea. Every combo/spin box in this panel
        # already gets this same treatment (_no_wheel) for the same reason;
        # this QTextEdit was the one widget that didn't, and was exactly the
        # spot the mouse tends to land on while trying to scroll the column.
        _no_wheel(self._description)
        lay.addWidget(self._description)
        return frame

    # ── cartão 2: Configurações ──

    def _build_settings_card(self) -> QFrame:
        frame, lay, _section = _card("Configurações")

        _, self._repeatable = _toggle_row("Repetível")
        self._time_limit = _spin(0, 1440, 0)
        _no_wheel(self._time_limit)
        _, self._fail_on_abandon = _toggle_row("Falha se abandonar")
        _, self._auto_accept = _toggle_row("Auto aceitar")
        _, self._hide_on_map = _toggle_row("Ocultar no mapa")
        self._priority = _combo(PRIORITIES)
        _no_wheel(self._priority)

        # Grid 2 colunas em vez de um campo por linha — os 6 campos deste
        # cartão cabem lado a lado sem apertar, reduzindo a altura pela
        # metade (mesmo padrão de EditorBase.grid() usado em Dungeons).
        lay.addLayout(self._grid([
            ("Repetível", self._repeatable),
            ("Tempo limite (min)", self._time_limit),
            ("Falha se abandonar", self._fail_on_abandon),
            ("Auto aceitar", self._auto_accept),
            ("Ocultar no mapa", self._hide_on_map),
            ("Prioridade", self._priority),
        ], columns=2))
        return frame

    # ── cartão 3: Recompensas ──

    def _build_rewards_card(self) -> QFrame:
        frame, lay, _section = _card("Recompensas")

        stats = QHBoxLayout()
        self._reward_exp = _spin(0, 999999999, 0)
        self._reward_gold = _spin(0, 999999999, 0)
        self._reward_rep = _spin(0, 999999999, 0)
        for w in (self._reward_exp, self._reward_gold, self._reward_rep):
            _no_wheel(w)
        stats.addLayout(self._stat("EXP", self._reward_exp))
        stats.addLayout(self._stat("Gold", self._reward_gold))
        stats.addLayout(self._stat("Reputação", self._reward_rep))
        lay.addLayout(stats)

        self._rewards_holder = QVBoxLayout()
        self._rewards_holder.setSpacing(4)
        lay.addLayout(self._rewards_holder)

        self._add_reward_btn = QToolButton()
        self._add_reward_btn.setText("+ Adicionar Recompensa")
        self._add_reward_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_reward_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 5px 10px; font-size: 10px; }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); border-color: {Colors.ACCENT}; }}
        """)
        self._add_reward_btn.clicked.connect(self._on_open_reward_picker)
        lay.addWidget(self._add_reward_btn)
        return frame

    # ── estilo local (mesmo _INPUT_STYLE + regra de QTextEdit multiline) ──

    @staticmethod
    def _input_style() -> str:
        return f"""
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 5px; padding: 3px 6px; color: {Colors.TEXT_PRIMARY}; font-size: 10px;
            }}
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {Colors.ACCENT}; }}
            {combo_qss(padding="3px 8px")}
        """

    @staticmethod
    def _field(label_text: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        lbl.setFixedWidth(70)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    @staticmethod
    def _grid(pairs: list[tuple[str, QWidget]], columns: int = 2) -> QGridLayout:
        """Rótulo à esquerda, campo à direita, em `columns` pares por linha
        — mesmo padrão de EditorBase.grid() (Dungeons)."""
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)
        for i, (label_text, widget) in enumerate(pairs):
            row, col = divmod(i, columns)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(lbl, row, col * 2)
            layout.addWidget(widget, row, col * 2 + 1)
            layout.setColumnStretch(col * 2 + 1, 1)
        return layout

    @staticmethod
    def _stat(label_text: str, widget: QWidget) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        col.addWidget(lbl)
        col.addWidget(widget)
        return col

    def _track(self, widget):
        for signal_name in ("textChanged", "currentTextChanged", "valueChanged", "toggled"):
            signal = getattr(widget, signal_name, None)
            if signal is not None:
                signal.connect(self._on_field_changed)
                break

    def _on_field_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    # ── API pública ──

    def set_regions(self, regions: list[dict]):
        current = self._region.currentText()
        self._region.blockSignals(True)
        self._region.clear()
        self._region.addItem("— Nenhuma —")
        self._region.addItems([r.get("name", "") for r in regions])
        if current:
            idx = self._region.findText(current)
            if idx >= 0:
                self._region.setCurrentIndex(idx)
        self._region.blockSignals(False)

    def set_items_catalog(self, items: list[dict]):
        """Catálogo usado pelo picker buscável de "+ Adicionar Recompensa"
        (mesmo componente que Mobs usa em Drops Principais/Habilidades)."""
        self._items_catalog = items

    # ── Recompensas: itens ──

    def _on_open_reward_picker(self):
        dlg = _CatalogPickerDialog("Adicionar Recompensa", "Buscar Item", self._items_catalog, parent=self)
        dlg.exec()
        if dlg.picked_id:
            self._on_pick_reward_item(dlg.picked_id)

    def _on_pick_reward_item(self, item_id: str):
        if any(r["item_id"] == item_id for r in self._reward_items):
            return
        entry = next((i for i in self._items_catalog if i.get("id") == item_id), None)
        name = entry.get("name") if entry else ""
        self._reward_items.append({"item_id": item_id, "name": name or "", "qty": 1})
        self._rebuild_reward_rows()
        self._on_field_changed()

    def _rebuild_reward_rows(self):
        while self._rewards_holder.count():
            item = self._rewards_holder.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for reward in self._reward_items:
            row = _RewardItemRow(reward["item_id"], reward.get("name", ""), reward.get("qty", 1))
            row.removed.connect(self._on_remove_reward_item)
            row.qty_changed_connect(self._on_field_changed)
            self._rewards_holder.addWidget(row)

    def _on_remove_reward_item(self, item_id: str):
        self._reward_items = [r for r in self._reward_items if r["item_id"] != item_id]
        self._rebuild_reward_rows()
        self._on_field_changed()

    # ── Tags ──

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
            # A widget built with no parent stays hidden after addWidget()
            # reparents it — Qt only shows it asynchronously later, missing
            # the layout pass that runs right after and leaving the chip
            # stuck without a real geometry.
            chip.show()
        self._tags_flow.addWidget(self._tag_input)

    # ── Imagem ──

    def _on_pick_image(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if path:
            self._on_image_picked(path)

    def _on_image_picked(self, path: str):
        self._thumb.set_image(path)
        self._image = path
        self.image_changed.emit(path)
        self._on_field_changed()

    # ── carregar / coletar ──

    def set_empty(self):
        self._loading = True
        try:
            self._name.clear()
            self._title.clear()
            self._type.setCurrentIndex(0)
            self._region.setCurrentIndex(0)
            self._level_min.setValue(1)
            self._level_max.setValue(1)
            self._tags = []
            self._rebuild_tags()
            self._description.clear()
            self._repeatable.setChecked(False)
            self._time_limit.setValue(0)
            self._fail_on_abandon.setChecked(False)
            self._auto_accept.setChecked(False)
            self._hide_on_map.setChecked(False)
            self._priority.setCurrentText("Média")
            self._reward_exp.setValue(0)
            self._reward_gold.setValue(0)
            self._reward_rep.setValue(0)
            self._reward_items = []
            self._rebuild_reward_rows()
            self._image = ""
            self._thumb.set_image("")
        finally:
            self._loading = False
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._loading = True
        try:
            self._name.setText(record.get("name") or "")
            self._title.setText(record.get("title") or "")
            qtype = record.get("quest_type") or "Principal"
            if qtype not in QUEST_TYPES:
                qtype = "Principal"
            self._type.setCurrentText(qtype)
            region_name = record.get("_region_name") or ""
            idx = self._region.findText(region_name) if region_name else 0
            self._region.setCurrentIndex(idx if idx >= 0 else 0)
            self._level_min.setValue(int(record.get("level_req") or 1))
            self._level_max.setValue(int(record.get("level_max") or 1))
            self._tags = list(json_list(record.get("tags_json")))
            self._rebuild_tags()
            self._description.setPlainText(record.get("description") or "")
            self._repeatable.setChecked(bool(record.get("repeatable")))
            self._time_limit.setValue(int((record.get("time_limit_seconds") or 0) / 60))
            self._fail_on_abandon.setChecked(bool(record.get("fail_on_abandon")))
            self._auto_accept.setChecked(bool(record.get("auto_accept")))
            self._hide_on_map.setChecked(bool(record.get("hide_on_map")))
            priority = record.get("priority") or "Média"
            if priority not in PRIORITIES:
                priority = "Média"
            self._priority.setCurrentText(priority)

            rewards = json_obj(record.get("rewards"))
            self._reward_exp.setValue(int(rewards.get("exp") or 0))
            self._reward_gold.setValue(int(rewards.get("gold") or 0))
            self._reward_rep.setValue(int(rewards.get("reputation") or 0))
            self._reward_items = list(rewards.get("items") or [])
            self._rebuild_reward_rows()

            self._image = record.get("image") or ""
            self._thumb.set_image(self._image)
        finally:
            self._loading = False

    def collect(self) -> dict:
        """Retorna os campos prontos para uow.quests.update(). `image` só
        aparece quando aponta para um arquivo local recém-escolhido — quem
        chama decide se precisa importar (ver panel.py._save_quest)."""
        region_name = self._region.currentText()
        rows = [self._rewards_holder.itemAt(i).widget() for i in range(self._rewards_holder.count())]
        items_out = [
            {"item_id": reward["item_id"], "name": reward.get("name", ""), "qty": row.qty()}
            for reward, row in zip(self._reward_items, rows)
        ]
        values = {
            "name": self._name.text().strip() or "Nova Quest",
            "title": self._title.text().strip(),
            "quest_type": self._type.currentText(),
            "_region_name": region_name if self._region.currentIndex() > 0 else "",
            "level_req": self._level_min.value(),
            "level_max": self._level_max.value(),
            "tags_json": json.dumps(self._tags, ensure_ascii=False),
            "description": self._description.toPlainText(),
            "repeatable": 1 if self._repeatable.isChecked() else 0,
            "time_limit_seconds": self._time_limit.value() * 60,
            "fail_on_abandon": 1 if self._fail_on_abandon.isChecked() else 0,
            "auto_accept": 1 if self._auto_accept.isChecked() else 0,
            "hide_on_map": 1 if self._hide_on_map.isChecked() else 0,
            "priority": self._priority.currentText(),
            "rewards": json.dumps({
                "exp": self._reward_exp.value(),
                "gold": self._reward_gold.value(),
                "reputation": self._reward_rep.value(),
                "items": items_out,
            }, ensure_ascii=False),
        }
        if self._image:
            values["image"] = self._image
        return values
