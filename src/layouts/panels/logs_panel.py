"""Painel de Logs — exibe logs em tempo real com botão de limpar."""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QPlainTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QObject

from src.styles.tokens import Colors, Typography
from src.components.collapsible_panel import CollapsiblePanel


class _LogSignal(QObject):
    """Bridge para emitir logs na thread principal."""
    log_received = Signal(str)


class QtLogHandler(logging.Handler):
    """Handler que redireciona logs para o painel Qt."""

    def __init__(self):
        super().__init__()
        self._signal = _LogSignal()
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        self.setFormatter(fmt)

    @property
    def log_received(self):
        return self._signal.log_received

    def emit(self, record):
        msg = self.format(record)
        self._signal.log_received.emit(msg)


class LogsPanel(CollapsiblePanel):
    """Painel de logs com visualização e botão de limpar."""

    def __init__(self, parent=None):
        super().__init__(title="Logs", icon="📋", parent=parent, radius=12)

        # Título maior
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)

        # Botão limpar no header
        self._clear_btn = QToolButton()
        self._clear_btn.setText("🗑")
        self._clear_btn.setToolTip("Limpar Logs")
        self._clear_btn.setFixedSize(18, 18)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 11px; color: {Colors.TEXT_MUTED}; background: transparent; border-radius: 4px; }}
            QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}
        """)
        self._clear_btn.clicked.connect(self.clear_logs)
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, self._clear_btn)

        # Counter
        self._count_label = QLabel("0")
        self._count_label.setStyleSheet(f"""
            font-size: 8px; color: {Colors.TEXT_MUTED};
            background: rgba(10,16,30,0.5); border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 8px; padding: 1px 5px;
        """)
        header_layout.insertWidget(header_layout.count() - 1, self._count_label)

        # Text area
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(500)
        self._text.setStyleSheet(f"""
            QPlainTextEdit {{
                background: rgba(4, 8, 20, 0.6);
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
                color: {Colors.TEXT_SECONDARY};
                font-family: "Consolas", "Courier New", monospace;
                font-size: 9px;
                padding: 6px;
            }}
            QPlainTextEdit QScrollBar:vertical {{
                width: 6px; background: transparent;
            }}
            QPlainTextEdit QScrollBar::handle:vertical {{
                background: {Colors.BORDER}; border-radius: 3px;
            }}
        """)
        self.content_layout.addWidget(self._text, 1)

        # Handler
        self._handler = QtLogHandler()
        self._handler.log_received.connect(self._append_log)
        self._log_count = 0

    @property
    def handler(self) -> QtLogHandler:
        return self._handler

    def _append_log(self, msg: str):
        self._text.appendPlainText(msg)
        self._log_count += 1
        self._count_label.setText(str(self._log_count))

    def clear_logs(self):
        self._text.clear()
        self._log_count = 0
        self._count_label.setText("0")

    def clear_log_files(self):
        """Remove arquivos .log antigos do disco."""
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / "logs"
        if log_dir.exists():
            for f in log_dir.glob("*.log"):
                try:
                    f.unlink()
                except OSError:
                    pass
