"""JsonBulkEditor — o botão "{ } JSON" + o editor inline que ele abre.

Diferente do bloco de Itens/Habilidades (onde botão e editor moram dentro
da mesma coluna estreita), aqui o botão fica no cabeçalho de cada metade
("GERENCIAMENTO DA BASE"/"GERENCIAMENTO DE DUNGEONS") e o editor inline
abre logo abaixo, ocupando a largura toda da metade — por isso os dois
widgets (`button`/`panel`) são expostos separados, para o dono decidir
onde cada um entra no layout, em vez de um QWidget único que já embute os
dois numa coluna fixa.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QTextEdit
from PySide6.QtCore import QObject, Qt, Signal

from src.styles.tokens import Colors


class JsonBulkEditor(QObject):
    """Não é um widget em si — só a lógica que liga `button` a `panel`."""

    apply_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._template = ""

        self.button = QToolButton()
        self.button.setText("{ } JSON")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip("Criar vários registros de uma vez em JSON")
        self.button.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); border: 1px solid {Colors.BORDER_SUBTLE};
                padding: 4px 10px; color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold; border-radius: 6px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        self.button.clicked.connect(self._toggle)

        self.panel = QFrame()
        self.panel.setStyleSheet(
            f"QFrame {{ background: rgba(0,0,0,0.15); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        jl = QVBoxLayout(self.panel)
        jl.setContentsMargins(8, 6, 8, 6)
        jl.setSpacing(5)
        hint = QLabel("Cole uma lista JSON para criar vários registros de uma vez — "
                       "categorias/tipos citados que ainda não existem são criados automaticamente.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        jl.addWidget(hint)
        self._edit = QTextEdit()
        self._edit.setFixedHeight(110)
        self._edit.setStyleSheet(
            f"QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; font-family: Consolas, monospace; "
            f"background: rgba(0,0,0,0.25); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 4px; }}"
        )
        jl.addWidget(self._edit)
        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {Colors.ERROR}; font-size: 8pt; background: transparent; border: none;")
        self._error.hide()
        jl.addWidget(self._error)
        jbtns = QHBoxLayout()
        jbtns.addStretch()
        cancel = QToolButton()
        cancel.setText("Cancelar")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 10px; font-size: 8pt; "
            f"color: {Colors.TEXT_MUTED}; background: transparent; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.08); }}"
        )
        cancel.clicked.connect(self._toggle)
        jbtns.addWidget(cancel)
        apply_btn = QToolButton()
        apply_btn.setText("Aplicar")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: 4px; padding: 3px 12px; font-size: 8pt; font-weight: bold; "
            f"color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        apply_btn.clicked.connect(lambda: self.apply_requested.emit(self._edit.toPlainText()))
        jbtns.addWidget(apply_btn)
        jl.addLayout(jbtns)
        self.panel.hide()

    def set_template(self, text: str):
        """Placeholder/exemplo mostrado na primeira vez que o editor abre."""
        self._template = text

    def _toggle(self):
        showing = not self.panel.isVisible()
        if showing and not self._edit.toPlainText().strip():
            self._edit.setPlainText(self._template)
        self._error.hide()
        self.panel.setVisible(showing)

    def show_error(self, message: str):
        self._error.setText(message)
        self._error.setVisible(bool(message))

    def close(self):
        self._edit.clear()
        self._error.hide()
        self.panel.hide()
