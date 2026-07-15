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

        # Brush properties panel (hidden by default)
        self.brush_panel = BrushToolPanel(self)
        self.brush_panel.hide()
        self.brush_panel.close_requested.connect(lambda: (self.brush_panel.hide(), self._reposition()))

        # Grid settings panel (hidden by default)
        self.grid_panel = GridSettingsPanel(self)
        self.grid_panel.hide()
        self.grid_panel.close_requested.connect(self._close_grid_panel)

        # Terrain settings panel (hidden by default)
        self.terrain_panel = TerrainSettingsPanel(self)
        self.terrain_panel.hide()
        self.terrain_panel.close_requested.connect(self._close_terrain_panel)
        self.terrain_panel.infinite_toggled.connect(self._on_terrain_infinite)
        self.terrain_panel.dimensions_changed.connect(self._on_terrain_dims)
        self.terrain_panel.shape_changed.connect(self._on_terrain_shape)
        self.terrain_panel.terrain_visibility.connect(self._on_terrain_visibility)
        self.terrain_panel.terrain_added.connect(self._on_terrain_added)
        self.terrain_panel.terrain_removed.connect(self._on_terrain_removed)
        self.terrain_panel.terrain_selected.connect(self._on_terrain_selected)
        self.terrain_panel.background_changed.connect(self._on_background_changed)

        # Map boundary overlays: one per terrain card
        self._terrain_boundaries: dict[str, MapBoundary] = {}

        # Explorer (esquerda)
        self._left_scroll = self._make_scroll()
        left_container = QWidget()
        left_container.setAttribute(Qt.WA_TranslucentBackground)
        left_container.setStyleSheet("background: transparent;")
        left_lay = QVBoxLayout(left_container)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left_lay.setSpacing(8)
        self.left_panel = ExplorerPanel()
        self.filters_panel = FilterPanel()
        left_lay.addWidget(self.left_panel, 1)
        left_lay.addWidget(self.filters_panel)
        left_lay.addStretch()
        self._left_scroll.setWidget(left_container)
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

        # Logs (dentro do container direito)
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

        # Zoom control integrado no minimap
        self.minimap.zoom_changed.connect(self._on_zoom_slider)
        # Grid toggle via keyboard shortcut
        self.canvas.engine.grid_toggled.connect(self._on_grid_toggled)
        # Compass expansão → esconde/mostra minimap
        self.compass.expanded_changed.connect(self._on_compass_toggle)
        # Logs
        self.top_bar.logs_clicked.connect(self._open_logs)
        # Menu fullscreen views
        self.top_bar.menu_clicked.connect(self._on_menu_view)

        # ═══ Fullscreen menu view state ═══
        self._active_menu: str = ""  # current fullscreen menu name, "" = canvas mode
        self._menu_container: QWidget | None = None  # fullscreen menu widget

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
        """Força recalcular posições quando um painel muda de tamanho."""
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

        # Canvas: preenche tudo, fica embaixo
        self.canvas.setGeometry(0, 0, w, h)
        self.canvas.lower()

        # TopBar: topo, largura total
        self.top_bar.setGeometry(0, 0, w, top_h)

        # Explorer: esquerda, abaixo do top, até status
        self._left_scroll.setGeometry(0, body_top, self.LEFT_W, body_h)

        # Inspector: direita, abaixo do top, até status
        self._right_scroll.setGeometry(w - self.RIGHT_W, body_top, self.RIGHT_W, body_h)

        # Toolbar: abaixo do top, entre painéis laterais
        self.canvas_toolbar.setGeometry(center_x, body_top, center_w, toolbar_h)

        # Brush panel: lateral esquerda da área central
        if self.brush_panel.isVisible():
            bp_top = body_top + toolbar_h + 4
            bp_h = body_h - toolbar_h - prog_h - 8
            self.brush_panel.setGeometry(center_x + 4, bp_top, self.brush_panel.PANEL_WIDTH, bp_h)
            self.brush_panel.raise_()

        # Grid panel: same position as brush panel, height fits content
        if self.grid_panel.isVisible():
            gp_top = body_top + toolbar_h + 4
            gp_h = self.grid_panel.sizeHint().height()
            self.grid_panel.setGeometry(center_x + 4, gp_top, self.grid_panel.PANEL_WIDTH, gp_h)
            self.grid_panel.raise_()

        # Terrain panel: smart height — fits content, capped at max available
        if self.terrain_panel.isVisible():
            tp_top = body_top + toolbar_h + 4
            tp_max = body_h - toolbar_h - prog_h - 8
            # Calculate needed height from internal scroll container
            container = self.terrain_panel.findChild(QScrollArea)
            if container and container.widget():
                needed = container.widget().sizeHint().height() + 20  # margins
            else:
                needed = self.terrain_panel.sizeHint().height()
            tp_h = min(needed, tp_max)
            self.terrain_panel.setGeometry(center_x + 4, tp_top, self.terrain_panel.PANEL_WIDTH, tp_h)
            self.terrain_panel.raise_()

        # Progression: centro-baixo, entre laterais, acima do status
        self.progression.setGeometry(center_x, body_bottom - prog_h, center_w, prog_h)

        # StatusBar: fundo, largura total
        self.status_bar.setGeometry(0, h - status_h, w, status_h)

        # Overlays na área central livre (abaixo da toolbar, acima da progression)
        ov_top = body_top + toolbar_h
        ov_h = max(0, body_h - toolbar_h - prog_h)

        self.compass.move(center_x + center_w - self.compass.width() - 16, ov_top + 8)
        self.minimap.move(
            center_x + center_w - self.minimap.width() - 16,
            ov_top + ov_h - self.minimap.height() - 8,
        )
        self.minimap.raise_()
        self.compass.raise_()

        # Fullscreen menu view (covers everything between topbar and statusbar)
        if self._menu_container and self._menu_container.isVisible():
            self._menu_container.setGeometry(0, top_h, w, body_h)
            self._menu_container.raise_()

    def _on_zoom(self, percent: int):
        self.status_bar.zoom_label.setText(f"{percent}%")
        self.canvas_toolbar.zoom_label.setText(f"{percent}%")
        self.minimap.set_zoom(percent)

    def _on_zoom_slider(self, percent: int):
        """Slider do zoom_control alterado pelo usuário → aplica no viewport."""
        self.canvas.engine.viewport.set_zoom(percent / 100.0)

    def _on_tool_selected(self, tool_name: str):
        """Mostra/esconde brush panel conforme a ferramenta ativa."""
        if tool_name == "Brush":
            self.grid_panel.hide()
            self.terrain_panel.hide()
            self.brush_panel.show()
            self._connect_brush_panel()
            self.brush_panel._on_tab_clicked(0)
        else:
            self.brush_panel.hide()
        self._reposition()

    def _connect_brush_panel(self):
        """Conecta sliders do brush panel ao BrushEngine."""
        engine = self.canvas.engine.brush_engine
        panel = self.brush_panel

        # Sync panel to current engine values
        panel.size_slider.set_value(engine.config.size)
        panel.opacity_slider.set_value(engine.config.opacity * 100)
        panel.density_slider.set_value(engine.config.density)

        for sig in (panel.size_slider.value_changed, panel.opacity_slider.value_changed,
                    panel.softness_slider.value_changed, panel.density_slider.value_changed,
                    panel.scale_slider.value_changed, panel.rotation_slider.value_changed,
                    panel.asset_selected, panel.favorite_toggled,
                    panel.mode_changed, panel.tab_changed):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError):
                pass

        panel.size_slider.value_changed.connect(self._on_brush_size_changed)
        panel.opacity_slider.value_changed.connect(self._on_brush_opacity_changed)
        panel.density_slider.value_changed.connect(engine.set_density)
        panel.asset_selected.connect(self._on_brush_asset_selected)
        panel.tab_changed.connect(self._on_brush_tab_changed)
        panel.favorite_toggled.connect(self._on_brush_favorite_toggled)

        # Auto-refresh brush grid when assets are added/removed via config panel
        asset_engine = self.canvas.engine._asset_engine
        if asset_engine and hasattr(asset_engine, 'library') and asset_engine.library:
            library = asset_engine.library
            try:
                library.asset_added.disconnect(self._on_library_changed)
            except (RuntimeError, TypeError):
                pass
            try:
                library.asset_removed.disconnect(self._on_library_changed)
            except (RuntimeError, TypeError):
                pass
            library.asset_added.connect(self._on_library_changed)
            library.asset_removed.connect(self._on_library_changed)

        # Terrain-specific params → BrushTool
        brush_tool = self.canvas.engine._brush_tool
        panel.softness_slider.value_changed.connect(lambda v: setattr(brush_tool, 'softness', v / 100.0))
        panel.scale_slider.value_changed.connect(self._on_texture_scale_changed)
        panel.rotation_slider.value_changed.connect(self._on_texture_rotation_changed)
        panel.mode_changed.connect(self._on_brush_mode_changed)

    def _populate_brush_assets(self, category: str = None):
        """Load asset thumbnails into the brush panel grid, filtered by category."""
        asset_engine = self.canvas.engine._asset_engine
        if not asset_engine or not hasattr(asset_engine, 'library'):
            return
        library = asset_engine.library
        if not library:
            return

        if category == "__favorites__":
            assets = library.list_favorites()
        elif category:
            assets = library.list_by_category(category)
        else:
            assets = library.list_all()

        items = []
        for asset in assets:
            thumb = library.thumbnails.get_pixmap(asset.id)
            items.append({
                "id": asset.id,
                "name": asset.name,
                "pixmap": thumb,
                "favorite": library.is_favorite(asset.id),
            })
        self.brush_panel.set_assets(items)

    def _on_brush_asset_selected(self, asset_id: str):
        """User clicked an asset in the brush panel grid."""
        # Auto-create project if none active
        self._ensure_project()

        engine = self.canvas.engine.brush_engine
        engine.clear_assets()
        engine.add_asset(asset_id)
        self.canvas.engine._brush_tool.set_active_asset(asset_id)
        if self.canvas.engine._asset_engine:
            pixmap = self.canvas.engine._asset_engine.get_pixmap(asset_id)
            # Apply brightness/contrast from project settings
            window = self.window()
            if window and hasattr(window, 'uow') and window.uow:
                settings = window.uow.asset_settings.get(asset_id)
                brightness = settings.get("brightness", 0.0)
                contrast = settings.get("contrast", 0.0)
                if (brightness != 0.0 or contrast != 0.0) and pixmap and not pixmap.isNull():
                    pixmap = self._apply_image_adjustments(pixmap, brightness, contrast)
            self.brush_panel.set_texture_preview(pixmap)

    def _apply_image_adjustments(self, pixmap: QPixmap, brightness: float, contrast: float) -> QPixmap:
        """Apply brightness (-100..100) and contrast (-100..100) to a pixmap."""
        from PySide6.QtGui import QImage
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        # Normalize to -1..1 range
        b = brightness / 100.0
        c = (contrast + 100.0) / 100.0  # 0..2 range, 1 = no change
        c = c * c  # quadratic for more natural feel

        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                r = max(0.0, min(1.0, (color.redF() - 0.5) * c + 0.5 + b))
                g = max(0.0, min(1.0, (color.greenF() - 0.5) * c + 0.5 + b))
                bl = max(0.0, min(1.0, (color.blueF() - 0.5) * c + 0.5 + b))
                color.setRedF(r)
                color.setGreenF(g)
                color.setBlueF(bl)
                image.setPixelColor(x, y, color)

        return QPixmap.fromImage(image)

    def _on_brush_size_changed(self, value):
        """Update brush engine size and refresh cursor circle."""
        self.canvas.engine.brush_engine.set_size(value)
        self.canvas.engine._brush_tool.update_cursor_size()

    def _on_brush_opacity_changed(self, value):
        """Update brush engine opacity and preview."""
        self.canvas.engine.brush_engine.set_opacity(value / 100.0)
        self.brush_panel.texture_preview.set_opacity(value / 100.0)

    def _on_brush_mode_changed(self, mode: str):
        """Switch brush between paint, mask, and erase modes."""
        brush_tool = self.canvas.engine._brush_tool
        brush_tool.erase_mode = (mode == "erase")
        brush_tool.mask_mode = (mode == "mask")

    def _on_brush_tab_changed(self, category: str):
        """Filter brush assets grid by the selected tab category."""
        self._populate_brush_assets(category if category else None)

    def _on_brush_favorite_toggled(self, asset_id: str):
        """Toggle favorite on an asset and refresh the grid."""
        asset_engine = self.canvas.engine._asset_engine
        if not asset_engine or not hasattr(asset_engine, 'library'):
            return
        library = asset_engine.library
        if library:
            library.toggle_favorite(asset_id)
            # Refresh current tab
            idx = next((i for i, b in enumerate(self.brush_panel._tab_buttons) if b.isChecked()), 0)
            cats = self.brush_panel._tab_categories
            cat = cats[idx] if idx < len(cats) else None
            self._populate_brush_assets(cat if cat else None)

    def _on_library_changed(self, _name: str):
        """Refresh brush panel grid when library assets change."""
        if self.brush_panel.isVisible():
            idx = next((i for i, b in enumerate(self.brush_panel._tab_buttons) if b.isChecked()), 0)
            cats = self.brush_panel._tab_categories
            cat = cats[idx] if idx < len(cats) else None
            self._populate_brush_assets(cat if cat else None)

    def _on_texture_scale_changed(self, value):
        """Update texture scale on brush tool, active terrain layer, and preview."""
        brush_tool = self.canvas.engine._brush_tool
        brush_tool.texture_scale = value / 100.0
        self.brush_panel.texture_preview.set_scale(value / 100.0)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)

    def _on_texture_rotation_changed(self, value):
        """Update texture rotation on brush tool, active terrain layer, and preview."""
        brush_tool = self.canvas.engine._brush_tool
        brush_tool.texture_rotation = value
        self.brush_panel.texture_preview.set_rotation(value)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)

    def _on_brush_preset_changed(self, preset_name: str):
        """Aplica preset de pincel."""
        from src.engines.map.brush import create_forest_brush, create_rock_brush, create_vegetation_brush, BrushConfig
        engine = self.canvas.engine.brush_engine

        presets = {
            "Grass": lambda: BrushConfig(name="Grass", size=100, spacing=0.3, scatter=0.5, density=3, opacity=1.0, assets=[]),
            "Snow": lambda: BrushConfig(name="Snow", size=150, spacing=0.3, scatter=0.4, density=2, opacity=0.9, assets=[]),
            "Sand": lambda: BrushConfig(name="Sand", size=120, spacing=0.25, scatter=0.6, density=2, opacity=1.0, assets=[]),
            "Ocean": lambda: BrushConfig(name="Ocean", size=200, spacing=0.2, scatter=0.3, density=1, opacity=0.8, assets=[]),
            "Rock": lambda: create_rock_brush([]),
            "Swamp": lambda: BrushConfig(name="Swamp", size=130, spacing=0.3, scatter=0.7, density=2, opacity=0.9, assets=[]),
        }

        factory = presets.get(preset_name)
        if factory:
            config = factory()
            engine.set_config(config)
            self.brush_panel.size_slider.set_value(config.size)
            self.brush_panel.opacity_slider.set_value(config.opacity * 100)
            self.brush_panel.density_slider.set_value(config.density)

    def _on_compass_toggle(self, expanded: bool):
        """Esconde minimap se compass expandida colide com ele."""
        self._reposition()
        if expanded and self.compass.geometry().intersects(self.minimap.geometry()):
            self.minimap.hide()
        else:
            self.minimap.show()

    def _on_toolbar_action(self, name: str):
        """Handles non-tool toolbar buttons."""
        # Panel actions deactivate brush tool
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

    def _toggle_grid_panel(self):
        """Toggle grid visibility and settings panel."""
        self.canvas.engine._toggle_grid()
        visible = self.canvas.engine.grid.visible
        if visible:
            self.brush_panel.hide()
            self.terrain_panel.hide()
            self.grid_panel.show()
            self._connect_grid_panel()
        else:
            self.grid_panel.hide()
        self._reposition()

    def _close_grid_panel(self):
        """Close grid panel and disable grid."""
        self.canvas.engine._toggle_grid()
        self.grid_panel.hide()
        self._reposition()

    def _on_grid_toggled(self, visible: bool):
        """Called when grid is toggled via keyboard shortcut."""
        if visible:
            self.brush_panel.hide()
            self.terrain_panel.hide()
            self.grid_panel.show()
            self._connect_grid_panel()
        else:
            self.grid_panel.hide()
        self._reposition()

    def _connect_grid_panel(self):
        """Sync grid panel sliders to GridManager."""
        grid = self.canvas.engine.grid
        panel = self.grid_panel

        panel.size_slider.set_value(grid.cell_size)
        panel.subdivisions_slider.set_value(grid.subdivisions)
        panel.snap_check.setChecked(True)

        for sig in (panel.size_slider.value_changed, panel.subdivisions_slider.value_changed,
                    panel.opacity_slider.value_changed, panel.snap_toggled, panel.shape_changed):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError, RuntimeWarning):
                pass

        def _update_size(v):
            grid.cell_size = int(v)
            self.canvas.engine._update_grid()

        def _update_sub(v):
            grid.subdivisions = int(v)
            self.canvas.engine._update_grid()

        def _update_opacity(v):
            alpha_major = int(v * 2.55)  # 0-100 → 0-255
            alpha_minor = int(v * 1.0)   # 0-100 → 0-100
            grid.color_major = QColor(255, 255, 255, min(255, alpha_major))
            grid.color_minor = QColor(255, 255, 255, min(255, alpha_minor))
            self.canvas.engine._update_grid()

        def _update_shape(shape_name):
            grid.shape = shape_name
            self.canvas.engine._update_grid()

        panel.size_slider.value_changed.connect(_update_size)
        panel.subdivisions_slider.value_changed.connect(_update_sub)
        panel.opacity_slider.value_changed.connect(_update_opacity)
        panel.shape_changed.connect(_update_shape)
        panel.snap_toggled.connect(lambda on: self.canvas.engine.snap.toggle())

    def _open_logs(self):
        open_logs_dialog(self, self.log_handler)

    # ─── Fullscreen Menu Views ───

    def _canvas_widgets(self) -> list[QWidget]:
        """All widgets that belong to the canvas/map editing mode (excluding canvas itself)."""
        return [
            self.canvas_toolbar, self.brush_panel,
            self.grid_panel, self.terrain_panel, self._left_scroll,
            self._right_scroll, self.progression, self.compass, self.minimap,
        ]

    def _on_menu_view(self, menu_name: str):
        """Toggle fullscreen menu view. Click same menu again to close."""
        # Mapa = return to canvas mode
        if menu_name == "Mapa":
            self._hide_menu_view()
            return
        # Logs = dialog, not fullscreen
        if menu_name == "Logs":
            self._hide_menu_view()
            return
        # Toggle: click same menu again to close
        if menu_name == self._active_menu:
            self._hide_menu_view()
        else:
            self._show_menu_view(menu_name)
            # Ensure the button stays checked (topbar already did this)
            self.top_bar.set_active_menu(menu_name)

    def _show_menu_view(self, menu_name: str):
        """Hide all canvas widgets and show fullscreen menu panel."""
        # Hide previous menu if any
        if self._menu_container:
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        # Hide canvas mode widgets
        for w in self._canvas_widgets():
            w.hide()

        self._active_menu = menu_name

        # Create menu container (transparent so canvas/background stays visible)
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
            panel.setMaximumWidth(16777215)  # remove max width constraint
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
            # Fallback placeholder
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
        """Close fullscreen menu and restore canvas mode."""
        if self._menu_container:
            self._menu_container.hide()
            self._menu_container.deleteLater()
            self._menu_container = None

        self._active_menu = ""

        # Mark "Mapa" as active in topbar
        self.top_bar.set_active_menu("Mapa")

        # Restore canvas mode widgets
        for w in self._canvas_widgets():
            if w in (self.brush_panel, self.grid_panel, self.terrain_panel):
                continue  # these stay hidden unless explicitly opened
            w.show()

        self._reposition()

    def _on_menu_project_opened(self, proj):
        """Project opened from fullscreen menu."""
        window = self.window()
        if window and hasattr(window, '_on_panel_project_opened'):
            window._on_panel_project_opened(proj)
        self._hide_menu_view()

    def _on_menu_new_project(self):
        """New project from fullscreen menu."""
        window = self.window()
        if window and hasattr(window, 'new_project'):
            window.new_project()
        self._hide_menu_view()

    def _on_menu_delete_project(self, path: str):
        """Delete project from fullscreen menu."""
        from pathlib import Path as P
        import shutil
        window = self.window()
        target = P(path)

        # If deleting the active project, clean up
        if window and hasattr(window, 'project') and window.project and str(window.project.path) == path:
            window.autosave.stop()
            if window.uow:
                window.uow.close()
                window.uow = None
            window.project = None
            window.setWindowTitle(f"MAKEMAP — v0.1.0")
            self.top_bar.set_project_name("")

        # Delete from disk
        if target.exists():
            shutil.rmtree(target)

        # Refresh the ProjectsPanel inside the menu container
        if self._menu_container:
            from src.layouts.panels.projects_panel import ProjectsPanel
            panel = self._menu_container.findChild(ProjectsPanel)
            if panel:
                panel.set_active("")
                panel.refresh()

    # ─── Terrain Panel ───

    def _ensure_project(self):
        """Auto-create and persist a project if none is active (MAKEVID pattern)."""
        window = self.window()
        if window and hasattr(window, 'project') and window.project is None:
            window.new_project()

    def _toggle_terrain_panel(self):
        """Toggle terrain settings panel."""
        if self.terrain_panel.isVisible():
            self._close_terrain_panel()
        else:
            self.brush_panel.hide()
            self.grid_panel.hide()
            self.terrain_panel.show()
        self._reposition()

    def _close_terrain_panel(self):
        """Close terrain panel and uncheck toolbar button."""
        self.terrain_panel.hide()
        self.canvas_toolbar.uncheck_action("Terreno")
        self._reposition()

    def _on_terrain_infinite(self, infinite: bool):
        """Toggle terrain boundaries visibility."""
        if infinite:
            self.canvas.engine.clear_map_bounds()
            self.canvas.engine._brush_tool.set_active_boundary(None)
            # Hide all terrain boundaries
            for boundary in self._terrain_boundaries.values():
                boundary.hide()
        else:
            # Restore terrain boundaries based on eye icon state
            w = self.terrain_panel.map_width
            h = self.terrain_panel.map_height
            shape = self.terrain_panel.map_shape
            self.canvas.engine.set_map_bounds(w, h, shape)
            for tid, boundary in self._terrain_boundaries.items():
                card = self.terrain_panel._cards.get(tid)
                if card and card.is_visible:
                    boundary.show(w, h, shape)
            # Set active boundary to selected terrain
            sel_id = self.terrain_panel.selected_terrain_id
            if sel_id:
                self.canvas.engine._brush_tool.set_active_boundary(self._terrain_boundaries.get(sel_id))
        self._reposition()

    def _on_terrain_dims(self, width: int, height: int):
        """Update only the selected terrain boundary dimensions."""
        if not self.terrain_panel.is_infinite:
            self.canvas.engine.set_map_bounds(width, height, self.terrain_panel.map_shape)
        # Only update the selected terrain boundary
        sel_id = self.terrain_panel.selected_terrain_id
        if sel_id:
            boundary = self._terrain_boundaries.get(sel_id)
            if boundary and boundary.visible:
                boundary.update_dimensions(width, height)

    def _on_terrain_shape(self, shape: str):
        """Update only the selected terrain boundary shape."""
        if not self.terrain_panel.is_infinite:
            self.canvas.engine.set_map_bounds(
                self.terrain_panel.map_width, self.terrain_panel.map_height, shape
            )
        # Only update the selected terrain boundary
        sel_id = self.terrain_panel.selected_terrain_id
        if sel_id:
            boundary = self._terrain_boundaries.get(sel_id)
            if boundary and boundary.visible:
                boundary.update_shape(shape)

    def _on_terrain_visibility(self, terrain_id: str, visible: bool):
        """Toggle terrain boundary visibility from card eye icon."""
        # Only show boundaries when not in infinite mode
        if self.terrain_panel.is_infinite:
            return
        boundary = self._terrain_boundaries.get(terrain_id)
        if not boundary:
            return
        w = self.terrain_panel.map_width
        h = self.terrain_panel.map_height
        shape = self.terrain_panel.map_shape
        if visible:
            boundary.show(w, h, shape)
            # If boundary has no position yet, place at viewport center
            if boundary.position.isNull():
                view_center = self.canvas.engine.viewport.mapToScene(
                    self.canvas.engine.viewport.viewport().rect().center()
                )
                boundary.set_position(view_center)
            self._fit_to_boundary(boundary)
        else:
            boundary.hide()

    def _fit_to_boundary(self, boundary):
        """Zoom and center the viewport to fit the given boundary."""
        if not boundary._item:
            return
        rect = boundary._item.mapToScene(boundary._item.boundingRect()).boundingRect()
        # Add some padding
        padding = 80
        rect.adjust(-padding, -padding, padding, padding)
        self.canvas.engine.viewport.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        # Update zoom state
        new_zoom = self.canvas.engine.viewport.transform().m11()
        self.canvas.engine.viewport._zoom = new_zoom
        self.canvas.engine.viewport.zoom_changed.emit(new_zoom)
        self.canvas.engine.viewport.view_changed.emit()

    def _on_terrain_selected(self, terrain_id: str):
        """Update brush tool active boundary to the selected terrain panel."""
        boundary = self._terrain_boundaries.get(terrain_id)
        if not self.terrain_panel.is_infinite:
            self.canvas.engine._brush_tool.set_active_boundary(boundary)
        else:
            self.canvas.engine._brush_tool.set_active_boundary(None)

    def _on_terrain_added(self, terrain_id: str, name: str):
        """Create a boundary overlay for the new terrain at viewport center."""
        # Auto-create project if none active (same pattern as MAKEVID)
        self._ensure_project()

        scene = self.canvas.engine.viewport.scene()
        # Get the terrain card color
        card = self.terrain_panel._cards.get(terrain_id)
        color = None
        if card:
            # Extract color from the swatch widget
            swatch = card.layout().itemAt(0).widget()
            if swatch:
                ss = swatch.styleSheet()
                # Parse "background: #RRGGBB;" from stylesheet
                import re
                m = re.search(r'background:\s*(#[0-9a-fA-F]{6})', ss)
                if m:
                    color = QColor(m.group(1))
        boundary = MapBoundary(scene, color)
        w = self.terrain_panel.map_width
        h = self.terrain_panel.map_height
        shape = self.terrain_panel.map_shape
        # Only show if not in infinite mode
        if not self.terrain_panel.is_infinite:
            boundary.show(w, h, shape)
            # Position at current viewport center
            view_center = self.canvas.engine.viewport.mapToScene(
                self.canvas.engine.viewport.viewport().rect().center()
            )
            boundary.set_position(view_center)
        self._terrain_boundaries[terrain_id] = boundary
        # Sync active boundary to brush tool if this is the selected terrain
        if self.terrain_panel.selected_terrain_id == terrain_id and not self.terrain_panel.is_infinite:
            self.canvas.engine._brush_tool.set_active_boundary(boundary)

    def _on_terrain_removed(self, terrain_id: str):
        """Remove boundary overlay for deleted terrain."""
        boundary = self._terrain_boundaries.pop(terrain_id, None)
        if boundary:
            boundary.hide()
        # Update brush tool boundary to newly selected terrain
        sel_id = self.terrain_panel.selected_terrain_id
        if sel_id and not self.terrain_panel.is_infinite:
            self.canvas.engine._brush_tool.set_active_boundary(self._terrain_boundaries.get(sel_id))
        else:
            self.canvas.engine._brush_tool.set_active_boundary(None)

    def _on_background_changed(self, bg_type: str, value: str):
        """Apply background change to the canvas viewport."""
        viewport = self.canvas.engine.viewport
        if bg_type == "none":
            viewport.set_background(None, None)
        elif bg_type == "color":
            viewport.set_background(QColor(value), None)
        elif bg_type in ("image", "gif"):
            from PySide6.QtGui import QPixmap
            pix = QPixmap(value)
            if not pix.isNull():
                viewport.set_background(None, pix)
            else:
                viewport.set_background(None, None)
