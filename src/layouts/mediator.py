"""Layout Mediator — handles signal connections between panels and canvas engine."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class BrushMediator:
    """Manages brush panel ↔ canvas engine connections."""

    def __init__(self, layout: MainLayout):
        self._l = layout

    def connect_panel(self):
        """Connect brush panel sliders to BrushEngine."""
        engine = self._l.canvas.engine.brush_engine
        panel = self._l.brush_panel
        brush_tool = self._l.canvas.engine._brush_tool

        panel.size_slider.set_value(engine.config.size)
        panel.opacity_slider.set_value(engine.config.opacity * 100)
        panel.density_slider.set_value(engine.config.density)
        panel.softness_slider.set_value(brush_tool.softness * 100)
        panel.scale_slider.set_value(brush_tool.texture_scale * 100)
        panel.rotation_slider.set_value(brush_tool.texture_rotation)

        for sig in (panel.size_slider.value_changed, panel.opacity_slider.value_changed,
                    panel.softness_slider.value_changed, panel.density_slider.value_changed,
                    panel.scale_slider.value_changed, panel.rotation_slider.value_changed,
                    panel.asset_selected, panel.favorite_toggled,
                    panel.mode_changed, panel.tab_changed,
                    panel.random_rotation_check.toggled):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError):
                pass

        panel.size_slider.value_changed.connect(self.on_size_changed)
        panel.opacity_slider.value_changed.connect(self.on_opacity_changed)
        panel.softness_slider.value_changed.connect(lambda v: setattr(brush_tool, 'softness', v / 100.0))
        panel.density_slider.value_changed.connect(engine.set_density)
        panel.scale_slider.value_changed.connect(self.on_texture_scale_changed)
        panel.rotation_slider.value_changed.connect(self.on_texture_rotation_changed)
        panel.random_rotation_check.toggled.connect(lambda on: setattr(brush_tool, 'random_rotation', on))
        panel.asset_selected.connect(self.on_asset_selected)
        panel.tab_changed.connect(self.on_tab_changed)
        panel.favorite_toggled.connect(self.on_favorite_toggled)
        panel.mode_changed.connect(self.on_mode_changed)

        # Library change watcher
        asset_engine = self._l.canvas.engine._asset_engine
        if asset_engine and hasattr(asset_engine, 'library') and asset_engine.library:
            library = asset_engine.library
            try:
                library.asset_added.disconnect(self.on_library_changed)
                library.asset_removed.disconnect(self.on_library_changed)
            except (RuntimeError, TypeError):
                pass
            library.asset_added.connect(self.on_library_changed)
            library.asset_removed.connect(self.on_library_changed)

        # Populate grid with current active tab
        idx = next((i for i, b in enumerate(panel._tab_buttons) if b.isChecked()), 0)
        cats = panel._tab_categories
        self.populate_assets(cats[idx] if idx < len(cats) else None)

    def populate_assets(self, category: str = None):
        """Load asset thumbnails into the brush panel grid."""
        asset_engine = self._l.canvas.engine._asset_engine
        if not asset_engine or not hasattr(asset_engine, 'library'):
            return
        library = asset_engine.library
        if not library:
            return

        if category == "__favorites__":
            assets = library.list_favorites()
        elif category:
            assets = library.list_by_category(category)
        else:
            assets = library.list_all()

        items = []
        for asset in assets:
            thumb = library.thumbnails.get_pixmap(asset.id)
            items.append({
                "id": asset.id,
                "name": asset.name,
                "pixmap": thumb,
                "favorite": library.is_favorite(asset.id),
            })
        self._l.brush_panel.set_assets(items)

    def on_asset_selected(self, asset_id: str):
        self._l._ensure_project()
        engine = self._l.canvas.engine.brush_engine
        engine.clear_assets()
        engine.add_asset(asset_id)
        self._l.canvas.engine._brush_tool.set_active_asset(asset_id)
        if self._l.canvas.engine._asset_engine:
            pixmap = self._l.canvas.engine._asset_engine.get_pixmap(asset_id)
            window = self._l.window()
            if window and hasattr(window, 'uow') and window.uow:
                settings = window.uow.asset_settings.get(asset_id)
                brightness = settings.get("brightness", 0.0)
                contrast = settings.get("contrast", 0.0)
                if (brightness != 0.0 or contrast != 0.0) and pixmap and not pixmap.isNull():
                    pixmap = self._apply_adjustments(pixmap, brightness, contrast)
            self._l.brush_panel.set_texture_preview(pixmap)

    def _apply_adjustments(self, pixmap: QPixmap, brightness: float, contrast: float) -> QPixmap:
        from PySide6.QtGui import QImage
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        b = brightness / 100.0
        c = (contrast + 100.0) / 100.0
        c = c * c
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                r = max(0.0, min(1.0, (color.redF() - 0.5) * c + 0.5 + b))
                g = max(0.0, min(1.0, (color.greenF() - 0.5) * c + 0.5 + b))
                bl = max(0.0, min(1.0, (color.blueF() - 0.5) * c + 0.5 + b))
                color.setRedF(r)
                color.setGreenF(g)
                color.setBlueF(bl)
                image.setPixelColor(x, y, color)
        return QPixmap.fromImage(image)

    def on_size_changed(self, value):
        self._l.canvas.engine.brush_engine.set_size(value)
        self._l.canvas.engine._brush_tool.update_cursor_size()

    def on_opacity_changed(self, value):
        self._l.canvas.engine.brush_engine.set_opacity(value / 100.0)
        self._l.brush_panel.texture_preview.set_opacity(value / 100.0)

    def on_mode_changed(self, mode: str):
        brush_tool = self._l.canvas.engine._brush_tool
        brush_tool.erase_mode = (mode == "erase")
        brush_tool.mask_mode = (mode == "mask")

    def on_tab_changed(self, category: str):
        self.populate_assets(category if category else None)

    def on_favorite_toggled(self, asset_id: str):
        asset_engine = self._l.canvas.engine._asset_engine
        if not asset_engine or not hasattr(asset_engine, 'library'):
            return
        library = asset_engine.library
        if library:
            library.toggle_favorite(asset_id)
            idx = next((i for i, b in enumerate(self._l.brush_panel._tab_buttons) if b.isChecked()), 0)
            cats = self._l.brush_panel._tab_categories
            cat = cats[idx] if idx < len(cats) else None
            self.populate_assets(cat if cat else None)

    def on_library_changed(self, _name: str):
        if self._l.brush_panel.isVisible():
            idx = next((i for i, b in enumerate(self._l.brush_panel._tab_buttons) if b.isChecked()), 0)
            cats = self._l.brush_panel._tab_categories
            cat = cats[idx] if idx < len(cats) else None
            self.populate_assets(cat if cat else None)

    def on_texture_scale_changed(self, value):
        brush_tool = self._l.canvas.engine._brush_tool
        brush_tool.texture_scale = value / 100.0
        self._l.brush_panel.texture_preview.set_scale(value / 100.0)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)

    def on_texture_rotation_changed(self, value):
        brush_tool = self._l.canvas.engine._brush_tool
        brush_tool.texture_rotation = value
        self._l.brush_panel.texture_preview.set_rotation(value)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)


class TerrainMediator:
    """Manages terrain panel ↔ canvas engine connections."""

    def __init__(self, layout: MainLayout):
        self._l = layout
        from src.canvas.map_boundary import MapBoundary
        self._boundaries: dict[str, MapBoundary] = {}

    @property
    def boundaries(self):
        return self._boundaries

    def on_infinite(self, infinite: bool):
        if infinite:
            self._l.canvas.engine.clear_map_bounds()
            self._l.canvas.engine._brush_tool.set_active_boundary(None)
            for boundary in self._boundaries.values():
                boundary.hide()
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
        self._l._reposition()

    def on_dims(self, width: int, height: int):
        if not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine.set_map_bounds(width, height, self._l.terrain_panel.map_shape)
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id:
            boundary = self._boundaries.get(sel_id)
            if boundary and boundary.visible:
                boundary.update_dimensions(width, height)

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
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)

    def on_added(self, terrain_id: str, name: str):
        self._l._ensure_project()
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
            boundary.set_position(view_center)
        self._boundaries[terrain_id] = boundary
        if self._l.terrain_panel.selected_terrain_id == terrain_id and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(boundary)

    def on_removed(self, terrain_id: str):
        boundary = self._boundaries.pop(terrain_id, None)
        if boundary:
            boundary.hide()
        sel_id = self._l.terrain_panel.selected_terrain_id
        if sel_id and not self._l.terrain_panel.is_infinite:
            self._l.canvas.engine._brush_tool.set_active_boundary(self._boundaries.get(sel_id))
        else:
            self._l.canvas.engine._brush_tool.set_active_boundary(None)

    def on_background(self, bg_type: str, value: str):
        viewport = self._l.canvas.engine.viewport
        if bg_type == "none":
            viewport.set_background(None, None)
        elif bg_type == "color":
            viewport.set_background(QColor(value), None)
        elif bg_type in ("image", "gif"):
            ext = value.rsplit(".", 1)[-1].lower() if value else ""
            if ext in ("mp4", "webm", "mov"):
                viewport.set_video_background(value)
            else:
                pix = QPixmap(value)
                if not pix.isNull():
                    viewport.set_background(None, pix)
                else:
                    viewport.set_background(None, None)


class GridMediator:
    """Manages grid panel ↔ canvas engine connections."""

    def __init__(self, layout: MainLayout):
        self._l = layout

    def connect_panel(self):
        grid = self._l.canvas.engine.grid
        panel = self._l.grid_panel

        panel.size_slider.set_value(grid.cell_size)
        panel.subdivisions_slider.set_value(grid.subdivisions)
        panel.snap_check.setChecked(True)

        for sig in (panel.size_slider.value_changed, panel.subdivisions_slider.value_changed,
                    panel.opacity_slider.value_changed, panel.snap_toggled, panel.shape_changed):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError, RuntimeWarning):
                pass

        def _update_size(v):
            grid.cell_size = int(v)
            self._l.canvas.engine._update_grid()

        def _update_sub(v):
            grid.subdivisions = int(v)
            self._l.canvas.engine._update_grid()

        def _update_opacity(v):
            alpha_major = int(v * 2.55)
            alpha_minor = int(v * 1.0)
            grid.color_major = QColor(255, 255, 255, min(255, alpha_major))
            grid.color_minor = QColor(255, 255, 255, min(255, alpha_minor))
            self._l.canvas.engine._update_grid()

        def _update_shape(shape_name):
            grid.shape = shape_name
            self._l.canvas.engine._update_grid()

        panel.size_slider.value_changed.connect(_update_size)
        panel.subdivisions_slider.value_changed.connect(_update_sub)
        panel.opacity_slider.value_changed.connect(_update_opacity)
        panel.shape_changed.connect(_update_shape)
        panel.snap_toggled.connect(lambda on: self._l.canvas.engine.snap.toggle())
