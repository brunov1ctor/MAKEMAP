"""MarkerMediator — owns everything specific to the Marcador tool: tool
panel wiring (icon picker), placement, selection -> edit panel, edit panel
field changes -> live update + persistence, and the "shader" effects
animation timer. Self-contained (mirrors RegionMediator's style) rather
than split between main_layout.py handlers and a mediator, since markers
have no other place in the app that needs to reach into this state.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from src.canvas.marker_item import MarkerItem
from src.engines.marker import MarkerProperties, category_for_icon
from src.layouts.panels.marker.panel import MarkerToolPanel
from src.layouts.panels.marker.edit_panel import MarkerEditPanel

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_SYNC_DEBOUNCE_MS = 250
_EFFECT_TICK_MS = 100


class MarkerMediator:
    MAP_ID = "default"  # matches Brush/Region/Spawn/Text mediators

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._pending_icon = "📍"
        self._items: dict[str, MarkerItem] = {}  # canvas_items row id -> MarkerItem

        # Marcador — MarkerToolPanel (icon picker, shown while the tool is
        # armed) and MarkerEditPanel (rich per-marker editor, shown on
        # selection) never appear at the same time, so both register as
        # separate exclusive PanelManager entries occupying the same dock
        # slot instead of one "riding beside" the other (see
        # PanelManager registration in MainLayout).
        panel = MarkerToolPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_marker_panel)
        self._l.marker_panel = panel
        panel.icon_changed.connect(self._on_icon_picked)

        edit = MarkerEditPanel(self._l)
        edit.hide()
        edit.close_requested.connect(self._l._close_marker_edit_panel)
        edit.content_changed.connect(self._l._reposition)
        self._l.marker_edit_panel = edit
        edit.name_changed.connect(self._on_name_changed)
        edit.category_changed.connect(self._on_category_changed)
        edit.icon_changed.connect(self._on_icon_changed)
        edit.description_changed.connect(self._on_description_changed)
        edit.effects_changed.connect(self._on_effects_changed)
        edit.radius_changed.connect(self._on_radius_changed)
        edit.effect_intensity_changed.connect(self._on_effect_intensity_changed)

        self._l.canvas.engine._marker_tool.set_properties_provider(self._provide_properties)
        self._l.canvas.engine._marker_tool.set_parent_provider(lambda: self._active_boundary.group if self._active_boundary and self._active_boundary._item else None)
        self._l.canvas.engine.selection.selection_changed.connect(self._on_selection_changed)

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._schedule_sync)

        self._effect_timer = QTimer()
        self._effect_timer.timeout.connect(self._tick_effects)
        self._effect_timer.start(_EFFECT_TICK_MS)

    # ─── Tool panel: icon picker ───

    def _on_icon_picked(self, icon: str):
        self._pending_icon = icon

    def set_active_terrain(self, terrain_id: str):
        """Chamado por TerrainMediator.on_selected para sincronizar o label e o boundary ativo."""
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._active_boundary = boundary
        self._l.marker_panel.terrain_combo.set_terrain(terrain_id)

    def _provide_properties(self) -> MarkerProperties:
        """Read by MarkerTool at the moment a new marker is placed."""
        icon = self._pending_icon
        return MarkerProperties(icon=icon, category=category_for_icon(icon))

    # ─── Selection -> edit panel ───

    def _selected_marker(self) -> MarkerItem | None:
        for item in self._l.canvas.engine.selection.selected_items:
            if isinstance(item, MarkerItem):
                return item
        return None

    def _on_selection_changed(self, _ids):
        item = self._selected_marker()
        if item is None:
            self._l._panel_mgr.hide("MarcadorEdit")
            self._l._reposition()
            return
        self._l._panel_mgr.show("MarcadorEdit")
        self._l.marker_edit_panel.set_data(item.props, item.pos().x(), item.pos().y(), item.zValue())
        self._l._reposition()

    # ─── Edit panel -> item mutation + persistence ───

    def _on_name_changed(self, text: str):
        item = self._selected_marker()
        if item:
            item.props.name = text
            self._schedule_sync()

    def _on_category_changed(self, key: str):
        item = self._selected_marker()
        if item:
            item.props.category = key
            item.update()
            self._l.marker_edit_panel.update_header(item.props.icon, key)
            self._schedule_sync()

    def _on_icon_changed(self, icon: str):
        item = self._selected_marker()
        if item:
            item.props.icon = icon
            item.update()
            self._l.marker_edit_panel.update_header(icon, item.props.category)
            self._schedule_sync()

    def _on_description_changed(self, text: str):
        item = self._selected_marker()
        if item:
            item.props.description = text
            self._schedule_sync()

    def _on_effects_changed(self, effects: list):
        item = self._selected_marker()
        if item:
            item.props.effects = list(effects)
            item.prepareGeometryChange()
            item.update()
            self._schedule_sync()

    def _on_radius_changed(self, radius: float):
        item = self._selected_marker()
        if item:
            item.props.effect_radius = radius
            item.prepareGeometryChange()
            item.update()
            self._schedule_sync()

    def _on_effect_intensity_changed(self, intensity: float):
        item = self._selected_marker()
        if item:
            item.props.effect_intensity = intensity
            item.update()
            self._schedule_sync()

    # ─── Effects animation ───

    def _tick_effects(self):
        for item in self._l.canvas.engine.viewport.scene().items():
            if isinstance(item, MarkerItem) and item.props.effects:
                item.update()

    # ─── Persistence ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items.clear()
        if not self._uow:
            return

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != "marker":
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            props = MarkerProperties()
            for key, value in meta.items():
                if hasattr(props, key):
                    setattr(props, key, value)
            item = MarkerItem(props)
            item.setPos(row["position_x"], row["position_y"])
            item.setRotation(row["rotation"] or 0.0)
            item.setZValue(60)
            item.setData(1, row["id"])
            scene.addItem(item)
            self._items[row["id"]] = item

    def _schedule_sync(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            if not isinstance(item, MarkerItem) or not item.isVisible():
                continue
            fields = dict(
                item_type="marker", name=item.props.name,
                position_x=item.pos().x(), position_y=item.pos().y(),
                rotation=item.rotation(),
                metadata=json.dumps(dataclasses.asdict(item.props)),
            )
            row_id = item.data(1)
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            self._items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._items[stale_id]
