"""Logs — handler em memória + dialog para visualizar (estilo MAKEVID)."""

import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QObject


class _LogSignal(QObject):
    log_received = Signal(str)


class QtLogHandler(logging.Handler):
    """Handler que armazena logs em memória para exibição no dialog."""

    def __init__(self, max_lines: int = 500):
        super().__init__()
        self._signal = _LogSignal()
        self._lines: list[str] = []
        self._max = max_lines
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        self.setFormatter(fmt)

    @property
    def log_received(self):
        return self._signal.log_received

    def emit(self, record):
        msg = self.format(record)
        self._lines.append(msg)
        if len(self._lines) > self._max:
            self._lines = self._lines[-self._max:]
        self._signal.log_received.emit(msg)

    def get_content(self) -> str:
        return "\n".join(self._lines)

    def clear(self):
        self._lines.clear()


def open_logs_dialog(parent, handler: QtLogHandler):
    """Abre dialog com os logs acumulados."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Logs")
    dlg.resize(800, 500)

    layout = QVBoxLayout(dlg)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setStyleSheet("background: #0d0f1a; color: #66BB6A; font-family: Consolas; font-size: 9pt;")
    txt.setPlainText(handler.get_content())
    layout.addWidget(txt)

    def _on_new(msg):
        txt.append(msg)
    handler.log_received.connect(_on_new)

    btns = QHBoxLayout()
    btn_clear = QPushButton("Limpar")
    btn_clear.setStyleSheet("background: #EF5350; color: #fff; border: none; border-radius: 4px; padding: 6px 16px; font-weight: bold;")
    btn_clear.clicked.connect(lambda: (handler.clear(), txt.clear()))
    btn_close = QPushButton("Fechar")
    btn_close.clicked.connect(dlg.close)
    btns.addWidget(btn_clear)
    btns.addStretch()
    btns.addWidget(btn_close)
    layout.addLayout(btns)

    dlg.exec()
    handler.log_received.disconnect(_on_new)
