"""BrushMediator — brush panel + asset browser ↔ canvas engine wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class BrushMediator:
    """Manages brush panel ↔ canvas engine connections."""

    def __init__(self, layout: MainLayout):
        self._l = layout

    def connect_panel(self):
        """Connect brush config panel + asset browser panel to BrushEngine."""
        engine = self._l.canvas.engine.brush_engine
        panel = self._l.brush_panel
        browser = self._l.asset_browser_panel
        brush_tool = self._l.canvas.engine._brush_tool

        panel.size_slider.set_value(engine.config.size)
        panel.opacity_slider.set_value(engine.config.opacity * 100)
        panel.density_slider.set_value(engine.config.density)
        panel.softness_slider.set_value(brush_tool.softness * 100)
        panel.scale_slider.set_value(brush_tool.texture_scale * 100)
        panel.rotation_slider.set_value(brush_tool.texture_rotation)
        panel.roughness_slider.set_value(brush_tool.roughness * 100)
        panel.smoothness_slider.set_value(brush_tool.smoothness * 100)

        for sig in (panel.size_slider.value_changed, panel.opacity_slider.value_changed,
                    panel.softness_slider.value_changed, panel.density_slider.value_changed,
                    panel.scale_slider.value_changed, panel.rotation_slider.value_changed,
                    panel.roughness_slider.value_changed, panel.smoothness_slider.value_changed,
                    panel.mode_changed, panel.terrain_changed, panel.random_rotation_check.toggled,
                    browser.asset_selected, browser.favorite_toggled,
                    browser.tab_changed, browser.style_changed):
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
        panel.roughness_slider.value_changed.connect(self._on_roughness_changed)
        panel.smoothness_slider.value_changed.connect(self._on_smoothness_changed)
        panel.random_rotation_check.toggled.connect(lambda on: setattr(brush_tool, 'random_rotation', on))
        panel.mode_changed.connect(self.on_mode_changed)
        panel.terrain_changed.connect(self._on_terrain_target_changed)
        browser.asset_selected.connect(self.on_asset_selected)
        browser.tab_changed.connect(self.on_tab_changed)
        browser.favorite_toggled.connect(self.on_favorite_toggled)
        browser.style_changed.connect(self.on_style_changed)

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

        # "Pintando em" dropdown — targeted disconnect only (never a blanket
        # `.disconnect()`, these signals are shared with TerrainMediator's
        # own connections made once in main_layout.py). Refreshes the
        # option list whenever terrains are added/renamed/removed; doesn't
        # touch the current selection (set_terrain_options keeps it).
        terrain_panel = self._l.terrain_panel
        for sig in (terrain_panel.terrain_added, terrain_panel.terrain_renamed,
                    terrain_panel.terrain_removed):
            try:
                sig.disconnect(self._on_terrain_context_changed)
            except (RuntimeError, TypeError):
                pass
            sig.connect(self._on_terrain_context_changed)
        self._on_terrain_context_changed()

        # Populate grid with current active tab
        self.populate_assets(browser.current_category())

    def _on_terrain_context_changed(self, *_args):
        self._l.brush_panel.set_terrain_options(self._terrain_options())

    def _terrain_options(self) -> list[tuple[str, str]]:
        """(terrain_id, name) for every terrain that currently exists —
        feeds the "Pintando em" dropdown."""
        cards = self._l.terrain_panel._cards
        return [(tid, card.name) for tid, card in cards.items()]

    def _on_terrain_target_changed(self, terrain_id: str):
        """"Pintando em" dropdown picked a terrain (or "" for Mapa
        Infinito) — constrains the terrain brush to it, same mechanism
        TerrainMediator already uses for the currently-selected terrain
        card, just driven independently from this panel."""
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._l.canvas.engine._brush_tool.set_active_boundary(boundary)

    def populate_assets(self, category: str = None):
        """Load asset thumbnails into the asset browser grid.

        Filtered by both `category` (the browser's own tabs) and the style
        currently selected on the brush config panel — a "Cartoon" terrain
        pick shouldn't show up while browsing "Realistic" terrain.
        """
        asset_engine = self._l.canvas.engine._asset_engine
        if not asset_engine or not hasattr(asset_engine, 'library'):
            return
        library = asset_engine.library
        if not library:
            return

        style = self._l.asset_browser_panel.current_style()

        if category == "__favorites__":
            assets = library.list_favorites(style=style)
        elif category:
            assets = library.list_by_category(category, style=style)
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
        self._l.asset_browser_panel.set_assets(items)

    def on_style_changed(self, style: str):
        self.populate_assets(self._l.asset_browser_panel.current_category())

    def on_asset_selected(self, asset_id: str):
        self._l._ensure_project()
        engine = self._l.canvas.engine.brush_engine
        engine.clear_assets()
        engine.add_asset(asset_id)
        self._l.canvas.engine._brush_tool.set_active_asset(asset_id)
        if self._l.canvas.engine._asset_engine:
            library = getattr(self._l.canvas.engine._asset_engine, 'library', None)
            if library:
                name = library.get_name_by_id(asset_id)
                if name:
                    self._l.brush_panel.set_material_name(name)
            pixmap = self._l.canvas.engine._asset_engine.get_pixmap(asset_id)
            window = self._l.window()
            if window and hasattr(window, 'uow') and window.uow:
                settings = window.uow.asset_settings.get(asset_id)
                brightness = settings.get("brightness", 0.0)
                contrast = settings.get("contrast", 0.0)
                if (brightness != 0.0 or contrast != 0.0) and pixmap and not pixmap.isNull():
                    pixmap = self._apply_adjustments(pixmap, brightness, contrast)
            self._l.brush_panel.set_texture_preview(pixmap)
        # Picking a material is the end of the browsing task — close the
        # sub-panel and hand focus back to the compact brush config.
        self._l.asset_browser_panel.hide()
        self._l._reposition()

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
            self.populate_assets(self._l.asset_browser_panel.current_category())

    def on_library_changed(self, _name: str):
        if self._l.asset_browser_panel.isVisible():
            self.populate_assets(self._l.asset_browser_panel.current_category())

    def on_texture_scale_changed(self, value):
        brush_tool = self._l.canvas.engine._brush_tool
        brush_tool.texture_scale = value / 100.0
        self._l.brush_panel.texture_preview.set_scale(value / 100.0)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)

    def _on_roughness_changed(self, value):
        # Applies equivalently to both brush systems: jagged edge for
        # terrain's soft circular stamp, extra placement jitter for
        # object stamps (see BrushTool/BrushEngine).
        brush_tool = self._l.canvas.engine._brush_tool
        engine = self._l.canvas.engine.brush_engine
        brush_tool.roughness = value / 100.0
        engine.config.roughness = value / 100.0

    def _on_smoothness_changed(self, value):
        brush_tool = self._l.canvas.engine._brush_tool
        engine = self._l.canvas.engine.brush_engine
        brush_tool.smoothness = value / 100.0
        engine.config.smoothness = value / 100.0

    def on_texture_rotation_changed(self, value):
        brush_tool = self._l.canvas.engine._brush_tool
        brush_tool.texture_rotation = value
        self._l.brush_panel.texture_preview.set_rotation(value)
        if brush_tool._active_asset_id and brush_tool._active_asset_id in brush_tool._terrain_layers:
            layer = brush_tool._terrain_layers[brush_tool._active_asset_id]
            layer.set_texture_transform(brush_tool.texture_scale, brush_tool.texture_rotation)
