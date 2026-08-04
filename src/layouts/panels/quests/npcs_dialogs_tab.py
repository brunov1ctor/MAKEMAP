"""NpcsDialogsTab — aba de conteúdo "NPCs e Diálogos": quem entrega a quest
("giver") e quem a recebe de volta ("turn_in"), gravados na tabela
`quest_npcs` (já existia no banco, sem repositório até agora — ver
QuestNPCRepository), mais um texto livre de diálogo (`dialogue`, migration
36). Um NPC por papel é o suficiente pra maioria dos casos de uso; não há
árvore de diálogo por enquanto, só o texto que o NPC fala ao entregar/
receber a missão.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTextEdit, QSizePolicy,
)
from PySide6.QtCore import Signal

from src.styles.tokens import Colors
from src.layouts.panels.quests.constants import (
    _no_wheel, _section_label, panel_frame_style, sub_header, hrule, _INPUT_STYLE,
)


class NpcsDialogsTab(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style() + _INPUT_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._loading = False
        self._npcs: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header("NPCs e Diálogos"))

        self._giver = QComboBox()
        _no_wheel(self._giver)
        self._turn_in = QComboBox()
        _no_wheel(self._turn_in)
        outer.addLayout(self._field("NPC que entrega a quest", self._giver))
        outer.addLayout(self._field("NPC que recebe de volta", self._turn_in))

        outer.addWidget(hrule())
        outer.addWidget(_section_label("Diálogo"))
        self._dialogue = QTextEdit()
        self._dialogue.setPlaceholderText("O que o NPC diz ao entregar/receber a missão...")
        outer.addWidget(self._dialogue, 1)

        self._giver.currentIndexChanged.connect(self._on_field_changed)
        self._turn_in.currentIndexChanged.connect(self._on_field_changed)
        self._dialogue.textChanged.connect(self._on_field_changed)

    @staticmethod
    def _field(label_text: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        lbl.setFixedWidth(150)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    def _on_field_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    # ── API pública ──

    def set_npcs(self, npcs: list[dict]):
        self._npcs = npcs
        for combo in (self._giver, self._turn_in):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— Nenhum —", "")
            for npc in npcs:
                combo.addItem(npc.get("name") or "—", npc.get("id"))
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def set_empty(self):
        self._loading = True
        try:
            self._giver.setCurrentIndex(0)
            self._turn_in.setCurrentIndex(0)
            self._dialogue.clear()
        finally:
            self._loading = False
        self.setEnabled(False)

    def load(self, record: dict, giver_id: str = "", turn_in_id: str = ""):
        self.setEnabled(True)
        self._loading = True
        try:
            idx = self._giver.findData(giver_id)
            self._giver.setCurrentIndex(idx if idx >= 0 else 0)
            idx = self._turn_in.findData(turn_in_id)
            self._turn_in.setCurrentIndex(idx if idx >= 0 else 0)
            self._dialogue.setPlainText(record.get("dialogue") or "")
        finally:
            self._loading = False

    def collect(self) -> dict:
        return {
            "_giver_id": self._giver.currentData() or "",
            "_turn_in_id": self._turn_in.currentData() or "",
            "dialogue": self._dialogue.toPlainText(),
        }
