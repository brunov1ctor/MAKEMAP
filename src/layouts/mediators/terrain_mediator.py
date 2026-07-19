"""TerrainMediator — terrain panel ↔ canvas engine wiring."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPixmap

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class TerrainMediator:
    """Manages terrain panel ↔ canvas engine connections."""

    _STAGGER_STEP = 120.0
    _STAGGER_WRAP = 8

    def __init__(self, layout: MainLayout):
        self._l = layout
        from src.canvas.map_boundary import MapBoundary
        self._boundaries: dict[str, MapBoundary] = {}
        self._preview_boundary: MapBoundary | None = None

        # Which parallax preset (if any) is currently the live background —
        # so an edit made in the Config panel (rename/add layer/JSON import/
        # reorder) can refresh the canvas immediately instead of leaving it
        # showing a stale snapshot from before the edit.
        self._active_parallax_key: str | None = None
        from src.engines.map.parallax import get_parallax_library
        get_parallax_library().changed.connect(self._on_parallax_library_changed)

    @property
    def boundaries(self):
        return self._boundaries

    def _show_preview(self):
        """Dashed draft outline for the very first terrain, before "+ Novo"
        has been clicked — lets shape/size choices be seen on the map right
        away instead of only after a terrain already exists to edit."""
        from src.canvas.map_boundary import MapBoundary
        if self._preview_boundary is None:
            scene = self._l.canvas.engine.viewport.scene()
            self._preview_boundary = MapBoundary(scene)
        w = self._l.terrain_panel.map_width
        h = self._l.terrain_panel.map_height
        shape = self._l.terrain_panel.map_shape
        was_hidden = not self._preview_boundary.visible
        self._preview_boundary.show_preview(w, h, shape)
        if was_hidden:
            view_center = self._l.canvas.engine.viewport.mapToScene(
                self._l.canvas.engine.viewport.viewport().rect().center()
            )
            self._preview_boundary.set_position(view_center)

    def _hide_preview(self):
        if self._preview_boundary is not None:
            self._preview_boundary.hide()

    def _stagger_offset(self) -> QPointF:
        """Offsets each newly created terrain's spawn point away from the
        view center so it doesn't land exactly on top of an existing
        bounded terrain. All bounded terrains are shown simultaneously
        today — TerrainCard has no working hide toggle (its only button is
        a locate/find action) — so this isn't a rare edge case."""
        n = len(self._boundaries) % self._STAGGER_WRAP
        return QPointF(self._STAGGER_STEP * n, self._STAGGER_STEP * n)

    def _sync_all_boundaries(self):
        """Keeps the brush tool's full boundary list current so the grid
        overlay can clip across every bounded terrain at once (see
        CanvasEngine._update_grid), not just whichever one is selected."""
        self._l.canvas.engine._brush_tool.set_all_boundaries(list(self._boundaries.values()))
        self._l.canvas.engine._update_grid()

    def on_infinite(self, infinite: bool):
        if infinite:
            self._l.canvas.engine.clear_map_bounds()
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
            for boundary in self._boundaries.values():
                boundary.hide()
            self._hide_preview()
        else:
            w = self._l.terrain_panel.map_width
            h = self._l.terrain_panel.map_height
            shape = self._l.terrain_panel.map_shape
            self._l.canvas.engine.set_map_bounds(w, h, shape)
            for tid, boundary in self._boundaries.items():
                card = self._l.terrain_panel._cards.get(tid)
                if card and card.is_visible:
                    boundary.show(w, h, shape)
            sel_id = self._l.terrain_panel.selected_terrain_id
            if sel_id:
                self._l.canvas.engine._brush_tool.set_active_boundary(self._boundaries.get(sel_id))
        self._sync_all_boundaries()
        self._l._reposition()

    def on_dims(self, width: int, height: int):
        if not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine.set_map_bounds(width, height, self._l.terrain_panel.map_shape)
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id:
            boundary = self._boundaries.get(sel_id)
            if boundary and boundary.visible:
                boundary.update_dimensions(width, height)
        elif not self._l.terrain_panel.is_infinite:
            self._show_preview()
        self._l.canvas.engine._update_grid()

    def on_shape(self, shape: str):
        if not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine.set_map_bounds(
                self._l.terrain_panel.map_width, self._l.terrain_panel.map_height, shape
            )
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id:
            boundary = self._boundaries.get(sel_id)
            if boundary and boundary.visible:
                boundary.update_shape(shape)
        elif not self._l.terrain_panel.is_infinite:
            self._show_preview()
        self._l.canvas.engine._update_grid()

    def on_visibility(self, terrain_id: str, visible: bool):
        if self._l.terrain_panel.is_infinite:
            return
        boundary = self._boundaries.get(terrain_id)
        if not boundary:
            return
        w = self._l.terrain_panel.map_width
        h = self._l.terrain_panel.map_height
        shape = self._l.terrain_panel.map_shape
        if visible:
            boundary.show(w, h, shape)
            if boundary.position.isNull():
                view_center = self._l.canvas.engine.viewport.mapToScene(
                    self._l.canvas.engine.viewport.viewport().rect().center()
                )
                boundary.set_position(view_center)
            self._fit_to_boundary(boundary)
        else:
            boundary.hide()
        self._sync_all_boundaries()

    def _fit_to_boundary(self, boundary):
        if not boundary._item:
            return
        rect = boundary._item.mapToScene(boundary._item.boundingRect()).boundingRect()
        padding = 80
        rect.adjust(-padding, -padding, padding, padding)
        self._l.canvas.engine.viewport.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        new_zoom = self._l.canvas.engine.viewport.transform().m11()
        self._l.canvas.engine.viewport._zoom = new_zoom
        self._l.canvas.engine.viewport.zoom_changed.emit(new_zoom)
        self._l.canvas.engine.viewport.view_changed.emit()

    def on_selected(self, terrain_id: str):
        boundary = self._boundaries.get(terrain_id)
        if not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(boundary)
            if boundary:
                self._l.terrain_panel.sync_from_boundary(
                    boundary.shape, boundary.width, boundary.height
                )
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
        self._l.canvas.engine._update_grid()

    def on_added(self, terrain_id: str, name: str):
        self._l._ensure_project()
        self._hide_preview()
        from src.canvas.map_boundary import MapBoundary
        scene = self._l.canvas.engine.viewport.scene()
        card = self._l.terrain_panel._cards.get(terrain_id)
        color = None
        if card:
            swatch = card.layout().itemAt(0).widget()
            if swatch:
                ss = swatch.styleSheet()
                m = re.search(r'background:\s*(#[0-9a-fA-F]{6})', ss)
                if m:
                    color = QColor(m.group(1))
        boundary = MapBoundary(scene, color)
        w = self._l.terrain_panel.map_width
        h = self._l.terrain_panel.map_height
        shape = self._l.terrain_panel.map_shape
        if not self._l.terrain_panel.is_infinite:
            boundary.show(w, h, shape)
            view_center = self._l.canvas.engine.viewport.mapToScene(
                self._l.canvas.engine.viewport.viewport().rect().center()
            )
            boundary.set_position(view_center + self._stagger_offset())
        self._boundaries[terrain_id] = boundary
        if self._l.terrain_panel.selected_terrain_id == terrain_id and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(boundary)
        self._sync_all_boundaries()

    def on_removed(self, terrain_id: str):
        boundary = self._boundaries.pop(terrain_id, None)
        if boundary:
            boundary.hide()
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(self._boundaries.get(sel_id))
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
        self._sync_all_boundaries()

    def on_background(self, bg_type: str, value: str):
        viewport = self._l.canvas.engine.viewport
        self._active_parallax_key = value if bg_type == "parallax" else None
        if bg_type == "none":
            viewport.set_background(None, None)
        elif bg_type == "color":
            viewport.set_background(QColor(value), None)
        elif bg_type == "image":
            pix = QPixmap(value)
            if not pix.isNull():
                viewport.set_background(None, pix)
            else:
                viewport.set_background(None, None)
        elif bg_type == "parallax":
            from src.engines.map.parallax import get_parallax_library
            preset = get_parallax_library().get_preset(value)
            if preset and preset.layers:
                viewport.set_parallax_layers(preset.layers)
            else:
                viewport.clear_parallax()

    def _on_parallax_library_changed(self):
        """Re-applies the currently active parallax preset whenever its data
        changes (Config panel edits, JSON import, layer reorder, etc.) — so
        the canvas stays in sync without the user having to reselect the
        preset in the Terrain panel."""
        if self._active_parallax_key:
            self.on_background("parallax", self._active_parallax_key)
