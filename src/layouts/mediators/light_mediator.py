"""LightMediator — owns everything specific to the Iluminação tool: type
picker panel wiring (arms LightTool), placement, selection -> edit panel,
edit panel field changes -> live update + persistence, and the shadow/
volumetric refresh timer. Self-contained (mirrors MarkerMediator/
RegionMediator's style) rather than a wall of handlers in main_layout.py.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from src.canvas.light_item import LightItem
from src.canvas.lighting_overlay import GlobalLightingOverlay
from src.engines.light import GLOBAL_TYPES, LightProperties, default_color, default_intensity
from src.layouts.panels.light.panel import LightPanel
from src.layouts.panels.light.edit_panel import LightEditPanel
from src.layouts.panels.light.sky_panel import SkyEditPanel

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_SYNC_DEBOUNCE_MS = 250
_REFRESH_TICK_MS = 150
# Periodic safety-net: force the overlay's lights-list cache to refresh
# every N ticks regardless, bounding worst-case staleness for any light
# add/remove path not explicitly hooked to mark_lights_dirty() below.
_REFRESH_SAFETY_NET_TICKS = 20
# The global "sky" setting isn't a canvas_items row (see GLOBAL_TYPES) — it
# lives in the generic ui_state key/value store instead (UIStateRepository).
_SKY_UI_STATE_KEY = "light_sky::default"  # matches LightMediator.MAP_ID


class LightMediator:
    MAP_ID = "default"

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._pending_type = "point"
        self._items: dict[str, LightItem] = {}  # canvas_items row id -> LightItem
        # Single global setting, not a placed item — see GLOBAL_TYPES.
        self._sky_props = LightProperties(light_type="sky", color=default_color("sky"))

        # Iluminação — same dual-exclusive-slot trick as Marcador: LightPanel
        # (type picker, opened by the toolbar toggle) and LightEditPanel
        # (per-light editor, opened on selection) never show together.
        panel = LightPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_light_panel)
        self._l.light_panel = panel
        panel.type_picked.connect(self._on_type_picked)

        edit = LightEditPanel(self._l)
        edit.hide()
        edit.close_requested.connect(self._l._close_light_edit_panel)
        edit.content_changed.connect(self._l._reposition)
        self._l.light_edit_panel = edit
        edit.type_changed.connect(self._on_type_changed)
        edit.intensity_changed.connect(self._on_intensity_changed)
        edit.radius_changed.connect(self._on_radius_changed)
        edit.falloff_changed.connect(self._on_falloff_changed)
        edit.color_changed.connect(self._on_color_changed)
        edit.shadows_changed.connect(self._on_shadows_changed)
        edit.volumetric_changed.connect(self._on_volumetric_changed)
        edit.direction_changed.connect(self._on_direction_changed)
        edit.cone_changed.connect(self._on_cone_changed)

        # "Sky" is a global day/night setting, not a placed object (see
        # GLOBAL_TYPES) — its own exclusive slot, opened directly from
        # LightPanel instead of arming a placement tool.
        sky = SkyEditPanel(self._l)
        sky.hide()
        sky.close_requested.connect(self._l._close_sky_edit_panel)
        sky.content_changed.connect(self._l._reposition)
        self._l.sky_edit_panel = sky
        sky.day_amount_changed.connect(self._on_sky_day_amount_changed)
        sky.color_changed.connect(self._on_sky_color_changed)

        self._l.canvas.engine._light_tool.set_properties_provider(self._provide_properties)
        self._l.canvas.engine._light_tool.set_parent_provider(lambda: self._active_boundary.group if self._active_boundary and self._active_boundary._item else None)
        self._l.canvas.engine.selection.selection_changed.connect(self._on_selection_changed)

        self._overlay = GlobalLightingOverlay()
        self._overlay.set_sky(self._sky_props)
        self._l.canvas.engine.viewport.scene().addItem(self._overlay)
        # Every LightItem (however constructed — placed fresh or loaded from
        # the DB) reports straight to this overlay when it moves, instead of
        # the overlay only finding out up to _REFRESH_TICK_MS later.
        LightItem.bind_overlay(self._overlay)
        # Assets/mobs (the things lights can be occluded by) moving is the
        # other half of "something changed" the periodic tick used to be the
        # only way to catch — TransformEngine already emits these for every
        # drag/rotate/resize, so reuse them instead of polling blind.
        self._l.canvas.engine.transform.items_moved.connect(self._on_occluders_moved)
        self._l.canvas.engine.transform.transform_finished.connect(self._on_occluders_moved)

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._schedule_sync)
        # history_changed also fires for light placement/deletion (both go
        # through the generic undo stack — PlaceObjectCommand and generic
        # multi-select delete — with no dedicated LightMediator.on_removed
        # choke point), so it's reused here to keep the overlay's lights
        # cache in sync with the scene's actual light set.
        self._l.canvas.engine.history.history_changed.connect(self._overlay.mark_lights_dirty)

        self._sky_sync_timer = QTimer()
        self._sky_sync_timer.setSingleShot(True)
        self._sky_sync_timer.timeout.connect(self._sync_sky_to_db)

        self._refresh_tick_count = 0
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._tick_refresh)
        self._refresh_timer.start(_REFRESH_TICK_MS)

    # ─── Type picker -> arm tool (or, for "sky", open its global panel) ───

    def _on_type_picked(self, key: str):
        if key in GLOBAL_TYPES:
            self._l._panel_mgr.show("SkyEdit")
            self._l.sky_edit_panel.set_data(self._sky_props)
            self._l._reposition()
            return
        self._pending_type = key
        self._l.canvas.engine.tool_manager.activate("Luz")

    def set_active_terrain(self, terrain_id: str):
        """Chamado por TerrainMediator.on_selected para sincronizar o label e o boundary ativo."""
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._active_boundary = boundary
        self._l.light_panel.terrain_combo.set_terrain(terrain_id)

    def _provide_properties(self) -> LightProperties:
        return LightProperties(
            light_type=self._pending_type, color=default_color(self._pending_type),
            intensity=default_intensity(self._pending_type),
        )

    # ─── Sky panel -> global setting mutation + persistence ───

    def _on_sky_day_amount_changed(self, value: float):
        self._sky_props.day_amount = value
        self._overlay.prepareGeometryChange()
        self._overlay.update()
        self._sky_sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _on_sky_color_changed(self, hex_color: str):
        self._sky_props.color = hex_color
        self._overlay.update()
        self._sky_sync_timer.start(_SYNC_DEBOUNCE_MS)

    # ─── Selection -> edit panel ───

    def _selected_light(self) -> LightItem | None:
        for item in self._l.canvas.engine.selection.selected_items:
            if isinstance(item, LightItem):
                return item
        return None

    def _on_selection_changed(self, _ids):
        item = self._selected_light()
        if item is None:
            self._l._panel_mgr.hide("LightEdit")
            self._l._reposition()
            return
        self._l._panel_mgr.show("LightEdit")
        self._l.light_edit_panel.set_data(item.props, item.pos().x(), item.pos().y())
        self._l._reposition()

    # ─── Edit panel -> item mutation + persistence ───

    def _refresh_handles(self, item: LightItem):
        """Re-sync the TransformEngine selection border/handles to the
        item's current geometry — needed whenever a field that changes its
        boundingRect (radius, cone angle/direction, type) is edited from
        the panel, since that path only calls item.update()/
        prepareGeometryChange() on the item itself and never re-runs
        show_handles(); left alone, the purple selection box stays frozen
        at whatever size it was when the item was first selected, visibly
        drifting out of sync with the (now smaller/bigger/rotated) cone or
        radius gizmo drawn on top of it."""
        if item in self._l.canvas.engine.selection.selected_items:
            self._l.canvas.engine.transform.show_handles([item])

    def _on_type_changed(self, key: str):
        item = self._selected_light()
        if item:
            item.props.light_type = key
            item.prepareGeometryChange()
            item.update()
            self._refresh_handles(item)
            self._overlay.prepareGeometryChange()
            self._overlay.update()
            self._schedule_sync()

    def _on_intensity_changed(self, value: float):
        item = self._selected_light()
        if item:
            item.props.intensity = value
            item.update()
            self._schedule_sync()

    def _on_radius_changed(self, value: float):
        item = self._selected_light()
        if item:
            item.props.radius = value
            item.prepareGeometryChange()
            item.update()
            self._refresh_handles(item)
            # The overlay's own boundingRect()/animated_footprint() unions
            # each light's own radius-dependent footprint (see
            # GlobalLightingOverlay._light_footprint) — its declared
            # geometry needs to grow/shrink with it too.
            self._overlay.prepareGeometryChange()
            self._overlay.update()
            self._schedule_sync()

    def _on_falloff_changed(self, value: float):
        item = self._selected_light()
        if item:
            item.props.falloff = value
            self._overlay.update()
            self._schedule_sync()

    def _on_color_changed(self, hex_color: str):
        item = self._selected_light()
        if item:
            item.props.color = hex_color
            item.update()
            self._schedule_sync()

    def _on_shadows_changed(self, enabled: bool):
        item = self._selected_light()
        if item:
            item.props.shadows = enabled
            item.update()
            self._schedule_sync()

    def _on_volumetric_changed(self, enabled: bool):
        item = self._selected_light()
        if item:
            item.props.volumetric = enabled
            item.update()
            self._schedule_sync()

    def _on_direction_changed(self, value: float):
        item = self._selected_light()
        if item:
            item.props.direction_deg = value
            item.update()
            self._refresh_handles(item)
            self._schedule_sync()

    def _on_cone_changed(self, value: float):
        item = self._selected_light()
        if item:
            item.props.cone_angle_deg = value
            item.update()
            self._refresh_handles(item)
            self._schedule_sync()

    # ─── Global illumination refresh ───
    # The overlay's own paint() animates (volumetric beam rotation — driven
    # by time.monotonic(), see
    # lighting_overlay.py), so it needs a periodic repaint tick regardless
    # of whether anything actually moved — there's no "nothing changed,
    # skip the tick" for an animated frame. What the tick no longer has to
    # pay for is redoing the occluder-shadow math on every single fire: with
    # GlobalLightingOverlay's per-light geometry cache (_light_cache),
    # LightItem itself reporting moves instantly (bind_overlay/
    # notify_light_moved) and occluders reporting via _on_occluders_moved
    # below, a tick where nothing relevant changed just reuses cached
    # geometry instead of re-querying the scene and rebuilding shadow
    # polygons for every light.

    def _tick_refresh(self):
        self._refresh_tick_count += 1
        if self._refresh_tick_count % _REFRESH_SAFETY_NET_TICKS == 0:
            self._overlay.mark_lights_dirty()
        rect = self._overlay.animated_footprint()
        if rect is None:
            return
        self._overlay.update(rect)

    def _on_occluders_moved(self, *_args):
        """TransformEngine.items_moved (live, during a drag) / .transform_
        finished (rotate, resize, end of drag) — an asset or mob that could
        occlude a light just changed; bump the overlay's occluder
        generation so cached shadow geometry is recomputed next paint
        instead of only catching up whenever the next timer tick lands."""
        self._overlay.bump_occluder_generation()
        self._overlay.update()

    # ─── Persistence ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()
        self._load_sky_from_db()

    def _load_sky_from_db(self):
        if not self._uow:
            return
        raw = self._uow.ui_state.get(_SKY_UI_STATE_KEY, "")
        try:
            meta = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            meta = {}
        props = LightProperties(light_type="sky", color=default_color("sky"))
        for key, value in meta.items():
            if hasattr(props, key):
                setattr(props, key, value)
        self._sky_props = props
        self._overlay.set_sky(self._sky_props)
        self._overlay.prepareGeometryChange()
        self._overlay.update()

    def _sync_sky_to_db(self):
        if not self._uow:
            return
        self._uow.ui_state.set(_SKY_UI_STATE_KEY, json.dumps(dataclasses.asdict(self._sky_props)))

    def _load_from_db(self):
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._items.clear()
        if not self._uow:
            return

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != "light":
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            props = LightProperties()
            for key, value in meta.items():
                if hasattr(props, key):
                    setattr(props, key, value)
            item = LightItem(props)
            item.setPos(row["position_x"], row["position_y"])
            item.setZValue(60)  # matches light_tool.py's placement z — see its comment
            item.setData(1, row["id"])
            scene.addItem(item)
            self._items[row["id"]] = item
        self._overlay.mark_lights_dirty()

    def _schedule_sync(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            if not isinstance(item, LightItem) or not item.isVisible():
                continue
            fields = dict(
                item_type="light", name=item.props.light_type,
                position_x=item.pos().x(), position_y=item.pos().y(),
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
