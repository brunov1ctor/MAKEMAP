"""SpawnMediator — Spawn panel ↔ canvas engine wiring.

Categories/mobs are read LIVE from the same DB rows the Mobs module owns
(mob_categories/mobs) — nothing is cached/copied here beyond the current
selection, so renaming or adding a mob/category in the Mobs module is
reflected the next time a category is reopened in the Spawn panel.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPixmap

from src.layouts.panels.spawn.portrait_compose import compose_group_portrait
from src.layouts.panels.spawn.panel import SpawnPanel
from src.layouts.panels.spawn.mob_sub_panel import SpawnMobSubPanel
from src.services.project_assets import resolve_asset_path

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_PREVIEW_SIZE = 56
# Debounce for _sync_to_db — same reasoning/value as BrushMediator's own:
# history_changed fires once per completed stamp/undo/redo, not per mouse-
# move, so this only coalesces rapid back-to-back sequences into one DB
# round trip.
_SYNC_DEBOUNCE_MS = 250


class SpawnMediator:
    """Manages Spawn panel ↔ canvas engine connections."""

    MAP_ID = "default"  # matches BrushMediator/RegionMediator

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._active_kind = "mob"  # "mob" | "npc" — toggled via SpawnPanel.kind_changed
        self._active_mob_name = ""
        self._active_face: QPixmap | None = None
        self._stamp_items: dict[str, object] = {}  # canvas_items row id -> QGraphicsPixmapItem

        # Spawn de Mobs/NPCs — categories (SpawnPanel) + mob sub-panel, same
        # adjacent-panel pattern as Brush/AssetBrowser: pick a category,
        # SpawnMobSubPanel rides next to it, picking a mob/npc there closes
        # it back down.
        panel = SpawnPanel(self._l)
        panel.hide()
        panel.close_requested.connect(self._l._close_spawn_panel)
        self._l.spawn_panel = panel
        panel.category_selected.connect(self.on_category_selected)
        panel.size_changed.connect(self.on_size_changed)
        panel.quantity_changed.connect(self.on_quantity_changed)
        panel.kind_changed.connect(self.on_kind_changed)

        sub_panel = SpawnMobSubPanel(self._l)
        sub_panel.hide()
        sub_panel.close_requested.connect(self._l._toggle_spawn_mob_sub_panel)
        self._l.spawn_mob_sub_panel = sub_panel
        sub_panel.mob_selected.connect(self.on_mob_selected)

        self._l.canvas.engine._spawn_tool.on_stamp_placed(self._on_stamp_placed)
        self._l.canvas.engine._spawn_tool.set_parent_provider(
            lambda: self._active_boundary.group if self._active_boundary and self._active_boundary._item else None
        )
        self._active_boundary = None

        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._sync_to_db)
        self._l.canvas.engine.history.history_changed.connect(self._on_history_changed)

        # Clicking a placed mob-spawn stamp (via the normal Selecionar
        # tool) shows its info in the Inspector — see _on_selection_changed.
        self._l.canvas.engine.selection.selection_changed.connect(self._on_selection_changed)

    # ─── Persistence wiring (called by application.py on project load) ───

    def set_uow(self, uow):
        self._uow = uow
        self._active_mob_name = ""
        self._active_face = None
        self._l.canvas.engine._spawn_tool.set_entity(self._active_kind, None, "", None)
        self._l.spawn_panel.set_selected_mob("", None)
        self._refresh_categories()
        self._load_from_db()

    # ─── Kind-dependent repo lookups (mob vs npc) ───

    def _categories_repo(self):
        return self._uow.mob_categories if self._active_kind == "mob" else self._uow.npc_categories

    def _entities_repo(self):
        return self._uow.mobs if self._active_kind == "mob" else self._uow.npcs

    def _assets_for(self, entity_id: str):
        if self._active_kind == "mob":
            return self._uow.mob_assets.get_by_mob(entity_id)
        return self._uow.npc_assets.get_by_npc(entity_id)

    def on_kind_changed(self, kind: str):
        if kind == self._active_kind:
            return
        self._active_kind = kind
        self._active_mob_name = ""
        self._active_face = None
        self._l.canvas.engine._spawn_tool.set_entity(kind, None, "", None)
        self._l.spawn_mob_sub_panel.hide()
        self._refresh_categories()
        self._refresh_preview()

    def set_active_terrain(self, terrain_id: str):
        """Chamado por TerrainMediator.on_selected para sincronizar o label e o boundary ativo."""
        boundary = self._l._terrain_med.boundaries.get(terrain_id) if terrain_id else None
        self._active_boundary = boundary
        self._l.spawn_panel.terrain_combo.set_terrain(terrain_id)

    def _load_from_db(self):
        """Reloads every persisted mob/npc-spawn stamp for the current
        project. Mirrors BrushMediator._load_from_db's stamp-reload half —
        these stamps aren't parented to a boundary item (see
        SpawnTool._place), so plain scene.removeItem()/addItem() is safe
        here without the detach-first dance Brush's stamps need."""
        scene = self._l.canvas.engine.viewport.scene()
        for item in self._stamp_items.values():
            if item.scene() is not None:
                item.scene().removeItem(item)
        self._stamp_items.clear()
        if not self._uow:
            return

        project_dir = self._project_dir()
        tool = self._l.canvas.engine._spawn_tool
        for row in self._uow.canvas_items.get_by_map(self.MAP_ID):
            if row["item_type"] not in ("mob_spawn", "npc_spawn"):
                continue
            kind = "mob" if row["item_type"] == "mob_spawn" else "npc"
            repo = self._uow.mobs if kind == "mob" else self._uow.npcs
            entity_id = row["asset_id"]
            entity = repo.get(entity_id)
            if not entity:
                # The mob/npc itself was deleted since this was placed —
                # drop the orphaned stamp rather than showing a blank one.
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            quantity = int(meta.get("quantity", 1))
            size = float(meta.get("size", 64.0))
            face = self._load_face(entity, project_dir, kind)
            # NPCs have no "altura" (shadow-height) column yet — stamps
            # simply cast no shadow, same as a mob whose altura is 0.
            height = float(entity.get("altura", 0) or 0) if kind == "mob" else 0.0
            item = tool.build_stamp_item(
                entity_id, row["name"] or entity.get("name", ""), quantity, size, face,
                QPointF(row["position_x"], row["position_y"]),
                height=height, entity_kind=kind,
            )
            # Unlike BrushMediator's own reload (which relies solely on its
            # python-side dict for the row-id lookup), cache the row id
            # directly on the item too — _sync_to_db reads it via
            # item.data(1), and without this the very next sync would find
            # nothing there and insert a duplicate row for every reloaded
            # stamp.
            item.setData(1, row["id"])
            scene.addItem(item)
            self._stamp_items[row["id"]] = item

    def _on_history_changed(self):
        self._sync_timer.start(_SYNC_DEBOUNCE_MS)

    def _sync_to_db(self):
        """Upserts every currently-placed mob/npc-spawn stamp into the
        project DB, and drops rows for stamps no longer present — fired
        (debounced) off HistoryEngine.history_changed, which already covers
        stamp placement, undo and redo alike (see SpawnTool's begin_group/
        end_group). Mirrors BrushMediator._sync_to_db's stamp half."""
        if not self._uow:
            return
        seen_ids: set[str] = set()
        for item in self._l.canvas.engine.viewport.scene().items():
            data = item.data(0)
            item_type = data.get("item_type") if isinstance(data, dict) else None
            if item_type not in ("mob_spawn", "npc_spawn") or not item.isVisible():
                continue
            fields = dict(
                item_type=item_type, asset_id=data.get("mob_id") or "",
                name=data.get("name", ""), position_x=item.pos().x(), position_y=item.pos().y(),
                metadata=json.dumps({"quantity": data.get("quantity", 1), "size": data.get("size", 64.0)}),
            )
            row_id = item.data(1)
            # A cached id can go stale (undo hid the item, its row got
            # swept below, then redo brought it back still carrying that
            # dead id) — fall back to creating a fresh row, same as Brush.
            if not row_id or not self._uow.canvas_items.update(row_id, **fields):
                row_id = self._uow.canvas_items.create(map_id=self.MAP_ID, **fields)
                item.setData(1, row_id)
            self._stamp_items[row_id] = item
            seen_ids.add(row_id)

        for stale_id in set(self._stamp_items) - seen_ids:
            self._uow.canvas_items.delete(stale_id)
            del self._stamp_items[stale_id]

    def _project_dir(self):
        window = self._l.window()
        return window.project.path if window and getattr(window, "project", None) else None

    # ─── Categories ───

    def _refresh_categories(self):
        if not self._uow:
            self._l.spawn_panel.set_categories([])
            return
        default_icon = "🐾" if self._active_kind == "mob" else "🧙"
        roots = self._categories_repo().get_children(None)
        categories = [(c["id"], c.get("icon") or default_icon, c["name"]) for c in roots]
        self._l.spawn_panel.set_categories(categories)

    def _descendant_category_ids(self, root_id: str) -> set[str]:
        """A category folder can nest sub-folders (same tree the Mobs/NPCs
        module's own CATEGORIAS explorer navigates) — an entity filed under
        any of those still counts as "in" the top-level category picked
        here."""
        ids = {root_id}
        for child in self._categories_repo().get_children(root_id):
            ids |= self._descendant_category_ids(child["id"])
        return ids

    def on_category_selected(self, category_id: str):
        if not self._uow:
            return
        default_icon = "🐾" if self._active_kind == "mob" else "🧙"
        cat = self._categories_repo().get(category_id)
        icon = (cat.get("icon") if cat else "") or default_icon
        label = cat.get("name") if cat else category_id

        wanted = self._descendant_category_ids(category_id)
        project_dir = self._project_dir()
        entities = []
        for m in self._entities_repo().get_all():
            if m.get("category") not in wanted:
                continue
            entities.append((m["id"], m.get("name", ""), self._load_face(m, project_dir)))

        sub_panel = self._l.spawn_mob_sub_panel
        sub_panel.set_category(label, icon, entities)
        if not sub_panel.isVisible():
            sub_panel.show()
            sub_panel.raise_()
        self._l._reposition()

    def _load_face(self, entity: dict, project_dir, kind: str | None = None) -> QPixmap | None:
        """The image to stamp for this mob/npc — an image-type asset (see
        the Assets CRUD in the edit panel's extras section, e.g. "the
        goblin's face asset") takes priority over the entity's own
        Visão Geral portrait (`image_path`), since that's the art actually
        meant to represent it on the map, not just its catalog thumbnail.
        Falls back to the portrait if no image asset exists."""
        kind = kind or self._active_kind
        entity_id = entity.get("id", "")
        if entity_id and self._uow:
            assets = self._uow.mob_assets.get_by_mob(entity_id) if kind == "mob" \
                else self._uow.npc_assets.get_by_npc(entity_id)
            for asset in assets:
                if asset.get("asset_type") != "Imagem":
                    continue
                pixmap = self._load_portrait(asset.get("file_path", ""), project_dir)
                if pixmap is not None:
                    return pixmap
        return self._load_portrait(entity.get("image_path", ""), project_dir)

    @staticmethod
    def _load_portrait(image_path: str, project_dir) -> QPixmap | None:
        if not image_path:
            return None
        pixmap = QPixmap(resolve_asset_path(project_dir, image_path))
        return pixmap if not pixmap.isNull() else None

    def _resolve_drops(self, mob: dict, project_dir) -> list[tuple[dict, float, int]]:
        """mob["drops_json"] only carries {item_id, rate, qty} — resolve
        each item_id against the real Item catalog so the Inspector can
        render the same _DropTile cards the Mobs edit panel does, instead
        of a bare id (see InspectorPanel._GeralTab)."""
        try:
            drops = json.loads(mob.get("drops_json") or "[]")
        except (TypeError, ValueError):
            drops = []
        resolved = []
        for d in drops:
            item_id = d.get("item_id", "")
            item = self._uow.items.get(item_id) if item_id else None
            item = dict(item) if item else {"id": item_id, "name": "Item removido do catálogo"}
            item["image_path"] = resolve_asset_path(project_dir, item.get("image_path") or "")
            resolved.append((item, d.get("rate", 0), d.get("qty", 1)))
        return resolved

    def _resolve_abilities(self, mob: dict, project_dir) -> list[tuple[dict, bool]]:
        """Same idea as _resolve_drops but for abilities_json — mirrors
        ExtrasSectionMixin._resolve_ability (mob edit panel), just against
        a live DB lookup instead of a cached catalog list."""
        try:
            abilities = json.loads(mob.get("abilities_json") or "[]")
        except (TypeError, ValueError):
            abilities = []
        resolved = []
        for a in abilities:
            skill_id = a.get("skill_id")
            if skill_id:
                skill = self._uow.skills.get(skill_id)
                unlinked = skill is None
                skill = dict(skill) if skill else {"id": skill_id}
            else:
                unlinked = True
                skill = {
                    "id": "", "name": a.get("legacy_name", ""),
                    "description": a.get("legacy_description", ""),
                    "rarity": a.get("legacy_rarity", "common"),
                }
            if skill.get("image_path"):
                skill["image_path"] = resolve_asset_path(project_dir, skill["image_path"])
            resolved.append((skill, unlinked))
        return resolved

    # ─── Mob/NPC selection ───

    def on_mob_selected(self, entity_id: str):
        if not self._uow:
            return
        entity = self._entities_repo().get(entity_id)
        if not entity:
            return
        self._active_mob_name = entity.get("name", "")
        self._active_face = self._load_face(entity, self._project_dir())
        height = float(entity.get("altura", 0) or 0) if self._active_kind == "mob" else 0.0

        tool = self._l.canvas.engine._spawn_tool
        tool.set_entity(self._active_kind, entity_id, self._active_mob_name, self._active_face, height)

        self._l.spawn_mob_sub_panel.hide()
        self._refresh_preview()
        self._l._reposition()

    # ─── Auto-tag by região on placement ───

    def _on_stamp_placed(self, entity_id: str | None, scene_pos):
        """Fired by SpawnTool after every stamp — if it landed inside a
        painted região, tags that mob/npc with it (zone_id), the same
        field the "Região" dropdown in Visão Geral sets by hand. Shows up
        immediately as the "📍 <região>" badge on the entity's card next
        time the Mobs/NPCs module is opened."""
        if not self._uow or not entity_id:
            return
        region_id = self._l._region_med.region_at_point(scene_pos)
        if not region_id:
            return
        repo = self._entities_repo()
        entity = repo.get(entity_id)
        if not entity or entity.get("zone_id") == region_id:
            return
        repo.update(entity_id, zone_id=region_id)

    # ─── Selection → Inspector ─────────────────────────────────────────
    # SelectionEngine._emit only includes an item in the emitted `ids` list
    # when its data(0) carries an "id" key — mob-spawn stamps don't (see
    # SpawnTool.build_stamp_item's data(0) shape), so this reads
    # selection.selected_items directly instead of trusting the signal's
    # own payload, the same way MainLayout._on_selection_for_text_panel
    # already does for TextItem selections.

    def _on_selection_changed(self, _ids):
        if not self._uow:
            return
        selected = self._l.canvas.engine.selection.selected_items
        entity_id = None
        kind = None
        for item in selected:
            data = item.data(0)
            if isinstance(data, dict) and data.get("item_type") in ("mob_spawn", "npc_spawn"):
                entity_id = data.get("mob_id")
                kind = "mob" if data["item_type"] == "mob_spawn" else "npc"
                break
        if not entity_id:
            # Selection changed to something else (or nothing) — only clear
            # the Inspector when nothing at all is selected, so switching
            # to a different kind of element (once something else wires
            # into the Inspector) isn't stomped on by this mediator.
            if not selected:
                self._l.right_panel.clear()
            return
        project_dir = self._project_dir()
        if kind == "mob":
            mob = self._uow.mobs.get(entity_id)
            if not mob:
                return
            try:
                pixmap = self._load_face(mob, project_dir, "mob")
                region_name = self._l._region_med.zone_name(mob.get("zone_id", "")) if mob.get("zone_id") else ""
                drops = self._resolve_drops(mob, project_dir)
                abilities = self._resolve_abilities(mob, project_dir)
                self._l.right_panel.set_mob(
                    mob, pixmap=pixmap, region_name=region_name, drops=drops, abilities=abilities,
                )
            except Exception:
                # A bad/legacy DB value here (malformed drops_json, odd image
                # path, ...) shouldn't leave the Inspector silently blank with
                # no clue why — log it and fall back to at least the name/type,
                # which don't depend on any of the above.
                logger.exception("Falha ao popular o Inspector para o mob %s", entity_id)
                self._l.right_panel.set_element(name=mob.get("name", ""), type_="Mob")
        else:
            npc = self._uow.npcs.get(entity_id)
            if not npc:
                return
            try:
                pixmap = self._load_face(npc, project_dir, "npc")
                region_name = self._l._region_med.zone_name(npc.get("zone_id", "")) if npc.get("zone_id") else ""
                self._l.right_panel.set_npc(npc, pixmap=pixmap, region_name=region_name)
            except Exception:
                logger.exception("Falha ao popular o Inspector para o npc %s", entity_id)
                self._l.right_panel.set_element(name=npc.get("name", ""), type_="NPC")

    # ─── Stamp mode params ───

    def on_size_changed(self, size: float):
        self._l.canvas.engine._spawn_tool.set_size(size)
        self._refresh_preview()

    def on_quantity_changed(self, quantity: int):
        self._l.canvas.engine._spawn_tool.set_quantity(quantity)
        self._refresh_preview()

    def _refresh_preview(self):
        panel = self._l.spawn_panel
        if self._active_face is None:
            panel.set_selected_mob(self._active_mob_name, None)
            return
        tool = self._l.canvas.engine._spawn_tool
        preview = compose_group_portrait(self._active_face, tool.quantity, _PREVIEW_SIZE)
        panel.set_selected_mob(self._active_mob_name, preview)
