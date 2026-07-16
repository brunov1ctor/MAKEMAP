"""Projects Panel — CRUD de projetos estilo MAKEVID."""

import logging
import time
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors, Typography
from src.services.project import Project
from src.services.recents import load_recents, add_recent, PROJECTS_DIR


def _btn_style(color, bg="transparent", hover_bg=None):
    hover_bg = hover_bg or color
    return (
        f"QPushButton {{ background: {bg}; color: {color}; font-weight: bold; "
        f"font-size: 8pt; border: 1px solid {color}; border-radius: 6px; padding: 0 10px; }}"
        f"QPushButton:hover {{ background: {hover_bg}; color: #0B1929; }}"
    )


def _btn_primary():
    return (
        f"QPushButton {{ background: {Colors.ACCENT}; color: #0B1929; font-weight: bold; "
        f"font-size: 8pt; border: none; border-radius: 6px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}"
    )


class _ProjectCard(QWidget):
    """Card de projeto individual."""

    open_requested = Signal(str)      # path
    delete_requested = Signal(str)    # path
    renamed = Signal(str, str)        # path, new_name

    def __init__(self, name: str, path: str, is_active: bool, parent=None):
        super().__init__(parent)
        self._path = path
        self._name = name
        self._active = is_active
        self.setObjectName("projCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        border_color = "rgba(79,195,247,0.5)" if is_active else Colors.GLASS_BORDER
        self.setStyleSheet(
            f"QWidget#projCard {{ background: {Colors.GLASS_BG}; border: 1px solid {border_color}; border-radius: 10px; }}"
            f"QWidget#projCard:hover {{ background: {Colors.PANEL_HOVER}; border-color: {Colors.ACCENT}; }}"
            f"QWidget#projCard QLabel {{ background: transparent; border: none; }}"
        )
        self._build()

    def _build(self):
        L = QVBoxLayout(self)
        L.setContentsMargins(12, 10, 12, 10)
        L.setSpacing(4)

        # ── Nome ──
        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        self._name_lbl = QLabel(self._name)
        self._name_lbl.setStyleSheet(
            f"color: {Colors.ACCENT if self._active else Colors.TEXT_PRIMARY}; "
            f"font-size: 10pt; font-weight: bold;"
        )
        name_row.addWidget(self._name_lbl)

        if self._active:
            badge = QLabel("● ATIVO")
            badge.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 7pt; font-weight: bold;")
            name_row.addWidget(badge)

        name_row.addStretch()

        self._name_edit = QLineEdit(self._name)
        self._name_edit.setFixedHeight(24)
        self._name_edit.setStyleSheet(
            f"background: {Colors.BG_TERTIARY}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 2px 6px; font-size: 9pt;"
        )
        self._name_edit.returnPressed.connect(self._confirm_rename)
        self._name_edit.hide()
        name_row.addWidget(self._name_edit)
        L.addLayout(name_row)

        # ── Path ──
        path_lbl = QLabel(self._path)
        path_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt;")
        path_lbl.setWordWrap(True)
        L.addWidget(path_lbl)

        # ── Confirmação de delete ──
        self._confirm_widget = QWidget()
        self._confirm_widget.setStyleSheet("background: transparent;")
        cw_l = QHBoxLayout(self._confirm_widget)
        cw_l.setContentsMargins(0, 2, 0, 0)
        cw_l.setSpacing(6)
        warn = QLabel("Tudo será perdido. Confirmar?")
        warn.setStyleSheet(f"color: {Colors.ERROR}; font-size: 8pt; font-weight: bold;")
        cw_l.addWidget(warn)
        cw_l.addStretch()
        btn_yes = QPushButton("Sim, deletar")
        btn_yes.setFixedHeight(22)
        btn_yes.setStyleSheet(_btn_style("#0B1929", bg=Colors.ERROR, hover_bg="#ff6666"))
        btn_yes.clicked.connect(lambda: self.delete_requested.emit(self._path))
        cw_l.addWidget(btn_yes)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(22)
        btn_cancel.setStyleSheet(_btn_style(Colors.TEXT_MUTED))
        btn_cancel.clicked.connect(self._hide_confirm)
        cw_l.addWidget(btn_cancel)
        self._confirm_widget.hide()
        L.addWidget(self._confirm_widget)

        # ── Botões ──
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 4, 0, 0)
        btns.setSpacing(6)

        if not self._active:
            btn_open = QPushButton("Abrir")
            btn_open.setFixedHeight(26)
            btn_open.setStyleSheet(_btn_primary())
            btn_open.clicked.connect(lambda: self.open_requested.emit(self._path))
            btns.addWidget(btn_open)

        self._btn_rename = QPushButton("Renomear")
        self._btn_rename.setFixedHeight(26)
        self._btn_rename.setStyleSheet(_btn_style(Colors.WARNING))
        self._btn_rename.clicked.connect(self._toggle_rename)
        btns.addWidget(self._btn_rename)

        self._btn_del = QPushButton("Deletar")
        self._btn_del.setFixedHeight(26)
        self._btn_del.setStyleSheet(_btn_style(Colors.ERROR))
        self._btn_del.clicked.connect(self._on_delete_clicked)
        btns.addWidget(self._btn_del)

        btns.addStretch()
        L.addLayout(btns)

    def _on_delete_clicked(self):
        self._confirm_widget.show()
        self._btn_del.hide()

    def _hide_confirm(self):
        self._confirm_widget.hide()
        self._btn_del.show()

    def _toggle_rename(self):
        if self._name_edit.isHidden():
            self._name_edit.setText(self._name)
            self._name_lbl.hide()
            self._name_edit.show()
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            self._btn_rename.setText("Salvar")
        else:
            self._confirm_rename()

    def _confirm_rename(self):
        new_name = self._name_edit.text().strip() or self._name
        if new_name != self._name:
            try:
                proj = Project.open(Path(self._path))
                proj.meta.name = new_name
                proj.save()
                self._name = new_name
                self._name_lbl.setText(new_name)
                self.renamed.emit(self._path, new_name)
            except Exception as e:
                logging.getLogger("MAKEMAP").warning("Rename error: %s", e)
        self._name_edit.hide()
        self._name_lbl.show()
        self._btn_rename.setText("Renomear")


class ProjectsPanel(QWidget):
    """Painel CRUD de projetos — overlay glass, draggable."""

    closed = Signal()
    project_opened = Signal(object)   # Project
    new_requested = Signal()
    delete_requested = Signal(str)    # path

    def __init__(self, active_path: str = "", parent=None):
        super().__init__(parent)
        self._active_path = active_path
        self._drag_pos = None
        self.setMinimumWidth(350)
        self.setMaximumWidth(500)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(0)

        # ── Header ──
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 6, 0, 4)
        hdr.setSpacing(6)

        title = QLabel("PROJETOS")
        title.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        btn_new = QPushButton("+ Novo")
        btn_new.setFixedHeight(26)
        btn_new.setStyleSheet(_btn_primary())
        btn_new.clicked.connect(self.new_requested.emit)
        hdr.addWidget(btn_new)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: none; font-size: 14px; border-radius: 12px; }}"
            f"QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.closed.emit)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # ── Contagem ──
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;"
        )
        layout.addWidget(self._count_lbl)

        # ── Separador ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        layout.addWidget(sep)

        # ── Lista scroll ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._content)
        self._list_layout.setContentsMargins(0, 8, 0, 8)
        self._list_layout.setSpacing(6)
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.pos().y() < 50:
            self._drag_pos = event.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = self.mapToParent(event.pos() - self._drag_pos)
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def set_active(self, path: str):
        self._active_path = path

    def refresh(self):
        """Reconstrói a lista de projetos a partir dos recentes."""
        self._content.hide()
        L = self._list_layout

        while L.count():
            item = L.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        entries = load_recents()
        valid = [e for e in entries if Path(e.path).exists()]
        n = len(valid)
        self._count_lbl.setText(f"  {n} projeto{'s' if n != 1 else ''}")

        if not valid:
            empty = QLabel("Nenhum projeto. Clique em + Novo para começar.")
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
            L.addWidget(empty)
            L.addStretch()
            self._content.show()
            return

        for entry in valid:
            card = _ProjectCard(
                entry.name, entry.path,
                is_active=(entry.path == self._active_path),
                parent=self._content,
            )
            card.open_requested.connect(self._on_open)
            card.delete_requested.connect(self._on_delete)
            card.renamed.connect(self._on_renamed)
            L.addWidget(card)

        L.addStretch()
        self._content.show()

    def _on_open(self, path: str):
        try:
            proj = Project.open(Path(path))
            self._active_path = path
            self.project_opened.emit(proj)
            self.refresh()
        except Exception as e:
            logging.getLogger("MAKEMAP").warning("Open error: %s", e)

    def _on_delete(self, path: str):
        self.delete_requested.emit(path)

    def _on_renamed(self, path: str, new_name: str):
        add_recent(new_name, path)
        if path == self._active_path:
            try:
                proj = Project.open(Path(path))
                self.project_opened.emit(proj)
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(14, 22, 42, 230))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.drawPath(path)
        p.end()
