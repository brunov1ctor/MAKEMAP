"""MAKEMAP Application — core class with project management, autosave, logging."""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog,
    QVBoxLayout, QStyleFactory,
)
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, QRect

from src.styles.stylesheet import build_stylesheet
from src.layouts.main_layout import MainLayout
from src.components.glass_widgets import AmbientBackground
from src.services.project import Project, ProjectMeta
from src.services.autosave import AutosaveService
from src.services.recents import add_recent, PROJECTS_DIR
from src.database.unit_of_work import UnitOfWork
from src.engines.assets.engine import AssetEngine

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

        # Mark the project dirty (and flip the status label to "Alterações
        # pendentes") on every completed edit — same history_changed signal
        # every mediator's own DB-sync debounce already listens to. Without
        # this, AutosaveService.notify_change() was never called by
        # anything, so project.dirty stayed permanently False and
        # _do_autosave's guard silently skipped every timer tick — autosave
        # was wired up but never actually fired.
        self.layout_widget.canvas.engine.history.history_changed.connect(self.autosave.notify_change)

        self._setup_shortcuts()
        self._screen_watch_connected = False

    def showEvent(self, event):
        super().showEvent(event)
        # windowHandle() is only valid once the native window exists, which
        # happens on first show — connect here (once) instead of in
        # __init__, and immediately clamp in case we're already opening on
        # a monitor smaller than the 1280x720 floor set above.
        if not self._screen_watch_connected and self.windowHandle():
            self.windowHandle().screenChanged.connect(self._on_screen_changed)
            self._screen_watch_connected = True
            self._clamp_to_screen()

    def _on_screen_changed(self, screen):
        # Deferred: right after a drag-to-another-monitor, Qt hasn't
        # necessarily finished re-maximizing the window yet — measuring on
        # the next event-loop tick gets the settled geometry.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._clamp_to_screen)

    def _clamp_to_screen(self):
        """Keep the window fully on whatever screen it's currently on.

        setMinimumSize(1280, 720) below assumes a monitor at least that
        big; dragged to a smaller one, Windows still enforces that floor
        and leaves the excess (bottom/right — whatever panel happens to be
        open, e.g. Config) physically off-screen instead of shrinking to
        fit. Relaxing the floor to the smaller screen's own available size
        and re-clamping position/size mirrors what FloatingCoordinator
        already does for floating panels, just one level up — for the
        window itself against its monitor instead of a panel against the
        window.
        """
        screen = self.screen()
        if not screen:
            return
        avail = screen.availableGeometry()

        self.setMinimumSize(min(1280, avail.width()), min(720, avail.height()))

        if self.isMaximized():
            if self.geometry() != avail:
                self.setGeometry(avail)
            return

        geo = QRect(self.x(), self.y(), min(self.width(), avail.width()), min(self.height(), avail.height()))
        if geo.right() > avail.right():
            geo.moveRight(avail.right())
        if geo.bottom() > avail.bottom():
            geo.moveBottom(avail.bottom())
        if geo.left() < avail.left():
            geo.moveLeft(avail.left())
        if geo.top() < avail.top():
            geo.moveTop(avail.top())
        if geo != self.geometry():
            self.setGeometry(geo)

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

    def _on_panel_project_opened(self, proj: Project):
        self._load_project(proj)
        # Also close fullscreen menu if open
        self.layout_widget._menu_med._hide_menu_view()

    def _load_project(self, proj: Project):
        """Make `proj` the active project without touching any panel visibility."""
        self.project = proj
        self._on_project_loaded()

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
        self.uow = None
        try:
            self._wire_project_loaded()
        except Exception:
            # A failure partway through leaves some mediators wired to the
            # new (about-to-be-discarded) uow and others still pointing at
            # the old one — that mixed state can't be trusted, so fail
            # closed (no project open) instead of pretending either the old
            # or the new project is still consistently loaded. Re-raised so
            # every caller's existing except-Exception-and-show-dialog path
            # (open_project/save_project_as/_do_open) still surfaces this.
            if self.uow:
                self.uow.close()
            self.uow = None
            self.project = None
            self.setWindowTitle(f"{APP_NAME} — v{VERSION}")
            self.layout_widget.top_bar.set_project_name("")
            self.layout_widget.top_bar.set_modules_enabled(False)
            raise

    def _wire_project_loaded(self):
        # Initialize project database
        self.uow = UnitOfWork(self.project.db_path)

        # Connect project DB to terrains (map boundaries) first — Região and
        # Brush both resolve a terrain_id against TerrainMediator.boundaries
        # when reloading their own state, so boundaries must already be
        # repopulated by the time those run.
        self.layout_widget._terrain_med.set_uow(self.uow)

        # Connect project DB to painted regions (loads any saved zones)
        self.layout_widget._region_med.set_uow(self.uow)

        # Connect project DB to the Spawn panel (loads live mob categories)
        self.layout_widget._spawn_med.set_uow(self.uow)

        # Connect project DB to the Texto tool (loads any saved text objects)
        self.layout_widget._text_med.set_uow(self.uow)

        # Connect project DB to the Marcador tool (loads any saved markers)
        self.layout_widget._marker_med.set_uow(self.uow)

        # Connect project DB to the Iluminação tool (loads any saved lights)
        self.layout_widget._light_med.set_uow(self.uow)

        # Connect project DB to the asset effects editor (per-asset painted regions)
        self.layout_widget._asset_effects_med.set_uow(self.uow)

        # Connect project DB to the Progressão do Mundo panel (loads any
        # saved pipelines, or seeds the two default ones on a fresh project)
        self.layout_widget._progression_med.set_uow(self.uow)

        # Connect project DB to the Brush tool (loads any saved terrain
        # painting + object stamps, clearing whatever the previous project
        # had painted).
        self.layout_widget._brush_med.set_uow(self.uow)

        # Connect project DB to the Explorer panel (loads any saved
        # per-element icon/label-color overrides)
        self.layout_widget._explorer_sync_med.set_uow(self.uow)

        # Explorer panel reflects all of the above \u2014 refresh once everything
        # else has finished reloading from the DB (see ExplorerSyncMediator.
        # refresh_now's docstring for why history_changed alone misses this).
        self.layout_widget._explorer_sync_med.refresh_now()

        self.setWindowTitle(f"{APP_NAME} \u2014 {self.project.meta.name}")
        self.layout_widget.top_bar.set_project_name(self.project.meta.name)
        self.layout_widget.top_bar.set_modules_enabled(True)
        self.layout_widget.status_bar.save_label.setText("Salvo")
        self.layout_widget.engines.set_uow(self.uow)
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
        self.asset_engine.library.close()
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
        # The native Windows style ("windowsvista"/"windows11") only honors
        # a subset of QSS — combobox popups, menus and dialogs kept
        # rendering with the OS's own light chrome no matter what the
        # stylesheet below said, since that native style ignores most of
        # the relevant selectors. Fusion is a cross-platform Qt style that
        # actually paints from the stylesheet, so the dark theme applies
        # consistently instead of only to the widgets a native style
        # happens to fully delegate.
        self.app.setStyle(QStyleFactory.create("Fusion"))
        self.app.setStyleSheet(build_stylesheet())

        sys.excepthook = self._handle_exception

        self.window = MainWindow()

        # Conectar logs ao handler
        self.logger.addHandler(self.window.layout_widget.log_handler)

    def run(self) -> int:
        self.window.showMaximized()
        if self.window.project is None:
            # Force the Projects screen up front instead of landing on Mapa
            # with nothing to save into — see MenuViewMediator._on_menu_view.
            self.window.layout_widget._menu_med._on_menu_view("Projetos")
            # Fade out every other module button so there's nothing to
            # click into that would silently no-op every action without a
            # project loaded yet (re-enabled in _on_project_loaded).
            self.window.layout_widget.top_bar.set_modules_enabled(False)
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
