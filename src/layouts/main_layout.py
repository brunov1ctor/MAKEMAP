"""Main layout — mapa fullscreen com painéis glass flutuando por cima."""

import warnings
warnings.filterwarnings("ignore", message=".*Failed to disconnect.*", category=RuntimeWarning)

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.layouts.panels.top_bar import TopBar
from src.layouts.panels.toolbar import CanvasToolbar
from src.layouts.panels.brush_panel import BrushToolPanel
from src.layouts.panels.grid_panel import GridSettingsPanel
from src.layouts.panels.explorer import ExplorerPanel, FilterPanel
from src.layouts.panels.canvas_area import CanvasArea
from src.layouts.panels.inspector import InspectorPanel, QuestPanel, LayersPanel
from src.layouts.panels.progression import ProgressionBar
from src.layouts.panels.status_bar import StatusBar
from src.layouts.panels.logs_panel import QtLogHandler, open_logs_dialog
from src.canvas.overlays import Compass, MiniMap
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
        self.canvas_toolbar.action_triggered.connect(self._on_toolbar_action)

        # Brush properties panel (hidden by default)
        self.brush_panel = BrushToolPanel(self)
        self.brush_panel.hide()
        self.brush_panel.close_requested.connect(lambda: (self.brush_panel.hide(), self._reposition()))

        # Grid settings panel (hidden by default)
        self.grid_panel = GridSettingsPanel(self)
        self.grid_panel.hide()

        self.canvas_toolbar.tool_selected.connect(self._on_tool_selected)
        self.canvas_toolbar.action_triggered.connect(self._on_toolbar_action)

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
        # Compass expansão → esconde/mostra minimap
        self.compass.expanded_changed.connect(self._on_compass_toggle)
        # Logs
        self.top_bar.logs_clicked.connect(self._open_logs)

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
            bp_h = min(body_h - toolbar_h - prog_h - 8, 600)
            self.brush_panel.setGeometry(center_x + 4, bp_top, self.brush_panel.PANEL_WIDTH, bp_h)
            self.brush_panel.raise_()

        # Grid panel: abaixo da toolbar, entre painéis laterais
        if self.grid_panel.isVisible():
            gp_h = self.grid_panel.height()
            self.grid_panel.setGeometry(center_x, body_top + toolbar_h, center_w, gp_h)

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
            self.brush_panel.show()
            self.grid_panel.hide()
            self._connect_brush_panel()
            # Load assets for the currently selected tab
            self.brush_panel._on_tab_changed(self.brush_panel._tabs.currentIndex())
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
                    panel.preset_combo.currentTextChanged, panel.asset_selected,
                    panel.mode_changed, panel.tab_changed):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError):
                pass

        panel.size_slider.value_changed.connect(self._on_brush_size_changed)
        panel.opacity_slider.value_changed.connect(self._on_brush_opacity_changed)
        panel.density_slider.value_changed.connect(engine.set_density)
        panel.asset_selected.connect(self._on_brush_asset_selected)
        panel.preset_combo.currentTextChanged.connect(self._on_brush_preset_changed)
        panel.tab_changed.connect(self._on_brush_tab_changed)

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

        if category:
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
            })
        self.brush_panel.set_assets(items)

    def _on_brush_asset_selected(self, asset_id: str):
        """User clicked an asset in the brush panel grid."""
        engine = self.canvas.engine.brush_engine
        engine.clear_assets()
        engine.add_asset(asset_id)
        self.canvas.engine._brush_tool.set_active_asset(asset_id)
        if self.canvas.engine._asset_engine:
            pixmap = self.canvas.engine._asset_engine.get_pixmap(asset_id)
            self.brush_panel.set_texture_preview(pixmap)

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
        actions = {
            "Grid": self._toggle_grid_panel,
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
        self.grid_panel.setVisible(visible)
        if visible:
            self._connect_grid_panel()
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
            grid.color_major = QColor(255, 255, 255, int(v * 60))
            grid.color_minor = QColor(255, 255, 255, int(v * 25))
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
