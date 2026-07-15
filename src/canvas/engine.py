"""Canvas Engine — assembles viewport, grid, snap, tools, and input."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QMouseEvent, QKeyEvent

from src.canvas.viewport import Viewport
from src.canvas.grid import GridManager
from src.canvas.snap import SnapManager
from src.canvas.tools.base import ToolManager
from src.canvas.tools.defaults import SelectTool, MoveTool, PanTool
from src.canvas.tools.brush_tool import BrushTool, RegionTool, RoadTool, RiverTool
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

    def _register_default_tools(self):
        self.tool_manager.register(SelectTool(self.viewport, self.selection))
        self.tool_manager.register(MoveTool(self.viewport, self.transform, self.history))
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

    def _on_view_changed(self):
        if self.grid.visible:
            self._update_grid()

    def _update_grid(self):
        view_rect = self.viewport.mapToScene(self.viewport.viewport().rect()).boundingRect()
        self.grid.update(view_rect)

    # --- Event routing ---

    def _on_mouse_press(self, event: QMouseEvent):
        # Pan with middle button or space always takes priority
        if event.button() == Qt.MouseButton.MiddleButton or self.viewport._space_held:
            self.viewport._panning = True
            self.viewport._pan_start = event.position()
            self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
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

        self.tool_manager.mouse_move(event, scene_pos)

    def _on_mouse_release(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (
            self.viewport._panning and not self.viewport._space_held
        ):
            self.viewport._panning = False
            self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return

        scene_pos = self.viewport.mapToScene(int(event.position().x()), int(event.position().y()))
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

        # Snap toggle
        if event.text().upper() == "S":
            self.snap.toggle()
            return

        self.input_manager.handle_key_press(event)

    def _on_key_release(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.viewport._space_held = False
            if not self.viewport._panning:
                self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return

        self.input_manager.handle_key_release(event)

    # --- Public API ---

    def zoom_in(self):
        self.viewport.zoom_in()

    def zoom_out(self):
        self.viewport.zoom_out()

    def zoom_reset(self):
        self.viewport.zoom_reset()
