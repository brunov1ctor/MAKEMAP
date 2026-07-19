"""RegionMediator — Região panel ↔ canvas engine wiring."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout
    from src.canvas.zone_visual import ZoneVisual


class RegionMediator:
    """Manages Região panel ↔ canvas engine connections.

    Mirrors TerrainMediator's dict[id, canvas-object] + on_added/on_removed/
    on_selected shape, with one structural difference: a region's id/card
    can only be created AFTER the user finishes drawing its polygon on the
    canvas (RegionTool's multi-click gesture), not synchronously on "+ Novo"
    like Terrain's default-shaped boundary. So "+ Novo" here only *arms*
    drawing mode; the actual id/card creation happens in _on_finalized.
    """

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._regions: dict[str, "ZoneVisual"] = {}
        # Snapshot of (category_key, label, color) taken when "+ Novo" arms
        # drawing — used at finalize time instead of a fresh panel lookup,
        # so a category deleted *while* a draw is in progress still lands
        # its finished polygon in a sensibly-labeled (re-created) section
        # instead of being silently dropped.
        self._pending_category: tuple[str, str, QColor] | None = None
        self._l.canvas.engine.zone_region_finalized.connect(self._on_finalized)

    def on_add_requested(self, category_key: str):
        info = self._l.region_panel.category_info(category_key)
        if info is None:
            return
        label, color = info
        self._pending_category = (category_key, label, color)
        self._l.canvas.engine.set_zone_type(category_key)
        self._l.canvas.engine.tool_manager.activate("Região")

    def _on_finalized(self, polygon, zone_key: str):
        if self._pending_category and self._pending_category[0] == zone_key:
            _, label, color = self._pending_category
        else:
            info = self._l.region_panel.category_info(zone_key)
            label, color = info if info else (zone_key.capitalize(), QColor(150, 150, 150, 90))
        self._pending_category = None

        region_id = str(uuid.uuid4())
        name = f"{label} {self._l.region_panel.category_count(zone_key) + 1}"

        visual = self._l.canvas.engine.paint_zone(polygon, zone_key, region_id, name, 0, color)
        self._regions[region_id] = visual
        self._l.region_panel.add_region_card(
            region_id, name, zone_key, stars=0,
            category_label=label, category_color=color,
        )

    def on_renamed(self, region_id: str, new_name: str):
        visual = self._regions.get(region_id)
        if visual:
            visual.set_name(new_name)

    def on_removed(self, region_id: str):
        visual = self._regions.pop(region_id, None)
        if visual:
            # Hide-not-remove — same convention as TerrainMediator.on_removed.
            visual.set_visible(False)

    def on_stars_changed(self, region_id: str, stars: int):
        visual = self._regions.get(region_id)
        if visual:
            visual.set_stars(stars)

    def on_selected(self, region_id: str):
        # Card highlight is entirely panel-internal (mirrors TerrainCard's
        # own click highlight) — nothing canvas-side needs to happen here.
        pass

    def on_locate(self, region_id: str):
        visual = self._regions.get(region_id)
        if not visual:
            return
        item = visual.root_item
        rect = item.mapToScene(item.boundingRect()).boundingRect()
        padding = 80
        rect.adjust(-padding, -padding, padding, padding)
        viewport = self._l.canvas.engine.viewport
        viewport.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        new_zoom = viewport.transform().m11()
        viewport._zoom = new_zoom
        viewport.zoom_changed.emit(new_zoom)
        viewport.view_changed.emit()
