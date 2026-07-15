"""MAKEMAP Application — core class with project management, autosave, logging."""

import sys
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog,
    QVBoxLayout,
)
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt

from src.styles.stylesheet import build_stylesheet
from src.layouts.main_layout import MainLayout
from src.components.glass_widgets import AmbientBackground
from src.services.project import Project, ProjectMeta
from src.services.autosave import AutosaveService
from src.services.recents import add_recent, PROJECTS_DIR
from src.database.unit_of_work import UnitOfWork
from src.engines.assets.engine import AssetEngine
from src.layouts.panels.projects_panel import ProjectsPanel

VERSION = "0.1.0"
APP_NAME = "MAKEMAP"


def setup_logging() -> logging.Logger:
    """Configura logging global — apenas para o painel Qt (sem arquivo)."""
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    return logger


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)

        self.project: Project | None = None
        self.uow: UnitOfWork | None = None
        self.autosave = AutosaveService(self)
        self.autosave.state_changed.connect(self._on_save_state)

        # Global asset engine (works without project)
        self.asset_engine = AssetEngine(parent=self)

        # AmbientBackground como central widget, MainLayout como filho
        self._bg = AmbientBackground()
        self.setCentralWidget(self._bg)

        # Layout dentro do background
        bg_layout = QVBoxLayout(self._bg)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(0)

        self.layout_widget = MainLayout()
        self.layout_widget.setAttribute(Qt.WA_TranslucentBackground)
        bg_layout.addWidget(self.layout_widget)

        # Inject asset engine into canvas immediately
        self.layout_widget.canvas.engine.set_asset_engine(self.asset_engine)

        # Projects panel (overlay)
        self._projects_panel = ProjectsPanel(parent=self._bg)
        self._projects_panel.hide()
        self._projects_panel.closed.connect(self._hide_projects)
        self._projects_panel.project_opened.connect(self._on_panel_project_opened)
        self._projects_panel.new_requested.connect(self.new_project)
        self._projects_panel.delete_requested.connect(self._on_panel_delete)

        # Conectar botão Arquivo da topbar
        self.layout_widget.top_bar.arquivo_clicked.connect(self._toggle_projects)

        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Atalhos de teclado sem menu bar nativo."""
        from PySide6.QtGui import QShortcut
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_project)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_project)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.save_project)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(self.save_project_as)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

    # --- Project actions ---

    def new_project(self):
        """Cria projeto direto no PROJECTS_DIR (sem abrir explorer)."""
        import time
        name = f"Projeto_{int(time.time())}"
        try:
            self.project = Project.create(PROJECTS_DIR, name)
            self._on_project_loaded()
            if self._projects_panel.isVisible():
                self._projects_panel.set_active(str(self.project.path))
                self._projects_panel.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível criar o projeto:\n{e}")

    def open_project(self):
        if not self._confirm_discard():
            return

        directory = QFileDialog.getExistingDirectory(
            self, "Selecione a pasta do projeto (.makemap)"
        )
        if not directory:
            return

        self._do_open(Path(directory))

    def save_project(self):
        if not self.project:
            return
        try:
            self.project.save()
            self.layout_widget.status_bar.save_label.setText("Salvo")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Salvar", str(e))

    def save_project_as(self):
        if not self.project:
            return

        directory = QFileDialog.getExistingDirectory(self, "Salvar Como — escolha o diretório")
        if not directory:
            return

        name, ok = self._ask_name(self.project.meta.name)
        if not ok or not name:
            return

        try:
            import shutil
            new_path = Path(directory) / f"{name}{Project.EXTENSION}"
            shutil.copytree(self.project.path, new_path)
            self.project = Project.open(new_path)
            self.project.meta.name = name
            self.project.save()
            self._on_project_loaded()
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _toggle_projects(self):
        if self._projects_panel.isVisible():
            self._hide_projects()
        else:
            self._show_projects()

    def _show_projects(self):
        p = self._projects_panel
        p.set_active(str(self.project.path) if self.project else "")
        pw = 420
        ph = min(550, self.height() - 100)
        p.setFixedSize(pw, ph)
        p.move(20, 76)
        p.raise_()
        p.show()

    def _hide_projects(self):
        self._projects_panel.hide()

    def _on_panel_project_opened(self, proj: Project):
        self._hide_projects()
        self.project = proj
        self._on_project_loaded()

    def _on_panel_delete(self, path: str):
        from pathlib import Path as P
        target = P(path)
        if self.project and str(self.project.path) == path:
            self.autosave.stop()
            if self.uow:
                self.uow.close()
                self.uow = None
        if target.exists():
            import shutil
            shutil.rmtree(target)
        self.project = None
        self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
        self.layout_widget.top_bar.set_project_name("")
        self._projects_panel.set_active("")
        self._projects_panel.refresh()

    def delete_project(self):
        if not self.project:
            return
        reply = QMessageBox.warning(
            self, "Deletar Projeto",
            f"Tem certeza que deseja deletar '{self.project.meta.name}'?\n\n"
            "Esta ação é irreversível. Todos os dados serão perdidos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.autosave.stop()
        if self.uow:
            self.uow.close()
            self.uow = None
        self.project.delete()
        self.project = None
        self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
        self.layout_widget.top_bar.set_project_name("")
        self.layout_widget.status_bar.save_label.setText("")

    # --- Helpers ---

    def _do_open(self, path: Path):
        try:
            if AutosaveService.has_recovery(path):
                reply = QMessageBox.question(
                    self, "Recuperação",
                    "Foi encontrado um autosave. Deseja recuperar a sessão anterior?",
                )
                if reply == QMessageBox.StandardButton.Yes:
                    data = AutosaveService.recover_latest(path)
                    if data:
                        meta = ProjectMeta.from_dict(data)
                        self.project = Project(path, meta)
                        self._on_project_loaded()
                        return

            self.project = Project.open(path)
            self._on_project_loaded()
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Abrir", str(e))

    def _on_project_loaded(self):
        # Close previous DB
        if self.uow:
            self.uow.close()

        # Initialize project database
        self.uow = UnitOfWork(self.project.db_path)

        # Connect project DB to asset engine
        self.asset_engine.set_uow(self.uow)
        self.asset_engine._project_path = self.project.path

        self.setWindowTitle(f"{APP_NAME} \u2014 {self.project.meta.name}")
        self.layout_widget.top_bar.set_project_name(self.project.meta.name)
        self.layout_widget.status_bar.save_label.setText("Salvo")
        self.layout_widget.engines.update_stats()
        self.autosave.start(self.project)
        add_recent(self.project.meta.name, str(self.project.path))

    def _on_save_state(self, state: str):
        self.layout_widget.status_bar.save_label.setText(state)

    def _confirm_discard(self) -> bool:
        if self.project and self.project.dirty:
            reply = QMessageBox.question(
                self, "Alterações não salvas",
                "Existem alterações não salvas. Deseja descartar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    def _ask_name(self, default: str = "Novo Projeto") -> tuple[str, bool]:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nome do Projeto", "Nome:", text=default)
        return name.strip(), ok

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
            return
        self.autosave.stop()
        self.asset_engine.library.stop()
        if self.uow:
            self.uow.close()
        event.accept()


class Application:
    """Entry point — initializes Qt, logging, and global error handler."""

    def __init__(self):
        self.logger = setup_logging()
        self.logger.info("Iniciando %s v%s", APP_NAME, VERSION)

        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationVersion(VERSION)
        self.app.setStyleSheet(build_stylesheet())

        sys.excepthook = self._handle_exception

        self.window = MainWindow()

        # Conectar logs ao handler
        self.logger.addHandler(self.window.layout_widget.log_handler)

    def run(self) -> int:
        self.window.showMaximized()
        self.logger.info("Janela principal exibida")
        return self.app.exec()

    def _handle_exception(self, exc_type, exc_value, exc_tb):
        self.logger.critical(
            "Exceção não tratada", exc_info=(exc_type, exc_value, exc_tb)
        )
        QMessageBox.critical(
            self.window,
            "Erro Fatal",
            f"Ocorreu um erro inesperado:\n{exc_value}\n\nVerifique os logs para detalhes.",
        )
