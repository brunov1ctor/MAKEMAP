"""BrushMediator — brush panel + asset browser ↔ canvas engine wiring."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPixmap

from src.layouts.panels.brush.panel import BrushToolPanel
from src.layouts.panels.brush.asset_browser import AssetBrowserPanel

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

# Debounce for _sync_to_db — history_changed fires once per completed
# stroke/stamp-group/undo/redo, not per mouse-move, so this just coalesces
# a rapid back-to-back sequence (e.g. undo mashing) into one DB round trip
# rather than gating on every single edit.
_SYNC_DEBOUNCE_MS = 250


class BrushMediator:
    """Manages brush panel ↔ canvas engine connections."""

    MAP_ID = "default"  # matches RegionMediator — neither is scoped to the (unimplemented) maps/worlds hierarchy

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._terrain_rows: dict[str, str] = {}  # asset_id -> painted_terrain row id
        self._stamp_items: dict[str, object] = {}  # canvas_items row id -> QGraphicsPixmapItem

        panel = BrushToolPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_brush_panels)
        panel.assets_requested.connect(self._l._toggle_asset_browser)
        self._l.brush_panel = panel

        # Asset browser (category tabs + search + grid) rides next to
        # brush_panel — opened by clicking the texture preview rectangle
        # (see BrushToolPanel.assets_requested / MainLayout._toggle_asset_browser),
        # same adjacent-panel pattern as RegionEditPanel beside Região's
        # CRUD list.
        browser = AssetBrowserPanel(self._l)
        browser.hide()
        browser.close_requested.connect(self._l._toggle_asset_browser)
        self._l.asset_browser_panel = browser

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._on_history_changed)

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        engine = self._l.canvas.engine
        engine.clear_terrain_layers()
        for item in self._stamp_items.values():
            # May be parented to a boundary item rather than added directly
            # to the scene (see place_stamp_item) — scene.removeItem() on a
            # non-top-level child is unreliable, same reasoning
            # PlaceObjectCommand documents for why it uses visibility
            # instead. Detach first so removal is unambiguous either way.
            item.setParentItem(None)
            scene = item.scene()
            if scene:
                scene.removeItem(item)
        self._stamp_items.clear()
        self._terrain_rows.clear()
        if not self._uow:
            return

        for row in self._uow.painted_terrain.get_by_map(self.MAP_ID):
            layer = engine.get_or_create_terrain_layer(row["asset_id"])
            layer.import_mask_png_base64(row["mask_png"], row["mask_x"], row["mask_y"])
            layer.set_texture_transform(row["texture_scale"], row["texture_rotation"])
            self._terrain_rows[row["asset_id"]] = row["id"]

        # The water/land foam halo (BrushTool._apply_shoreline_blend) is
        # purely derived from the painted masks — never persisted itself
        # — so without recomputing it here, a reloaded project shows every
        # terrain mask correctly but the foam only reappears once the user
        # paints another stroke.
        try:
            engine._brush_tool._apply_shoreline_blend()
        except Exception:
            logger.exception("Falha ao recalcular halo de espuma terra-água ao carregar o projeto")

        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] != "asset":
                continue
            item = engine.place_stamp_item(
                row["asset_id"], QPointF(row["position_x"], row["position_y"]),
                row["rotation"], row["scale_x"], row["opacity"],
            )
            if item is None:
                continue
            self._stamp_items[row["id"]] = item

    def _on_history_changed(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        """Upserts every currently-painted terrain mask + object stamp into
        the project DB, and drops rows for stamps no longer present —
        fired (debounced) off HistoryEngine.history_changed, which already
        covers stroke completion, stamp placement, undo and redo alike."""
        if not self._uow:
            return
        engine = self._l.canvas.engine

        for asset_id, layer in engine.terrain_layers().items():
            mask_png, mask_x, mask_y = layer.export_mask_png_base64()
            fields = dict(
                asset_id=asset_id, mask_png=mask_png, mask_x=mask_x, mask_y=mask_y,
                texture_scale=layer.texture_scale, texture_rotation=layer.texture_rotation,
            )
            row_id = self._terrain_rows.get(asset_id)
            if row_id:
                self._uow.painted_terrain.update(row_id, **fields)
            else:
                self._terrain_rows[asset_id] = self._uow.painted_terrain.create(map_id=self.MAP_ID, **fields)

        seen_ids: set[str] = set()
        for item in engine.viewport.scene().items():
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "asset" or not item.isVisible():
                continue
            center = item.mapToScene(item.boundingRect().center())
            fields = dict(
                item_type="asset", asset_id=data.get("asset_id", ""),
                position_x=center.x(), position_y=center.y(),
                rotation=item.rotation(), scale_x=item.scale(), scale_y=item.scale(),
                opacity=item.opacity(),
            )
            row_id = item.data(1)
            # A cached id can go stale (e.g. undo hid the item, its row got
            # swept as "no longer present" below, then redo brought it back
            # still carrying that dead id) — fall back to creating a fresh
            # row rather than silently no-op'ing an update that matches
            # nothing.
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            self._stamp_items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._stamp_items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._stamp_items[stale_id]

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
                    browser.tab_changed, browser.style_changed, browser.effects_requested):
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
        browser.effects_requested.connect(self._l._asset_effects_med.open_editor)

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

        # First time this session the panel opens with nothing painted yet
        # (BrushTool._active_asset_id starts ""), the brush would otherwise
        # sit empty until the user manually picks a material — default it
        # to whatever was last used in this project, or the first asset in
        # the library on a genuinely first-ever use.
        self._ensure_default_asset(browser)

    _LAST_ASSET_KEY = "last_brush_asset_id"

    def _ensure_default_asset(self, browser):
        brush_tool = self._l.canvas.engine._brush_tool
        if brush_tool._active_asset_id:
            return  # already has one — a real pick this session, don't override it

        asset_engine = self._l.canvas.engine._asset_engine
        library = getattr(asset_engine, "library", None) if asset_engine else None
        if not library:
            return

        window = self._l.window()
        uow = window.uow if window and hasattr(window, "uow") else None

        asset_id = ""
        if uow:
            last_id = uow.ui_state.get(self._LAST_ASSET_KEY, "")
            if last_id and library.get_pixmap(last_id) is not None:
                asset_id = last_id
        if not asset_id:
            # Fall back to whatever's actually first in the CURRENTLY
            # populated grid (not library.list_all()[0]) — the browser's
            # default tab/category may not be "all assets", so those two
            # "first" answers can disagree; using the grid's own first
            # button guarantees set_selected_asset below finds a match.
            if browser._asset_buttons:
                asset_id = browser._asset_buttons[0].asset_id

        if not asset_id:
            return  # empty library — nothing to default to
        browser.set_selected_asset(asset_id)
        self.on_asset_selected(asset_id)

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
            # "water" is a real category folder too (see
            # engines/assets/library.py's CATEGORY_FOLDERS) — same lookup
            # as any other tab.
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
        window = self._l.window()
        if window and hasattr(window, "uow") and window.uow:
            window.uow.ui_state.set(self._LAST_ASSET_KEY, asset_id)
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
