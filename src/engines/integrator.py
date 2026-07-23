"""Engine Integrator — connects all engines to the UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QPointF

from src.engines.map.painting import PaintingEngine, PaintMode
from src.engines.map.road import RoadEngine
from src.engines.map.river import RiverEngine
from src.engines.procedural import ProceduralEngine
from src.engines.smart_asset import SmartAssetEngine
from src.engines.game.mmorpg import MMORPGEngine, EntityType, GameEntity
from src.engines.io.workspace import WorkspaceManager
from src.engines.view_modes import ViewModeEngine, ViewMode
from src.engines.io.export import MapExportEngine
from src.engines.validation import ValidationEngine
from src.engines.performance import PerformanceEngine
from src.engines.explorer_inspector import ExplorerEngine, InspectorEngine, TreeNode, NodeType, PropertyDef, PropertyType
from src.engines.plugin_sdk import PluginSDK, HookType
from src.engines.polish import PolishEngine
from src.engines.rendering import RenderingEngine
from src.engines.typography import TypographyEngine


class EngineIntegrator(QObject):
    """Instantiates and wires all engines together and to the UI."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Instantiate engines
        self.painting = PaintingEngine()
        self.road = RoadEngine()
        self.river = RiverEngine()
        self.procedural = ProceduralEngine()
        self.smart_asset = SmartAssetEngine()
        self.mmorpg = MMORPGEngine()
        self.workspace = WorkspaceManager()
        self.view_modes = ViewModeEngine()
        self.export = MapExportEngine()
        self.validation = ValidationEngine()
        self.performance = PerformanceEngine()
        self.explorer = ExplorerEngine()
        self.inspector = InspectorEngine()
        self.plugins = PluginSDK()
        self.polish = PolishEngine()
        self.rendering = RenderingEngine()
        self.typography = TypographyEngine()

        # Load smart asset presets
        self.smart_asset.preset_castle()
        self.smart_asset.preset_mountain()
        self.smart_asset.preset_village()
        self.smart_asset.preset_lake()

    def connect_ui(self, layout):
        """Wire engines to MainLayout panels."""
        from src.layouts.main_layout import MainLayout
        ml: MainLayout = layout

        # ─── Canvas Toolbar → Tool Engines ───────────────────────────────
        ml.canvas_toolbar.tool_selected.connect(self._on_tool_selected)

        # ─── Explorer → ExplorerEngine ───────────────────────────────────
        ml.left_panel.search.textChanged.connect(self.explorer.search)
        ml.left_panel.tree.itemClicked.connect(self._on_tree_item_clicked)

        # ─── Status Bar → Performance ────────────────────────────────────
        ml.status_bar.fit_clicked.connect(self._on_fit_clicked)

        # ─── View Mode → Workspace ───────────────────────────────────────
        ml.top_bar.module_changed.connect(self._on_module_changed)

        # ─── Inspector change callback ───────────────────────────────────
        self.inspector.on_change(self._on_property_changed)

        # Store reference
        self._layout = ml

    # ─── Handlers ────────────────────────────────────────────────────────

    def _on_tool_selected(self, tool_name: str):
        """Route tool selection to appropriate engine mode."""
        tool_map = {
            "Desenhar": PaintMode.PAINT,
            "Borracha": PaintMode.ERASE,
        }
        if tool_name in tool_map:
            self.painting.set_mode(tool_map[tool_name])

        # Activate tool in canvas tool manager
        self._layout.canvas.engine.tool_manager.activate(tool_name)

        # Update status
        self._layout.status_bar.tool_label.setText(tool_name)

        # Emit plugin hook
        self.plugins.emit(HookType.ON_TOOL_CHANGE, tool=tool_name)

    def _on_tree_item_clicked(self, item, column):
        """Sync explorer tree click to inspector."""
        name = item.text(0)
        # Find or create node
        nodes = self.explorer.get_filtered_nodes()
        node = next((n for n in nodes if n.name == name), None)
        if node:
            self.explorer.select(node.id)
            self._inspect_node(node)

        self.plugins.emit(HookType.ON_SELECTION_CHANGE, selection=[name])

    def _inspect_node(self, node: TreeNode):
        """Show node properties in inspector panel."""
        props = [
            PropertyDef(key="name", label="Nome", value=node.name, section="Geral"),
            PropertyDef(key="type", label="Tipo", prop_type=PropertyType.ENUM,
                        value=node.node_type.name,
                        options=[t.name for t in NodeType], section="Geral"),
            PropertyDef(key="visible", label="Visível", prop_type=PropertyType.BOOL,
                        value=node.visible, section="Geral"),
            PropertyDef(key="locked", label="Bloqueado", prop_type=PropertyType.BOOL,
                        value=node.locked, section="Geral"),
        ]
        self.inspector.inspect(node.id, props)

        # Update inspector header
        self._layout.right_panel.set_element(
            name=node.name,
            type_=node.node_type.name,
            tags=", ".join(node.tags) if node.tags else "",
        )

    def _on_property_changed(self, target_id: str, key: str, value):
        """Handle property edit from inspector."""
        node = self.explorer.get_node(target_id)
        if node:
            if key == "name":
                self.explorer.rename_node(target_id, value)
            elif key == "visible":
                node.visible = value
            elif key == "locked":
                node.locked = value

        self.plugins.emit(HookType.ON_ITEM_MODIFY, item_id=target_id, key=key, value=value)

    def _on_module_changed(self, module_name: str):
        """Map top bar module buttons to view modes."""
        mode_map = {
            "Mapa": ViewMode.ILLUSTRATION,
            "Terreno": ViewMode.TERRAIN,
            "Entidades": ViewMode.ENTITY,
            "Quests": ViewMode.ENTITY,
            "Pintura": ViewMode.BRUSH,
            "Grid": ViewMode.GRID,
        }
        mode = mode_map.get(module_name)
        if mode:
            self.view_modes.set_mode(mode)

    def _on_fit_clicked(self):
        """Fit canvas to view."""
        self._layout.canvas.engine.zoom_reset()

    # ─── Public API ──────────────────────────────────────────────────────

    def update_stats(self):
        """Push engine stats to status bar."""
        entities = self.mmorpg
        self._layout.status_bar.update_stats(
            regions=len(self.painting.get_all_regions()),
            mobs=len(entities.get_entities_by_type(EntityType.MOB)),
            npcs=len(entities.get_entities_by_type(EntityType.NPC)),
            quests=len(entities.get_entities_by_type(EntityType.QUEST)),
            dungeons=len(entities.get_entities_by_type(EntityType.DUNGEON)),
            bosses=len(entities.get_entities_by_type(EntityType.BOSS)),
            items=self.rendering.cache.size if hasattr(self.rendering, 'cache') else 0,
        )

    def validate_project(self) -> dict:
        """Run validation and return result."""
        ctx = {
            "item_count": self.performance.memory.total_items,
            "layer_count": 10,
            "entities": {e.id: {"name": e.name, "type": e.entity_type.name}
                         for e in self.mmorpg._entities.values()},
            "connections": [{"id": c.id, "source_id": c.source_id, "target_id": c.target_id}
                            for c in self.mmorpg._connections.values()],
        }
        result = self.validation.validate(ctx)
        return {"passed": result.passed, "errors": result.error_count, "warnings": result.warning_count}

    def get_performance_overlay(self) -> str:
        return self.performance.get_overlay_text()
