"""BrushMediator — brush panel + asset browser ↔ canvas engine wiring."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPixmap

from src.canvas.brush_effects_overlay import BrushEffectsOverlay
from src.canvas.tools.brush_tool import BrushTool
from src.canvas.path_item import RiverPathItem, RoadPathItem
from src.engines.map.brush_effects import ANIMATED_EFFECTS
from src.layouts.panels.brush.panel import BrushToolPanel
from src.layouts.panels.brush.asset_browser import AssetBrowserPanel

_PATH_ITEM_CLASSES = {"river_path": RiverPathItem, "road_path": RoadPathItem}

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

# Debounce for _sync_to_db — history_changed fires once per completed
# stroke/stamp-group/undo/redo, not per mouse-move, so this just coalesces
# a rapid back-to-back sequence (e.g. undo mashing) into one DB round trip
# rather than gating on every single edit.
_SYNC_DEBOUNCE_MS = 250

# Repaint tick for BrushEffectsOverlay's animated effects (Névoa, Poeira,
# ...) — same cadence/safety-net pattern RegionMediator used to drive its
# own (now-removed) região effects overlay.
_EFFECTS_TICK_MS = 150
_EFFECTS_SAFETY_NET_TICKS = 20


class BrushMediator:
    """Manages brush panel ↔ canvas engine connections."""

    MAP_ID = "default"  # matches RegionMediator — neither is scoped to the (unimplemented) maps/worlds hierarchy

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._terrain_rows: dict[str, str] = {}  # asset_id -> painted_terrain row id
        self._stamp_items: dict[str, object] = {}  # canvas_items row id -> QGraphicsPixmapItem
        self._path_items: dict[str, object] = {}  # canvas_items row id -> RiverPathItem/RoadPathItem

        panel = BrushToolPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_brush_panels)
        panel.assets_requested.connect(self._l._toggle_asset_browser)
        panel.content_changed.connect(self._l._reposition)
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

        # Rio/Estrada finalize a path directly on the item (see path_tool.py
        # — no press/release/stroke of the tool's own to hang a history push
        # off, unlike BrushTool's terrain strokes), so wire it explicitly
        # here instead. Persistence itself piggybacks on the SAME debounced
        # _sync_to_db this push triggers via history_changed — no separate
        # save call needed.
        self._l.canvas.engine._river_path_tool.on_path_finalized(self._on_path_finalized)
        self._l.canvas.engine._road_path_tool.on_path_finalized(self._on_path_finalized)

        self._effects_overlay = BrushEffectsOverlay()
        self._l.canvas.engine.viewport.scene().addItem(self._effects_overlay)
        self._effects_tick_count = 0
        self._effects_timer = QTimer()
        self._effects_timer.timeout.connect(self._tick_effects)
        self._effects_timer.start(_EFFECTS_TICK_MS)

        # Bounded map, no terreno selected — see BrushTool.on_bounds_missing.
        self._l.canvas.engine._brush_tool.on_bounds_missing = self._on_bounds_missing

    def _on_path_finalized(self, item):
        """A Rio/Estrada trace was just locked in (double-click/Enter/tool
        switch — see path_tool.py). The item is already on the scene and
        visible, so push PlaceObjectCommand purely for undo/redo (same
        visibility-toggle trick brush stamps use — redo() is a harmless
        no-op here since the item's already visible); the push's
        history_changed fires _sync_to_db (debounced), which is what
        actually persists it (see the river_path/road_path loop there)."""
        from src.engines.core.history import PlaceObjectCommand
        self._l.canvas.engine.history.push(PlaceObjectCommand(item))

    def _on_bounds_missing(self):
        self._l.info_modal.show_message(
            "Nenhum terreno selecionado. Crie um terreno antes de pintar, "
            "ou ative o Mapa Infinito."
        )
        self._l._reposition()

    def _tick_effects(self):
        """Drives BrushEffectsOverlay's animated effects (Névoa's
        breathe/drift) — the overlay's paint() is time.monotonic()-driven,
        so it needs to actually repaint on a schedule, but only when some
        stroke is actually animated; otherwise this is a no-op."""
        self._effects_tick_count += 1
        if self._effects_tick_count % _EFFECTS_SAFETY_NET_TICKS == 0:
            self._effects_overlay.mark_dirty()
        if not self._effects_overlay.has_active():
            return
        self._effects_overlay.prepareGeometryChange()
        self._effects_overlay.update()

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    @staticmethod
    def _serialize_path(item) -> str:
        points, controls_out, controls_in = item.export_points()
        return json.dumps({
            "width": item.width,
            "points": [[p.x(), p.y()] for p in points],
            "cout": [[c.x(), c.y()] if c else None for c in controls_out],
            "cin": [[c.x(), c.y()] if c else None for c in controls_in],
        })

    @staticmethod
    def _deserialize_path(metadata_json: str):
        data = json.loads(metadata_json or "{}")
        points = [QPointF(x, y) for x, y in data.get("points", [])]
        controls_out = [QPointF(c[0], c[1]) if c else None for c in data.get("cout", [])]
        controls_in = [QPointF(c[0], c[1]) if c else None for c in data.get("cin", [])]
        return data.get("width", 20.0), points, controls_out, controls_in

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
        for item in self._path_items.values():
            scene = item.scene()
            if scene:
                scene.removeItem(item)
        self._path_items.clear()
        if not self._uow:
            return

        for row in self._uow.painted_terrain.get_by_map(self.MAP_ID):
            asset_id = row["asset_id"]
            if asset_id.startswith(BrushTool.EFFECT_ASSET_PREFIX):
                layer = engine.get_or_create_effect_layer(asset_id)
            else:
                layer = engine.get_or_create_terrain_layer(asset_id)
                layer.set_texture_transform(row["texture_scale"], row["texture_rotation"])
            layer.import_mask_png_base64(row["mask_png"], row["mask_x"], row["mask_y"])
            self._terrain_rows[asset_id] = row["id"]
        self._effects_overlay.mark_dirty()

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
            item_type = row["item_type"]
            if item_type == "asset":
                item = engine.place_stamp_item(
                    row["asset_id"], QPointF(row["position_x"], row["position_y"]),
                    row["rotation"], row["scale_x"], row["opacity"],
                )
                if item is None:
                    continue
                self._stamp_items[row["id"]] = item
            elif item_type in _PATH_ITEM_CLASSES:
                width, points, controls_out, controls_in = self._deserialize_path(row["metadata"])
                if len(points) < 2:
                    continue
                texture = engine._asset_engine.get_pixmap(row["asset_id"]) if engine._asset_engine and row["asset_id"] else None
                item = _PATH_ITEM_CLASSES[item_type](width=width, texture=texture)
                item.setData(0, {"item_type": item_type, "asset_id": row["asset_id"] or ""})
                item.setOpacity(row["opacity"])
                engine.viewport.scene().addItem(item)
                item.load_points(points, controls_out, controls_in)
                self._path_items[row["id"]] = item

    def _on_history_changed(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)
        # Painting/erasing/undoing/redoing an effect stroke can grow, shrink
        # or remove its mask — the overlay's cached active-layers list and
        # bounds need to know, same "mark_dirty on every mutation" pattern
        # RegionMediator used to run for its own (now-removed) effects.
        self._effects_overlay.mark_dirty()

    def _sync_to_db(self):
        """Upserts every currently-painted terrain mask + object stamp into
        the project DB, and drops rows for stamps no longer present —
        fired (debounced) off HistoryEngine.history_changed, which already
        covers stroke completion, stamp placement, undo and redo alike."""
        if not self._uow:
            return
        engine = self._l.canvas.engine

        for asset_id, layer in list(engine.terrain_layers().items()):
            # Layer deletado via lixeira — item removido da cena mas layer
            # ainda no dicionário; drop do DB sem remover do dict (undo
            # pode readicionar o item à cena, e a próxima sync o persiste).
            if layer.item.scene() is None:
                row_id = self._terrain_rows.pop(asset_id, None)
                if row_id:
                    self._uow.painted_terrain.delete(row_id)
                continue
            mask_png, mask_x, mask_y = layer.export_mask_png_base64()
            row_id = self._terrain_rows.get(asset_id)
            if not mask_png:
                if row_id:
                    self._uow.painted_terrain.delete(row_id)
                    del self._terrain_rows[asset_id]
                continue
            fields = dict(
                asset_id=asset_id, mask_png=mask_png, mask_x=mask_x, mask_y=mask_y,
                texture_scale=layer.texture_scale, texture_rotation=layer.texture_rotation,
            )
            if row_id:
                self._uow.painted_terrain.update(row_id, **fields)
            else:
                self._terrain_rows[asset_id] = self._uow.painted_terrain.create(map_id=self.MAP_ID, **fields)

        for asset_id, layer in list(engine.effect_layers().items()):
            if layer.item.scene() is None:
                row_id = self._terrain_rows.pop(asset_id, None)
                if row_id:
                    self._uow.painted_terrain.delete(row_id)
                continue
            mask_png, mask_x, mask_y = layer.export_mask_png_base64()
            row_id = self._terrain_rows.get(asset_id)
            if not mask_png:
                if row_id:
                    self._uow.painted_terrain.delete(row_id)
                    del self._terrain_rows[asset_id]
                continue
            fields = dict(
                asset_id=asset_id, mask_png=mask_png, mask_x=mask_x, mask_y=mask_y,
                effect_key=asset_id[len(BrushTool.EFFECT_ASSET_PREFIX):],
            )
            if row_id:
                self._uow.painted_terrain.update(row_id, **fields)
            else:
                self._terrain_rows[asset_id] = self._uow.painted_terrain.create(map_id=self.MAP_ID, **fields)

        seen_ids: set[str] = set()
        for item in engine.viewport.scene().items():
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "asset" or not item.isVisible():
                continue
            # An effect layer's own _LayerItem is ALSO tagged item_type
            # "asset" (see BrushTool._get_or_create_effect_layer, so it
            # falls under the Select tool's "Assets" filter) but it's a
            # painted mask, not a placed object stamp — its mask already
            # gets persisted in the painted_terrain loop above, so skip it
            # here rather than writing a bogus canvas_items row for it.
            if data.get("effect_key"):
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

        seen_path_ids: set[str] = set()
        for item in engine.viewport.scene().items():
            data = item.data(0)
            item_type = data.get("item_type") if isinstance(data, dict) else None
            # Still mid-trace (not finalized yet) — nothing to persist until
            # it locks in, same reasoning a not-yet-released brush stroke
            # never hits painted_terrain either.
            if item_type not in _PATH_ITEM_CLASSES or item.is_editing() or not item.isVisible():
                continue
            fields = dict(
                item_type=item_type, asset_id=data.get("asset_id", ""),
                opacity=item.opacity(), metadata=self._serialize_path(item),
            )
            row_id = item.data(1)
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            self._path_items[row_id] = item
            seen_path_ids.add(row_id)

        for stale_id in set(self._path_items) - seen_path_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._path_items[stale_id]

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
                    panel.mode_changed, panel.random_rotation_check.toggled,
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

        # Refreshes the terrain label whenever terrains are added/renamed/removed.
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
        self.on_asset_selected(asset_id, switch_tool=False)

    def _on_terrain_context_changed(self, *_args):
        options = self._terrain_options()
        self._l.brush_panel.set_terrain_options(options)
        for panel_attr in ("text_panel", "marker_panel", "spawn_panel", "light_panel"):
            panel = getattr(self._l, panel_attr, None)
            if panel and hasattr(panel, "terrain_combo"):
                panel.terrain_combo.set_options(options)
        self._l._refresh_compass_hud()

    def _terrain_options(self) -> list[tuple[str, str]]:
        cards = self._l.terrain_panel._cards
        return [(tid, card.name) for tid, card in cards.items()]

    def populate_assets(self, category: str = None):
        """Load asset thumbnails into the asset browser grid.

        Filtered by both `category` (the browser's own tabs) and the style
        currently selected on the brush config panel — a "Cartoon" terrain
        pick shouldn't show up while browsing "Realistic" terrain.

        "effects" is a special, style-agnostic category (see BrushTool.
        EFFECT_ASSET_PREFIX/brush_effects.ANIMATED_EFFECTS): unlike a
        terrain texture, an animated effect looks identical regardless of
        which asset style is active, and it isn't a real library file at
        all — so this branch never touches the library/style and instead
        builds a fixed, procedurally-generated list straight from
        ANIMATED_EFFECTS, same list every time.
        """
        if category == "effects":
            from src.engines.assets.effect_configs import get_effect_config
            from src.services.asset_adjustments import apply_brightness_contrast
            from PySide6.QtGui import QImage
            items = []
            for key in ANIMATED_EFFECTS:
                cfg = get_effect_config(key)
                pixmap = None
                if cfg["image_path"]:
                    img = QImage(cfg["image_path"])
                    if not img.isNull():
                        img = apply_brightness_contrast(img, cfg["brightness"], cfg["contrast"])
                        pixmap = QPixmap.fromImage(img)
                items.append({"id": f"{BrushTool.EFFECT_ASSET_PREFIX}{key}", "name": key, "pixmap": pixmap})
            self._l.asset_browser_panel.set_assets(items)
            # Panel height now tracks its content (see AssetBrowserPanel.
            # content_height / PanelLayoutEngine.apply) instead of always
            # filling available space, so a repopulated grid needs an
            # explicit re-layout to actually resize.
            self._l._reposition()
            return

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
        self._l._reposition()

    def on_style_changed(self, style: str):
        self.populate_assets(self._l.asset_browser_panel.current_category())

    def on_asset_selected(self, asset_id: str, switch_tool: bool = True):
        """`switch_tool=False` (see _ensure_default_asset) restores the
        asset/texture state a water/road pick needs without also forcing
        the active canvas tool to Rio/Estrada and the panel to its
        Largura/Opacidade-only layout — appropriate for an explicit user
        click on that asset, not for silently pre-selecting whatever asset
        was last used when a project/app first opens (which used to make
        the very first Pincel click of a session land on the Rio panel
        with no river ever drawn, if the previous session ended on a water
        asset)."""
        engine_obj = self._l.canvas.engine
        engine_obj.brush_engine.clear_assets()
        engine_obj.brush_engine.add_asset(asset_id)
        engine_obj._brush_tool.set_active_asset(asset_id)

        if asset_id.startswith(BrushTool.EFFECT_ASSET_PREFIX):
            self._l.brush_panel.set_material_name(asset_id[len(BrushTool.EFFECT_ASSET_PREFIX):])
            self._l.brush_panel.set_texture_preview(None)
            self._l.asset_browser_panel.hide()
            self._l._reposition()
            return

        # Resolve name + pixmap
        pixmap = None
        name = ""
        if engine_obj._asset_engine:
            library = getattr(engine_obj._asset_engine, 'library', None)
            if library:
                name = library.get_name_by_id(asset_id)
                if name:
                    self._l.brush_panel.set_material_name(name)
            pixmap = engine_obj._asset_engine.get_pixmap(asset_id)
            window = self._l.window()
            if window and hasattr(window, 'uow') and window.uow:
                settings = window.uow.asset_settings.get(asset_id)
                brightness = settings.get("brightness", 0.0)
                contrast = settings.get("contrast", 0.0)
                if (brightness != 0.0 or contrast != 0.0) and pixmap and not pixmap.isNull():
                    pixmap = self._apply_adjustments(pixmap, brightness, contrast)
            self._l.brush_panel.set_texture_preview(pixmap)

        # Water/road assets switch to the dedicated path tool (Rio/Estrada —
        # click-to-add-points bezier tracing, see path_tool.py) instead of
        # being brush-painted like plain terrain; any other category falls
        # back to the standard Brush tool + params panel.
        category = self._asset_category(asset_id)
        if category == "water":
            engine_obj._river_path_tool.set_texture(pixmap, asset_id)
            if switch_tool:
                engine_obj.tool_manager.activate("Rio")
                # Width always comes from the brush's own Size (the same
                # Tamanho slider under Parâmetros) — Rio/Estrada has no
                # width slider of its own.
                self.on_size_changed(engine_obj.brush_engine.config.size)
                self._l.brush_panel.set_path_material(name, pixmap)
                self._l.brush_panel.set_panel_mode(BrushToolPanel.MODE_RIVER)
        elif category == "road":
            engine_obj._road_path_tool.set_texture(pixmap, asset_id)
            if switch_tool:
                engine_obj.tool_manager.activate("Estrada")
                self.on_size_changed(engine_obj.brush_engine.config.size)
                self._l.brush_panel.set_path_material(name, pixmap)
                self._l.brush_panel.set_panel_mode(BrushToolPanel.MODE_ROAD)
        elif switch_tool:
            if engine_obj.tool_manager.active_name in ("Estrada", "Rio"):
                engine_obj.tool_manager.activate("Brush")
            self._l.brush_panel.set_panel_mode(BrushToolPanel.MODE_BRUSH)

        window = self._l.window()
        if window and hasattr(window, "uow") and window.uow:
            window.uow.ui_state.set(self._LAST_ASSET_KEY, asset_id)
        self._l.asset_browser_panel.hide()
        self._l._reposition()

    def reset_panel_mode(self):
        """Force the panel back to the plain parameter-grid layout.

        set_panel_mode(MODE_RIVER/MODE_ROAD) only ever gets called from
        on_asset_selected, when a water/road asset is picked — leaving the
        panel itself (a single shared widget, not a fresh one per mode) in
        whatever mode it was last in otherwise. Clicking away to another
        tool and back to the Pincel toolbar button doesn't go through
        on_asset_selected at all (see MainLayout._on_tool_selected, which
        only shows/hides the panel), so without this the panel kept
        reopening on the leftover Rio/Estrada layout — right after
        finalizing a river, or on any later Pincel click that session —
        instead of the normal Tamanho/Opacidade/... grid."""
        self._l.brush_panel.set_panel_mode(BrushToolPanel.MODE_BRUSH)

    def _asset_category(self, asset_id: str) -> str:
        """Returns the library category of an asset, or '' if unknown."""
        asset_engine = self._l.canvas.engine._asset_engine
        library = getattr(asset_engine, 'library', None) if asset_engine else None
        if not library:
            return ''
        try:
            row = library._db.execute(
                "SELECT category FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
            return row["category"] if row else ''
        except Exception:
            return ''

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
        # Keep path tools in sync with the Size slider — Rio/Estrada has no
        # width slider of its own (see _build_path_params_page), the Size
        # slider under Parâmetros is the only control for it.
        self._l.canvas.engine._river_path_tool.set_width(value)
        self._l.canvas.engine._road_path_tool.set_width(value)
        self._l.brush_panel.size_slider.set_value(value)

    def on_opacity_changed(self, value):
        self._l.canvas.engine.brush_engine.set_opacity(value / 100.0)
        self._l.brush_panel.texture_preview.set_opacity(value / 100.0)
        # Rio/Estrada has no opacity slider of its own — the Opacidade
        # slider under Parâmetros drives this too, applied live to
        # whichever río/estrada trace is mid-edit, if any.
        for path_tool in (self._l.canvas.engine._river_path_tool, self._l.canvas.engine._road_path_tool):
            if path_tool.active_item is not None:
                path_tool.active_item.setOpacity(value / 100.0)

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
