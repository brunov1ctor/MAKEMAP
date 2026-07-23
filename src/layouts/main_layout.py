"""Main layout — mapa fullscreen com painéis glass flutuando por cima."""

import warnings
warnings.filterwarnings("ignore", message=".*Failed to disconnect.*", category=RuntimeWarning)

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QSizePolicy, QLabel
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QColor, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.top_bar import TopBar
from src.layouts.panels.toolbar import CanvasToolbar
from src.layouts.panels.brush.panel import BrushToolPanel
from src.layouts.panels.brush.asset_browser import AssetBrowserPanel
from src.layouts.panels.grid_panel import GridSettingsPanel
from src.layouts.panels.terrain.panel import TerrainSettingsPanel
from src.layouts.panels.region.panel import RegionSettingsPanel
from src.layouts.panels.region.region_edit_panel import RegionEditPanel
from src.layouts.panels.select_panel import SelectToolPanel
from src.layouts.panels.text_panel import TextToolPanel, radius_from_percent
from src.layouts.panels.color_customize_panel import ColorCustomizePanel
from src.layouts.panels.explorer import ExplorerPanel, FilterPanel
from src.layouts.panels.canvas_area import CanvasArea
from src.layouts.panels.inspector import InspectorPanel, QuestPanel, LayersPanel
from src.layouts.panels.progression import ProgressionBar
from src.layouts.panels.status_bar import StatusBar
from src.layouts.panels.logs_panel import QtLogHandler, open_logs_dialog
from src.canvas.overlays import Compass, CompassHUD, MiniMap
from src.canvas.map_boundary import MapBoundary
from src.engines.integrator import EngineIntegrator
from src.layouts.mediators import BrushMediator, TerrainMediator, GridMediator, ToolbarMediator, RegionMediator
from src.layouts.panel_manager import PanelManager
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

        self.brush_panel = BrushToolPanel(self)
        self.brush_panel.hide()
        self.brush_panel.close_requested.connect(self._close_brush_panels)
        self.brush_panel.assets_requested.connect(self._toggle_asset_browser)

        self.select_panel = SelectToolPanel(self)
        self.select_panel.hide()
        self.select_panel.close_requested.connect(self._close_select_panel)
        self.select_panel.layers_changed.connect(self.canvas.engine.selection.set_layer_filter)

        self.text_panel = TextToolPanel(self)
        self.text_panel.hide()
        self.text_panel.close_requested.connect(self._close_text_panel)
        self.text_panel.content_changed.connect(self._reposition)
        self.text_panel.font_family_changed.connect(self._on_text_family)
        self.text_panel.font_weight_changed.connect(self._on_text_weight)
        self.text_panel.font_size_changed.connect(self._on_text_font_size)
        self.text_panel.bold_changed.connect(self._on_text_bold)
        self.text_panel.italic_changed.connect(self._on_text_italic)
        self.text_panel.color_changed.connect(self._on_text_color)
        self.text_panel.align_changed.connect(self._on_text_align)
        self.text_panel.line_height_changed.connect(self._on_text_line_height)
        self.text_panel.letter_spacing_changed.connect(self._on_text_letter_spacing)
        self.text_panel.shadow_toggled.connect(self._on_text_shadow_toggled)
        self.text_panel.shadow_color_changed.connect(self._on_text_shadow_color)
        self.text_panel.shadow_opacity_changed.connect(self._on_text_shadow_opacity)
        self.text_panel.shadow_x_changed.connect(self._on_text_shadow_x)
        self.text_panel.shadow_y_changed.connect(self._on_text_shadow_y)
        self.text_panel.shadow_blur_changed.connect(self._on_text_shadow_blur)
        self.text_panel.outline_toggled.connect(self._on_text_outline_toggled)
        self.text_panel.outline_color_changed.connect(self._on_text_outline_color)
        self.text_panel.outline_width_changed.connect(self._on_text_outline_width)
        self.text_panel.glow_toggled.connect(self._on_text_glow_toggled)
        self.text_panel.glow_color_changed.connect(self._on_text_glow_color)
        self.text_panel.glow_blur_changed.connect(self._on_text_glow_blur)
        self.text_panel.curvature_changed.connect(self._on_text_curvature)
        self.text_panel.opacity_changed.connect(self._on_text_opacity)
        self.text_panel.strikethrough_toggled.connect(self._on_text_strikethrough)
        self.text_panel.overline_toggled.connect(self._on_text_overline)
        self.text_panel.underline_toggled.connect(self._on_text_underline)
        self.text_panel.double_underline_toggled.connect(self._on_text_double_underline)
        self.text_panel.box_toggled.connect(self._on_text_box)
        self.text_panel.cloud_toggled.connect(self._on_text_cloud)
        self.text_panel.serif_toggled.connect(self._on_text_serif)

        # Single shared "Personalizar" picker sub-panel, reused for whichever
        # ColorField (text color, shadow, outline, glow) opens it — same
        # single-instance-reused pattern as RegionEditPanel across zone cards.
        # Rides beside text_panel like RegionEditPanel does beside
        # RegionSettingsPanel — positioned manually in resizeEvent, not
        # through PanelManager's single-slot layout.
        self.color_customize_panel = ColorCustomizePanel(self)
        self.color_customize_panel.hide()
        self._active_color_field = None
        self._active_pattern_key = None
        self.color_customize_panel.close_requested.connect(self._close_color_customize)
        self.color_customize_panel.pattern_changed.connect(self._on_color_customize_pattern_changed)
        self.text_panel.color_field.customize_requested.connect(
            lambda: self._open_color_customize("text", self.text_panel.color_field)
        )
        self.text_panel.shadow_color.customize_requested.connect(
            lambda: self._open_color_customize("shadow", self.text_panel.shadow_color)
        )
        self.text_panel.outline_color.customize_requested.connect(
            lambda: self._open_color_customize("outline", self.text_panel.outline_color)
        )
        self.text_panel.glow_color.customize_requested.connect(
            lambda: self._open_color_customize("glow", self.text_panel.glow_color)
        )

        self.canvas.engine.selection.selection_changed.connect(self._on_selection_for_text_panel)

        # Asset browser (category tabs + search + grid), positioned right
        # next to Brush. Opens only via the texture preview click — NOT
        # automatically with the Brush tool, since most brush tweaks don't
        # need it open. Closing Brush closes it too. Kept out of
        # PanelManager's exclusivity model on purpose: Brush+AssetBrowser can
        # be visible *simultaneously*, the opposite of what "exclusive" means
        # there (only Grid/Terrain/Brush stay mutually exclusive with
        # each other).
        self.asset_browser_panel = AssetBrowserPanel(self)
        self.asset_browser_panel.hide()
        self.asset_browser_panel.close_requested.connect(self._close_brush_panels)

        self.grid_panel = GridSettingsPanel(self)
        self.grid_panel.hide()
        self.grid_panel.close_requested.connect(self._close_grid_panel)

        self.terrain_panel = TerrainSettingsPanel(self)
        self.terrain_panel.hide()
        self.terrain_panel.close_requested.connect(self._close_terrain_panel)

        self.region_panel = RegionSettingsPanel(self)
        self.region_panel.hide()
        self.region_panel.close_requested.connect(self._close_region_panel)

        self.region_edit_panel = RegionEditPanel(self)
        self.region_edit_panel.hide()
        self.region_edit_panel.content_changed.connect(self._reposition)

        # ═══ Mediators ═══
        self._brush_med = BrushMediator(self)
        self._terrain_med = TerrainMediator(self)
        self._grid_med = GridMediator(self)
        self._region_med = RegionMediator(self)
        self._toolbar_med = ToolbarMediator(self)
        self._toolbar_med.connect()

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
        )
        self._panel_mgr.register(
            "Region", self.region_panel,
            on_hide=self._on_region_panel_hidden,
        )
        # RegionEdit rides next to Region (not through PanelManager's
        # exclusivity — same reasoning as AssetBrowserPanel next to Brush):
        # the CRUD list and the detail/paint panel need to be visible
        # *together*, the opposite of mutual exclusivity.
        self._panel_mgr.register(
            "Select", self.select_panel,
        )
        self._panel_mgr.register(
            "Text", self.text_panel, on_hide=self._close_color_customize,
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
        # Deferred — same reasoning as Região's card list: a freshly
        # inserted TerrainCard's sizeHint() isn't settled synchronously.
        self.terrain_panel.content_changed.connect(lambda: QTimer.singleShot(0, self._reposition))

        # Map boundary overlays reference
        self._terrain_boundaries = self._terrain_med.boundaries

        # Região panel signals → mediator
        self.region_panel.region_add_requested.connect(self._region_med.on_add_requested)
        self.region_panel.region_renamed.connect(self._region_med.on_renamed)
        self.region_panel.region_removed.connect(self._region_med.on_removed)
        self.region_panel.region_selected.connect(self._region_med.on_card_clicked)
        self.region_panel.region_edit_requested.connect(self._region_med.on_selected)
        self.region_panel.region_locate_requested.connect(self._region_med.on_locate)
        self.region_panel.region_visibility_toggled.connect(self._region_med.on_card_visibility_toggled)
        self.region_panel.region_paint_cleared.connect(self._region_med.on_paint_cleared)
        # Deferred (not a direct connect like Terrain's content_changed):
        # this one fires right after a brand-new RegionCard is inserted
        # into the list layout, and a freshly-constructed child widget's
        # sizeHint() isn't reliably settled until Qt's run an event-loop
        # tick — reading it synchronously here would undercount and leave
        # the panel too short to show the just-added card.
        self.region_panel.content_changed.connect(lambda: QTimer.singleShot(0, self._reposition))

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
        left_lay.addStretch()
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
        self.compass.attach_viewport(self.canvas.engine.viewport)
        self.compass_hud = CompassHUD(self)
        self.minimap = MiniMap(self)
        self.minimap.set_viewport(self.canvas.engine.viewport)
        self.canvas.engine._brush_tool.set_minimap(self.minimap)

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
        self.floating.register("asset_browser_panel", self.asset_browser_panel)
        self.floating.register("grid_panel", self.grid_panel)
        self.floating.register("terrain_panel", self.terrain_panel)
        self.floating.register("region_panel", self.region_panel)
        self.floating.register("select_panel", self.select_panel)
        self.floating.register("text_panel", self.text_panel)
        self.minimap.moved.connect(lambda: self.floating.push_clear("minimap"))
        self.compass.moved.connect(lambda: self.floating.push_clear("compass"))
        # compass_hud is anchored relative to the compass. position_changed
        # fires on every real move — including each step of a move-drag, not
        # just once it ends — so the HUD chip tracks the drag live instead of
        # jumping to its new spot only after release (moved, above, still
        # fires once at drag-end for push_clear's obstacle-nudge, which in
        # turn moves the compass again and re-emits position_changed, so the
        # HUD re-anchors off its actual final position either way).
        self.compass.position_changed.connect(self._reposition_compass_hud)

        # ═══ Conexões ═══
        self.canvas.engine.cursor_moved.connect(
            # Scene Y grows downward (Qt convention); displayed Y is flipped
            # so it grows upward like a map's north, matching the grid ruler.
            lambda x, y: self.status_bar.coords.setText(f"X: {x:.0f}  Y: {-y:.0f}")
        )
        self.canvas.engine.zoom_changed.connect(self._on_zoom)
        self.canvas.engine.tool_changed.connect(
            lambda t: self.status_bar.tool_label.setText(f"🔧 {t}")
        )
        self.canvas.engine.tool_changed.connect(self.canvas_toolbar.sync_active)
        self.canvas.engine.text_committed.connect(self._close_text_panel)
        self.status_bar.zoom_in_clicked.connect(self.canvas.engine.zoom_in)
        self.status_bar.zoom_out_clicked.connect(self.canvas.engine.zoom_out)
        self.minimap.zoom_changed.connect(self._on_zoom_slider)
        self.canvas.engine.grid_toggled.connect(self._on_grid_toggled)
        self.compass.expanded_changed.connect(self._on_compass_toggle)
        self.canvas.engine.viewport.view_changed.connect(self._refresh_compass_hud)
        self.terrain_panel.terrain_selected.connect(lambda _id: self._refresh_compass_hud())
        self.terrain_panel.terrain_renamed.connect(lambda _id, _name: self._refresh_compass_hud())
        from src.engines.map.navigation import get_navigation_library
        get_navigation_library().changed.connect(self._refresh_compass_hud)
        self._refresh_compass_hud()  # reflect the active preset's "Info" checkbox right away, not just after a later toggle
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

    def _reposition_compass_hud(self):
        """Anchors compass_hud to the compass's current spot — split out so
        Compass.position_changed (fired on every move, mid-drag included)
        can call just this instead of the full _reposition/resizeEvent, and
        the HUD tracks the drag live instead of jumping once it ends."""
        self.compass_hud.move(
            self.compass.x() + self.compass.width() - self.compass_hud.width(),
            self.compass.y() + self.compass.height() + 6,
        )
        self.compass_hud.raise_()

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
        self._toolbar_med.layout(w, h, center_x, center_w, body_top, body_h)

        # Brush/Grid/Terrain panels normally sit right below the toolbar's
        # default top-docked slot — but the toolbar is now draggable, so
        # carve the panel area around wherever it actually is instead of
        # assuming that fixed slot.
        avail = QRect(center_x + 4, body_top + 4, max(0, center_w - 8), max(0, body_h - prog_h - 8))
        avail = self._toolbar_med.carve_panel_area(avail)
        self._panel_mgr.layout(avail.x(), avail.y(), avail.width(), avail.height())

        # Região's CRUD list has a pinned header + "Nova Região" button
        # living OUTSIDE its card-list scroll area, so PanelManager's
        # generic _content_height() (which only measures the first
        # QScrollArea it finds) undercounts it — override with the panel's
        # own content_height(), which accounts for both.
        if self.region_panel.isVisible():
            rp = self.region_panel.geometry()
            rp_h = min(self.region_panel.content_height(), avail.height())
            self.region_panel.setGeometry(rp.x(), rp.y(), rp.width(), rp_h)

        # Terrain nests several QScrollAreas (whole-panel, terrain-card
        # list, background image browser) — same ambiguity as Região's
        # generic sizing, same override via its own content_height().
        if self.terrain_panel.isVisible():
            tp = self.terrain_panel.geometry()
            tp_h = min(self.terrain_panel.content_height(), avail.height())
            self.terrain_panel.setGeometry(tp.x(), tp.y(), tp.width(), tp_h)

        # Personalizar rides next to Texto (not through PanelManager — see
        # where it's created), sized to its own content.
        if self.text_panel.isVisible() and self.color_customize_panel.isVisible():
            tp_rect = self.text_panel.geometry()
            cc_x = tp_rect.right() + 8
            cc_w = min(self.color_customize_panel.PANEL_WIDTH, max(0, avail.right() - cc_x))
            cc_h = min(PanelManager._content_height(self.color_customize_panel), avail.height())
            self.color_customize_panel.setGeometry(cc_x, tp_rect.y(), cc_w, cc_h)
            self.color_customize_panel.raise_()

        # Asset browser rides next to Brush (not through PanelManager — see
        # the comment where it's created) whenever both are visible.
        if self.brush_panel.isVisible() and self.asset_browser_panel.isVisible():
            bp_rect = self.brush_panel.geometry()
            ab_x = bp_rect.right() + 8
            ab_w = min(self.asset_browser_panel.PANEL_WIDTH, max(0, avail.right() - ab_x))
            self.asset_browser_panel.setGeometry(ab_x, bp_rect.y(), ab_w, bp_rect.height())
            self.asset_browser_panel.raise_()

        # Região's edit panel rides next to the CRUD list the same way —
        # but sized to its OWN content (collapsible sections growing/
        # shrinking), same smart-height behavior Terrain's BackgroundSection
        # gets via PanelManager._content_height, not just copying Region's
        # height verbatim (which ignored its collapsed/expanded sections).
        if self.region_panel.isVisible() and self.region_edit_panel.isVisible():
            rp_rect = self.region_panel.geometry()
            re_x = rp_rect.right() + 8
            re_w = min(self.region_edit_panel.PANEL_WIDTH, max(0, avail.right() - re_x))
            # Capped to the available work area, NOT to Region's own height —
            # the two panels size independently to their own content now, so
            # one being shorter must never squash the other.
            max_h = max(0, avail.bottom() - rp_rect.y())
            re_h = min(PanelManager._content_height(self.region_edit_panel), max_h)
            self.region_edit_panel.setGeometry(re_x, rp_rect.y(), re_w, re_h)
            self.region_edit_panel.raise_()

        self.progression.setGeometry(center_x, body_bottom - prog_h, center_w, prog_h)
        self.status_bar.setGeometry(0, h - status_h, w, status_h)

        ov_top = body_top + toolbar_h
        ov_h = max(0, body_h - toolbar_h - prog_h)

        if self.compass.has_custom_position():
            # User dragged it via its own grip — keep their spot, just
            # clamp to stay reachable on resize (same pattern as minimap).
            cx = min(max(self.compass.x(), center_x), max(center_x, center_x + center_w - self.compass.width()))
            cy = min(max(self.compass.y(), ov_top), max(ov_top, ov_top + ov_h - self.compass.height()))
            self.compass.move(cx, cy)
        else:
            self.compass.move(center_x + center_w - self.compass.width() - 16, ov_top + 8)
        if self.minimap.has_custom_position():
            # User dragged it — keep their spot, just clamp to stay reachable on resize.
            mx = min(max(self.minimap.x(), center_x), max(center_x, center_x + center_w - self.minimap.width()))
            my = min(max(self.minimap.y(), ov_top), max(ov_top, ov_top + ov_h - self.minimap.height()))
            self.minimap.move(mx, my)
        else:
            self.minimap.move(
                center_x + center_w - self.minimap.width() - 16,
                ov_top + ov_h - self.minimap.height() - 8,
            )
        self.minimap.raise_()
        self.compass.raise_()
        # Raised last — compass_hud is a readout attached to the compass and
        # must stay legible even where its card overlaps the minimap (e.g. on
        # a short/narrow window), not get painted over by whichever of those
        # two happened to be raised most recently.
        self._reposition_compass_hud()
        # Both compass and compass_hud just landed at their default anchor
        # (top-right of the canvas), which on a short/narrow window can
        # collide with the minimap's own default anchor (bottom-right) —
        # nudge minimap clear of them here too, not just on the reactive
        # drag/visibility-toggle paths above, so this isn't left to whichever
        # of those happens to fire next.
        if not self.minimap.has_custom_position():
            self.floating.push_clear("minimap")

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

    def _on_brush_panel_hidden(self):
        """Fires whenever the Brush panel is hidden for ANY reason — explicit
        toggle, switching to another tool, or PanelManager's exclusivity
        closing it to open Grid/Terrain — so its sub-panel (Assets) never
        stays orphaned on screen with nothing to anchor next to."""
        self.asset_browser_panel.hide()
        self._reposition()

    def _on_region_panel_hidden(self):
        """Same reasoning as _on_brush_panel_hidden — the edit panel has
        nothing to anchor next to (and no CRUD list to add its card to)
        once Region itself is closed, by PanelManager's exclusivity or
        otherwise."""
        if self.region_edit_panel.isVisible():
            self._region_med.on_close_edit()
        self._reposition()

    def _on_tool_selected(self, tool_name: str):
        if tool_name == "Brush":
            self._panel_mgr.show("Brush")
        else:
            self._panel_mgr.hide("Brush")
            self.asset_browser_panel.hide()
        if tool_name == "Selecionar":
            self._panel_mgr.show("Select")
        else:
            self._panel_mgr.hide("Select")
        if tool_name == "Texto":
            self._panel_mgr.show("Text")
        elif not self._text_selected_items():
            self._panel_mgr.hide("Text")
            self._close_color_customize()
        self._reposition()

    def _close_select_panel(self):
        self._panel_mgr.hide("Select")
        self._reposition()

    # ─── Text Panel ───

    def _text_selected_items(self) -> list:
        from src.canvas.text_item import TextItem
        return [it for it in self.canvas.engine.selection.selected_items if isinstance(it, TextItem)]

    def _on_selection_for_text_panel(self, _ids):
        items = self._text_selected_items()
        if items:
            it = items[0]
            self.text_panel.set_values(it.props)
            self._panel_mgr.show("Text")
        elif self.canvas.engine.tool_manager.active_name != "Texto":
            self._panel_mgr.hide("Text")
            self._close_color_customize()
        self._reposition()

    def _close_text_panel(self):
        self._panel_mgr.hide("Text")
        self._close_color_customize()
        self._reposition()

    # ─── "Personalizar" paint picker ───

    @staticmethod
    def _pattern_target(props, key: str):
        """(object, base-color-attr) pair for a Personalizar key — obj.pattern
        is the PaintGrid, getattr(obj, attr) is the plain fallback hex."""
        return {
            "text": (props, "color"),
            "shadow": (props.shadow, "color"),
            "outline": (props.outline, "color"),
            "glow": (props.glow, "color"),
        }[key]

    def _open_color_customize(self, key: str, field):
        self._active_color_field = field
        self._active_pattern_key = key
        cells = None
        items = self._text_selected_items()
        if items:
            obj, attr = self._pattern_target(items[0].props, key)
            obj.pattern.ensure(getattr(obj, attr))
            cells = obj.pattern.cells
        self.color_customize_panel.load_pattern(cells, field.color())
        self.color_customize_panel.show()
        self._reposition()

    def _on_color_customize_pattern_changed(self, cells: list):
        if not self._active_pattern_key:
            return
        dominant = cells[0] if cells else self._active_color_field.color()
        for it in self._text_selected_items():
            obj, attr = self._pattern_target(it.props, self._active_pattern_key)
            obj.pattern.cells = list(cells)
            setattr(obj, attr, dominant)
            it.prepareGeometryChange()
            it.update()
        self._active_color_field.set_color(dominant)

    def _close_color_customize(self):
        self.color_customize_panel.hide()
        self._active_color_field = None
        self._active_pattern_key = None
        self._reposition()

    def _on_text_family(self, family: str):
        for it in self._text_selected_items():
            it.props.font_family = family
            it.prepareGeometryChange()
            it.update()

    def _on_text_weight(self, weight: int):
        for it in self._text_selected_items():
            it.props.font_weight = weight
            it.prepareGeometryChange()
            it.update()

    def _on_text_font_size(self, value: float):
        for it in self._text_selected_items():
            it.props.font_size = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_bold(self, checked: bool):
        for it in self._text_selected_items():
            it.props.font_weight = 700 if checked else 400
            it.prepareGeometryChange()
            it.update()

    def _on_text_italic(self, checked: bool):
        for it in self._text_selected_items():
            it.props.italic = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_color(self, color: str):
        for it in self._text_selected_items():
            it.props.color = color
            it.props.pattern.fill(color)
            it.update()

    def _on_text_align(self, align):
        for it in self._text_selected_items():
            it.props.align = align
            it.update()

    def _on_text_line_height(self, value: float):
        for it in self._text_selected_items():
            it.props.spacing.line_height = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_letter_spacing(self, value: float):
        for it in self._text_selected_items():
            it.props.spacing.letter_spacing = value
            it.prepareGeometryChange()
            it.update()

    # ─── Estilo Panel ───

    def _on_text_shadow_toggled(self, checked: bool):
        for it in self._text_selected_items():
            it.props.shadow.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_shadow_color(self, color: str):
        for it in self._text_selected_items():
            it.props.shadow.color = color
            it.props.shadow.pattern.fill(color)
            it.update()

    def _on_text_shadow_opacity(self, percent: float):
        for it in self._text_selected_items():
            it.props.shadow.opacity = percent / 100.0
            it.update()

    def _on_text_shadow_x(self, value: float):
        for it in self._text_selected_items():
            it.props.shadow.offset_x = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_shadow_y(self, value: float):
        for it in self._text_selected_items():
            it.props.shadow.offset_y = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_shadow_blur(self, value: float):
        for it in self._text_selected_items():
            it.props.shadow.blur = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_outline_toggled(self, checked: bool):
        for it in self._text_selected_items():
            it.props.outline.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_outline_color(self, color: str):
        for it in self._text_selected_items():
            it.props.outline.color = color
            it.props.outline.pattern.fill(color)
            it.update()

    def _on_text_outline_width(self, value: float):
        for it in self._text_selected_items():
            it.props.outline.width = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_glow_toggled(self, checked: bool):
        for it in self._text_selected_items():
            it.props.glow.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_glow_color(self, color: str):
        for it in self._text_selected_items():
            it.props.glow.color = color
            it.props.glow.pattern.fill(color)
            it.update()

    def _on_text_glow_blur(self, value: float):
        for it in self._text_selected_items():
            it.props.glow.radius = value
            it.prepareGeometryChange()
            it.update()

    def _on_text_curvature(self, percent: float):
        for it in self._text_selected_items():
            it.props.curve.enabled = percent > 0
            it.props.curve.radius = radius_from_percent(percent)
            it.prepareGeometryChange()
            it.update()

    def _on_text_opacity(self, percent: float):
        for it in self._text_selected_items():
            it.props.opacity = percent / 100.0
            it.update()

    # ─── Enfeites ───

    def _on_text_strikethrough(self, checked: bool):
        for it in self._text_selected_items():
            it.props.strikethrough = checked
            it.update()

    def _on_text_overline(self, checked: bool):
        for it in self._text_selected_items():
            it.props.overline = checked
            it.update()

    def _on_text_underline(self, checked: bool):
        for it in self._text_selected_items():
            it.props.underline = checked
            it.update()

    def _on_text_double_underline(self, checked: bool):
        for it in self._text_selected_items():
            it.props.double_underline = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_box(self, checked: bool):
        for it in self._text_selected_items():
            it.props.ribbon.enabled = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_cloud(self, checked: bool):
        for it in self._text_selected_items():
            it.props.cloud = checked
            it.prepareGeometryChange()
            it.update()

    def _on_text_serif(self, checked: bool):
        for it in self._text_selected_items():
            it.props.serif = checked
            it.prepareGeometryChange()
            it.update()

    def _toggle_asset_browser(self):
        """Texture preview clicked — open/close the Assets browser next to Brush."""
        if not self.brush_panel.isVisible():
            return
        if self.asset_browser_panel.isVisible():
            self.asset_browser_panel.hide()
        else:
            self.asset_browser_panel.show()
        self._reposition()

    def _close_brush_panels(self):
        self._panel_mgr.hide("Brush")
        self.asset_browser_panel.hide()
        self._reposition()

    # ─── Toolbar Actions ───

    def _on_toolbar_action(self, name: str):
        actions = {
            "Grid": self._toggle_grid_panel,
            "Terreno": self._toggle_terrain_panel,
            "Região": self._toggle_region_panel,
            "Undo": self.canvas.engine.history.undo,
            "Redo": self.canvas.engine.history.redo,
        }
        action = actions.get(name)
        if action:
            action()

    # ─── Grid Panel ───

    def _toggle_grid_panel(self):
        self._panel_mgr.toggle("Grid")
        self._reposition()

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
        self._panel_mgr.toggle("Terrain")
        self._reposition()

    def _close_terrain_panel(self):
        self._panel_mgr.hide("Terrain")
        self.canvas_toolbar.uncheck_action("Terreno")
        self._reposition()

    # ─── Região Panel ───

    def _toggle_region_panel(self):
        self._panel_mgr.toggle("Region")
        self._reposition()

    def _close_region_panel(self):
        self._panel_mgr.hide("Region")
        self._reposition()

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
        # Shown purely by the "Info" checkbox, independent of whether the
        # compass face itself is expanded/collapsed — tying it to expanded
        # meant checking the box silently did nothing unless the compass
        # had *also* been separately double-clicked open first.
        allowed = self._hud_allowed()
        self.compass_hud.setVisible(allowed)
        if not allowed:
            return
        viewport = self.canvas.engine.viewport
        center = viewport.mapToScene(viewport.viewport().rect().center())
        self.compass_hud.update_info(
            self.terrain_panel.selected_terrain_name,
            float(self.terrain_panel.map_width), float(self.terrain_panel.map_height),
            center.x(), center.y(),
        )

    # ─── Logs ───

    def _open_logs(self):
        # Logs is a modal dialog on top of whatever's currently shown, not
        # a fullscreen menu view — restore whichever nav button was really
        # active (e.g. "Mobs") once it closes, since top_bar._on_nav_clicked
        # already switched the top bar to show "Logs" as checked.
        previous = self._active_menu or "Mapa"
        open_logs_dialog(self, self.log_handler)
        self.top_bar.set_active_menu(previous)

    # ─── Fullscreen Menu Views ───

    def _canvas_widgets(self) -> list[QWidget]:
        return [
            self.canvas_toolbar, self.brush_panel, self.asset_browser_panel,
            self.grid_panel, self.terrain_panel, self.region_panel, self.select_panel,
            self.text_panel,
            self._left_container, self._right_scroll, self.progression, self.compass,
            self.compass_hud, self.minimap,
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
            panel.project_created.connect(self._on_menu_project_created)
            panel.delete_requested.connect(self._on_menu_delete_project)
            layout.addWidget(panel)
        elif menu_name == "Mobs":
            from src.layouts.panels.mobs.panel import MobsPanel
            window = self.window()
            uow = window.uow if window and hasattr(window, 'uow') else None
            panel = MobsPanel(uow, zones_provider=self._region_med.zones_list, parent=container)
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
            if w in (self.brush_panel, self.asset_browser_panel, self.grid_panel,
                     self.terrain_panel, self.region_panel, self.select_panel, self.text_panel,
                     self.compass_hud):
                continue
            w.show()
        # Not part of the blanket show() above — its visibility rule is
        # "Info" checkbox state, not plain show/hide (see _refresh_compass_hud).
        self._refresh_compass_hud()
        self._reposition()

    def _on_menu_project_opened(self, proj):
        window = self.window()
        if window and hasattr(window, '_on_panel_project_opened'):
            window._on_panel_project_opened(proj)
        self._hide_menu_view()

    def _on_menu_project_created(self, proj):
        # Unlike opening an existing project, keep the Projetos view open —
        # the new card is shown in edit mode so the user can type its name.
        window = self.window()
        if window and hasattr(window, '_load_project'):
            window._load_project(proj)

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
