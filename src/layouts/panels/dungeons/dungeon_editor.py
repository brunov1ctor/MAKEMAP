"""DungeonEditor — DETALHES DA DUNGEON.

Mesma conversão de abas em seções da construção: "Geral" virou Informações
Básicas, "Layout" e "Encontros" e "Chefes" viraram seções próprias, e os
blocos que na referência estavam soltos na coluna da direita (Recompensas,
Modificadores, Requisitos de Acesso, Status, Informações Adicionais) entram
na mesma pilha, na ordem em que se costuma preencher: o que define a
dungeon primeiro, o que ela devolve depois, e a telemetria por último.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QLineEdit, QTextEdit, QCheckBox, QLabel

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import (
    DIFFICULTIES, GENERATION_TYPES, DUNGEON_BIOMES,
    DUNGEON_MODIFIERS, _combo, _spin, _no_wheel, caption, value_label,
    json_list, json_obj,
)
from src.layouts.panels.dungeons.editor_base import SectionEditor
from src.layouts.panels.dungeons.row_list import EditableRowList, TEXT, INT


class DungeonEditor(SectionEditor):
    """Editor de uma dungeon."""

    def __init__(self, parent=None):
        """Tipo não tem mais campo aqui — quem decide isso agora é a aba
        ativa em CategoryTabBar, no momento em que a dungeon é criada."""
        super().__init__("Detalhes da Dungeon", fallback_icon="🕳", parent=parent)
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
        self._code = self.track(QLineEdit())
        self._code.setFixedHeight(24)
        self._code.setPlaceholderText("dungeon_echo_cave_01")
        self._level_min = self.track(_no_wheel(_spin(1, 999, 1)))
        self._level_max = self.track(_no_wheel(_spin(1, 999, 10)))
        self._difficulty = self.track(_no_wheel(_combo(DIFFICULTIES, "Normal")))
        self._est_time = self.track(QLineEdit("20:00"))
        self._est_time.setFixedHeight(24)
        self._est_time.setPlaceholderText("mm:ss")
        self._group_min = self.track(_no_wheel(_spin(1, 100, 1)))
        self._group_max = self.track(_no_wheel(_spin(1, 100, 4)))
        self._biome = self.track(_no_wheel(_combo(DUNGEON_BIOMES)))
        basics.content_layout.addLayout(self.grid([
            ("Nome:", self._name),
            ("ID:", self._code),
            ("Dificuldade:", self._difficulty),
            ("Nível Mínimo:", self._level_min),
            ("Nível Máximo:", self._level_max),
            ("Tempo Estimado:", self._est_time),
            ("Bioma:", self._biome),
            ("Grupo (mín.):", self._group_min),
            ("Grupo (máx.):", self._group_max),
        ], columns=2))
        basics.content_layout.addWidget(caption("Descrição:"))
        self._description = QTextEdit()
        self._description.setFixedHeight(54)
        self.track(self._description)
        basics.content_layout.addWidget(self._description)

        # 2. Layout
        layout_section = self.add_section("Layout")
        self._rooms = self.track(_no_wheel(_spin(1, 999, 1)))
        self._floors = self.track(_no_wheel(_spin(1, 99, 1)))
        self._generation = self.track(_no_wheel(_combo(GENERATION_TYPES)))
        self._secret_rooms = self.track(_no_wheel(_spin(0, 99, 0)))
        self._checkpoints = QCheckBox("Tem pontos de retorno (checkpoints)")
        self.track(self._checkpoints)
        layout_section.content_layout.addLayout(self.grid([
            ("Salas:", self._rooms),
            ("Andares:", self._floors),
            ("Geração:", self._generation),
            ("Salas Secretas:", self._secret_rooms),
        ], columns=2))
        layout_section.content_layout.addWidget(self._checkpoints)
        self._layout_summary = QLabel("")
        self._layout_summary.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        layout_section.content_layout.addWidget(self._layout_summary)
        for widget in (self._rooms, self._floors):
            widget.valueChanged.connect(self._update_layout_summary)

        # 3. Encontros
        encounters = self.add_section("Encontros")
        self._encounters = EditableRowList(
            [("mob", "Criatura", TEXT, None, 3),
             ("count", "Qtd", INT, (1, 999), 1),
             ("room", "Sala", INT, (1, 999), 1)],
            add_label="+ Adicionar encontro",
        )
        self._encounters.changed.connect(self._on_field_changed)
        encounters.content_layout.addWidget(self._encounters)

        # 4. Chefes
        bosses = self.add_section("Chefes")
        self._bosses = EditableRowList(
            [("name", "Nome do chefe", TEXT, None, 3),
             ("room", "Sala", INT, (1, 999), 1),
             ("mechanic", "Mecânica principal", TEXT, None, 3)],
            add_label="+ Adicionar chefe",
        )
        self._bosses.changed.connect(self._on_field_changed)
        bosses.content_layout.addWidget(self._bosses)

        # 5. Recompensas Principais
        rewards = self.add_section("Recompensas Principais", expanded=True)
        self._rewards = EditableRowList(
            [("icon", "⚔", TEXT, None, 0),
             ("item", "Item", TEXT, None, 3),
             ("amount", "Qtd", INT, (1, 9999), 1),
             ("chance", "Chance %", INT, (1, 100), 1)],
            add_label="+ Adicionar recompensa",
        )
        self._rewards.changed.connect(self._on_field_changed)
        rewards.content_layout.addWidget(self._rewards)

        # 6. Modificadores — multiplicadores aplicados dentro da dungeon.
        modifiers = self.add_section("Modificadores")
        modifiers.content_layout.addWidget(caption(
            "Variação em relação ao mundo aberto, em porcentagem."))
        self._modifiers = {}
        pairs = []
        for key, label, icon, suffix in DUNGEON_MODIFIERS:
            spin = _no_wheel(_spin(-100, 1000, 0))
            spin.setSuffix(suffix)
            self.track(spin)
            self._modifiers[key] = spin
            pairs.append((f"{icon}  {label}:", spin))
        modifiers.content_layout.addLayout(self.grid(pairs, columns=2))

        # 7. Requisitos de Acesso
        access = self.add_section("Requisitos de Acesso")
        self._req_level = self.track(_no_wheel(_spin(1, 999, 1)))
        self._req_quest = self.track(QLineEdit())
        self._req_quest.setFixedHeight(24)
        self._req_quest.setPlaceholderText("Quest obrigatória (opcional)")
        self._req_item = self.track(QLineEdit())
        self._req_item.setFixedHeight(24)
        self._req_item.setPlaceholderText("Item-chave (opcional)")
        access.content_layout.addLayout(self.grid([
            ("Nível do Jogador:", self._req_level),
            ("Quest:", self._req_quest),
            ("Item:", self._req_item),
        ]))

        # 8. Status
        status = self.add_section("Status", expanded=True)
        self._active = QCheckBox("Ativo")
        self._visible = QCheckBox("Visível no Mapa")
        self._group_available = QCheckBox("Disponível para Grupos")
        for box in (self._active, self._visible, self._group_available):
            self.track(box)
            status.content_layout.addWidget(box)

        # 9. Informações Adicionais — só leitura, alimentado por quem
        # integrar a telemetria do jogo.
        extra = self.add_section("Informações Adicionais")
        self._stat_success = value_label("—")
        self._stat_completions = value_label("—")
        self._stat_best = value_label("—")
        self._stat_attempts = value_label("—")
        extra.content_layout.addLayout(self.stat_grid([
            ("Taxa de Sucesso", self._stat_success),
            ("Jogadores Completaram", self._stat_completions),
            ("Melhor Tempo", self._stat_best),
            ("Tentativas Totais", self._stat_attempts),
        ], columns=2))

    def _update_layout_summary(self, *_args):
        rooms, floors = self._rooms.value(), self._floors.value()
        per_floor = rooms / floors if floors else rooms
        self._layout_summary.setText(f"{rooms} salas em {floors} andar(es) — ~{per_floor:.1f} por andar.")

    def _on_image_changed(self, path: str):
        self._image = path

    # ── Carregar / coletar ──

    def set_empty(self):
        self._loading = True
        self._record = {}
        self._image = ""
        self.set_header("Nenhuma dungeon selecionada",
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
            self._name.setText(record.get("name", ""))
            self._code.setText(record.get("code") or "")
            self._level_min.setValue(int(record.get("level_min") or 1))
            self._level_max.setValue(int(record.get("level_max") or 1))
            self._difficulty.setCurrentText(record.get("difficulty") or "Normal")
            self._est_time.setText(record.get("est_time") or "")
            self._group_min.setValue(int(record.get("group_min") or 1))
            self._group_max.setValue(int(record.get("group_max") or 1))
            self._biome.setCurrentText(record.get("biome") or DUNGEON_BIOMES[0])
            self._description.setPlainText(record.get("description") or "")

            self._rooms.setValue(int(record.get("rooms") or 1))
            self._floors.setValue(int(record.get("floors") or 1))
            self._generation.setCurrentText(record.get("generation") or GENERATION_TYPES[0])
            self._secret_rooms.setValue(int(record.get("secret_rooms") or 0))
            self._checkpoints.setChecked(bool(record.get("checkpoints")))
            self._update_layout_summary()

            self._encounters.set_rows(json_list(record.get("encounters")))
            self._bosses.set_rows(json_list(record.get("bosses")))
            # Recompensas gravadas antes da coluna "chance" existir não têm
            # esse campo — tratamos como garantidas (100%) em vez de 0%.
            rewards = json_list(record.get("rewards"))
            for reward in rewards:
                reward.setdefault("chance", 100)
            self._rewards.set_rows(rewards)

            modifiers = json_obj(record.get("modifiers"))
            for key, spin in self._modifiers.items():
                spin.setValue(int(modifiers.get(key) or 0))

            self._req_level.setValue(int(record.get("req_level") or 1))
            self._req_quest.setText(record.get("req_quest") or "")
            self._req_item.setText(record.get("req_item") or "")

            self._active.setChecked(bool(record.get("active", 1)))
            self._visible.setChecked(bool(record.get("visible_on_map", 1)))
            self._group_available.setChecked(bool(record.get("group_available")))

            self._stat_success.setText(f"{round(float(record.get('success_rate') or 0))}%")
            self._stat_completions.setText(f"{int(record.get('completions') or 0):,}".replace(",", "."))
            self._stat_best.setText(record.get("best_time") or "—")
            self._stat_attempts.setText(f"{int(record.get('attempts') or 0):,}".replace(",", "."))

            self.set_thumbnail(record.get("image") or "")
            self.set_header(
                record.get("name") or "—",
                f"{record.get('dungeon_type') or '—'} • Nível "
                f"{record.get('level_min') or 1}-{record.get('level_max') or 1}",
                record.get("description") or "",
                "Disponível" if record.get("active", 1) else "Inativa",
            )
        finally:
            self._loading = False

    def collect(self) -> dict:
        return {
            "name": self._name.text().strip() or "Nova Dungeon",
            "code": self._code.text().strip(),
            "image": self._image,
            "level_min": self._level_min.value(),
            "level_max": self._level_max.value(),
            "difficulty": self._difficulty.currentText(),
            "est_time": self._est_time.text().strip(),
            "group_min": self._group_min.value(),
            "group_max": self._group_max.value(),
            "biome": self._biome.currentText(),
            "description": self._description.toPlainText().strip(),
            "rooms": self._rooms.value(),
            "floors": self._floors.value(),
            "generation": self._generation.currentText(),
            "secret_rooms": self._secret_rooms.value(),
            "checkpoints": int(self._checkpoints.isChecked()),
            "encounters": json.dumps(self._encounters.rows(), ensure_ascii=False),
            "bosses": json.dumps(self._bosses.rows(), ensure_ascii=False),
            "rewards": json.dumps(self._rewards.rows(), ensure_ascii=False),
            "modifiers": json.dumps(
                {key: spin.value() for key, spin in self._modifiers.items()}, ensure_ascii=False),
            "req_level": self._req_level.value(),
            "req_quest": self._req_quest.text().strip(),
            "req_item": self._req_item.text().strip(),
            "active": int(self._active.isChecked()),
            "visible_on_map": int(self._visible.isChecked()),
            "group_available": int(self._group_available.isChecked()),
        }
