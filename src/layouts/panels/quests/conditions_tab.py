"""ConditionsTab — aba de conteúdo "Condições": pré-requisitos para aceitar
a quest (nível mínimo, outra quest concluída, item em posse, etc.), guardados
em `conditions_json` (migration 36). Mesmo EditableRowList genérico de
ObjectivesTab, só com colunas diferentes.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QScrollArea, QSizePolicy
from PySide6.QtCore import Signal

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.row_list import EditableRowList, TEXT, COMBO
from src.layouts.panels.quests.constants import panel_frame_style, sub_header, json_list

CONDITION_TYPES = [
    "Nível mínimo", "Quest concluída", "Item em posse",
    "Reputação mínima", "Personalizado",
]


class ConditionsTab(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header("Condições para aceitar"))

        hint = QLabel("O que o jogador precisa ter/ter feito antes de a quest ficar disponível.")
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
                ("condition_type", "Tipo", COMBO, CONDITION_TYPES, 2),
                ("value", "Valor (ex.: nível, nome da quest/item/facção)", TEXT, None, 3),
            ],
            add_label="+ Adicionar condição",
        )
        self._list.changed.connect(self.changed.emit)
        scroll.setWidget(self._list)
        outer.addWidget(scroll, 1)

    def set_empty(self):
        self._list.set_rows([])
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._list.set_rows(json_list(record.get("conditions_json")))

    def collect(self) -> dict:
        import json
        return {"conditions_json": json.dumps(self._list.rows(), ensure_ascii=False)}
