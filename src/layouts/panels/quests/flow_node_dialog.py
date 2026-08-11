"""FlowNodeDialog — popover simples pra editar um FlowNode (tipo/título/
subtítulo) ao dar duplo-clique nele. Um QDialog custom em vez de
QInputDialog nativo, pra não quebrar o visual "glass" que o resto do app usa.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors, combo_qss
from src.layouts.panels.quests.flow_node import NODE_TYPES, NODE_TYPE_ORDER
from src.layouts.panels.quests.constants import _no_wheel


class FlowNodeDialog(QDialog):
    def __init__(self, node_type: str, title: str, subtitle: str,
                 ref_type: str = "", ref_id: str = "",
                 npcs: list[dict] | None = None, mobs: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar nó do fluxo")
        self.setModal(True)
        self.setFixedWidth(340)
        self.setStyleSheet(f"""
            QDialog {{ background: {Colors.BG_ELEVATED}; }}
            QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 5px; padding: 5px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
            {combo_qss(padding="5px 8px")}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        outer.addWidget(QLabel("Tipo"))
        self._type = QComboBox()
        _no_wheel(self._type)
        for key in NODE_TYPE_ORDER:
            meta = NODE_TYPES[key]
            self._type.addItem(f"{meta['icon']} {meta['label']}", key)
        idx = self._type.findData(node_type)
        self._type.setCurrentIndex(idx if idx >= 0 else 0)
        outer.addWidget(self._type)

        outer.addWidget(QLabel("Título"))
        self._title = QLineEdit(title)
        outer.addWidget(self._title)

        outer.addWidget(QLabel("Subtítulo (opcional)"))
        self._subtitle = QLineEdit(subtitle)
        outer.addWidget(self._subtitle)

        outer.addWidget(QLabel("Vincular a (opcional — mostra o botão 📍 Ver no mapa)"))
        self._ref = QComboBox()
        _no_wheel(self._ref)
        self._ref.addItem("— Nenhum —", ("", ""))
        for npc in (npcs or []):
            self._ref.addItem(f"NPC: {npc.get('name') or '—'}", ("npc", npc.get("id", "")))
        for mob in (mobs or []):
            self._ref.addItem(f"Mob: {mob.get('name') or '—'}", ("mob", mob.get("id", "")))
        idx = self._ref.findData((ref_type, ref_id)) if ref_id else 0
        self._ref.setCurrentIndex(idx if idx >= 0 else 0)
        outer.addWidget(self._ref)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 6px 14px; font-size: 10px; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Salvar")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        outer.addLayout(btn_row)

    def values(self) -> tuple[str, str, str, str, str]:
        ref_type, ref_id = self._ref.currentData()
        return self._type.currentData(), self._title.text().strip(), self._subtitle.text().strip(), ref_type, ref_id
