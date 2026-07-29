"""MenuViewMediator — owns the fullscreen "menu view" system: TopBar's nav
buttons (Projetos, Mobs, Itens, Dungeons, ...) swap the whole canvas out for
a fullscreen panel instead of opening a floating sub-panel, plus the Logs
modal dialog (tracks _active_menu so it can restore whichever nav button was
really active once Logs closes). Same `self._l = layout` mediator
convention as LightMediator/TextMediator, extracted verbatim from
MainLayout's "Fullscreen Menu Views"/"Logs" sections (no behavior change).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QLabel
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.logs_panel import open_logs_dialog

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class MenuViewMediator:
    def __init__(self, layout: MainLayout):
        self._l = layout
        self._active_menu: str = ""
        self._menu_container: QWidget | None = None
        self._active_panel: QWidget | None = None

        self._l.top_bar.logs_clicked.connect(self._open_logs)
        self._l.top_bar.menu_clicked.connect(self._on_menu_view)

    # ─── Logs ───

    def _open_logs(self):
        # Logs is a modal dialog on top of whatever's currently shown, not
        # a fullscreen menu view — restore whichever nav button was really
        # active (e.g. "Mobs") once it closes, since top_bar._on_nav_clicked
        # already switched the top bar to show "Logs" as checked.
        previous = self._active_menu or "Mapa"
        open_logs_dialog(self._l, self._l.log_handler)
        self._l.top_bar.set_active_menu(previous)

    # ─── Fullscreen Menu Views ───

    def _canvas_widgets(self) -> list[QWidget]:
        l = self._l
        return [
            l.canvas_toolbar, l.brush_panel,
            l.grid_panel, l.terrain_panel, l.region_panel, l.select_panel,
            l.text_panel,
            l._left_container, l._right_scroll, l.progression, l.compass,
            l.compass_hud, l.minimap,
        ]

    def _on_menu_view(self, menu_name: str):
        if menu_name == "Mapa":
            self._hide_menu_view()
            return
        if menu_name == "Logs":
            # Logs opens as its own modal dialog (see _open_logs, wired to
            # top_bar.logs_clicked) — it isn't a fullscreen menu view, so
            # opening it shouldn't close whatever panel (Mobs, etc.) is
            # already open underneath.
            return
        if menu_name == self._active_menu:
            self._hide_menu_view()
        else:
            self._show_menu_view(menu_name)
            self._l.top_bar.set_active_menu(menu_name)

    def _show_menu_view(self, menu_name: str):
        l = self._l
        if self._menu_container:
            self._flush_active_panel()
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        for w in self._canvas_widgets():
            w.hide()

        self._active_menu = menu_name

        from src.layouts.panels.projects_panel import ProjectsPanel
        from src.layouts.panels.menu_panels import MENU_PANELS

        container = QWidget(l)
        container.setAttribute(Qt.WA_TranslucentBackground)
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if menu_name == "Projetos":
            window = l.window()
            panel = ProjectsPanel(
                active_path=str(window.project.path) if window and hasattr(window, 'project') and window.project else "",
                parent=container,
            )
            panel.setMaximumWidth(16777215)
            panel.setMinimumWidth(0)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            panel.closed.connect(self._hide_menu_view)
            panel.project_opened.connect(self._on_menu_project_opened)
            panel.project_created.connect(self._on_menu_project_created)
            panel.delete_requested.connect(self._on_menu_delete_project)
            layout.addWidget(panel)
        elif menu_name == "Mobs":
            from src.layouts.panels.mobs.panel import MobsPanel
            window = l.window()
            uow = window.uow if window and hasattr(window, 'uow') else None
            project_dir = window.project.path if window and getattr(window, 'project', None) else None
            panel = MobsPanel(
                uow, zones_provider=l._region_med.zones_list,
                zone_thumbnail_provider=l._region_med.zone_thumbnail,
                project_dir=project_dir, parent=container,
            )
            panel.closed.connect(self._hide_menu_view)
            layout.addWidget(panel)
        elif menu_name == "Itens":
            from src.layouts.panels.items.panel import ItemsSkillsPanel
            window = l.window()
            uow = window.uow if window and hasattr(window, 'uow') else None
            project_dir = window.project.path if window and getattr(window, 'project', None) else None
            panel = ItemsSkillsPanel(uow, project_dir=project_dir, parent=container)
            panel.closed.connect(self._hide_menu_view)
            layout.addWidget(panel)
        elif menu_name == "Dungeons":
            from src.layouts.panels.dungeons.panel import DungeonsPanel
            window = l.window()
            uow = window.uow if window and hasattr(window, 'uow') else None
            project_dir = window.project.path if window and getattr(window, 'project', None) else None
            panel = DungeonsPanel(uow, project_dir=project_dir, parent=container)
            panel.closed.connect(self._hide_menu_view)
            layout.addWidget(panel)
        elif menu_name in MENU_PANELS:
            panel_class = MENU_PANELS[menu_name]
            panel = panel_class(container)
            panel.closed.connect(self._hide_menu_view)
            layout.addWidget(panel)
        else:
            placeholder = QWidget(container)
            placeholder.setAttribute(Qt.WA_TranslucentBackground)
            placeholder.setStyleSheet("background: transparent;")
            ph_layout = QVBoxLayout(placeholder)
            ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(f"{menu_name}")
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 18px; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph_layout.addWidget(lbl)
            layout.addWidget(placeholder)

        self._menu_container = container
        self._active_panel = layout.itemAt(0).widget() if layout.count() else None
        container.show()
        container.raise_()
        l._reposition()

    def _flush_active_panel(self):
        """Menu panels switch (or the whole app closes) without the
        panel's own close button ever being clicked — deleteLater() below
        would otherwise silently drop whatever a panel's debounced
        autosave timer (e.g. ItemsSkillsPanel) hasn't committed yet."""
        flush = getattr(self._active_panel, "flush_pending_saves", None)
        if callable(flush):
            flush()

    def _hide_menu_view(self):
        l = self._l
        if self._menu_container:
            self._flush_active_panel()
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        self._active_menu = ""
        l.top_bar.set_active_menu("Mapa")

        for w in self._canvas_widgets():
            if w in (l.brush_panel, l.grid_panel,
                     l.terrain_panel, l.region_panel, l.select_panel, l.text_panel,
                     l.compass_hud):
                continue
            w.show()
        # Not part of the blanket show() above — its visibility rule is
        # "Info" checkbox state, not plain show/hide (see _refresh_compass_hud).
        l._refresh_compass_hud()
        l._reposition()

    def _on_menu_project_opened(self, proj):
        window = self._l.window()
        if window and hasattr(window, '_on_panel_project_opened'):
            window._on_panel_project_opened(proj)
        self._hide_menu_view()

    def _on_menu_project_created(self, proj):
        # Unlike opening an existing project, keep the Projetos view open —
        # the new card is shown in edit mode so the user can type its name.
        window = self._l.window()
        if window and hasattr(window, '_load_project'):
            window._load_project(proj)

    def _on_menu_delete_project(self, path: str):
        from pathlib import Path as P
        import shutil
        window = self._l.window()
        target = P(path)

        if window and hasattr(window, 'project') and window.project and str(window.project.path) == path:
            window.autosave.stop()
            if window.uow:
                window.uow.close()
                window.uow = None
            window.project = None
            window.setWindowTitle("MAKEMAP — v0.1.0")
            self._l.top_bar.set_project_name("")

        if target.exists():
            shutil.rmtree(target)

        if self._menu_container:
            from src.layouts.panels.projects_panel import ProjectsPanel
            panel = self._menu_container.findChild(ProjectsPanel)
            if panel:
                panel.set_active("")
                panel.refresh()
