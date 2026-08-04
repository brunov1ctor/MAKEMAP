"""EventsTab — aba de conteúdo "Eventos": gatilhos que disparam em pontos da
quest (ao iniciar, ao completar um objetivo, ao concluir, ao abandonar),
guardados em `events_json` (migration 36). Mesmo EditableRowList genérico de
ObjectivesTab/ConditionsTab, só com colunas diferentes.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QScrollArea, QSizePolicy
from PySide6.QtCore import Signal

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.row_list import EditableRowList, TEXT, COMBO
from src.layouts.panels.quests.constants import panel_frame_style, sub_header, json_list

EVENT_TRIGGERS = [
    "Ao iniciar", "Ao completar objetivo", "Ao concluir quest",
    "Ao abandonar", "Personalizado",
]


class EventsTab(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header("Eventos"))

        hint = QLabel("Cutscenes, spawns ou outros gatilhos disparados em pontos-chave da quest.")
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
                ("trigger", "Gatilho", COMBO, EVENT_TRIGGERS, 2),
                ("description", "Descrição do evento", TEXT, None, 3),
            ],
            add_label="+ Adicionar evento",
        )
        self._list.changed.connect(self.changed.emit)
        scroll.setWidget(self._list)
        outer.addWidget(scroll, 1)

    def set_empty(self):
        self._list.set_rows([])
        self.setEnabled(False)

    def load(self, record: dict):
        self.setEnabled(True)
        self._list.set_rows(json_list(record.get("events_json")))

    def collect(self) -> dict:
        import json
        return {"events_json": json.dumps(self._list.rows(), ensure_ascii=False)}
