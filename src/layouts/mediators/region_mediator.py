"""RegionMediator — Região panel ↔ canvas engine wiring.

Built around a real circular brush (RegionBrushTool/RegionLayer). "Nova
Região" creates the card (and DB row) immediately — with a blank layer,
default type/color — and does NOT open the edit panel or arm the brush;
it's a plain "add an entry" action. Clicking that (or any) card is what
opens RegionEditPanel and arms RegionBrushTool targeting its RegionLayer,
so painting grows/shrinks it live. This split (create vs. paint) mirrors
how you'd add a row then edit it, rather than forcing a paint stroke
before the entry even exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QColor, QPixmap

from src.engines.map.region_layer import RegionLayer
from src.engines.map.zones import DEFAULT_ZONE_COLOR
from src.services.project_assets import import_asset, resolve_asset_path

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


@dataclass
class _Zone:
    id: str
    category_key: str
    name: str
    color: QColor
    layer: RegionLayer
    stars: int = 0
    estilo: str = "Nenhum"
    observacao: str = ""
    visible: bool = True
    radius: float = 50.0
    softness: float = 0.5
    opacity: float = 0.5
    mode: str = "add"
    terrain_id: str = ""  # "" = Mapa Infinito — which terrain's bounds constrain painting
    image_path: str = ""  # user-uploaded reference photo, dropped/picked on the card


class RegionMediator:
    """Manages Região panel ↔ canvas engine connections."""

    MAP_ID = "default"  # painted_zones aren't scoped to the (unimplemented) maps/worlds hierarchy

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._zones: dict[str, _Zone] = {}
        self._active_id: str | None = None
        self._is_creating = False
        self._uow = None

        tool = self._l.canvas.engine._region_brush_tool
        tool.on_stroke_finished(self._on_stroke_finished)

        panel = self._l.region_edit_panel
        panel.name_changed.connect(self._on_name_changed)
        panel.terrain_changed.connect(self._on_terrain_changed)
        panel.category_changed.connect(self._on_category_changed)
        panel.color_changed.connect(self._on_color_changed)
        panel.radius_changed.connect(self._on_radius_changed)
        panel.mode_changed.connect(self._on_mode_changed)
        panel.opacity_changed.connect(self._on_opacity_changed)
        panel.stars_changed.connect(self._on_stars_changed)
        panel.estilo_changed.connect(self._on_estilo_changed)
        panel.observacao_changed.connect(self._on_observacao_changed)
        panel.close_requested.connect(self.on_close_edit)
        panel.save_requested.connect(self.on_save_requested)

        region_panel = self._l.region_panel
        region_panel.region_terrain_changed.connect(self._on_card_terrain_changed)

        # Refresh every "pintando em" dropdown (card list + edit panel)
        # whenever terrains are added/renamed/removed — mirrors the
        # pattern BrushMediator uses for its own dropdown.
        # Deferred via QTimer: RegionMediator is constructed (and thus
        # connects here) before main_layout.py wires
        # terrain_panel.terrain_added → TerrainMediator.on_added, which is
        # what registers the boundary this reads — running synchronously
        # would see a stale/missing boundary for the just-added terrain.
        terrain_panel = self._l.terrain_panel
        for sig in (terrain_panel.terrain_added, terrain_panel.terrain_renamed,
                    terrain_panel.terrain_removed):
            sig.connect(lambda *_a: QTimer.singleShot(0, self._on_terrain_context_changed))

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._load_from_db()

    def _load_from_db(self):
        if not self._uow:
            return
        for zone in list(self._zones.values()):
            zone.layer.remove_from_scene()
        self._zones.clear()
        self._l.region_panel.clear_regions()
        for row in self._uow.zones.get_by_map(self.MAP_ID):
            color = QColor(row["color"])
            layer = self._l.canvas.engine.create_region_layer(color)
            layer.import_mask_png_base64(row["mask_png"], row["mask_x"], row["mask_y"])
            layer.set_style(row["estilo"] or "Nenhum")
            layer.item.setVisible(bool(row["visible"]))
            layer.set_opacity(row["brush_opacity"])
            zone = _Zone(
                id=row["id"], category_key=row["category_key"], name=row["name"], color=color,
                layer=layer, stars=row["stars"], estilo=row["estilo"] or "Nenhum",
                observacao=row["observacao"] or "", visible=bool(row["visible"]),
                radius=row["brush_radius"], softness=row["brush_softness"],
                opacity=row["brush_opacity"], terrain_id=row["terrain_id"] or "",
                image_path=row["image_path"] or "",
            )
            self._zones[zone.id] = zone
            photo = self._load_photo(zone.image_path)
            self._l.region_panel.add_region_card(
                zone.id, zone.name, zone.category_key, zone.color,
                area_m2=layer.area_m2(), object_count=self._count_objects_in(zone),
                visible=zone.visible,
                terrain_label=self._terrain_label(zone.terrain_id),
                terrain_id=zone.terrain_id, photo=photo,
            )
            layer.update_label(zone.name, zone.stars)

    # ─── "Nova Região" → configure fields → "Salvar" → card appears ───
    # Painting is a separate, later step: only clicking the newly-created
    # card (like any other) arms the brush — see on_selected/_open_edit.

    def on_add_requested(self):
        layer = self._l.canvas.engine.create_region_layer(DEFAULT_ZONE_COLOR)
        region_id = str(uuid.uuid4())
        name = f"Região {self._l.region_panel.region_count() + 1}"
        zone = _Zone(id=region_id, category_key="", name=name, color=QColor(DEFAULT_ZONE_COLOR), layer=layer)
        layer.set_opacity(zone.opacity)
        self._zones[region_id] = zone
        self._active_id = region_id
        self._is_creating = True

        panel = self._l.region_edit_panel
        panel.set_terrain_options(self._terrain_options())
        panel.load(
            zone.name, zone.category_key, zone.color,
            zone.radius, zone.softness, zone.mode, zone.opacity,
            zone.stars, zone.estilo, zone.observacao, zone.terrain_id,
        )
        panel.set_create_mode(True)
        panel.show()
        panel.raise_()
        self._l.region_panel.set_new_button_enabled(False)
        self._l._reposition()
        # No brush armed yet — this is field configuration, not painting.

    def on_save_requested(self):
        if not self._is_creating:
            return
        zone = self._current_zone()
        if zone is None:
            return
        self._l.region_panel.add_region_card(
            zone.id, zone.name, zone.category_key, zone.color,
            area_m2=0.0, object_count=0, visible=zone.visible,
            terrain_label=self._terrain_label(zone.terrain_id),
        )
        self._persist_create(zone)
        self._is_creating = False
        self.on_close_edit()

    # ─── Clicking a card — arms the brush right away, no panel ───

    def on_card_clicked(self, region_id: str):
        """Just selecting a card (not "Editar" from its "..." menu) arms
        the brush directly targeting it, so you can start painting right
        away without opening the full field editor. Clicking the same
        card again (see RegionSettingsPanel._on_card_selected) deselects
        it — region_id comes through as "" — which disarms the brush and
        stops painting instead of leaving it targeting a card that no
        longer reads as selected.

        Deliberately does NOT switch the active canvas tool back to
        "Selecionar" — RegionBrushTool safely no-ops on mouse events while
        it has no target (see RegionBrushTool.mouse_press/_paint), so
        painting is already stopped; switching tools would also flip the
        "Selecionar" toolbar button on, which reads as if the user had
        clicked it themselves."""
        if not region_id:
            self._active_id = None
            self._l.canvas.engine._region_brush_tool.set_target(None)
            return
        zone = self._zones.get(region_id)
        if zone is None:
            return
        self._active_id = zone.id
        self._is_creating = False
        self._arm_brush(zone)

    # ─── "Editar" from the "..." menu (edit + paint mode) ───

    def on_selected(self, region_id: str):
        zone = self._zones.get(region_id)
        if zone is None:
            return
        self._is_creating = False
        self._open_edit(zone)

    def zones_list(self) -> list[tuple[str, str]]:
        """(zone_id, name) for every painted região — feeds the "Região"
        dropdown in other modules (e.g. Mobs) that tag entities by zone."""
        return [(z.id, z.name) for z in self._zones.values()]

    def zone_name(self, zone_id: str) -> str:
        zone = self._zones.get(zone_id)
        return zone.name if zone else ""

    def zone_thumbnail(self, zone_id: str, size: int = 24) -> QPixmap | None:
        """Small preview image for `zone_id` — user photo if set, else a
        painted-mask preview (unlike RegionCard's own thumbnail, which
        never shows the mask — see RegionCard.set_color). Used by the Mobs
        module to badge a mob's card with the actual look of the região
        it's tagged to, image-only (no name/icon) — see MobCard.set_data."""
        zone = self._zones.get(zone_id)
        if not zone:
            return None
        if zone.image_path:
            photo = self._load_photo(zone.image_path)
            if photo is not None and not photo.isNull():
                return photo
        thumb = zone.layer.thumbnail(size)
        return thumb if not thumb.isNull() else None

    def region_at_point(self, scene_pos: QPointF) -> str | None:
        """The id of whichever painted região's mask contains `scene_pos`,
        or None — used by SpawnMediator to auto-tag a mob with the região
        it was stamped into. On overlapping régions, the first match wins
        (no defined stacking order between régions today)."""
        for zone in self._zones.values():
            if zone.layer.contains_point(scene_pos):
                return zone.id
        return None

    def _terrain_options(self) -> list[tuple[str, str]]:
        """(terrain_id, name) for every terrain that currently exists —
        feeds the "Pintando em" dropdown."""
        boundaries = self._l._terrain_med.boundaries
        cards = self._l.terrain_panel._cards
        return [(tid, cards[tid].name) for tid in boundaries if tid in cards]

    def _terrain_label(self, terrain_id: str) -> str:
        if not terrain_id:
            return "Mapa Infinito"
        card = self._l.terrain_panel._cards.get(terrain_id)
        return card.name if card else "Mapa Infinito"

    def _on_terrain_context_changed(self, *_args):
        options = self._terrain_options()
        self._l.region_panel.set_terrain_options(options)
        self._l.region_edit_panel.set_terrain_options(options)

    def _on_card_terrain_changed(self, region_id: str, terrain_id: str):
        """"Pintando em" dropdown changed directly on a card (not via the
        edit panel) — same effect as _on_terrain_changed, just triggered
        from the card list instead of the open edit panel."""
        zone = self._zones.get(region_id)
        if zone is None:
            return
        zone.terrain_id = terrain_id
        self._persist_fields(zone, terrain_id=terrain_id)
        if self._active_id == zone.id:
            boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
            self._l.canvas.engine._region_brush_tool.set_active_boundary(boundary)
            self._l.region_edit_panel.set_terrain_id(terrain_id)

    def _arm_brush(self, zone: _Zone):
        tool = self._l.canvas.engine._region_brush_tool
        tool.set_target(zone.layer)
        tool.set_mode(zone.mode)
        # radius only — softness has no user-facing control anymore
        # (RegionBrushTool keeps its own fixed default) and opacity is
        # the layer's own live QGraphicsItem opacity now (see
        # RegionLayer.set_opacity / _on_opacity_changed), not a brush
        # stroke param.
        tool.set_params(radius=zone.radius)
        boundary = self._l._terrain_med.boundaries.get(zone.terrain_id) if zone.terrain_id else None
        tool.set_active_boundary(boundary)
        self._l.canvas.engine.tool_manager.activate("RegiãoPincel")

    def _on_terrain_changed(self, terrain_id: str):
        zone = self._current_zone()
        if not zone:
            return
        zone.terrain_id = terrain_id
        self._persist_fields(zone, terrain_id=terrain_id)
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._l.canvas.engine._region_brush_tool.set_active_boundary(boundary)
        card = self._l.region_panel.get_card(zone.id)
        if card:
            card.set_terrain_label(self._terrain_label(terrain_id))
            card.set_terrain_id(terrain_id)

    def _open_edit(self, zone: _Zone):
        self._active_id = zone.id
        panel = self._l.region_edit_panel
        panel.set_terrain_options(self._terrain_options())
        panel.load(
            zone.name, zone.category_key, zone.color,
            zone.radius, zone.softness, zone.mode, zone.opacity,
            zone.stars, zone.estilo, zone.observacao, zone.terrain_id,
        )
        panel.set_create_mode(False)
        panel.show()
        panel.raise_()
        self._l.region_panel.set_new_button_enabled(False)
        self._l._reposition()
        self._arm_brush(zone)

    def on_close_edit(self):
        if self._is_creating:
            # Closed without ever clicking "Salvar" — discard the
            # in-progress região instead of leaving an orphaned layer/entry
            # that isn't in the list and was never persisted.
            zone = self._current_zone()
            if zone:
                zone.layer.remove_from_scene()
                self._zones.pop(zone.id, None)
            self._is_creating = False
        self._active_id = None
        tool = self._l.canvas.engine._region_brush_tool
        tool.set_target(None)
        self._l.region_edit_panel.hide()
        self._l.region_panel.set_new_button_enabled(True)
        self._l.canvas.engine.tool_manager.activate("Selecionar")
        self._l._reposition()

    # ─── Brush stroke → card creation / persistence ───

    def _on_stroke_finished(self):
        zone = self._current_zone()
        if zone is None:
            return
        area_m2 = zone.layer.area_m2()
        object_count = self._count_objects_in(zone)
        card = self._l.region_panel.get_card(zone.id)
        if card:
            card.set_stats(area_m2, object_count)
        zone.layer.update_label(zone.name, zone.stars)
        self._persist_mask(zone)

    def _count_objects_in(self, zone: _Zone) -> int:
        """Heuristic: stamped/generated assets are documented (paint_zone,
        brush_tool) to sit at zValue >= 10, above terrain (1) and zones
        (5) — count scene items at that tier whose position falls inside
        this zone's painted mask."""
        count = 0
        for item in self._l.canvas.engine.viewport.scene().items():
            if item.zValue() < 10:
                continue
            if zone.layer.contains_point(item.scenePos()):
                count += 1
        return count

    # ─── Edit panel field handlers ───

    def _current_zone(self) -> _Zone | None:
        return self._zones.get(self._active_id) if self._active_id else None

    def _on_name_changed(self, name: str):
        zone = self._current_zone()
        if not zone or not name:
            return
        zone.name = name
        card = self._l.region_panel.get_card(zone.id)
        if card:
            card.set_name(name)
        zone.layer.update_label(name, zone.stars)
        self._persist_fields(zone, name=name)

    def _on_category_changed(self, category_key: str):
        zone = self._current_zone()
        if not zone:
            return
        zone.category_key = category_key
        card = self._l.region_panel.get_card(zone.id)
        if card:
            card.set_category_label(category_key)
        self._persist_fields(zone, category_key=category_key)

    def _on_color_changed(self, color: QColor):
        zone = self._current_zone()
        if not zone:
            return
        zone.color = QColor(color)
        zone.layer.set_color(color)
        card = self._l.region_panel.get_card(zone.id)
        if card:
            card.set_color(zone.color)
        self._persist_fields(zone, color=color.name(QColor.NameFormat.HexArgb))

    def on_card_visibility_toggled(self, region_id: str, visible: bool):
        """From the card's own eye toggle — the only way to toggle
        visibility now (the edit panel's redundant "Visível" checkbox was
        removed; clicking the eye already does the same thing)."""
        zone = self._zones.get(region_id)
        if not zone:
            return
        zone.visible = visible
        zone.layer.item.setVisible(visible)
        zone.layer.set_label_visible(visible)
        self._persist_fields(zone, visible=int(visible))

    def _project_dir(self):
        window = self._l.window()
        return window.project.path if window and getattr(window, "project", None) else None

    def _load_photo(self, image_path: str) -> QPixmap | None:
        if not image_path:
            return None
        pixmap = QPixmap(resolve_asset_path(self._project_dir(), image_path))
        return pixmap if not pixmap.isNull() else None

    def on_card_image_changed(self, region_id: str, path: str):
        """A photo was dropped/picked directly on the card's thumbnail
        (see RegionCard._on_image_dropped) — copies it into the project
        folder (same reasoning as Mobs' portrait, see project_assets.py)
        and persists the relative path, then swaps the card's display in
        immediately rather than waiting for a reload."""
        zone = self._zones.get(region_id)
        if not zone:
            return
        stored_path = import_asset(self._project_dir(), path, "assets/regions", region_id)
        zone.image_path = stored_path
        card = self._l.region_panel.get_card(region_id)
        if card:
            card.set_photo(self._load_photo(stored_path))
        self._persist_fields(zone, image_path=stored_path)

    def on_paint_cleared(self, region_id: str):
        """"Apagar Pintura" from the card's "..." menu — wipes the mask,
        keeps the card/entry itself (name, tipo, cor, etc.)."""
        zone = self._zones.get(region_id)
        if not zone:
            return
        zone.layer.clear_paint()
        card = self._l.region_panel.get_card(region_id)
        if card:
            card.set_stats(0.0, 0)
        self._persist_mask(zone)

    def _on_radius_changed(self, radius: float):
        zone = self._current_zone()
        if not zone:
            return
        zone.radius = radius
        self._l.canvas.engine._region_brush_tool.set_params(radius=radius)

    def _on_mode_changed(self, mode: str):
        zone = self._current_zone()
        if not zone:
            return
        zone.mode = mode
        self._l.canvas.engine._region_brush_tool.set_mode(mode)

    def _on_opacity_changed(self, opacity: float):
        """Now the região's own live transparency (RegionLayer.
        set_opacity — a real QGraphicsItem opacity), not a brush stroke
        param. That old wiring only ever fed the paint MASK's alpha,
        which SourceOver-accumulates and can never be lowered once
        painted — dragging it after already painting an area visibly did
        nothing, which is what this replaces."""
        zone = self._current_zone()
        if not zone:
            return
        zone.opacity = opacity
        zone.layer.set_opacity(opacity)
        self._persist_fields(zone, brush_opacity=opacity)

    def _on_stars_changed(self, stars: int):
        zone = self._current_zone()
        if not zone:
            return
        zone.stars = stars
        zone.layer.update_label(zone.name, stars)
        self._persist_fields(zone, stars=stars)

    def _on_estilo_changed(self, estilo: str):
        zone = self._current_zone()
        if not zone:
            return
        zone.estilo = estilo
        zone.layer.set_style(estilo)
        self._persist_fields(zone, estilo=estilo)

    def _on_observacao_changed(self, text: str):
        zone = self._current_zone()
        if not zone:
            return
        zone.observacao = text
        self._persist_fields(zone, observacao=text)

    # ─── Card signal handlers (rename/delete/duplicate/locate from "..." menu) ───

    def on_renamed(self, region_id: str, new_name: str):
        zone = self._zones.get(region_id)
        if zone:
            zone.name = new_name
            self._persist_fields(zone, name=new_name)
            if self._active_id == region_id:
                self._l.region_edit_panel.set_name(new_name)

    def on_removed(self, region_id: str):
        zone = self._zones.pop(region_id, None)
        if zone:
            zone.layer.remove_from_scene()
            if self._uow:
                self._uow.zones.delete(zone.id)
            if self._active_id == region_id:
                self.on_close_edit()

    def on_card_hover_entered(self, region_id: str):
        """Highlights the matching região on the map while its card is
        hovered — brightens/thickens the região's OWN existing painted
        border (see RegionLayer.set_hover) rather than drawing a second
        outline on top of it."""
        zone = self._zones.get(region_id)
        if zone:
            zone.layer.set_hover(True)

    def on_card_hover_left(self, region_id: str):
        zone = self._zones.get(region_id)
        if zone:
            zone.layer.set_hover(False)

    def on_locate(self, region_id: str):
        """"Localizar" from a card's "..." menu — pans to the região
        without touching the current zoom level. Centers on the LARGEST
        contiguous painted patch (see RegionLayer.largest_blob_center_
        scene), not the bounding box of the whole layer — a região
        painted as several scattered patches would otherwise center on
        empty space between them (and the old fitInView-based bounding
        box also included the layer's raw, potentially much larger than
        painted, raster canvas)."""
        zone = self._zones.get(region_id)
        if not zone:
            return
        center = zone.layer.largest_blob_center_scene()
        if center is None:
            return
        self._l.canvas.engine.viewport.center_on_point(center)

    # ─── Persistence helpers ───

    def _persist_create(self, zone: _Zone):
        if not self._uow:
            return
        mask_png, mx, my = zone.layer.export_mask_png_base64()
        self._uow.zones.create(
            id=zone.id, map_id=self.MAP_ID, category_key=zone.category_key, name=zone.name,
            color=zone.color.name(QColor.NameFormat.HexArgb), mask_png=mask_png, mask_x=mx, mask_y=my,
            stars=zone.stars, estilo=zone.estilo, observacao=zone.observacao,
            visible=int(zone.visible), brush_radius=zone.radius, brush_softness=zone.softness,
            brush_opacity=zone.opacity,
        )

    def _persist_mask(self, zone: _Zone):
        if not self._uow:
            return
        mask_png, mx, my = zone.layer.export_mask_png_base64()
        self._uow.zones.update(zone.id, mask_png=mask_png, mask_x=mx, mask_y=my)

    def _persist_fields(self, zone: _Zone, **fields):
        if not self._uow:
            return
        self._uow.zones.update(zone.id, **fields)
