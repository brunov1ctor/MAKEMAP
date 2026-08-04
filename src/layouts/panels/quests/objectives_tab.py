"""ObjectivesTab — aba de conteúdo "Objetivos": os passos que o jogador
precisa cumprir, guardados na coluna `objectives` (JSON list) que já existia
na tabela `quests` desde antes deste painel existir. Reaproveita
EditableRowList (dungeons/row_list.py) — o mesmo widget genérico que
Custos/Requisitos/Destaque Visual de Construções usam — em vez de montar
mais uma variação de "N linhas + botão +".
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QScrollArea, QSizePolicy
from PySide6.QtCore import Signal

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.row_list import EditableRowList, TEXT, INT, COMBO
from src.layouts.panels.quests.constants import panel_frame_style, sub_header, json_list

OBJECTIVE_TYPES = [
    "Falar com NPC", "Coletar item", "Derrotar inimigo",
    "Chegar em local", "Interagir com objeto", "Personalizado",
]


class ObjectivesTab(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header("Objetivos"))

        hint = QLabel("Os passos que o jogador precisa cumprir, na ordem em que aparecem no diário de missões.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        outer.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._list = EditableRowList(
            columns=[
                ("description", "Descrição do objetivo", TEXT, None, 3),
                ("type", "Tipo", COMBO, OBJECTIVE_TYPES, 2),
                ("count", "Qtd", INT, (1, 999), 1),
            ],
            add_label="+ Adicionar objetivo",
        )
        self._list.changed.connect(self.changed.emit)
        scroll.setWidget(self._list)
        outer.addWidget(scroll, 1)

    def set_empty(self):
        self._list.set_rows([])
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._list.set_rows(json_list(record.get("objectives")))

    def collect(self) -> dict:
        import json
        return {"objectives": json.dumps(self._list.rows(), ensure_ascii=False)}
