"""MAKEMAP Application — core class with project management, autosave, logging."""

import sys
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog, QMenuBar, QMenu,
    QVBoxLayout,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from src.styles.stylesheet import build_stylesheet
from src.layouts.main_layout import MainLayout
from src.components.glass_widgets import AmbientBackground
from src.services.project import Project, ProjectMeta
from src.services.autosave import AutosaveService
from src.services import recents
from src.database.unit_of_work import UnitOfWork
from src.engines.assets.engine import AssetEngine

VERSION = "0.1.0"
APP_NAME = "MAKEMAP"

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)

    log_file = LOG_DIR / f"makemap_{datetime.now():%Y%m%d_%H%M%S}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)

        self.project: Project | None = None
        self.uow: UnitOfWork | None = None
        self.asset_engine: AssetEngine | None = None
        self.autosave = AutosaveService(self)
        self.autosave.state_changed.connect(self._on_save_state)

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

        self._build_menu()

    def _build_menu(self):
        menu_bar = self.menuBar()

        # --- File menu ---
        file_menu: QMenu = menu_bar.addMenu("&Arquivo")

        new_action = QAction("&Novo Projeto", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Abrir Projeto", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        # Recents submenu
        self.recents_menu = file_menu.addMenu("Projetos &Recentes")
        self._refresh_recents_menu()

        file_menu.addSeparator()

        save_action = QAction("&Salvar", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Salvar &Como...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        delete_action = QAction("&Deletar Projeto", self)
        delete_action.triggered.connect(self.delete_project)
        file_menu.addAction(delete_action)

        file_menu.addSeparator()

        exit_action = QAction("&Sair", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    # --- Project actions ---

    def new_project(self):
        if not self._confirm_discard():
            return

        directory = QFileDialog.getExistingDirectory(self, "Escolha o diretório do projeto")
        if not directory:
            return

        name, ok = self._ask_name()
        if not ok or not name:
            return

        try:
            self.project = Project.create(Path(directory), name)
            self._on_project_loaded()
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
        self.asset_engine = None
        self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
        self.layout_widget.top_bar.set_project_name("Sem Projeto")
        self.layout_widget.status_bar.save_label.setText("")

    # --- Helpers ---

    def _do_open(self, path: Path):
        try:
            # Check recovery
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
        # Close previous DB if any
        if self.uow:
            self.uow.close()

        # Initialize database
        self.uow = UnitOfWork(self.project.db_path)

        # Initialize Asset Engine
        self.asset_engine = AssetEngine(self.project.path, self.uow)

        self.setWindowTitle(f"{APP_NAME} — {self.project.meta.name}")
        self.layout_widget.top_bar.set_project_name(self.project.meta.name)
        self.layout_widget.status_bar.save_label.setText("Salvo")
        self.layout_widget.engines.update_stats()
        self.autosave.start(self.project)
        recents.add_recent(self.project.meta.name, str(self.project.path))
        self._refresh_recents_menu()

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

    def _refresh_recents_menu(self):
        self.recents_menu.clear()
        for entry in recents.load_recents():
            action = QAction(f"{entry.name}  —  {entry.path}", self)
            path = Path(entry.path)
            action.triggered.connect(lambda checked, p=path: self._do_open(p))
            self.recents_menu.addAction(action)

    def closeEvent(self, event):
        if not self._confirm_discard():
            event.ignore()
            return
        self.autosave.stop()
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

    def run(self) -> int:
        self.window.show()
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
