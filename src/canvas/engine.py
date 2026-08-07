"""Canvas Engine — assembles viewport, grid, snap, tools, and input."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QMouseEvent, QKeyEvent

from src.canvas.viewport import Viewport
from src.canvas.grid import GridManager
from src.canvas.snap import SnapManager
from src.canvas.pan_controller import KeyboardPanController, PAN_KEYS
from src.canvas.tools.base import ToolManager
from src.canvas.tools.defaults import PanTool
from src.canvas.tools.select import SelectTool
from src.canvas.tools.brush_tool import BrushTool, RegionTool, RoadTool, RiverTool, RegionBrushTool
from src.canvas.tools.path_tool import RiverPathTool, RoadPathTool
from src.canvas.tools.text_tool import TextTool
from src.canvas.text_item import TextItem
from src.canvas.tools.spawn_tool import SpawnTool
from src.canvas.tools.marker_tool import MarkerTool
from src.canvas.tools.light_tool import LightTool
from src.canvas.tools.terrain_freehand_tool import TerrainFreehandTool
from src.engines.map.region_layer import RegionLayer
from src.engines.map.terrain_layer import TerrainLayer
from src.canvas.map_boundary import MovableBoundaryItem
from src.engines.map.brush import BrushEngine
from src.canvas.input_manager import InputManager
from src.engines.core.selection import SelectionEngine
from src.engines.core.transform import TransformEngine, HandleType
from src.engines.core.clipboard import ClipboardEngine
from src.engines.core.history import HistoryEngine
from src.engines.procedural import ProceduralEngine, GeneratorParams, GeneratorType
from src.engines.audio import SoundEngine
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsTextItem,
)
from PySide6.QtGui import QPainterPath, QBrush, QPen, QColor, QPolygonF
from src.canvas.item_utils import suppress_selection_decoration


class CanvasEngine(QWidget):
    """Complete canvas widget with all subsystems integrated."""

    zoom_changed = Signal(int)  # percent
    cursor_moved = Signal(float, float)
    tool_changed = Signal(str)
    text_committed = Signal()  # a just-placed text object finished its first edit
    selection_changed = Signal(list)  # list of selected IDs
    grid_toggled = Signal(bool)  # grid visible state
    zone_region_finalized = Signal(QPolygonF, str)  # (polygon, category_key) — RegionMediator owns id/card creation

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Viewport
        self.viewport = Viewport(self)
        layout.addWidget(self.viewport)

        # Grid
        self.grid = GridManager(self.viewport.scene())

        # Snap
        self.snap = SnapManager(self.grid)

        # Selection Engine
        self.selection = SelectionEngine(self.viewport.scene(), self)
        self.selection.selection_changed.connect(self.selection_changed.emit)

        # Transform Engine
        self.transform = TransformEngine(self.viewport.scene(), self)
        self.selection.selection_changed.connect(self._on_selection_changed)
        # A TextItem finishing its inline edit doesn't change Qt's own
        # selection state (it was already selected the whole time), so
        # selection_changed never fires on its own — re-run the handle
        # visibility check here so the resize/rotate frame appears once
        # typing commits (see _on_selection_changed's is_editing() filter).
        self.text_committed.connect(lambda: self._on_selection_changed([]))

        # Clipboard Engine
        self.clipboard = ClipboardEngine(self.viewport.scene(), self)

        # History Engine (Undo/Redo)
        self.history = HistoryEngine(self)

        # Procedural Engine
        self.procedural = ProceduralEngine()

        # Asset engine (injected later via set_asset_engine)
        self._asset_engine = None

        # Biome preset for the next finalized region — set via the toolbar's
        # Região/Bioma dropdown ("" = plain Região, default generation).
        self._region_preset: str = ""
        # Zone type for the next finalized region — set via the Região
        # panel's "+ Novo" per category ("" = not zone-painting). Mutually
        # exclusive with _region_preset. The id→visual mapping is owned by
        # RegionMediator (mirrors TerrainMediator._boundaries), not here.
        self._zone_type: str = ""

        # Tools
        self.tool_manager = ToolManager(self.viewport, self)
        self._register_default_tools()

        # Input
        self.input_manager = InputManager(self.tool_manager)
        self._register_global_shortcuts()

        # Sound Engine
        self.sound_engine = SoundEngine(self)
        self._brush_tool.set_sound_engine(self.sound_engine)
        self._brush_tool.set_snap_manager(self.snap)
        self.sound_engine.start()

        # Debounce timer for sound context — view_changed fires on every
        # pan/zoom pixel; scanning all visible items that frequently is
        # wasteful. 500ms after the last movement is enough for ambient
        # sound to feel responsive without burning CPU mid-drag.
        from PySide6.QtCore import QTimer
        self._sound_update_timer = QTimer(self)
        self._sound_update_timer.setSingleShot(True)
        self._sound_update_timer.setInterval(500)
        self._sound_update_timer.timeout.connect(self._update_sound_context)

        # Connect signals
        self.viewport.zoom_changed.connect(lambda z: self.zoom_changed.emit(int(z * 100)))
        self.viewport.zoom_changed.connect(lambda z: self.sound_engine.on_zoom_changed(int(z * 100)))
        self.viewport.cursor_moved.connect(self.cursor_moved.emit)
        self.viewport.view_changed.connect(self._on_view_changed)
        self.viewport.view_changed.connect(self._sound_update_timer.start)
        # Pan (PanTool drag, space/middle-drag, keyboard pan) all move the
        # scrollbars directly instead of going through view_changed — hook
        # the scrollbars themselves so the grid/measurement overlay keeps
        # following the viewport during every kind of pan, not just zoom.
        self.viewport.horizontalScrollBar().valueChanged.connect(self._on_view_changed)
        self.viewport.verticalScrollBar().valueChanged.connect(self._on_view_changed)
        self.tool_manager.tool_changed.connect(self.tool_changed.emit)

        # Override viewport events to route through tools
        self.viewport.mousePressEvent = self._on_mouse_press
        self.viewport.mouseMoveEvent = self._on_mouse_move
        self.viewport.mouseReleaseEvent = self._on_mouse_release
        self.viewport.mouseDoubleClickEvent = self._on_mouse_double_click
        self.viewport.keyPressEvent = self._on_key_press
        self.viewport.keyReleaseEvent = self._on_key_release

        # Activate default tool — Pan, so the map is movable right away
        # without first having to toggle Selecionar off (see CanvasToolbar).
        self.tool_manager.activate("Pan")

        # Grid starts hidden — user activates via toolbar or 'G' key
        self.grid.visible = False

        # ─── Keyboard pan ───
        self._pan = KeyboardPanController(self.viewport, self)
        self._pan.panned.connect(self._on_pan_delta)

        # Stop pan when the viewport loses focus (e.g. user clicks a panel)
        # so WASD keys don't stay "stuck" after focus leaves the canvas.
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QObject, QEvent

        class _PanKeyGuard(QObject):
            """App-wide filter: forwards pan keys (WASD/arrows) to the canvas
            viewport regardless of which widget currently has focus — so
            clicking a button in any panel never blocks map panning."""
            def __init__(self, pan_ctrl, vp, engine, parent=None):
                super().__init__(parent)
                self._pan = pan_ctrl
                self._vp = vp
                self._engine = engine
            def eventFilter(self, obj, event):
                from src.canvas.pan_controller import PAN_KEYS
                is_vp = obj is self._vp or obj is self._vp.viewport()
                if not is_vp:
                    if (event.type() == QEvent.Type.KeyPress
                            and not event.isAutoRepeat()
                            and event.key() in PAN_KEYS):
                        self._engine._on_key_press(event)
                        return True
                    if (event.type() == QEvent.Type.KeyRelease
                            and not event.isAutoRepeat()
                            and event.key() in PAN_KEYS
                            and self._pan.active):
                        self._pan.key_released(event.key())
                return False

        self._pan_key_guard = _PanKeyGuard(self._pan, self.viewport, self, self)
        QApplication.instance().installEventFilter(self._pan_key_guard)

        # ─── Map bounds (None = infinite) ───
        self._map_bounds: dict | None = None  # {width, height, shape}

        # Grid rebuild cache — see _update_grid(). Panning/zooming fires
        # view_changed (and the scrollbar valueChanged hooks) up to 60x/sec,
        # and a naive rebuild tears down and recreates every grid line/label
        # QGraphicsItem each time, which is what made WASD/mouse panning
        # feel laggy even on an otherwise empty map.
        self._grid_cache_rect = None  # QRectF, in scene coords, padded beyond the viewport
        self._grid_cache_zoom: float | None = None
        self._grid_cache_bounded: bool | None = None

    def _register_default_tools(self):
        self.tool_manager.register(
            SelectTool(self.viewport, self.selection, self.transform, self.history, tool_manager=self.tool_manager)
        )
        self.tool_manager.register(PanTool(self.viewport, self.selection, self.transform, self.history))
        self._text_tool = TextTool(
            self.viewport, self.tool_manager, self.history, self.selection, self.transform,
            on_committed=self.text_committed.emit,
        )
        self.tool_manager.register(self._text_tool)

        # Brush (asset painting)
        self.brush_engine = BrushEngine(self)
        self._brush_tool = BrushTool(
            self.viewport, self.brush_engine, history_engine=self.history, tool_manager=self.tool_manager)
        self.tool_manager.register(self._brush_tool)

        # Region tool with procedural generation callback
        self._region_tool = RegionTool(self.viewport)
        self._region_tool.on_region_finalized(self._on_region_finalized)
        self.tool_manager.register(self._region_tool)

        # Map tools (legacy click-polygon)
        self.tool_manager.register(RoadTool(self.viewport))
        self.tool_manager.register(RiverTool(self.viewport))

        # Animated path tools — activated automatically when a road/water
        # asset is selected in the Brush panel (see BrushMediator.on_asset_selected)
        self._river_path_tool = RiverPathTool(self.viewport, tool_manager=self.tool_manager)
        self._road_path_tool = RoadPathTool(self.viewport, tool_manager=self.tool_manager)
        self.tool_manager.register(self._river_path_tool)
        self.tool_manager.register(self._road_path_tool)

        # Região panel's paint brush (distinct from RegionTool's click-polygon,
        # used by the toolbar's Bioma/Estrada/Rio dropdown) — deliberately
        # never wired to self.snap (see RegionBrushTool._paint): a região is
        # a freeform painted area, not grid-tile placement, so it shouldn't
        # inherit whatever Snap/Grid state the terrain Brush tool left on.
        self._region_brush_tool = RegionBrushTool(self.viewport, history_engine=self.history)
        self.tool_manager.register(self._region_brush_tool)

        # Spawn panel's mob-group stamp (see SpawnMediator/spawn_tool.py)
        self._spawn_tool = SpawnTool(
            self.viewport, history_engine=self.history,
            selection_engine=self.selection, transform_engine=self.transform,
        )
        self.tool_manager.register(self._spawn_tool)

        # Marcador tool's point-of-interest pin (see MarkerMediator/marker_tool.py)
        self._marker_tool = MarkerTool(
            self.viewport, self.tool_manager, self.history, self.selection, self.transform,
        )
        self.tool_manager.register(self._marker_tool)

        # Iluminação panel's light object (see LightMediator/light_tool.py)
        self._light_tool = LightTool(
            self.viewport, self.tool_manager, self.history, self.selection, self.transform,
        )
        self.tool_manager.register(self._light_tool)

        # Terreno panel's "Livre" freehand boundary drawing (see
        # TerrainMediator/terrain_freehand_tool.py)
        self._terrain_freehand_tool = TerrainFreehandTool(self.viewport)
        self._terrain_freehand_tool.set_snap_manager(self.snap)
        self.tool_manager.register(self._terrain_freehand_tool)

    def set_asset_engine(self, asset_engine):
        """Injeta o AssetEngine após o projeto ser carregado."""
        self._asset_engine = asset_engine
        self._brush_tool.set_asset_engine(asset_engine)

    @property
    def asset_engine(self):
        """Public read accessor for the AssetEngine injected via
        set_asset_engine — for callers (e.g. ExplorerSyncMediator) that
        just need name/thumbnail lookups by asset_id, without reaching
        into the private `_asset_engine` attribute from outside."""
        return self._asset_engine

    def set_region_preset(self, preset_key: str):
        """Biome preset (see engines/map/presets.py) to populate the next
        Região polygon with — picked via the toolbar's Bioma submenu.
        Empty string reverts to the plain default generator."""
        self._region_preset = preset_key or ""

    def set_zone_type(self, zone_key: str):
        """Zone type (see engines/map/zones.py) to paint the next Região
        polygon as — armed by the Região panel's "+ Novo" per category.
        Empty string reverts to the plain default generator (or biome)."""
        self._zone_type = zone_key or ""

    def create_region_layer(self, color: QColor) -> RegionLayer:
        """A blank, paintable Região layer — brush-painted colored area
        managed by RegionMediator/RegionBrushTool. See region_layer.py."""
        return RegionLayer(self.viewport.scene(), color)

    def get_or_create_terrain_layer(self, asset_id: str) -> TerrainLayer:
        """Brush-tool material layer for `asset_id` — reaches into
        BrushTool the same way `create_region_layer` reaches into
        RegionLayer, so BrushMediator can reload persisted terrain masks
        without touching BrushTool internals directly."""
        return self._brush_tool._get_or_create_terrain_layer(asset_id)

    def terrain_layers(self) -> dict[str, TerrainLayer]:
        """All brush-painted terrain layers, keyed by asset_id — for
        BrushMediator to export/persist."""
        return self._brush_tool._terrain_layers

    def effect_layers(self) -> dict[str, TerrainLayer]:
        """All brush-painted animated effect layers (Névoa, Poeira, ...),
        keyed by "effect:<key>" asset_id — for BrushMediator to
        export/persist, same idea as terrain_layers()."""
        return self._brush_tool._effect_layers

    def get_or_create_effect_layer(self, asset_id: str) -> TerrainLayer:
        """Effect-layer counterpart to get_or_create_terrain_layer() —
        used by BrushMediator to reload a persisted effect stroke."""
        return self._brush_tool._get_or_create_effect_layer(asset_id)

    def refresh_shoreline_blend(self):
        """Re-runs the terrain-water/land foam pass immediately — used by
        AssetEffectsMediator when the "🌊 Maresia" toggle changes, so an
        already-painted shoreline's foam overlay updates (or clears) right
        away instead of only on that water asset's next brush stroke."""
        self._brush_tool._apply_shoreline_blend()

    def clear_terrain_layers(self):
        """Removes every brush-painted terrain AND effect layer from the
        scene — used when switching projects (see
        BrushMediator._load_from_db)."""
        for layer in self._brush_tool._terrain_layers.values():
            layer.remove_from_scene()
        self._brush_tool._terrain_layers.clear()
        for layer in self._brush_tool._effect_layers.values():
            layer.remove_from_scene()
        self._brush_tool._effect_layers.clear()
        # The foam/opacity-blend overlays are purely derived from these
        # layers (see BrushTool._clear_all_blend_overlays) — without this
        # they'd linger in the scene, orphaned, after the layers they were
        # blending are long gone.
        self._brush_tool._clear_all_blend_overlays()

    def place_stamp_item(self, asset_id: str, position: QPointF, rotation: float,
                          scale: float, opacity: float) -> QGraphicsPixmapItem | None:
        """Builds a brush-stamped object item at a scene position — shared
        by live painting (BrushTool._on_object_stamp) and DB reload
        (BrushMediator._load_from_db) so both produce identical items."""
        return self._brush_tool.place_stamp_item(asset_id, position, rotation, scale, opacity)

    def paint_zone(self, polygon: QPolygonF, zone_key: str, region_id: str,
                    name: str, stars: int, color: QColor):
        """Fills the finalized polygon with a flat translucent zone color —
        no procedural objects, just an area tag (Residencial/Comercial/...)
        with its name and a star-rating badge drawn on top, same idea as
        Cities Skylines' zoning paint. Returns a ZoneVisual the caller
        (RegionMediator) tracks by region_id — this method itself holds no
        id→item bookkeeping."""
        from src.engines.core.history import PlaceObjectCommand
        from src.canvas.zone_visual import ZoneVisual, star_text

        path = QPainterPath()
        path.addPolygon(polygon)
        path.closeSubpath()

        item = QGraphicsPathItem(path)
        item.setBrush(QBrush(color))
        item.setPen(QPen(color.darker(150), 1.5))
        # Above painted terrain (z=1) but below stamped/generated assets
        # (z=10+) — a ground-level tint, not an object sitting on top.
        item.setZValue(5)
        item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        item.setData(0, {"item_type": "zone", "zone_type": zone_key, "region_id": region_id})
        suppress_selection_decoration(item)

        # Children of a QGraphicsItem paint after (on top of) it regardless
        # of zValue, so no extra z-offset is needed for these to sit above
        # the translucent fill.
        name_item = QGraphicsSimpleTextItem(name, item)
        font = name_item.font()
        font.setBold(True)
        font.setPointSize(10)
        name_item.setFont(font)
        name_item.setBrush(QBrush(QColor("#ffffff")))

        stars_item = QGraphicsSimpleTextItem(star_text(stars), item)
        stars_item.setBrush(QBrush(QColor(255, 210, 60)))

        visual = ZoneVisual(item, name_item, stars_item)
        visual.recenter(path.boundingRect().center())

        self.viewport.scene().addItem(item)
        if self.history:
            self.history.push(PlaceObjectCommand(item))
        return visual

    def _on_region_finalized(self, polygon):
        """Renderiza geração procedural dentro do polígono finalizado."""
        if self._zone_type:
            self.zone_region_finalized.emit(polygon, self._zone_type)
            return

        if not self._asset_engine:
            return

        if self._region_preset:
            from src.engines.map.presets import PRESETS
            preset = PRESETS.get(self._region_preset)
            if preset:
                from src.engines.map.generator import MapGenerator
                from src.engines.procedural import GenerationResult
                items = MapGenerator().generate_region(polygon, preset, seed=0)
                self._render_generation_result(GenerationResult(items=items))
                return

        # Plain "Região" mode (no biome preset picked) — the original default.
        params = GeneratorParams(
            area=polygon.boundingRect(),
            polygon=polygon,
            seed=0,
        )
        result = self.procedural.generate(GeneratorType.FOREST, params)
        self._render_generation_result(result)

    def _render_generation_result(self, result):
        """Renderiza GenerationResult na cena como QGraphicsPixmapItems."""
        for gen_item in result.items:
            if not gen_item.asset_id:
                continue
            pixmap = self._asset_engine.get_pixmap(gen_item.asset_id) if self._asset_engine else None
            if not pixmap or pixmap.isNull():
                continue
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            item.setTransformOriginPoint(pixmap.width() / 2, pixmap.height() / 2)
            # See place_stamp_item's own setShapeMode for why — default
            # MaskShape misses clicks on a sprite's transparent padding.
            item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
            item.setPos(
                gen_item.position.x() - pixmap.width() / 2,
                gen_item.position.y() - pixmap.height() / 2,
            )
            item.setScale(gen_item.scale)
            item.setRotation(gen_item.rotation)
            item.setOpacity(gen_item.opacity)
            item.setZValue(0.5 + gen_item.z_offset)
            item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
            item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
            item.setData(0, {"item_type": "asset"})
            suppress_selection_decoration(item)
            self.viewport.scene().addItem(item)

    def _on_selection_changed(self, ids: list):
        """Show/hide transform handles based on selection.

        Terrain/effect layer items get the handle box too — its bounds
        come from selection_bounding_rect() (see _LayerItem in
        terrain_layer.py and TransformEngine._item_bounds), which is
        already scoped to just the clicked/box-selected blob, not the
        item's full raster canvas (which can be 4096x4096 even for a tiny
        painted patch) — so the box correctly hugs only the selected
        paint, same as any other object. A TextItem mid inline-edit is
        still excluded — its own dashed edit-highlight is enough while
        typing, and a resize/rotate handle frame doesn't make sense until
        editing commits (see text_committed's connection below, which
        re-runs this once it does).
        """
        selected = self.viewport.scene().selectedItems()
        other_selected = [
            it for it in selected
            if not (isinstance(it, TextItem) and it.is_editing())
        ]

        if other_selected:
            self.transform.show_handles(other_selected)
        else:
            self.transform.hide_handles()

    def _register_global_shortcuts(self):
        self.input_manager.register_global("G", self._toggle_grid)
        # Note: Ctrl+C/V/X/D handled in _on_key_press since they need modifiers

    def _toggle_grid(self):
        self.grid.toggle()
        if self.grid.visible:
            # Rebuilds may have been skipped entirely while hidden (view
            # never updates a grid nobody can see), so the cached lines can
            # be stale for the current viewport — force a fresh build.
            self._update_grid(force=True)
        self.grid_toggled.emit(self.grid.visible)

    def _on_view_changed(self):
        if self.grid.visible or self.grid.show_measurements:
            self._update_grid()

    def _update_grid(self, force: bool = False):
        full_view_rect = self.viewport.mapToScene(self.viewport.viewport().rect()).boundingRect()
        zoom = self.viewport.zoom_level
        bounded = self._map_bounds is not None

        # Skip the (expensive) rebuild while the current viewport is still
        # fully covered by the last padded build — panning within that
        # margin needs no new lines, only pans that cross it do. Zoom or
        # bounds toggling always forces a fresh build since line spacing /
        # clipping depend on them.
        if (
            not force
            and self._grid_cache_rect is not None
            and self._grid_cache_zoom == zoom
            and self._grid_cache_bounded == bounded
            and self._grid_cache_rect.contains(full_view_rect)
        ):
            return

        margin_x = full_view_rect.width() * 0.5
        margin_y = full_view_rect.height() * 0.5
        padded_rect = full_view_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        view_rect = padded_rect
        clip_path = None
        # Clip grid to map bounds if set — bounded terrains' grid should
        # conform to their exact boundary shape(s), not just a rectangle.
        if self._map_bounds:
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPainterPath
            # Union across every bounded terrain currently shown — not just
            # the selected one — so the grid covers all of them at once and
            # actually grows as terrains are added, instead of staying
            # clipped to whichever terrain happened to be selected last.
            boundaries = [
                b for b in self._brush_tool._all_boundaries
                if b is not None and b.visible and b._item is not None
            ]
            if boundaries:
                union_path = QPainterPath()
                bounds = None
                for b in boundaries:
                    # Boundary can be anywhere in the scene (positioned at
                    # view center when created, or dragged since) — use its
                    # real scene rect, not one centered on the scene origin.
                    scene_path = b._item.mapToScene(b._item.path())
                    union_path = union_path.united(scene_path)
                    rect = scene_path.boundingRect()
                    bounds = rect if bounds is None else bounds.united(rect)
                clip_path = union_path
            else:
                hw = self._map_bounds["width"] / 2
                hh = self._map_bounds["height"] / 2
                bounds = QRectF(-hw, -hh, self._map_bounds["width"], self._map_bounds["height"])
            view_rect = view_rect.intersected(bounds)

        self.grid.update(view_rect, zoom, clip_path, full_view_rect)
        self._grid_cache_rect = padded_rect
        self._grid_cache_zoom = zoom
        self._grid_cache_bounded = bounded

    # --- Event routing ---

    def _on_mouse_press(self, event: QMouseEvent):
        # Pan with middle button or space always takes priority
        if event.button() == Qt.MouseButton.MiddleButton or self.viewport._space_held:
            self._commit_stray_text_edit(None)
            self.viewport._panning = True
            self.viewport._pan_start = event.position()
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.viewport.begin_interactive_pan()
            return

        # Let boundary items handle their own press
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        self._commit_stray_text_edit(item)
        if isinstance(item, MovableBoundaryItem) and item._hit_border(item.mapFromScene(scene_pos)):
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.mousePressEvent(self.viewport, event)
            return

        # The delete/duplicate action buttons drawn by TransformEngine on a
        # selected item are only hit-tested by ItemInteraction, which lives
        # inside SelectTool — so a click on those buttons while some other
        # tool (e.g. RoadPathTool, still active after finalizing a road so
        # the user can keep tracing) is active, the click never reaches
        # them and instead falls through to that tool's own click handling.
        # Check
        # globally here first, same as the Delete/Backspace key shortcut
        # below in _on_key_press, so the buttons work no matter which tool
        # is active.
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.transform.handle_at(scene_pos)
            if handle in (HandleType.DELETE_ACTION, HandleType.DUPLICATE_ACTION):
                selected = self.viewport.scene().selectedItems()
                if handle == HandleType.DELETE_ACTION:
                    from src.canvas.tools.interaction import delete_items
                    delete_items(self.viewport.scene(), selected, self.transform, self.selection, self.history)
                else:
                    from src.canvas.tools.interaction import ItemInteraction
                    ItemInteraction(self.viewport, self.selection, self.transform, self.history)._duplicate_selected(selected)
                event.accept()
                return

        self.tool_manager.mouse_press(event, scene_pos)

    def _commit_stray_text_edit(self, clicked_item):
        """`viewport.mousePressEvent` is fully monkeypatched to this method
        (see __init__), which bypasses QGraphicsScene's own event dispatch —
        so a click outside a TextItem being inline-edited never reaches its
        _InlineTextEditor and never fires the focusOutEvent that would
        normally commit it (Enter/Escape were the only way out). Commit it
        here instead whenever the click isn't on that item or its editor."""
        for it in self.viewport.scene().items():
            if isinstance(it, TextItem) and it.is_editing():
                if clicked_item is not it and clicked_item is not it._editor:
                    it._finish_editing()
                break

    def _on_mouse_move(self, event: QMouseEvent):
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        self.viewport.cursor_moved.emit(scene_pos.x(), scene_pos.y())

        # Mouse events are monkey-patched to route through tools instead of
        # QGraphicsView's own dispatch (see _on_mouse_press) — which also
        # silently disabled Qt's hover machinery (hoverEnterEvent/
        # hoverLeaveEvent, and QGraphicsItem.cursor() applying automatically
        # on hover) scene-wide, since that's normally driven by
        # QGraphicsView.mouseMoveEvent. Replaying it here — only when no
        # button is held, so it never fights an active drag/pan/paint — is
        # side-effect-free (no button down means Qt's default handler does
        # nothing but hover-testing) and restores hover highlights/cursors
        # for every item, not just text.
        if event.buttons() == Qt.MouseButton.NoButton:
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.mouseMoveEvent(self.viewport, event)

        if self.viewport._panning:
            delta = event.position() - self.viewport._pan_start
            self.viewport._pan_start = event.position()
            self.viewport.horizontalScrollBar().setValue(
                self.viewport.horizontalScrollBar().value() - int(delta.x())
            )
            self.viewport.verticalScrollBar().setValue(
                self.viewport.verticalScrollBar().value() - int(delta.y())
            )
            return

        # Let boundary items handle hover/drag — but only near their actual
        # border (matches _on_mouse_press's own _hit_border check below).
        # Without that check, ANY move over a bounded terrain's whole
        # interior area (not just its edge) got redirected here instead of
        # reaching the active tool, silently breaking painting (terrain
        # brush, região brush, anything) for the entire inside of the
        # terrain, not just its border.
        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        if isinstance(item, MovableBoundaryItem) and item._hit_border(item.mapFromScene(scene_pos)):
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.mouseMoveEvent(self.viewport, event)
            return

        # Check if a boundary is being dragged (cursor may have left the item)
        for scene_item in self.viewport.scene().items():
            if isinstance(scene_item, MovableBoundaryItem) and scene_item._dragging:
                from PySide6.QtWidgets import QGraphicsView
                QGraphicsView.mouseMoveEvent(self.viewport, event)
                return

        self.tool_manager.mouse_move(event, scene_pos)

    def _on_mouse_double_click(self, event: QMouseEvent):
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        self.tool_manager.mouse_double_click(event, scene_pos)

    def _on_mouse_release(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (
            self.viewport._panning and not self.viewport._space_held
        ):
            if self.viewport._panning:
                self.viewport.end_interactive_pan()
            self.viewport._panning = False
            self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Let boundary items handle release
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        # Check if any boundary is being dragged
        for scene_item in self.viewport.scene().items():
            if isinstance(scene_item, MovableBoundaryItem) and scene_item._dragging:
                from PySide6.QtWidgets import QGraphicsView
                QGraphicsView.mouseReleaseEvent(self.viewport, event)
                return

        self.tool_manager.mouse_release(event, scene_pos)

    def _on_key_press(self, event: QKeyEvent):
        # An in-place text editor (e.g. TextItem's inline QGraphicsTextItem)
        # is currently focused — every key must reach it as actual typed
        # text, not get intercepted by WASD pan / global shortcuts below.
        # Both mouse AND key events on the viewport are monkey-patched to
        # route through tools instead of QGraphicsView's own dispatch, so
        # without this the scene's focused item never sees keystrokes at
        # all (not just WASD — typing wouldn't work for any key).
        if isinstance(self.viewport.scene().focusItem(), QGraphicsTextItem):
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.keyPressEvent(self.viewport, event)
            return

        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.viewport._space_held = True
            self.viewport.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        # Clipboard shortcuts (Ctrl+modifier)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            selected = self.viewport.scene().selectedItems()
            if event.key() == Qt.Key.Key_C:
                self.clipboard.copy(selected)
                return
            elif event.key() == Qt.Key.Key_X:
                self.clipboard.cut(selected)
                return
            elif event.key() == Qt.Key.Key_V:
                self.clipboard.paste()
                return
            elif event.key() == Qt.Key.Key_D:
                self.clipboard.duplicate(selected)
                return
            elif event.key() == Qt.Key.Key_Z:
                self.history.undo()
                return
            elif event.key() == Qt.Key.Key_Y:
                self.history.redo()
                return

        # Arrow keys + WASD — pan the map (continuous with acceleration)
        if event.key() in PAN_KEYS:
            if not event.isAutoRepeat():
                self._pan.key_pressed(event.key())
            return

        # Snap toggle (Shift+S, since S alone is pan)
        if event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.snap.toggle()
            return

        # Delete/Backspace — same trash action as the selection's own
        # delete handle, fired globally so it works no matter which tool is
        # active (fires here, not per-tool, since key events don't route
        # through a tool's ItemInteraction the way mouse events do).
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected = self.viewport.scene().selectedItems()
            if selected:
                from src.canvas.tools.interaction import delete_items
                delete_items(self.viewport.scene(), selected, self.transform, self.selection, self.history)
            return

        self.input_manager.handle_key_press(event)

    def _on_key_release(self, event: QKeyEvent):
        if isinstance(self.viewport.scene().focusItem(), QGraphicsTextItem):
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.keyReleaseEvent(self.viewport, event)
            return

        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.viewport._space_held = False
            if not self.viewport._panning:
                self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Stop pan keys
        if not event.isAutoRepeat() and event.key() in PAN_KEYS:
            self._pan.key_released(event.key())

        self.input_manager.handle_key_release(event)

    def _on_pan_delta(self, dx: float, dy: float):
        """Compensate active brush stroke and continue painting while panning."""
        if self._brush_tool._active_terrain_layer is not None:
            # The viewport moved, so the scene point under the cursor changed.
            # Get current cursor screen pos and compute new scene pos.
            cursor_screen = self.viewport.viewport().mapFromGlobal(
                self.viewport.cursor().pos()
            )
            scene_pos = self.viewport.mapToScene(cursor_screen)
            # Update last pos to avoid a jump, then paint at new scene pos
            self._brush_tool._last_terrain_pos = QPointF(
                scene_pos.x() - dx, scene_pos.y() - dy
            )
            self._brush_tool._continue_terrain_stroke(scene_pos)
        elif self._brush_tool._last_terrain_pos is not None:
            self._brush_tool._last_terrain_pos += QPointF(dx, dy)

    # --- Public API ---

    def set_map_bounds(self, width: int, height: int, shape: str):
        """Set finite map bounds. Brush and grid will be clipped."""
        self._map_bounds = {"width": width, "height": height, "shape": shape}
        self._brush_tool.set_map_bounds(width, height, shape)
        if self.grid.visible:
            self._update_grid()

    def clear_map_bounds(self):
        """Set map to infinite (no bounds)."""
        self._map_bounds = None
        self._brush_tool.set_map_bounds(None, None, None)
        if self.grid.visible:
            self._update_grid()

    def zoom_in(self):
        self.viewport.zoom_in()

    def zoom_out(self):
        self.viewport.zoom_out()

    def zoom_reset(self):
        self.viewport.zoom_reset()

    # --- Sound ---

    def start_sound(self):
        self.sound_engine.start()

    def stop_sound(self):
        self.sound_engine.stop()

    def _update_sound_context(self):
        """Scan visible items and notify sound engine layers."""
        view_rect = self.viewport.mapToScene(self.viewport.viewport().rect()).boundingRect()
        visible_items = self.viewport.scene().items(view_rect)
        object_keys = set()

        # Calculate terrain coverage in viewport
        terrain_coverage: dict[str, float] = {}
        view_area = view_rect.width() * view_rect.height()

        for asset_id, layer in self._brush_tool._terrain_layers.items():
            item = layer.item
            item_rect = item.mapRectToScene(item.boundingRect())
            intersection = view_rect.intersected(item_rect)
            if not intersection.isEmpty():
                # Get the sound key (category) for this terrain
                sound_key = self._brush_tool._get_asset_sound_key(asset_id)
                coverage = (intersection.width() * intersection.height()) / max(1.0, view_area)
                terrain_coverage[sound_key] = terrain_coverage.get(sound_key, 0.0) + min(1.0, coverage)

        # Notify sound engine about visible terrains
        if terrain_coverage:
            self.sound_engine.on_visible_terrains_changed(terrain_coverage)

        for item in visible_items:
            if isinstance(item, QGraphicsPixmapItem):
                # data(0) is a metadata dict on tagged items (item_type —
                # see SelectionEngine/HistoryEngine's convention) but was
                # historically documented as a plain sound-category string;
                # nothing ever actually set it as a string, so handle both
                # instead of assuming one and crashing on the other.
                data0 = item.data(0)
                if isinstance(data0, dict):
                    key = data0.get("item_type", "")
                else:
                    key = data0 or ""
                if key:
                    object_keys.add(str(key).lower())
                # data(1) = biome tag (e.g. "desert", "forest")
                biome = item.data(1) or ""
                if biome:
                    self.sound_engine.on_biome_changed(biome.lower())
                # data(2) = region/music tag
                region = item.data(2) or ""
                if region:
                    self.sound_engine.on_region_entered(region.lower())
        self.sound_engine.on_visible_objects_changed(object_keys)
