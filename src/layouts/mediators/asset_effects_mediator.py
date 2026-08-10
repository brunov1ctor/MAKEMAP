"""AssetEffectsMediator — populates the single shared AssetEffectsPanel for
a given asset_id (wired from the Config screen's card "✨" button, see
MenuViewMediator._show_menu_view), persists the painted grid to
asset_settings, and reactively attaches/refreshes AssetEffectsOverlay
children on every placed "asset" stamp in the scene — all without touching
brush_tool.py.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from src.canvas.asset_effects_overlay import AssetEffectsOverlay
from src.engines.asset_effects import empty_layers, has_any_effect, normalize_layers
from src.layouts.panels.assets.effects_panel import AssetEffectsPanel

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_REFRESH_TICK_MS = 150


class AssetEffectsMediator:
    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._cache: dict[str, dict] = {}  # asset_id -> layers (lazily loaded)

        # Asset effects editor (Config screen's card "✨" button) — single
        # shared in-app panel, same "never a window outside the app" rule
        # as every other picker here; floats centered over whatever's
        # showing instead of a QDialog. Its color picker is inline (see
        # _EffectConfigBlock in effects_panel.py), not a second riding
        # panel like Texto's ColorCustomizePanel.
        panel = AssetEffectsPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_asset_effects_panel)
        self._l.asset_effects_panel = panel
        panel.saved.connect(self._on_saved)
        panel.foam_toggled.connect(self._on_foam_toggled)

        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._tick)
        self._refresh_timer.start(_REFRESH_TICK_MS)

    def set_uow(self, uow):
        self._uow = uow
        self._cache.clear()
        self._detach_all()

    # ─── Open editor (card "✨" -> here) ───

    def open_editor(self, asset_id: str):
        if not asset_id or not self._uow:
            return
        library = self._library()
        name = library.get_name_by_id(asset_id) if library else asset_id
        pixmap = library.get_pixmap(asset_id) if library else None
        layers = self._load_layers(asset_id)
        is_water = library.is_water(asset_id) if library else False
        shore_foam = library.has_shore_foam(asset_id) if library else True

        panel = self._l.asset_effects_panel
        panel.load_asset(asset_id, name or asset_id, pixmap, layers, is_water=is_water, shore_foam=shore_foam)
        panel.show()
        self._l._reposition()
        # A widget's sizeHint() isn't reliable until Qt has actually laid
        # it out at least once — on this panel's very first show() (right
        # after construction/hide()) the layout hasn't settled yet, so
        # _content_height() below reads a 0 height and every button ends
        # up with zero clickable area. Same race PanelManager.show() already
        # works around for its own on_show callbacks (see panel_manager.py) —
        # repeat the reposition once more after the event loop catches up.
        QTimer.singleShot(0, self._l._reposition)

    def _library(self):
        engine = self._l.canvas.engine._asset_engine
        return getattr(engine, "library", None) if engine else None

    def _on_saved(self, asset_id: str, layers: dict):
        layers = normalize_layers(layers)
        if self._uow:
            self._uow.asset_settings.set(asset_id, effects_json=json.dumps(layers))
        self._cache[asset_id] = layers
        self._refresh_instances(asset_id, layers)

    def _on_foam_toggled(self, asset_id: str, enabled: bool):
        """"🌊 Maresia" checkbox — persists straight to the asset's own
        shore_foam column (see AssetLibrary.set_shore_foam), same
        immediate-apply behavior as the ★ favorite toggle elsewhere; no
        "Salvar" click needed. Also re-runs the shoreline blend pass right
        away (see CanvasEngine.refresh_shoreline_blend) so any foam already
        painted on the map updates immediately instead of only on that
        water asset's next brush stroke."""
        library = self._library()
        if library:
            library.set_shore_foam(asset_id, enabled)
        self._l.canvas.engine.refresh_shoreline_blend()

    # ─── Cache ───

    def _load_layers(self, asset_id: str) -> dict:
        if asset_id in self._cache:
            return self._cache[asset_id]
        layers = empty_layers()
        if self._uow:
            try:
                raw = self._uow.asset_settings.get(asset_id).get("effects_json") or "{}"
                loaded = json.loads(raw)
                layers = normalize_layers(loaded)
            except (TypeError, ValueError):
                pass
        self._cache[asset_id] = layers
        return layers

    # ─── Reactive attachment (scene scan, no brush_tool.py changes) ───

    def _tick(self):
        if not self._uow:
            return
        # No extra work needed when nothing has effects — the timer just
        # keeps running at a fixed cheap interval either way (same
        # trade-off Marker/Light's own refresh timers already make).
        for item in self._l.canvas.engine.viewport.scene().items():
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "asset":
                continue
            overlay = getattr(item, "_effects_overlay", None)
            if overlay is None:
                asset_id = data.get("asset_id") or ""
                layers = self._load_layers(asset_id) if asset_id else empty_layers()
                if has_any_effect(layers):
                    AssetEffectsOverlay(item, layers)
            else:
                overlay.update()

    def _refresh_instances(self, asset_id: str, layers: dict):
        """After saving new layers for `asset_id`, rebuild every already-
        attached overlay for that asset (old ones would otherwise keep
        showing the pre-save layers forever)."""
        for item in self._l.canvas.engine.viewport.scene().items():
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "asset":
                continue
            if data.get("asset_id") != asset_id:
                continue
            overlay = getattr(item, "_effects_overlay", None)
            if overlay is not None:
                overlay.set_cells(layers)
            elif has_any_effect(layers):
                AssetEffectsOverlay(item, layers)

    def _detach_all(self):
        for item in self._l.canvas.engine.viewport.scene().items():
            overlay = getattr(item, "_effects_overlay", None)
            if overlay is not None:
                if overlay.scene() is not None:
                    overlay.scene().removeItem(overlay)
                item._effects_overlay = None
