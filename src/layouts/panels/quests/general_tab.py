"""GeneralTab — conteúdo da aba "Geral" do editor de Quest: a cadeia de
missões que essa quest pertence e sua posição nela. Os demais campos
"gerais" (nome, tipo, região, nível, descrição, recompensas...) já vivem no
painel de propriedades sempre visível à direita (ver properties_panel.py) —
essa aba cobre só o que é específico da progressão em cadeia, que usa as
colunas chain_id/chain_order já existentes em quests.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.quests.constants import (
    _spin, _no_wheel, _section_label, panel_frame_style, sub_header, hrule,
)


class GeneralTab(QFrame):
    changed = Signal()
    chain_create_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("subpanel")
        self.setStyleSheet(panel_frame_style())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._loading = False
        self._chains: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        outer.addWidget(sub_header("Cadeia da Missão"))

        hint = QLabel(
            "Agrupe esta quest com outras numa sequência — a ordem decide "
            "em que posição ela aparece dentro da cadeia."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        outer.addWidget(hint)

        row = QHBoxLayout()
        chain_lbl = QLabel("Cadeia")
        chain_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        self._chain = QComboBox()
        _no_wheel(self._chain)
        self._chain.setEditable(True)
        self._chain.lineEdit().setPlaceholderText("Nenhuma — digite para criar uma nova")
        row.addWidget(chain_lbl)
        row.addWidget(self._chain, 1)
        outer.addLayout(row)

        order_row = QHBoxLayout()
        order_lbl = QLabel("Ordem na cadeia")
        order_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        self._order = _spin(0, 999, 0)
        _no_wheel(self._order)
        order_row.addWidget(order_lbl, 1)
        order_row.addWidget(self._order)
        outer.addLayout(order_row)

        outer.addWidget(hrule())
        outer.addWidget(_section_label("Quests nesta cadeia"))
        self._chain_list = QVBoxLayout()
        self._chain_list.setSpacing(4)
        outer.addLayout(self._chain_list)
        self._empty_lbl = QLabel("Selecione uma cadeia para ver as quests nela.")
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        self._chain_list.addWidget(self._empty_lbl)

        outer.addStretch()

        self._chain.currentTextChanged.connect(self._on_field_changed)
        self._order.valueChanged.connect(self._on_field_changed)

    def _on_field_changed(self, *_args):
        if not self._loading:
            self.changed.emit()

    # ── API pública ──

    def set_chains(self, chains: list[dict]):
        self._chains = chains
        current = self._chain.currentText()
        self._chain.blockSignals(True)
        self._chain.clear()
        self._chain.addItem("")
        self._chain.addItems([c.get("name", "") for c in chains])
        if current:
            idx = self._chain.findText(current)
            self._chain.setCurrentIndex(idx if idx >= 0 else 0)
        self._chain.blockSignals(False)

    def set_chain_quests(self, quests: list[dict], current_id: str = ""):
        """`quests` já vem ordenado por chain_order."""
        while self._chain_list.count():
            item = self._chain_list.takeAt(0)
            widget = item.widget()
            if widget is self._empty_lbl:
                # Reaproveitado a cada troca — só desanexar, não destruir
                # (mesmo padrão de record_list.py._rebuild). Chamar
                # deleteLater() nele e tentar readicioná-lo numa chamada
                # seguinte (antes do Qt processar essa destruição adiada)
                # derrubava o painel com "Internal C++ object already
                # deleted" — _save_quest chama isto a cada save debounced.
                widget.setParent(None)
            elif widget is not None:
                widget.deleteLater()
        if not quests:
            self._chain_list.addWidget(self._empty_lbl)
            return
        for i, q in enumerate(quests, start=1):
            row = QLabel(f"{i}. {q.get('name', '—')}")
            bold = "bold" if q.get("id") == current_id else "normal"
            color = Colors.ACCENT if q.get("id") == current_id else Colors.TEXT_SECONDARY
            row.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: {bold}; background: transparent; border: none;")
            self._chain_list.addWidget(row)

    def load(self, record: dict, chain_name: str = ""):
        self._loading = True
        try:
            self._chain.setCurrentText(chain_name)
            self._order.setValue(int(record.get("chain_order") or 0))
        finally:
            self._loading = False

    def collect(self) -> dict:
        return {
            "_chain_name": self._chain.currentText().strip(),
            "chain_order": self._order.value(),
        }
