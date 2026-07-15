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
from src.canvas.tools.brush_tool import BrushTool, RegionTool, RoadTool, RiverTool
from src.canvas.map_boundary import MovableBoundaryItem
from src.engines.map.brush import BrushEngine
from src.canvas.input_manager import InputManager
from src.engines.core.selection import SelectionEngine
from src.engines.core.transform import TransformEngine
from src.engines.core.clipboard import ClipboardEngine
from src.engines.core.history import HistoryEngine
from src.engines.procedural import ProceduralEngine, GeneratorParams, GeneratorType
from PySide6.QtWidgets import QGraphicsPixmapItem


class CanvasEngine(QWidget):
    """Complete canvas widget with all subsystems integrated."""

    zoom_changed = Signal(int)  # percent
    cursor_moved = Signal(float, float)
    tool_changed = Signal(str)
    selection_changed = Signal(list)  # list of selected IDs
    grid_toggled = Signal(bool)  # grid visible state

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

        # Clipboard Engine
        self.clipboard = ClipboardEngine(self.viewport.scene(), self)

        # History Engine (Undo/Redo)
        self.history = HistoryEngine(self)

        # Procedural Engine
        self.procedural = ProceduralEngine()

        # Asset engine (injected later via set_asset_engine)
        self._asset_engine = None

        # Tools
        self.tool_manager = ToolManager(self.viewport, self)
        self._register_default_tools()

        # Input
        self.input_manager = InputManager(self.tool_manager)
        self._register_global_shortcuts()

        # Connect signals
        self.viewport.zoom_changed.connect(lambda z: self.zoom_changed.emit(int(z * 100)))
        self.viewport.cursor_moved.connect(self.cursor_moved.emit)
        self.viewport.view_changed.connect(self._on_view_changed)
        self.tool_manager.tool_changed.connect(self.tool_changed.emit)

        # Override viewport events to route through tools
        self.viewport.mousePressEvent = self._on_mouse_press
        self.viewport.mouseMoveEvent = self._on_mouse_move
        self.viewport.mouseReleaseEvent = self._on_mouse_release
        self.viewport.keyPressEvent = self._on_key_press
        self.viewport.keyReleaseEvent = self._on_key_release

        # Activate default tool
        self.tool_manager.activate("Selecionar")

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

    def set_asset_engine(self, asset_engine):
        """Injeta o AssetEngine após o projeto ser carregado."""
        self._asset_engine = asset_engine
        self._brush_tool.set_asset_engine(asset_engine)

    def _on_region_finalized(self, polygon):
        """Renderiza geração procedural dentro do polígono finalizado."""
        if not self._asset_engine:
            return

        params = GeneratorParams(
            area=polygon.boundingRect(),
            polygon=polygon,
            seed=0,
        )
        # Usa o gerador de floresta como padrão (configurável depois)
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
            self.viewport.scene().addItem(item)

    def _on_selection_changed(self, ids: list):
        """Show/hide transform handles based on selection."""
        selected = self.viewport.scene().selectedItems()
        if selected:
            self.transform.show_handles(selected)
        else:
            self.transform.hide_handles()

    def _register_global_shortcuts(self):
        self.input_manager.register_global("G", self._toggle_grid)
        # Note: Ctrl+C/V/X/D handled in _on_key_press since they need modifiers

    def _toggle_grid(self):
        self.grid.toggle()
        if self.grid.visible:
            self._update_grid()
        self.grid_toggled.emit(self.grid.visible)

    def _on_view_changed(self):
        if self.grid.visible:
            self._update_grid()

    def _update_grid(self):
        view_rect = self.viewport.mapToScene(self.viewport.viewport().rect()).boundingRect()
        # Clip grid to map bounds if set
        if self._map_bounds:
            from PySide6.QtCore import QRectF
            hw = self._map_bounds["width"] / 2
            hh = self._map_bounds["height"] / 2
            bounds = QRectF(-hw, -hh, self._map_bounds["width"], self._map_bounds["height"])
            view_rect = view_rect.intersected(bounds)
        self.grid.update(view_rect)

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

        # Let boundary items handle hover/drag
        item = self.viewport.scene().itemAt(scene_pos, self.viewport.transform())
        if isinstance(item, MovableBoundaryItem):
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
