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
from src.canvas.tools.defaults import SelectTool, PanTool
from src.canvas.tools.brush_tool import BrushTool, RegionTool, RoadTool, RiverTool, RegionBrushTool
from src.engines.map.region_layer import RegionLayer
from src.canvas.map_boundary import MovableBoundaryItem
from src.engines.map.brush import BrushEngine
from src.canvas.input_manager import InputManager
from src.engines.core.selection import SelectionEngine
from src.engines.core.transform import TransformEngine
from src.canvas.selection_highlight import SelectionHighlight
from src.engines.core.clipboard import ClipboardEngine
from src.engines.core.history import HistoryEngine
from src.engines.procedural import ProceduralEngine, GeneratorParams, GeneratorType
from src.engines.audio import SoundEngine
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsPathItem, QGraphicsSimpleTextItem
from PySide6.QtGui import QPainterPath, QBrush, QPen, QColor, QPolygonF
from src.canvas.item_utils import suppress_selection_decoration


class CanvasEngine(QWidget):
    """Complete canvas widget with all subsystems integrated."""

    zoom_changed = Signal(int)  # percent
    cursor_moved = Signal(float, float)
    tool_changed = Signal(str)
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
        self.selection_highlight = SelectionHighlight(self.viewport.scene())
        self.selection.selection_changed.connect(self._on_selection_changed)

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

        # Connect signals
        self.viewport.zoom_changed.connect(lambda z: self.zoom_changed.emit(int(z * 100)))
        self.viewport.zoom_changed.connect(lambda z: self.sound_engine.on_zoom_changed(int(z * 100)))
        self.viewport.cursor_moved.connect(self.cursor_moved.emit)
        self.viewport.view_changed.connect(self._on_view_changed)
        self.viewport.view_changed.connect(self._update_sound_context)
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

        # ─── Map bounds (None = infinite) ───
        self._map_bounds: dict | None = None  # {width, height, shape}

    def _register_default_tools(self):
        self.tool_manager.register(SelectTool(self.viewport, self.selection))
        self.tool_manager.register(PanTool(self.viewport))

        # Brush (asset painting)
        self.brush_engine = BrushEngine(self)
        self._brush_tool = BrushTool(self.viewport, self.brush_engine, history_engine=self.history)
        self.tool_manager.register(self._brush_tool)

        # Region tool with procedural generation callback
        self._region_tool = RegionTool(self.viewport)
        self._region_tool.on_region_finalized(self._on_region_finalized)
        self.tool_manager.register(self._region_tool)

        # Map tools
        self.tool_manager.register(RoadTool(self.viewport))
        self.tool_manager.register(RiverTool(self.viewport))

        # Região panel's paint brush (distinct from RegionTool's click-polygon,
        # used by the toolbar's Bioma/Estrada/Rio dropdown)
        self._region_brush_tool = RegionBrushTool(self.viewport, history_engine=self.history)
        self._region_brush_tool.set_snap_manager(self.snap)
        self.tool_manager.register(self._region_brush_tool)

    def set_asset_engine(self, asset_engine):
        """Injeta o AssetEngine após o projeto ser carregado."""
        self._asset_engine = asset_engine
        self._brush_tool.set_asset_engine(asset_engine)

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
            item.setPos(
                gen_item.position.x() - pixmap.width() / 2,
                gen_item.position.y() - pixmap.height() / 2,
            )
            item.setScale(gen_item.scale)
            item.setRotation(gen_item.rotation)
            item.setOpacity(gen_item.opacity)
            item.setZValue(10 + gen_item.z_offset)
            item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
            item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
            item.setData(0, {"item_type": "asset"})
            suppress_selection_decoration(item)
            self.viewport.scene().addItem(item)

    def _on_selection_changed(self, ids: list):
        """Show/hide transform handles based on selection.

        Terrain layer items span their entire raster canvas, not just the
        painted area, so a bounding-box rectangle around one is misleading —
        those get a mask-contour perimeter highlight instead of move/resize
        handles.
        """
        selected = self.viewport.scene().selectedItems()
        terrain_by_item = {layer.item: layer for layer in self._brush_tool._terrain_layers.values()}
        terrain_selected = [terrain_by_item[it] for it in selected if it in terrain_by_item]
        other_selected = [it for it in selected if it not in terrain_by_item]

        if other_selected:
            self.transform.show_handles(other_selected)
        else:
            self.transform.hide_handles()

        if terrain_selected:
            self.selection_highlight.show(terrain_selected)
        else:
            self.selection_highlight.hide()

    def _register_global_shortcuts(self):
        self.input_manager.register_global("G", self._toggle_grid)
        # Note: Ctrl+C/V/X/D handled in _on_key_press since they need modifiers

    def _toggle_grid(self):
        self.grid.toggle()
        if self.grid.visible:
            self._update_grid()
        self.grid_toggled.emit(self.grid.visible)

    def _on_view_changed(self):
        if self.grid.visible or self.grid.show_measurements:
            self._update_grid()

    def _update_grid(self):
        full_view_rect = self.viewport.mapToScene(self.viewport.viewport().rect()).boundingRect()
        view_rect = full_view_rect
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

        self.grid.update(view_rect, self.viewport.zoom_level, clip_path, full_view_rect)

    # --- Event routing ---

    def _on_mouse_press(self, event: QMouseEvent):
        # Pan with middle button or space always takes priority
        if event.button() == Qt.MouseButton.MiddleButton or self.viewport._space_held:
            self.viewport._panning = True
            self.viewport._pan_start = event.position()
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Let boundary items handle their own press
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        if isinstance(item, MovableBoundaryItem) and item._hit_border(item.mapFromScene(scene_pos)):
            from PySide6.QtWidgets import QGraphicsView
            QGraphicsView.mousePressEvent(self.viewport, event)
            return

        self.tool_manager.mouse_press(event, scene_pos)

    def _on_mouse_move(self, event: QMouseEvent):
        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
        self.viewport.cursor_moved.emit(scene_pos.x(), scene_pos.y())

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

    def _on_mouse_release(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (
            self.viewport._panning and not self.viewport._space_held
        ):
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

        self.input_manager.handle_key_press(event)

    def _on_key_release(self, event: QKeyEvent):
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
