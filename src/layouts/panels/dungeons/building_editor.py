"""BuildingEditor — DETALHES DA CONSTRUÇÃO.

As abas da referência viraram seções: "Geral" abriu em Informações Básicas
+ Custos + Requisitos, "Progresso" virou a seção Progressão (é onde o tier
e a construção-mãe da árvore são editados) e "Produção" virou a seção
Produção. Destaque Visual fecha a coluna.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QTextEdit, QLabel

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    STRUCTURE_TYPES, BUILD_STATUSES, STATUS_LABELS, RESOURCE_ICONS,
    _combo, _spin, _no_wheel, caption, value_label, json_list, json_obj,
)
from src.layouts.panels.dungeons.editor_base import SectionEditor
from src.layouts.panels.dungeons.row_list import EditableRowList, TEXT, INT, COMBO, CHECK

_RESOURCE_NAMES = list(RESOURCE_ICONS.keys())


class BuildingEditor(SectionEditor):
    """Editor de uma construção da base."""

    def __init__(self, buildings_provider=None, parent=None):
        """`buildings_provider` devolve a lista de construções — usada pelo
        combo "Desbloqueada por", que é a aresta da árvore de progressão.
        Categoria não tem mais campo aqui — quem decide isso agora é a aba
        ativa em CategoryTabBar, no momento em que a construção é criada."""
        super().__init__("Detalhes da Construção", fallback_icon="🏛", parent=parent)
        self._buildings_provider = buildings_provider or (lambda: [])
        self._record: dict = {}
        self._image = ""
        self.image_changed.connect(self._on_image_changed)
        self._build_sections()
        self.finish_sections()
        self.set_empty()

    # ── Seções ──

    def _build_sections(self):
        # 1. Informações Básicas
        basics = self.add_section("Informações Básicas", expanded=True)
        self._name = self.track(QLineEdit())
        self._name.setFixedHeight(24)
        self._subcategory = self.track(QLineEdit())
        self._subcategory.setFixedHeight(24)
        self._subcategory.setPlaceholderText("Ex.: Coleta, Manufatura...")
        self._max_level = self.track(_no_wheel(_spin(1, 99, 5)))
        self._build_time = self.track(QLineEdit("02:30:00"))
        self._build_time.setPlaceholderText("hh:mm:ss")
        self._build_time.setFixedHeight(24)
        self._structure = self.track(_no_wheel(_combo(STRUCTURE_TYPES)))
        basics.content_layout.addLayout(self.grid([
            ("Nome:", self._name),
            ("Subcategoria:", self._subcategory),
            ("Nível Máximo:", self._max_level),
            ("Tempo de Construção:", self._build_time),
            ("Estrutura:", self._structure),
        ]))
        basics.content_layout.addWidget(caption("Descrição:"))
        self._description = QTextEdit()
        self._description.setFixedHeight(54)
        self.track(self._description)
        basics.content_layout.addWidget(self._description)

        # 2. Custos de Construção
        costs = self.add_section("Custos de Construção", expanded=True)
        self._costs = EditableRowList(
            [("resource", "Recurso", COMBO, _RESOURCE_NAMES, 2),
             ("amount", "Qtd", INT, (0, 9999999), 1)],
            add_label="+ Adicionar recurso",
        )
        self._costs.changed.connect(self._on_field_changed)
        costs.content_layout.addWidget(self._costs)

        # 3. Requisitos
        requirements = self.add_section("Requisitos", expanded=True)
        self._requirements = EditableRowList(
            [("label", "Ex.: Castelo do Nível 2", TEXT, None, 4),
             ("met", "Já atendido", CHECK, None, 0)],
            add_label="+ Adicionar requisito",
        )
        self._requirements.changed.connect(self._on_field_changed)
        requirements.content_layout.addWidget(self._requirements)

        # 4. Progressão — o que a aba "Progresso" media, mais os dois campos
        # que posicionam a construção na árvore ao lado.
        progression = self.add_section("Progressão")
        self._tier = self.track(_no_wheel(_spin(1, 9, 1)))
        self._parent = _no_wheel(_combo(["— Nenhuma (raiz) —"]))
        self.track(self._parent)
        self._status = _no_wheel(_combo([label for _k, label, _c in BUILD_STATUSES]))
        self.track(self._status)
        self._level = self.track(_no_wheel(_spin(0, 99, 1)))
        self._sort_order = self.track(_no_wheel(_spin(0, 999, 0)))
        progression.content_layout.addLayout(self.grid([
            ("Tier:", self._tier),
            ("Desbloqueada por:", self._parent),
            ("Status:", self._status),
            ("Nível Atual:", self._level),
            ("Ordem no Tier:", self._sort_order),
        ]))
        self._progress_lbl = value_label("—")
        progression.content_layout.addLayout(self.stat_grid([
            ("Progresso", self._progress_lbl),
        ], columns=1))

        # 5. Produção
        production = self.add_section("Produção")
        self._prod_resource = _no_wheel(_combo(["Nenhum"] + _RESOURCE_NAMES))
        self.track(self._prod_resource)
        self._prod_rate = self.track(_no_wheel(_spin(0, 999999, 0)))
        self._prod_capacity = self.track(_no_wheel(_spin(0, 9999999, 0)))
        self._prod_workers = self.track(_no_wheel(_spin(0, 999, 0)))
        self._prod_upkeep = self.track(_no_wheel(_spin(0, 999999, 0)))
        production.content_layout.addLayout(self.grid([
            ("Recurso Produzido:", self._prod_resource),
            ("Produção / hora:", self._prod_rate),
            ("Capacidade de Estoque:", self._prod_capacity),
            ("Trabalhadores:", self._prod_workers),
            ("Manutenção / hora (ouro):", self._prod_upkeep),
        ]))
        self._prod_summary = QLabel("")
        self._prod_summary.setWordWrap(True)
        self._prod_summary.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        production.content_layout.addWidget(self._prod_summary)
        for widget in (self._prod_resource, self._prod_rate, self._prod_capacity, self._prod_upkeep):
            signal = getattr(widget, "currentTextChanged", None) or widget.valueChanged
            signal.connect(self._update_production_summary)

        # 6. Destaque Visual
        visuals = self.add_section("Destaque Visual")
        visuals.content_layout.addWidget(caption(
            "Variantes de aparência oferecidas ao jogador quando a construção sobe de nível."))
        self._visuals = EditableRowList(
            [("icon", "🔥", TEXT, None, 0),
             ("name", "Nome da variante", TEXT, None, 3),
             ("level", "Nível", INT, (1, 99), 1)],
            add_label="+ Adicionar variante",
        )
        self._visuals.changed.connect(self._on_field_changed)
        visuals.content_layout.addWidget(self._visuals)

    def _on_image_changed(self, path: str):
        self._image = path

    def _update_production_summary(self, *_args):
        resource = self._prod_resource.currentText()
        if resource == "Nenhum" or not self._prod_rate.value():
            self._prod_summary.setText("Construção sem produção passiva.")
            return
        icon = RESOURCE_ICONS.get(resource, "📦")
        rate = self._prod_rate.value()
        capacity = self._prod_capacity.value()
        full_in = f"{capacity / rate:.1f} h para encher o estoque" if capacity and rate else "estoque ilimitado"
        upkeep = f" · custa {self._prod_upkeep.value()} 🪙/h" if self._prod_upkeep.value() else ""
        self._prod_summary.setText(f"{icon} {rate} {resource}/h · {full_in}{upkeep}")

    # ── Carregar / coletar ──

    def refresh_parent_options(self):
        """Repopula "Desbloqueada por" com as outras construções."""
        current = self._parent.currentData()
        self._parent.blockSignals(True)
        self._parent.clear()
        self._parent.addItem("— Nenhuma (raiz) —", "")
        for building in self._buildings_provider():
            if building.get("id") != self._record.get("id"):
                self._parent.addItem(building.get("name", "—"), building.get("id"))
        index = self._parent.findData(current)
        self._parent.setCurrentIndex(max(0, index))
        self._parent.blockSignals(False)

    def set_empty(self):
        self._loading = True
        self._record = {}
        self._image = ""
        self.set_header("Nenhuma construção selecionada",
                        "Escolha uma na lista ao lado ou crie uma nova.")
        self.set_thumbnail("")
        self.setEnabled(False)
        self._loading = False

    def load(self, record: dict):
        self._loading = True
        try:
            self.setEnabled(True)
            self._record = record
            self._image = record.get("image") or ""
            category = record.get("category") or "—"
            self._name.setText(record.get("name", ""))
            self._subcategory.setText(record.get("subcategory") or "")
            self._max_level.setValue(int(record.get("max_level") or 1))
            self._build_time.setText(record.get("build_time") or "00:00:00")
            self._structure.setCurrentText(record.get("structure") or STRUCTURE_TYPES[0])
            self._description.setPlainText(record.get("description") or "")

            self._costs.set_rows(json_list(record.get("costs")))
            self._requirements.set_rows(json_list(record.get("requirements")))
            self._visuals.set_rows(json_list(record.get("visuals")))

            self._tier.setValue(int(record.get("tier") or 1))
            self._status.setCurrentText(STATUS_LABELS.get(record.get("status"), "Disponível"))
            self._level.setValue(int(record.get("level") or 1))
            self._sort_order.setValue(int(record.get("sort_order") or 0))
            self.refresh_parent_options()
            index = self._parent.findData(record.get("parent_id") or "")
            self._parent.setCurrentIndex(max(0, index))
            max_level = max(1, int(record.get("max_level") or 1))
            self._progress_lbl.setText(
                f"Nível {record.get('level') or 0} de {max_level} "
                f"({round(100 * (int(record.get('level') or 0) / max_level))}%)"
            )

            production = json_obj(record.get("production"))
            self._prod_resource.setCurrentText(production.get("resource") or "Nenhum")
            self._prod_rate.setValue(int(production.get("rate") or 0))
            self._prod_capacity.setValue(int(production.get("capacity") or 0))
            self._prod_workers.setValue(int(production.get("workers") or 0))
            self._prod_upkeep.setValue(int(production.get("upkeep") or 0))
            self._update_production_summary()

            self.set_thumbnail(record.get("image") or "")
            self.set_header(
                record.get("name") or "—",
                f"{category} • Nível {record.get('level') or 1}",
                record.get("description") or "",
                STATUS_LABELS.get(record.get("status"), ""),
            )
        finally:
            self._loading = False

    def collect(self) -> dict:
        import json
        status_key = next(
            (key for key, label, _c in BUILD_STATUSES if label == self._status.currentText()),
            "disponivel",
        )
        return {
            "name": self._name.text().strip() or "Nova Construção",
            "subcategory": self._subcategory.text().strip(),
            "image": self._image,
            "description": self._description.toPlainText().strip(),
            "max_level": self._max_level.value(),
            "level": self._level.value(),
            "build_time": self._build_time.text().strip(),
            "structure": self._structure.currentText(),
            "tier": self._tier.value(),
            "parent_id": self._parent.currentData() or None,
            "status": status_key,
            "sort_order": self._sort_order.value(),
            "costs": json.dumps(self._costs.rows(), ensure_ascii=False),
            "requirements": json.dumps(self._requirements.rows(), ensure_ascii=False),
            "visuals": json.dumps(self._visuals.rows(), ensure_ascii=False),
            "production": json.dumps({
                "resource": self._prod_resource.currentText(),
                "rate": self._prod_rate.value(),
                "capacity": self._prod_capacity.value(),
                "workers": self._prod_workers.value(),
                "upkeep": self._prod_upkeep.value(),
            }, ensure_ascii=False),
        }
