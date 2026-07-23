"""Projects Panel — CRUD de projetos estilo MAKEVID."""

import logging
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QFrame, QSizePolicy, QToolButton, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from src.styles.tokens import Colors, Typography
from src.services.project import Project
from src.services.recents import load_recents, add_recent, PROJECTS_DIR
from src.services.project_assets import import_asset, resolve_asset_path


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


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


class _CoverThumb(QToolButton):
    """Capa quadrada do projeto, ocupando a coluna esquerda do card.

    Clicar abre o explorador de arquivos; uma imagem arrastada do
    Explorer/Finder pode ser solta direto sobre ela (mesma ideia do
    _DropImageButton dos Mobs). Emite `picked` com o caminho local — quem
    é dono do card decide onde copiar o arquivo.

    O lado é ditado de fora (o card mede a própria altura e chama
    set_side); a imagem é reescalada e cortada no centro a cada mudança,
    para preencher o quadrado sem distorcer.
    """

    picked = Signal(str)
    MIN_SIDE = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path = ""
        self.setFixedSize(self.MIN_SIDE, self.MIN_SIDE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setToolTip("Clique para escolher uma imagem — ou arraste uma até aqui")
        self._paint_style()
        self.clicked.connect(self._browse)

    def _paint_style(self, drop: bool = False):
        border = Colors.ACCENT if drop else Colors.BORDER_SUBTLE
        bg = "rgba(79,195,247,0.15)" if drop else "rgba(255,255,255,0.05)"
        self.setStyleSheet(
            f"QToolButton {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 8px; font-size: 22px; color: {Colors.TEXT_MUTED}; }}"
            f"QToolButton:hover {{ border-color: {Colors.ACCENT}; }}"
        )

    def set_side(self, side: int):
        side = max(self.MIN_SIDE, side)
        if side == self.width():
            return
        self.setFixedSize(side, side)
        self._render()

    def set_image(self, path: str):
        self._image_path = path or ""
        self._render()

    def _render(self):
        pixmap = QPixmap(self._image_path) if self._image_path else QPixmap()
        if pixmap.isNull():
            self.setIcon(QPixmap())
            self.setText("🖼")
            return
        # Preenche o quadrado inteiro (menos a borda) cortando o excedente
        # no centro — KeepAspectRatio sozinho deixaria faixas vazias em
        # imagens que não são quadradas.
        side = max(1, min(self.width(), self.height()) - 4)
        scaled = pixmap.scaled(
            side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        x = max(0, (scaled.width() - side) // 2)
        y = max(0, (scaled.height() - side) // 2)
        self.setIcon(scaled.copy(x, y, side, side))
        self.setIconSize(QSize(side, side))
        self.setText("")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem do projeto", "",
            "Imagens (" + " ".join(f"*{e}" for e in IMAGE_EXTS) + ")",
        )
        if path:
            self.set_image(path)
            self.picked.emit(path)

    # ── drag & drop ──

    def _accepted_path(self, mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            local = url.toLocalFile()
            if local and local.lower().endswith(IMAGE_EXTS):
                return local
        return None

    def dragEnterEvent(self, event):
        if self._accepted_path(event.mimeData()):
            self._paint_style(drop=True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._paint_style(drop=False)

    def dropEvent(self, event):
        path = self._accepted_path(event.mimeData())
        self._paint_style(drop=False)
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        self.set_image(path)
        self.picked.emit(path)


class _ProjectCard(QWidget):
    """Card de projeto individual."""

    open_requested = Signal(str)      # path
    delete_requested = Signal(str)    # path
    renamed = Signal(str, str)        # path, new_name

    def __init__(self, name: str, path: str, is_active: bool, editing: bool = False, parent=None):
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
        self._build(editing)

    def _build(self, editing: bool = False):
        # A capa ocupa uma coluna à esquerda do tamanho do card inteiro (não
        # só da linha do nome) — resizeEvent mantém o lado do quadrado igual
        # à altura real do card a cada mudança de conteúdo.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)

        self._cover = _CoverThumb()
        self._cover.set_image(self._cover_path())
        self._cover.picked.connect(self._on_cover_picked)
        outer.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignTop)

        right = QWidget()
        right.setStyleSheet("background: transparent;")
        L = QVBoxLayout(right)
        L.setContentsMargins(0, 0, 0, 0)
        L.setSpacing(4)
        outer.addWidget(right, 1)

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

        if editing:
            self._name_lbl.hide()
            self._name_edit.show()
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            self._btn_rename.setText("Salvar")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A altura do card varia com o conteúdo (confirmação de delete
        # aberta, edição de nome, etc.) — o quadrado da capa acompanha para
        # continuar do tamanho do card, como pedido.
        margins = self.layout().contentsMargins()
        self._cover.set_side(self.height() - margins.top() - margins.bottom())

    # ── Capa ──

    def _cover_path(self) -> str:
        """Caminho absoluto da capa gravada no project.json, ou "" se o
        projeto não tem capa (ou não pôde ser lido)."""
        try:
            proj = Project.open(Path(self._path))
        except Exception:
            return ""
        if not proj.meta.cover:
            return ""
        absolute = resolve_asset_path(self._path, proj.meta.cover)
        return absolute if absolute and Path(absolute).exists() else ""

    def _on_cover_picked(self, source: str):
        """Copia a imagem escolhida para dentro do projeto e grava o
        caminho relativo no meta — assim a capa acompanha a pasta do
        projeto se ela for movida, e não quebra se o arquivo original
        sumir."""
        try:
            proj = Project.open(Path(self._path))
            relative = import_asset(self._path, source, "thumbnails", "cover")
            proj.meta.cover = relative
            proj.save()
            self._cover.set_image(resolve_asset_path(self._path, relative))
        except Exception as e:
            logging.getLogger("MAKEMAP").warning("Cover error: %s", e)

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
    project_opened = Signal(object)   # Project — opening an existing project
    project_created = Signal(object)  # Project — creating a new one (panel stays open to rename)
    new_requested = Signal()
    delete_requested = Signal(str)    # path

    def __init__(self, active_path: str = "", parent=None):
        super().__init__(parent)
        self._active_path = active_path
        self._new_card_path: str | None = None
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
        btn_new.clicked.connect(self._new_project)
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
                editing=(entry.path == self._new_card_path),
                parent=self._content,
            )
            card.open_requested.connect(self._on_open)
            card.delete_requested.connect(self._on_delete)
            card.renamed.connect(self._on_renamed)
            L.addWidget(card)

        self._new_card_path = None
        L.addStretch()
        self._content.show()

    def _new_project(self):
        name = f"Projeto_{int(time.time())}"
        try:
            proj = Project.create(PROJECTS_DIR, name)
        except Exception as e:
            logging.getLogger("MAKEMAP").warning("New project error: %s", e)
            return
        add_recent(name, str(proj.path))
        self._new_card_path = str(proj.path)
        self._active_path = str(proj.path)
        self.refresh()
        self.project_created.emit(proj)

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
