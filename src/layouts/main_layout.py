"""Main layout — mapa fullscreen com painéis glass flutuando por cima."""

import warnings
warnings.filterwarnings("ignore", message=".*Failed to disconnect.*", category=RuntimeWarning)

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QSizePolicy, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.top_bar import TopBar
from src.layouts.panels.toolbar import CanvasToolbar
from src.layouts.panels.brush_panel import BrushToolPanel
from src.layouts.panels.grid_panel import GridSettingsPanel
from src.layouts.panels.terrain_panel import TerrainSettingsPanel
from src.layouts.panels.explorer import ExplorerPanel, FilterPanel
from src.layouts.panels.canvas_area import CanvasArea
from src.layouts.panels.inspector import InspectorPanel, QuestPanel, LayersPanel
from src.layouts.panels.progression import ProgressionBar
from src.layouts.panels.status_bar import StatusBar
from src.layouts.panels.logs_panel import QtLogHandler, open_logs_dialog
from src.canvas.overlays import Compass, MiniMap
from src.canvas.map_boundary import MapBoundary
from src.engines.integrator import EngineIntegrator
from src.layouts.mediator import BrushMediator, TerrainMediator, GridMediator
from src.layouts.panel_manager import PanelManager


class MainLayout(QWidget):
    """
    Canvas fullscreen + painéis como filhos diretos posicionados por cima.
    O canvas recebe mouse events nativamente nas áreas não cobertas.
    """

    LEFT_W = 280
    RIGHT_W = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {Colors.BG_SECONDARY};")

        # ═══ Canvas (sempre no fundo) ═══
        self.canvas = CanvasArea(self)

        # ═══ Painéis (filhos diretos, flutuam por cima) ═══
        self.top_bar = TopBar(self)

        self.canvas_toolbar = CanvasToolbar(self)
        self.canvas_toolbar.tool_selected.connect(self.canvas.engine.tool_manager.activate)
        self.canvas_toolbar.tool_selected.connect(self._on_tool_selected)
        self.canvas_toolbar.action_triggered.connect(self._on_toolbar_action)

        self.brush_panel = BrushToolPanel(self)
        self.brush_panel.hide()
        self.brush_panel.close_requested.connect(lambda: (self._panel_mgr.hide("Brush"), self._reposition()))

        self.grid_panel = GridSettingsPanel(self)
        self.grid_panel.hide()
        self.grid_panel.close_requested.connect(self._close_grid_panel)

        self.terrain_panel = TerrainSettingsPanel(self)
        self.terrain_panel.hide()
        self.terrain_panel.close_requested.connect(self._close_terrain_panel)

        # ═══ Mediators ═══
        self._brush_med = BrushMediator(self)
        self._terrain_med = TerrainMediator(self)
        self._grid_med = GridMediator(self)

        # ═══ Panel Manager ═══
        self._panel_mgr = PanelManager(self)
        self._panel_mgr.register(
            "Brush", self.brush_panel, fill_height=True,
            on_show=lambda: self._brush_med.connect_panel(),
        )
        self._panel_mgr.register(
            "Grid", self.grid_panel,
            on_show=lambda: self._grid_med.connect_panel(),
        )
        self._panel_mgr.register(
            "Terrain", self.terrain_panel,
        )

        # Terrain panel signals → mediator
        self.terrain_panel.infinite_toggled.connect(self._terrain_med.on_infinite)
        self.terrain_panel.dimensions_changed.connect(self._terrain_med.on_dims)
        self.terrain_panel.shape_changed.connect(self._terrain_med.on_shape)
        self.terrain_panel.terrain_visibility.connect(self._terrain_med.on_visibility)
        self.terrain_panel.terrain_added.connect(self._terrain_med.on_added)
        self.terrain_panel.terrain_removed.connect(self._terrain_med.on_removed)
        self.terrain_panel.terrain_selected.connect(self._terrain_med.on_selected)
        self.terrain_panel.background_changed.connect(self._terrain_med.on_background)
        self.terrain_panel.content_changed.connect(self._reposition)

        # Map boundary overlays reference
        self._terrain_boundaries = self._terrain_med.boundaries

        # Explorer (esquerda)
        self._left_container = QWidget(self)
        self._left_container.setAttribute(Qt.WA_TranslucentBackground)
        self._left_container.setStyleSheet("background: transparent;")
        left_lay = QVBoxLayout(self._left_container)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left_lay.setSpacing(8)
        self.left_panel = ExplorerPanel()
        self.filters_panel = FilterPanel()
        left_lay.addWidget(self.left_panel, 1)
        left_lay.addWidget(self.filters_panel, 0)
        self.left_panel.collapsed_changed.connect(
            lambda collapsed: left_lay.setStretchFactor(self.left_panel, 0 if collapsed else 1)
        )

        # Inspector (direita)
        self._right_scroll = self._make_scroll()
        right_container = QWidget()
        right_container.setAttribute(Qt.WA_TranslucentBackground)
        right_container.setStyleSheet("background: transparent;")
        right_lay = QVBoxLayout(right_container)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right_lay.setSpacing(8)
        self.right_panel = InspectorPanel()
        self.quest_panel = QuestPanel()
        self.layers_panel = LayersPanel()
        right_lay.addWidget(self.right_panel, 1)
        right_lay.addWidget(self.quest_panel)
        right_lay.addWidget(self.layers_panel)
        self._right_scroll.setWidget(right_container)
        self.right_panel.collapsed_changed.connect(
            lambda collapsed: right_lay.setStretchFactor(self.right_panel, 0 if collapsed else 1)
        )

        self.log_handler = QtLogHandler()
        right_lay.addStretch()

        # Progression + Status
        self.progression = ProgressionBar(self)
        self.progression.size_changed.connect(self._reposition)
        self.status_bar = StatusBar(self)

        # Overlays
        self.compass = Compass(self)
        self.minimap = MiniMap(self)
        self.minimap.set_viewport(self.canvas.engine.viewport)
        self.canvas.engine._brush_tool.set_minimap(self.minimap)

        # ═══ Conexões ═══
        self.canvas.engine.cursor_moved.connect(
            lambda x, y: self.status_bar.coords.setText(f"X: {x:.0f}  Y: {y:.0f}")
        )
        self.canvas.engine.zoom_changed.connect(self._on_zoom)
        self.canvas.engine.tool_changed.connect(
            lambda t: self.status_bar.tool_label.setText(f"🔧 {t}")
        )
        self.status_bar.zoom_in_clicked.connect(self.canvas.engine.zoom_in)
        self.status_bar.zoom_out_clicked.connect(self.canvas.engine.zoom_out)
        self.minimap.zoom_changed.connect(self._on_zoom_slider)
        self.canvas.engine.grid_toggled.connect(self._on_grid_toggled)
        self.compass.expanded_changed.connect(self._on_compass_toggle)
        self.top_bar.logs_clicked.connect(self._open_logs)
        self.top_bar.menu_clicked.connect(self._on_menu_view)

        # ═══ Fullscreen menu view state ═══
        self._active_menu: str = ""
        self._menu_container: QWidget | None = None

        # ═══ Engine Integrator ═══
        self.engines = EngineIntegrator(self)
        self.engines.connect_ui(self)

    def _make_scroll(self) -> QScrollArea:
        s = QScrollArea(self)
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        s.setAttribute(Qt.WA_TranslucentBackground)
        s.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
        """)
        return s

    def _reposition(self):
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if event:
            super().resizeEvent(event)
        w, h = self.width(), self.height()

        top_h = 72
        toolbar_h = 42
        status_h = 80
        prog_h = self.progression.height()

        body_top = top_h
        body_bottom = h - status_h
        body_h = body_bottom - body_top

        center_x = self.LEFT_W
        center_w = max(0, w - self.LEFT_W - self.RIGHT_W)

        self.canvas.setGeometry(0, 0, w, h)
        self.canvas.lower()
        self.top_bar.setGeometry(0, 0, w, top_h)
        self._left_container.setGeometry(0, body_top, self.LEFT_W, body_h)
        self._right_scroll.setGeometry(w - self.RIGHT_W, body_top, self.RIGHT_W, body_h)
        tb_w = min(self.canvas_toolbar.sizeHint().width(), center_w)
        tb_x = center_x + (center_w - tb_w) // 2
        self.canvas_toolbar.setGeometry(tb_x, body_top, tb_w, toolbar_h)

        panel_x = center_x + 4
        panel_y = body_top + toolbar_h + 4
        panel_max_h = body_h - toolbar_h - prog_h - 8
        self._panel_mgr.layout(panel_x, panel_y, self.brush_panel.PANEL_WIDTH, panel_max_h)

        self.progression.setGeometry(center_x, body_bottom - prog_h, center_w, prog_h)
        self.status_bar.setGeometry(0, h - status_h, w, status_h)

        ov_top = body_top + toolbar_h
        ov_h = max(0, body_h - toolbar_h - prog_h)
        self.compass.move(center_x + center_w - self.compass.width() - 16, ov_top + 8)
        self.minimap.move(
            center_x + center_w - self.minimap.width() - 16,
            ov_top + ov_h - self.minimap.height() - 8,
        )
        self.minimap.raise_()
        self.compass.raise_()

        if self._menu_container and self._menu_container.isVisible():
            self._menu_container.setGeometry(0, top_h, w, body_h)
            self._menu_container.raise_()

    # ─── Zoom ───

    def _on_zoom(self, percent: int):
        self.status_bar.zoom_label.setText(f"{percent}%")
        self.canvas_toolbar.zoom_label.setText(f"{percent}%")
        self.minimap.set_zoom(percent)

    def _on_zoom_slider(self, percent: int):
        self.canvas.engine.viewport.set_zoom(percent / 100.0)

    # ─── Tool Selection ───

    def _on_tool_selected(self, tool_name: str):
        if tool_name == "Brush":
            self._panel_mgr.show("Brush")
        else:
            self._panel_mgr.hide("Brush")
        self._reposition()

    # ─── Toolbar Actions ───

    def _on_toolbar_action(self, name: str):
        if name in ("Grid", "Terreno"):
            self.canvas.engine.tool_manager.activate("Selecionar")
            self.brush_panel.hide()

        actions = {
            "Grid": self._toggle_grid_panel,
            "Terreno": self._toggle_terrain_panel,
            "Snap": self.canvas.engine.snap.toggle,
            "Undo": self.canvas.engine.history.undo,
            "Redo": self.canvas.engine.history.redo,
        }
        action = actions.get(name)
        if action:
            action()

    # ─── Grid Panel ───

    def _toggle_grid_panel(self):
        self.canvas.engine._toggle_grid()
        if self.canvas.engine.grid.visible:
            self._panel_mgr.show("Grid")
        else:
            self._panel_mgr.hide("Grid")
        self._reposition()

    def _close_grid_panel(self):
        self.canvas.engine._toggle_grid()
        self._panel_mgr.hide("Grid")
        self._reposition()

    def _on_grid_toggled(self, visible: bool):
        if visible:
            self._panel_mgr.show("Grid")
        else:
            self._panel_mgr.hide("Grid")
        self._reposition()

    # ─── Terrain Panel ───

    def _ensure_project(self):
        window = self.window()
        if window and hasattr(window, 'project') and window.project is None:
            window.new_project()

    def _toggle_terrain_panel(self):
        self._panel_mgr.toggle("Terrain")
        self._reposition()

    def _close_terrain_panel(self):
        self._panel_mgr.hide("Terrain")
        self.canvas_toolbar.uncheck_action("Terreno")
        self._reposition()

    # ─── Compass ───

    def _on_compass_toggle(self, expanded: bool):
        self._reposition()
        if expanded and self.compass.geometry().intersects(self.minimap.geometry()):
            self.minimap.hide()
        else:
            self.minimap.show()

    # ─── Logs ───

    def _open_logs(self):
        open_logs_dialog(self, self.log_handler)

    # ─── Fullscreen Menu Views ───

    def _canvas_widgets(self) -> list[QWidget]:
        return [
            self.canvas_toolbar, self.brush_panel,
            self.grid_panel, self.terrain_panel, self._left_container,
            self._right_scroll, self.progression, self.compass, self.minimap,
        ]

    def _on_menu_view(self, menu_name: str):
        if menu_name == "Mapa":
            self._hide_menu_view()
            return
        if menu_name == "Logs":
            self._hide_menu_view()
            return
        if menu_name == self._active_menu:
            self._hide_menu_view()
        else:
            self._show_menu_view(menu_name)
            self.top_bar.set_active_menu(menu_name)

    def _show_menu_view(self, menu_name: str):
        if self._menu_container:
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        for w in self._canvas_widgets():
            w.hide()

        self._active_menu = menu_name

        from src.layouts.panels.projects_panel import ProjectsPanel
        from src.layouts.panels.menu_panels import MENU_PANELS

        container = QWidget(self)
        container.setAttribute(Qt.WA_TranslucentBackground)
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if menu_name == "Projetos":
            window = self.window()
            panel = ProjectsPanel(
                active_path=str(window.project.path) if window and hasattr(window, 'project') and window.project else "",
                parent=container,
            )
            panel.setMaximumWidth(16777215)
            panel.setMinimumWidth(0)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            panel.closed.connect(self._hide_menu_view)
            panel.project_opened.connect(self._on_menu_project_opened)
            panel.new_requested.connect(self._on_menu_new_project)
            panel.delete_requested.connect(self._on_menu_delete_project)
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
        container.show()
        container.raise_()
        self._reposition()

    def _hide_menu_view(self):
        if self._menu_container:
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        self._active_menu = ""
        self.top_bar.set_active_menu("Mapa")

        for w in self._canvas_widgets():
            if w in (self.brush_panel, self.grid_panel, self.terrain_panel):
                continue
            w.show()
        self._reposition()

    def _on_menu_project_opened(self, proj):
        window = self.window()
        if window and hasattr(window, '_on_panel_project_opened'):
            window._on_panel_project_opened(proj)
        self._hide_menu_view()

    def _on_menu_new_project(self):
        window = self.window()
        if window and hasattr(window, 'new_project'):
            window.new_project()
        self._hide_menu_view()

    def _on_menu_delete_project(self, path: str):
        from pathlib import Path as P
        import shutil
        window = self.window()
        target = P(path)

        if window and hasattr(window, 'project') and window.project and str(window.project.path) == path:
            window.autosave.stop()
            if window.uow:
                window.uow.close()
                window.uow = None
            window.project = None
            window.setWindowTitle("MAKEMAP — v0.1.0")
            self.top_bar.set_project_name("")

        if target.exists():
            shutil.rmtree(target)

        if self._menu_container:
            from src.layouts.panels.projects_panel import ProjectsPanel
            panel = self._menu_container.findChild(ProjectsPanel)
            if panel:
                panel.set_active("")
                panel.refresh()
