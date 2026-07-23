"""EditableRowList — a listinha editável repetida por várias seções.

Custos de Construção, Requisitos, Recompensas, Encontros, Chefes e Destaque
Visual têm todos a mesma forma: N linhas de poucos campos, um "+" para
acrescentar e um "✕" por linha para remover. Em vez de seis variações quase
iguais, cada seção declara suas colunas e reaproveita este widget; o valor
sai/entra como lista de dicts, que é exatamente como as colunas JSON do
banco guardam.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QSpinBox, QToolButton, QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import _no_wheel

# Tipos de coluna aceitos em `columns`.
TEXT = "text"
INT = "int"
COMBO = "combo"
CHECK = "check"

# (key, placeholder, kind, extra, stretch) — `extra` são as opções no COMBO
# e o par (mín, máx) no INT.
Column = tuple


class EditableRowList(QWidget):
    """Linhas de campos + botão de adicionar. Emite `changed` a cada edição."""

    changed = Signal()

    def __init__(self, columns: list[Column], add_label: str = "+ Adicionar", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._columns = columns
        self._rows: list[dict] = []   # {"widgets": {key: w}, "container": QWidget}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._rows_box = QVBoxLayout()
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(4)
        outer.addLayout(self._rows_box)

        self._empty = QLabel("Nada por aqui ainda.")
        self._empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        self._rows_box.addWidget(self._empty)

        add = QToolButton()
        add.setText(add_label)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.ACCENT}; border: none;
                font-size: 9px; font-weight: bold; padding: 2px 0; }}
            QToolButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        add.clicked.connect(self._on_add_clicked)
        add_row = QHBoxLayout()
        add_row.addWidget(add)
        add_row.addStretch()
        outer.addLayout(add_row)

    # ── API pública ──

    def set_rows(self, values: list[dict]):
        while self._rows:
            self._remove_row(self._rows[-1], notify=False)
        for value in values:
            self._add_row(value, notify=False)
        self._empty.setVisible(not self._rows)

    def rows(self) -> list[dict]:
        out = []
        for row in self._rows:
            record = {}
            for key, widget in row["widgets"].items():
                if isinstance(widget, QSpinBox):
                    record[key] = widget.value()
                elif isinstance(widget, QCheckBox):
                    record[key] = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    record[key] = widget.currentText()
                else:
                    record[key] = widget.text()
            out.append(record)
        return out

    # ── interno ──

    def _on_add_clicked(self):
        self._add_row({}, notify=True)
        self._empty.setVisible(not self._rows)

    def _build_field(self, column: Column, value):
        key, placeholder, kind = column[0], column[1], column[2]
        extra = column[3] if len(column) > 3 else None
        if kind == INT:
            widget = QSpinBox()
            minimum, maximum = extra or (0, 999999)
            widget.setRange(minimum, maximum)
            widget.setValue(int(value or 0))
            widget.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            widget.setFixedHeight(22)
            _no_wheel(widget)
            widget.valueChanged.connect(self.changed.emit)
        elif kind == COMBO:
            widget = QComboBox()
            widget.addItems(list(extra or []))
            widget.setEditable(True)
            widget.setFixedHeight(22)
            _no_wheel(widget)
            if value:
                widget.setCurrentText(str(value))
            widget.currentTextChanged.connect(self.changed.emit)
        elif kind == CHECK:
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.setToolTip(placeholder)
            widget.toggled.connect(self.changed.emit)
        else:
            widget = QLineEdit(str(value or ""))
            widget.setPlaceholderText(placeholder)
            widget.setFixedHeight(22)
            widget.textChanged.connect(self.changed.emit)
        return key, widget

    def _add_row(self, value: dict, notify: bool):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        line = QHBoxLayout(container)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(5)

        widgets: dict[str, QWidget] = {}
        for column in self._columns:
            key, widget = self._build_field(column, value.get(column[0]))
            stretch = column[4] if len(column) > 4 else 1
            line.addWidget(widget, stretch)
            widgets[key] = widget

        remove = QToolButton()
        remove.setText("✕")
        remove.setFixedSize(20, 20)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        row = {"widgets": widgets, "container": container}
        remove.clicked.connect(lambda: self._remove_row(row, notify=True))
        line.addWidget(remove)

        # O container só entra em cena depois de estar no layout — mostrar
        # antes de ter pai pisca uma janela nativa no Windows.
        self._rows_box.addWidget(container)
        self._rows.append(row)
        if notify:
            self.changed.emit()

    def _remove_row(self, row: dict, notify: bool):
        if row not in self._rows:
            return
        self._rows.remove(row)
        row["container"].setParent(None)
        row["container"].deleteLater()
        self._empty.setVisible(not self._rows)
        if notify:
            self.changed.emit()
