"""Main layout — mapa fullscreen com painéis glass flutuando por cima."""

import warnings
warnings.filterwarnings("ignore", message=".*Failed to disconnect.*", category=RuntimeWarning)

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.top_bar import TopBar
from src.layouts.panels.toolbar import CanvasToolbar
from src.layouts.panels.select_panel import SelectToolPanel
from src.layouts.panels.explorer import ExplorerPanel
from src.layouts.panels.canvas_area import CanvasArea
from src.layouts.panels.background_panel import BackgroundPanel
from src.layouts.panels.inspector import InspectorPanel, LayersPanel
from src.layouts.panels.progression import ProgressionBar
from src.layouts.panels.status_bar import StatusBar
from src.layouts.panels.info_modal import InfoModal
from src.layouts.panels.freehand_badge import FreehandBadge
from src.layouts.panels.logs_panel import QtLogHandler
from src.canvas.overlays import Compass, CompassHUD, MiniMap
from src.canvas.map_boundary import MapBoundary
from src.engines.integrator import EngineIntegrator
from src.layouts.mediators import (
    BrushMediator, TerrainMediator, GridMediator, ToolbarMediator, RegionMediator, SpawnMediator,
    TextMediator, MarkerMediator, LightMediator, AssetEffectsMediator, MenuViewMediator,
    ExplorerSyncMediator,
)
from src.layouts.panel_manager import PanelManager
from src.layouts.panel_layout_engine import PanelLayoutEngine
from src.layouts.floating_coordinator import FloatingCoordinator


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

        # No mediator owns this one (it's a thin 4-line filter checklist,
        # not worth a whole file) — constructed here same as top_bar/
        # canvas_toolbar above.
        self.select_panel = SelectToolPanel(self)
        self.select_panel.hide()
        self.select_panel.close_requested.connect(self._close_select_panel)
        self.select_panel.layers_changed.connect(self.canvas.engine.selection.set_layer_filter)
        self.select_panel.color_changed.connect(self.canvas.engine.transform.set_selection_color)
        self.select_panel.content_changed.connect(self._reposition)

        # One-off "you need to do X first" message, centered over the
        # canvas — not tied to any specific side panel (see info_modal.py).
        self.info_modal = InfoModal(self)
        self.info_modal.hide()

        # Follows the mouse while a "Livre" terreno boundary is being
        # drawn (see TerrainMediator) — positioned by a QTimer poll, not
        # panel_layout_engine's resize-driven apply(), since it needs to
        # track the cursor continuously, not just on layout changes.
        self.freehand_badge = FreehandBadge(self)
        self.freehand_badge.hide()

        # ═══ Mediators ═══
        # Every other panel (Brush/AssetBrowser, Grid, Terrain, Região/
        # RegionEdit, Spawn/SpawnMobSub, Texto/Personalizar, Marcador/
        # MarcadorEdit, Luz/LuzEdit/Céu, AssetEffects) is constructed by its
        # own mediator below — see e.g. LightMediator.__init__ — instead of
        # here, so a panel's construction lives next to the signal wiring
        # that gives it meaning.
        self._brush_med = BrushMediator(self)
        self._terrain_med = TerrainMediator(self)
        self._grid_med = GridMediator(self)
        self._region_med = RegionMediator(self)
        self._spawn_med = SpawnMediator(self)
        self._text_med = TextMediator(self)
        self._marker_med = MarkerMediator(self)
        self._light_med = LightMediator(self)
        self._asset_effects_med = AssetEffectsMediator(self)
        self._toolbar_med = ToolbarMediator(self)
        self._toolbar_med.connect()
        # After _region_med — _show_menu_view's "Mobs" view reads
        # l._region_med.zones_list/zone_thumbnail.
        self._menu_med = MenuViewMediator(self)

        # "Plano de Fundo" — a plain toolbar toggle (see CanvasToolbar's
        # "__view__"-adjacent entry / _on_toolbar_action below) rather than
        # its own mediator, since all it needs is wiring background_changed
        # straight to TerrainMediator.on_background (after _terrain_med
        # exists, above) — no canvas-engine state of its own to own.
        self.background_panel = BackgroundPanel(self)
        self.background_panel.hide()
        self.background_panel.close_requested.connect(self._close_background_panel)
        self.background_panel.background_changed.connect(self._terrain_med.on_background)

        # ═══ Panel Manager ═══
        self._panel_mgr = PanelManager(self)
        self._panel_mgr.register(
            "Brush", self.brush_panel,
            on_show=lambda: self._brush_med.connect_panel(),
            on_hide=self._on_brush_panel_hidden,
        )
        self._panel_mgr.register(
            "Grid", self.grid_panel,
            on_show=lambda: self._grid_med.connect_panel(),
        )
        self._panel_mgr.register(
            "Terrain", self.terrain_panel,
            on_hide=self._on_terrain_panel_hidden,
        )
        self._panel_mgr.register(
            "Background", self.background_panel,
        )
        self._panel_mgr.register(
            "Region", self.region_panel,
            on_hide=self._on_region_panel_hidden,
        )
        self._panel_mgr.register(
            "Spawn", self.spawn_panel,
            on_hide=self._on_spawn_panel_hidden,
        )
        # RegionEdit rides next to Region (not through PanelManager's
        # exclusivity): the CRUD list and the detail/paint panel need to
        # be visible *together*, the opposite of mutual exclusivity.
        self._panel_mgr.register(
            "Select", self.select_panel,
        )
        self._panel_mgr.register(
            "Text", self.text_panel, on_hide=self._text_med._close_color_customize,
        )
        # fill_height=True — same treatment as Brush: PanelManager gives
        # this the full available toolbar-panel height directly instead of
        # computing it from generic _content_height(), which (for this
        # panel specifically) would measure the icon grid's full unscrolled
        # content height regardless of IconPicker's own fixed/expanding
        # sizing, leaving a large empty gap between the hint text and the
        # icon grid that never actually grew to fill it.
        self._panel_mgr.register("Marcador", self.marker_panel, fill_height=True)
        self._panel_mgr.register("MarcadorEdit", self.marker_edit_panel)
        self._panel_mgr.register("Light", self.light_panel)
        self._panel_mgr.register("LightEdit", self.light_edit_panel)
        self._panel_mgr.register("SkyEdit", self.sky_edit_panel)

        # Explorer (esquerda)
        self._left_container = QWidget(self)
        self._left_container.setAttribute(Qt.WA_TranslucentBackground)
        self._left_container.setStyleSheet("background: transparent;")
        left_lay = QVBoxLayout(self._left_container)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left_lay.setSpacing(8)
        self.left_panel = ExplorerPanel()
        left_lay.addWidget(self.left_panel, 1)
        left_lay.addStretch()
        self.left_panel.collapsed_changed.connect(
            lambda collapsed: left_lay.setStretchFactor(self.left_panel, 0 if collapsed else 1)
        )

        # Inspector (direita)
        self._right_scroll = self._make_scroll()
        right_container = QWidget()
        right_container.setStyleSheet("background: transparent;")
        right_lay = QVBoxLayout(right_container)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right_lay.setSpacing(8)
        self.right_panel = InspectorPanel()
        self.layers_panel = LayersPanel()
        self.layers_panel.set_scene(self.canvas.engine.viewport.scene())
        right_lay.addWidget(self.right_panel, 1)
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
        self.compass.attach_viewport(self.canvas.engine.viewport)
        self.compass_hud = CompassHUD(self)
        self.minimap = MiniMap(self)
        self.minimap.set_viewport(self.canvas.engine.viewport)
        self.canvas.engine._brush_tool.set_minimap(self.minimap)
        self.canvas.engine._region_brush_tool.set_minimap(self.minimap)
        self.canvas.engine._river_path_tool.set_minimap(self.minimap)
        self.canvas.engine._road_path_tool.set_minimap(self.minimap)

        # ═══ Floating Coordinator ═══
        # Shared obstacle-avoidance registry for every panel that can move or
        # be shown/hidden independently — see floating_coordinator.py. Any
        # future flyout/sub-panel (e.g. something a toolbar button opens)
        # registers here too instead of hand-rolling its own obstacle list.
        self.floating = FloatingCoordinator(self)
        self.floating.register("toolbar", self.canvas_toolbar, movable=True)
        self.floating.register("minimap", self.minimap, movable=True)
        self.floating.register("compass", self.compass, movable=True)
        self.floating.register("compass_hud", self.compass_hud, movable=False)
        self.floating.register("top_bar", self.top_bar)
        self.floating.register("explorer", self._left_container)
        self.floating.register("inspector", self._right_scroll)
        self.floating.register("progression", self.progression)
        self.floating.register("status_bar", self.status_bar)
        self.floating.register("brush_panel", self.brush_panel)
        self.floating.register("grid_panel", self.grid_panel)
        self.floating.register("terrain_panel", self.terrain_panel)
        self.floating.register("background_panel", self.background_panel)
        self.floating.register("region_panel", self.region_panel)
        self.floating.register("select_panel", self.select_panel)
        self.floating.register("text_panel", self.text_panel)
        self.minimap.moved.connect(lambda: self.floating.push_clear("minimap"))
        self.compass.moved.connect(lambda: self.floating.push_clear("compass"))

        # ═══ Panel Layout Engine ═══
        # Everything about WHERE panels/overlays sit once the window size
        # (or which panels are visible) changes — see panel_layout_engine.py.
        self._panel_layout = PanelLayoutEngine(self)
        # compass_hud is anchored relative to the compass. position_changed
        # fires on every real move — including each step of a move-drag, not
        # just once it ends — so the HUD chip tracks the drag live instead of
        # jumping to its new spot only after release (moved, above, still
        # fires once at drag-end for push_clear's obstacle-nudge, which in
        # turn moves the compass again and re-emits position_changed, so the
        # HUD re-anchors off its actual final position either way).
        self.compass.position_changed.connect(self._panel_layout.reposition_compass_hud)

        # ═══ Conexões ═══
        self.canvas.engine.cursor_moved.connect(
            # Scene Y grows downward (Qt convention); displayed Y is flipped
            # so it grows upward like a map's north, matching the grid ruler.
            lambda x, y: self.status_bar.coords.setText(f"X: {x:.0f}  Y: {-y:.0f}")
        )
        self.canvas.engine.viewport.fps_updated.connect(self.status_bar.update_fps)
        self.canvas.engine.zoom_changed.connect(self._on_zoom)
        self.canvas.engine.tool_changed.connect(
            lambda t: self.status_bar.tool_label.setText(f"🔧 {t}")
        )
        self.canvas.engine.tool_changed.connect(self.canvas_toolbar.sync_active)
        self.status_bar.zoom_in_clicked.connect(self.canvas.engine.zoom_in)
        self.status_bar.zoom_out_clicked.connect(self.canvas.engine.zoom_out)
        self.minimap.zoom_changed.connect(self._on_zoom_slider)
        self.canvas.engine.grid_toggled.connect(self._on_grid_toggled)
        self.compass.expanded_changed.connect(self._on_compass_toggle)
        self.canvas.engine.viewport.view_changed.connect(self._refresh_compass_hud)
        from src.engines.map.navigation import get_navigation_library
        get_navigation_library().changed.connect(self._refresh_compass_hud)
        self._refresh_compass_hud()  # reflect the active preset's "Info" checkbox right away, not just after a later toggle

        # ═══ Engine Integrator ═══
        self.engines = EngineIntegrator(self)
        self.engines.connect_ui(self)

        # Explorer panel auto-sync — only reads other mediators' public
        # state (terrain layers, regiões, spawned/placed items), so it's
        # constructed last, after everything it reads from already exists.
        self._explorer_sync_med = ExplorerSyncMediator(self)

    def _make_scroll(self) -> QScrollArea:
        s = QScrollArea(self)
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self._panel_layout.apply(self.width(), self.height())

    # ─── Zoom ───

    def _on_zoom(self, percent: int):
        self.status_bar.zoom_label.setText(f"{percent}%")
        self.canvas_toolbar.zoom_label.setText(f"{percent}%")
        self.minimap.set_zoom(percent)

    def _on_zoom_slider(self, percent: int):
        self.canvas.engine.viewport.set_zoom(percent / 100.0)

    # ─── Tool Selection ───

    def _on_brush_panel_hidden(self):
        """Fires whenever the Brush panel is hidden for ANY reason — explicit
        toggle, switching to another tool, or PanelManager's exclusivity
        closing it to open Grid/Terrain. The adjacent asset browser has
        nothing to ride next to once that happens, same reasoning as
        _on_region_panel_hidden below."""
        self.brush_panel.show_section("params")
        self.asset_browser_panel.hide()
        self._reposition()

    def _toggle_asset_browser(self):
        if self.asset_browser_panel.isVisible():
            self.asset_browser_panel.hide()
        else:
            self.asset_browser_panel.show()
            self.asset_browser_panel.raise_()
        self._reposition()

    def _on_terrain_panel_hidden(self):
        """Same reasoning as _on_region_panel_hidden — the edit sub painel
        has no CRUD list to ride next to (or card to add to) once Terrain
        itself is closed, by PanelManager's exclusivity or otherwise."""
        self._terrain_med.on_close_edit()
        self._reposition()

    def _on_region_panel_hidden(self):
        """Same reasoning as _on_brush_panel_hidden — the edit panel has
        nothing to anchor next to (and no CRUD list to add its card to)
        once Region itself is closed, by PanelManager's exclusivity or
        otherwise. Always disarms RegionBrushTool (not just when the edit
        sub-panel was open) — a card can be armed via a plain click
        (on_card_clicked) without ever opening that sub-panel, and leaving
        it armed after the whole Região panel closes left the brush
        cursor/preview on the canvas (and painting still live) with no
        panel or toolbar button left showing it."""
        self._region_med.on_close_edit()
        self._reposition()

    def _on_spawn_panel_hidden(self):
        """Same reasoning as _on_brush_panel_hidden — the mob sub-panel has
        no categories list to ride next to once Spawn itself is closed."""
        self.spawn_mob_sub_panel.hide()
        self._reposition()

    def _close_spawn_panel(self):
        self._panel_mgr.hide("Spawn")
        self._reposition()

    def _toggle_spawn_mob_sub_panel(self):
        self.spawn_mob_sub_panel.hide()
        self._reposition()

    def _on_tool_selected(self, tool_name: str):
        # Same "independent menus, not simultaneous" rule as
        # _toggle_panel_exclusive: switching to a different tool clears
        # whatever's selected on canvas (stale Select-tool border/highlight
        # otherwise lingers on top of Brush/Spawn/etc.) — except when a
        # marker or text item is selected, since Marcador/Texto's own edit
        # panels are designed to stay open across tool switches (see the
        # _selected_marker()/_text_selected_items() checks below).
        if tool_name != "Selecionar" and not self._marker_med._selected_marker() \
                and not self._text_med._text_selected_items():
            self.canvas.engine.selection.clear()

        if tool_name == "Brush":
            self._panel_mgr.show("Brush")
            self._brush_med.reset_panel_mode()
        else:
            self._panel_mgr.hide("Brush")
            self.asset_browser_panel.hide()
        if tool_name == "Selecionar":
            self._panel_mgr.show("Select")
        else:
            self._panel_mgr.hide("Select")
        if tool_name == "Texto":
            self._panel_mgr.show("Text")
            self._text_med._arm_draft()
        elif not self._text_med._text_selected_items():
            self._panel_mgr.hide("Text")
            self._text_med._close_color_customize()
            self._text_med._pending_text = None
        if tool_name == "Spawn":
            self._panel_mgr.show("Spawn")
        else:
            self._panel_mgr.hide("Spawn")
            self.spawn_mob_sub_panel.hide()
        if tool_name == "Marcador":
            self._panel_mgr.show("Marcador")
        elif not self._marker_med._selected_marker():
            self._panel_mgr.hide("Marcador")
        self._reposition()

    def _close_select_panel(self):
        self._panel_mgr.hide("Select")
        self._reposition()

    def _close_marker_panel(self):
        self._panel_mgr.hide("Marcador")
        self._reposition()

    def _close_marker_edit_panel(self):
        self._panel_mgr.hide("MarcadorEdit")
        self.canvas.engine.selection.clear()
        self._reposition()

    def _close_brush_panels(self):
        self._panel_mgr.hide("Brush")
        self._reposition()

    # ─── Toolbar Actions ───

    def _on_toolbar_action(self, name: str):
        actions = {
            "Grid": self._toggle_grid_panel,
            "Terreno": self._toggle_terrain_panel,
            "Região": self._toggle_region_panel,
            "Iluminação": self._toggle_light_panel,
            "Plano de Fundo": self._toggle_background_panel,
            "Undo": self.canvas.engine.history.undo,
            "Redo": self.canvas.engine.history.redo,
        }
        action = actions.get(name)
        if action:
            action()

    def _toggle_panel_exclusive(self, name: str):
        """Toggle a toolbar-action panel (Grid/Terrain/Region/Light) that
        isn't a canvas tool of its own — these run independently from the
        Select tool, so opening one clears whatever's currently selected on
        canvas instead of leaving its stale selection border/highlight
        floating on top (they're independent menus, not meant to work
        simultaneously)."""
        self._panel_mgr.toggle(name)
        if self._panel_mgr.is_visible(name):
            self.canvas.engine.selection.clear()
        self._reposition()

    # ─── Grid Panel ───

    def _toggle_grid_panel(self):
        self._toggle_panel_exclusive("Grid")

    def _close_grid_panel(self):
        self._panel_mgr.hide("Grid")
        self._reposition()

    def _on_grid_toggled(self, visible: bool):
        # Fired by the 'G' shortcut — grid visibility itself is controlled by the
        # panel's shape dropdown ("Nenhum" = off), not by opening/closing the panel.
        if self._panel_mgr.is_visible("Grid"):
            self._grid_med.sync_shape_combo()

    # ─── Terrain Panel ───

    def _toggle_terrain_panel(self):
        self._toggle_panel_exclusive("Terrain")

    def _close_terrain_panel(self):
        self._panel_mgr.hide("Terrain")
        self.canvas_toolbar.uncheck_action("Terreno")
        self._reposition()

    # ─── Plano de Fundo Panel ───

    def _toggle_background_panel(self):
        self._toggle_panel_exclusive("Background")

    def _close_background_panel(self):
        self._panel_mgr.hide("Background")
        self.canvas_toolbar.uncheck_action("Plano de Fundo")
        self._reposition()

    # ─── Região Panel ───

    def _toggle_region_panel(self):
        self._toggle_panel_exclusive("Region")

    def _close_region_panel(self):
        self._panel_mgr.hide("Region")
        self._reposition()

    # ─── Iluminação Panel ───

    def _toggle_light_panel(self):
        self._toggle_panel_exclusive("Light")

    def _close_light_panel(self):
        self._panel_mgr.hide("Light")
        self.canvas_toolbar.uncheck_action("Iluminação")
        self._reposition()

    def _close_light_edit_panel(self):
        self._panel_mgr.hide("LightEdit")
        self.canvas.engine.selection.clear()
        self._reposition()

    def _close_sky_edit_panel(self):
        self._panel_mgr.hide("SkyEdit")
        self._reposition()

    # ─── Asset Effects Panel ───

    def _close_asset_effects_panel(self):
        self.asset_effects_panel.hide()

    # ─── View Dropdown (show/hide UI chrome) ───

    def _on_view_toggled(self, key: str, visible: bool):
        widget = {
            "top_bar": self.top_bar,
            "explorer": self._left_container,
            "inspector": self._right_scroll,
            "progression": self.progression,
            "status_bar": self.status_bar,
            "minimap": self.minimap,
            "compass": self.compass,
        }.get(key)
        if widget:
            widget.setVisible(visible)
            if visible:
                # Any movable panel could be parked where this one just
                # reappeared — not just the toolbar.
                self._toolbar_med.resolve_collision()
                self.floating.push_clear("minimap")

    # ─── Compass ───

    def _on_compass_toggle(self, expanded: bool):
        self._reposition()
        if expanded and self.compass.geometry().intersects(self.minimap.geometry()):
            self.minimap.hide()
        else:
            self.minimap.show()
        # The HUD's own visibility no longer depends on expanded/collapsed
        # (see _refresh_compass_hud) — this call just repositions it under
        # the compass's new size/geometry.
        self._refresh_compass_hud()
        self._reposition()

    def _hud_allowed(self) -> bool:
        """Whether the active navigation preset (if any) wants its HUD chip
        shown — the "ℹ Info" checkbox next to "+ Camada" in Config →
        Navegação. No active preset (fallback painted compass) always
        allows it, same as before that checkbox existed."""
        from src.engines.map.navigation import get_navigation_library
        preset = get_navigation_library().get_active_preset()
        return preset.show_info if preset else True

    def _refresh_compass_hud(self):
        allowed = self._hud_allowed()
        self.compass_hud.setVisible(allowed)
        if not allowed:
            return
        viewport = self.canvas.engine.viewport
        center = viewport.mapToScene(viewport.viewport().rect().center())
        terrain_id = self.brush_panel.active_terrain_id()
        # Busca o terreno diretamente do mediator para garantir nome correto
        # mesmo que brush_panel._terrain_names ainda não tenha sido populado.
        terr = self._terrain_med._terrains.get(terrain_id) if terrain_id else None
        terrain_name = terr.name if terr else ("Mapa Infinito" if not terrain_id else "")
        boundary = self._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        map_w = float(boundary.width) if boundary else 0.0
        map_h = float(boundary.height) if boundary else 0.0
        self.compass_hud.update_info(
            terrain_name,
            map_w, map_h,
            center.x(), center.y(),
        )

