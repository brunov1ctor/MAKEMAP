"""ExplorerSyncMediator — Explorer panel ↔ canvas engine wiring.

Unlike every other mediator in this package, this one owns no panel state
and never writes back into the canvas/other mediators (except relaying a
"Localizar" pan on click) — it only READS the real state already owned by
BrushTool's terrain layers, RegionMediator's zones, and the scene's tagged
items (npc/mob spawns, texto, luz, marcador), and pushes a freshly rebuilt
ExplorerNode tree into ExplorerPanel. See explorer_model.py for why the
tree itself is a disposable dataclass rather than an editable model.

Rebuilds are debounced off HistoryEngine.history_changed, same pattern
BrushMediator already uses for its own DB sync (see brush_mediator.py) —
that signal already fires on every completed stroke/stamp-group/undo/redo,
so no new signals are needed anywhere else in the app.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, QPointF

from src.canvas.tools.brush_tool import BrushTool
from src.engines.map.explorer_model import ExplorerNode

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

_SYNC_DEBOUNCE_MS = 250
_SELECT_DEBOUNCE_MS = 80  # faster — selection feels instant

# Fraction of a terrain blob's sampled points that must fall inside a
# single região for that blob to be considered fully "engolido" by it —
# at/above this, nesting inverts (região becomes the outer node, terreno
# nests inside it) instead of the normal terreno-outer/região-inner
# arrangement. Isolated here so it's easy to retune if 98% turns out wrong
# in practice.
_REGION_FULL_THRESHOLD = 0.98


class ExplorerSyncMediator:
    def __init__(self, layout: "MainLayout"):
        self._l = layout

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._rebuild)
        self._l.canvas.engine.history.history_changed.connect(self._on_history_changed)

        self._l.left_panel.node_activated.connect(self._on_node_activated)
        self._l.left_panel.node_hovered.connect(self._on_node_hovered)

        self._select_timer = QTimer()
        self._select_timer.setSingleShot(True)
        self._select_timer.timeout.connect(self._on_selection_changed)
        scene = self._l.canvas.engine.viewport.scene()
        scene.selectionChanged.connect(lambda: self._select_timer.start(_SELECT_DEBOUNCE_MS))
        # Also listen to SelectionEngine's own signal, not just Qt's raw
        # scene.selectionChanged — re-clicking a DIFFERENT blob of the same
        # already-selected terrain layer (two ponds painted with the same
        # water asset, see ItemInteraction.select_and_begin_drag) doesn't
        # change WHICH item is selected, so Qt's signal never re-fires, but
        # it does move the selection anchor and re-notify via
        # SelectionEngine.notify_changed() — without this, the Explorer
        # would keep highlighting the previously-clicked pond.
        self._l.canvas.engine.selection.selection_changed.connect(
            lambda _ids: self._select_timer.start(_SELECT_DEBOUNCE_MS)
        )

        self._selected_item_ids: set[int] = set()
        self._rebuild()
        self._l.layers_panel.refresh()

    def _on_history_changed(self):
        self._timer.start(_SYNC_DEBOUNCE_MS)

    def refresh_now(self):
        self._timer.stop()
        self._rebuild()

    # ─── Rebuild ─────────────────────────────────────────────────────────

    def _on_selection_changed(self):
        scene = self._l.canvas.engine.viewport.scene()
        self._selected_item_ids = {id(item) for item in scene.selectedItems()}
        # Rebuild the tree so nodes are reconstructed with the updated
        # selected= field — set_selected_ids alone re-renders with stale
        # nodes that still have selected=False from the previous _rebuild.
        self._rebuild()

    def _rebuild(self):
        self._l.layers_panel.refresh()
        # ── Pass 1: collect asset nodes with their scene bounding rects ──
        asset_nodes = self._collect_asset_nodes()  # list[ExplorerNode]
        # map id(scene_item) → (node, sceneBoundingRect) for containment test
        asset_scene_items: list[tuple[ExplorerNode, object]] = []
        scene = self._l.canvas.engine.viewport.scene()
        for node in asset_nodes:
            item = node.payload.get("item")
            if item is not None:
                asset_scene_items.append((node, item.sceneBoundingRect()))

        def _asset_node_at(pos) -> ExplorerNode | None:
            """Return the asset node whose sceneBoundingRect contains pos."""
            if pos is None:
                return None
            for anode, brect in asset_scene_items:
                if brect.contains(pos):
                    return anode
            return None

        # ── Pass 2: route non-asset overlays → asset or terrain ──
        terrain_children: dict[tuple, list[ExplorerNode]] = defaultdict(list)
        orphans: dict[str, list[ExplorerNode]] = defaultdict(list)

        for kind, nodes in [
            ("effect",  self._collect_effect_nodes()),
            ("river",   self._collect_river_nodes()),
            ("road",    self._collect_road_nodes()),
            ("npc",     self._collect_npc_nodes()),
            ("mob",     self._collect_mob_nodes()),
            ("text",    self._collect_text_nodes()),
            ("light",   self._collect_light_nodes()),
            ("marker",  self._collect_marker_nodes()),
        ]:
            for node in nodes:
                pos = node.payload.get("scene_pos")
                parent_asset = _asset_node_at(pos)
                if parent_asset is not None:
                    parent_asset.children.append(node)
                    continue
                key = self._terrain_blob_key_at(pos) if pos is not None else None
                if key is not None:
                    terrain_children[key].append(node)
                else:
                    orphans[kind].append(node)

        # ── Pass 3: route asset nodes → terrain ──
        for node in asset_nodes:
            pos = node.payload.get("scene_pos")
            key = self._terrain_blob_key_at(pos) if pos is not None else None
            if key is not None:
                terrain_children[key].append(node)
            else:
                orphans["asset"].append(node)

        selected_region_ids: set[str] = set()
        terrain_cat = self._build_terrain_category(terrain_children, selected_region_ids)
        region_cat  = self._build_region_category(selected_region_ids)

        _ORPHAN_META = {
            "effect": ("Efeitos",    "✨"),
            "river":  ("Rios",       "🌊"),
            "road":   ("Estradas",   "🛤"),
            "asset":  ("Assets",     "🖼"),
            "npc":    ("NPCs",       "🧙"),
            "mob":    ("Mobs",       "🐗"),
            "text":   ("Texto",      "📝"),
            "light":  ("Iluminação", "💡"),
            "marker": ("Marcadores", "📍"),
        }
        orphan_cats = [
            self._category_node(kind, label, glyph, orphans[kind])
            for kind, (label, glyph) in _ORPHAN_META.items()
            if orphans.get(kind)
        ]

        roots = [terrain_cat, region_cat] + orphan_cats
        self._l.left_panel.set_tree([r for r in roots if r.children])

    @staticmethod
    def _category_node(kind: str, label: str, glyph: str, children: list[ExplorerNode]) -> ExplorerNode:
        # Count is appended by ExplorerPanel at render time (not baked in
        # here) so client-side search filtering can recompute it against
        # the filtered child list without the mediator re-running.
        return ExplorerNode(
            id=f"category:{kind}", kind="category",
            label=label, icon_glyph=glyph, children=children,
        )

    # ─── Terrenos + regra terreno→região ────────────────────────────────

    def _terrain_blob_key_at(self, scene_pos: QPointF) -> tuple | None:
        """Returns (asset_id, blob_idx) of the terrain blob that contains
        `scene_pos`, or None if no terrain is painted there."""
        engine = self._l.canvas.engine
        for asset_id, layer in engine.terrain_layers().items():
            if layer.item.scene() is None:
                continue
            local_pos = layer.item.mapFromScene(scene_pos)
            blob = layer.blob_at_local(local_pos)
            if blob is not None:
                blobs = layer.connected_components_local()
                for idx, b in enumerate(blobs):
                    if b.bounds_local == blob.bounds_local:
                        return (asset_id, idx)
        return None

    def _build_terrain_category(self, terrain_children: dict[tuple, list[ExplorerNode]],
                                 selected_region_ids: set[str]) -> ExplorerNode:
        """`selected_region_ids` is an out-param (mutated, not returned) —
        every região a SELECTED terrain blob touches (see the per-child
        grouping below, or the full-coverage inversion) gets added here, so
        _build_region_category can mark that região's OWN standalone entry
        as selected too. Without this, a painted patch that nests under a
        região here would highlight correctly here but leave the "Regiões"
        category's separate listing of the exact same região looking
        unselected — confusing since it's the same underlying object shown
        twice."""
        engine = self._l.canvas.engine
        asset_engine = engine.asset_engine
        region_at_point = self._l._region_med.region_at_point
        children: list[ExplorerNode] = []
        for asset_id, layer in engine.terrain_layers().items():
            if layer.item.scene() is None:
                continue
            asset = asset_engine.get_asset(asset_id) if asset_engine else None
            asset_name = asset.name if asset else "Terreno"
            thumb = asset_engine.get_pixmap(asset_id) if asset_engine else None
            item_selected = id(layer.item) in self._selected_item_ids
            touched_blobs = layer.item.selected_blobs_local() if item_selected else None
            for blob_idx, blob in enumerate(layer.connected_components_local()):
                blob_selected = item_selected and (
                    touched_blobs is None
                    or any(b.bounds_local == blob.bounds_local for b in touched_blobs)
                )
                blob_children = terrain_children.get((asset_id, blob_idx), [])

                # Group this blob's children by whichever região (if any)
                # actually contains THEIR OWN point — a río painted through
                # a small região carved out of a much bigger terrain patch
                # nests under that região even though the região covers
                # nowhere near the whole patch (see the aggregate
                # full-blob check below, which is a separate question).
                region_groups: dict[str, list[ExplorerNode]] = defaultdict(list)
                plain_children: list[ExplorerNode] = []
                for child in blob_children:
                    pos = child.payload.get("scene_pos")
                    rid = region_at_point(pos) if pos is not None else None
                    if rid is not None:
                        region_groups[rid].append(child)
                    else:
                        plain_children.append(child)
                if blob_selected:
                    selected_region_ids.update(region_groups.keys())

                region_sub_nodes = []
                for rid, group in region_groups.items():
                    rnode = self._region_node(
                        rid, node_id=f"terrain-region:{asset_id}:{blob_idx}:{rid}",
                        selected=blob_selected,
                    )
                    rnode.children = group
                    region_sub_nodes.append((rid, rnode))

                terrain_node = ExplorerNode(
                    id=f"terrain:{asset_id}:{blob_idx}", kind="terrain",
                    selected=blob_selected, label=asset_name,
                    thumbnail=thumb, icon_glyph="🟫",
                    payload={"scene_pos": blob.center_scene, "item": layer.item},
                    children=plain_children + [n for _rid, n in region_sub_nodes],
                )

                # If a SINGLE região essentially engulfs the whole blob
                # (not just one child's point), invert: that região becomes
                # the OUTER node and terreno nests inside it instead —
                # "regiao engloba todo o terreno" per the ask. Its own
                # per-child group gets flattened straight into terreno's
                # children (no redundant região wrapper repeated twice);
                # any OTHER, smaller região pockets in the same blob still
                # nest normally inside terreno.
                full_region_id = self._covering_region(blob, threshold=_REGION_FULL_THRESHOLD)
                if full_region_id is not None:
                    if blob_selected:
                        selected_region_ids.add(full_region_id)
                    outer = self._region_node(
                        full_region_id, node_id=f"terrain-region-full:{asset_id}:{blob_idx}",
                        selected=blob_selected,
                    )
                    terrain_node.children = plain_children + region_groups.get(full_region_id, []) + [
                        n for rid, n in region_sub_nodes if rid != full_region_id
                    ]
                    outer.children = [terrain_node]
                    children.append(outer)
                else:
                    children.append(terrain_node)
        return self._category_node("terrain", "Terrenos", "🌍", children)

    def _collect_effect_nodes(self) -> list[ExplorerNode]:
        engine = self._l.canvas.engine
        nodes: list[ExplorerNode] = []
        for asset_id, layer in engine.effect_layers().items():
            if layer.item.scene() is None:
                continue
            effect_key = asset_id[len(BrushTool.EFFECT_ASSET_PREFIX):]
            item_selected = id(layer.item) in self._selected_item_ids
            touched_blobs = layer.item.selected_blobs_local() if item_selected else None
            for blob_idx, blob in enumerate(layer.connected_components_local()):
                blob_selected = item_selected and (
                    touched_blobs is None
                    or any(b.bounds_local == blob.bounds_local for b in touched_blobs)
                )
                nodes.append(ExplorerNode(
                    id=f"effect:{asset_id}:{blob_idx}", kind="effect",
                    selected=blob_selected, label=effect_key, icon_glyph="✨",
                    payload={"scene_pos": blob.center_scene, "item": layer.item},
                ))
        return nodes

    def _covering_region(self, blob, threshold: float = _REGION_FULL_THRESHOLD) -> str | None:
        """Which região (if any) covers >= `threshold` of `blob`'s sampled
        points — reuses the same downsampled grid points
        connected_components_local() already computed, so this costs one
        RegionMediator.region_at_point() query per point, no extra scan.
        Only used for the full-blob "regiao engloba todo o terreno"
        inversion check in _build_terrain_category — per-child nesting
        there tests each child's own point directly instead."""
        points = blob.sampled_points_scene
        if not points:
            return None
        region_at_point = self._l._region_med.region_at_point
        counts = Counter(region_at_point(p) for p in points)
        counts.pop(None, None)
        if not counts:
            return None
        best_region, freq = counts.most_common(1)[0]
        if freq / len(points) >= threshold:
            return best_region
        return None

    # ─── Regiões ─────────────────────────────────────────────────────────

    def _region_node(self, region_id: str, node_id: str | None = None, selected: bool = False) -> ExplorerNode:
        name = self._l._region_med.zone_name(region_id) or "Região"
        thumb = self._l._region_med.zone_thumbnail(region_id)
        return ExplorerNode(
            id=node_id or f"region:{region_id}", kind="region",
            selected=selected, label=name,
            thumbnail=thumb, icon_glyph="🗺", payload={"region_id": region_id},
        )

    def _build_region_category(self, selected_region_ids: set[str]) -> ExplorerNode:
        """Standalone listing of every região — `selected_region_ids` (see
        _build_terrain_category) is what lets this reflect a selection
        that actually happened via a covered terrain blob."""
        region_med = self._l._region_med
        children = [
            self._region_node(region_id, selected=region_id in selected_region_ids)
            for region_id, _name in region_med.zones_list()
            if region_med.zone_area_m2(region_id) > 0
        ]
        return self._category_node("region", "Regiões", "🗺", children)

    # ─── NPCs / Mobs / Texto / Iluminação / Marcadores (scene items) ─────

    def _scene_items_by_type(self, item_type: str) -> list:
        scene = self._l.canvas.engine.viewport.scene()
        result = []
        for item in scene.items():
            data = item.data(0)
            if isinstance(data, dict) and data.get("item_type") == item_type and item.isVisible():
                result.append(item)
        return result

    def _collect_asset_nodes(self) -> list[ExplorerNode]:
        nodes = []
        asset_engine = self._l.canvas.engine.asset_engine
        scene = self._l.canvas.engine.viewport.scene()
        for item in scene.items():
            if not item.isVisible():
                continue
            data = item.data(0)
            if not isinstance(data, dict):
                continue
            if data.get("item_type") != "asset" or data.get("effect_key"):
                continue
            asset_id = data.get("asset_id", "")
            name = ""
            thumb = None
            if asset_engine and asset_id:
                lib = getattr(asset_engine, "library", None)
                if lib:
                    name = lib.get_name_by_id(asset_id) or ""
                thumb = asset_engine.get_pixmap(asset_id)
            nodes.append(ExplorerNode(
                id=f"asset:{id(item)}", kind="asset",
                selected=id(item) in self._selected_item_ids,
                label=name or "Asset", thumbnail=thumb, icon_glyph="🖼",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    def _collect_river_nodes(self) -> list[ExplorerNode]:
        nodes = []
        asset_engine = self._l.canvas.engine.asset_engine
        scene = self._l.canvas.engine.viewport.scene()
        for item in scene.items():
            if not item.isVisible():
                continue
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "river_path":
                continue
            asset_id = data.get("asset_id", "")
            name = ""
            thumb = None
            if asset_engine and asset_id:
                lib = getattr(asset_engine, "library", None)
                if lib:
                    name = lib.get_name_by_id(asset_id) or ""
                thumb = asset_engine.get_pixmap(asset_id)
            nodes.append(ExplorerNode(
                id=f"river:{id(item)}", kind="asset",
                selected=id(item) in self._selected_item_ids,
                label=name or "Rio", thumbnail=thumb, icon_glyph="🌊",
                payload={"scene_pos": item.mapToScene(item.boundingRect().center()), "item": item},
            ))
        return nodes

    def _collect_road_nodes(self) -> list[ExplorerNode]:
        nodes = []
        asset_engine = self._l.canvas.engine.asset_engine
        scene = self._l.canvas.engine.viewport.scene()
        for item in scene.items():
            if not item.isVisible():
                continue
            data = item.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "road_path":
                continue
            asset_id = data.get("asset_id", "")
            name = ""
            thumb = None
            if asset_engine and asset_id:
                lib = getattr(asset_engine, "library", None)
                if lib:
                    name = lib.get_name_by_id(asset_id) or ""
                thumb = asset_engine.get_pixmap(asset_id)
            nodes.append(ExplorerNode(
                id=f"road:{id(item)}", kind="asset",
                selected=id(item) in self._selected_item_ids,
                label=name or "Estrada", thumbnail=thumb, icon_glyph="🛤",
                payload={"scene_pos": item.mapToScene(item.boundingRect().center()), "item": item},
            ))
        return nodes

    def _collect_npc_nodes(self) -> list[ExplorerNode]:
        nodes = []
        for item in self._scene_items_by_type("npc_spawn"):
            data = item.data(0)
            nodes.append(ExplorerNode(
                id=f"npc:{id(item)}", kind="npc", selected=id(item) in self._selected_item_ids,
                label=data.get("name") or "NPC", thumbnail=item.pixmap(), icon_glyph="🧙",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    def _collect_mob_nodes(self) -> list[ExplorerNode]:
        nodes = []
        for item in self._scene_items_by_type("mob_spawn"):
            data = item.data(0)
            nodes.append(ExplorerNode(
                id=f"mob:{id(item)}", kind="mob", selected=id(item) in self._selected_item_ids,
                label=data.get("name") or "Mob", thumbnail=item.pixmap(), icon_glyph="🐗",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    def _collect_text_nodes(self) -> list[ExplorerNode]:
        nodes = []
        for item in self._scene_items_by_type("text"):
            text = item.props.text
            label = (text[:24] + "…") if len(text) > 24 else (text or "Texto")
            nodes.append(ExplorerNode(
                id=f"text:{id(item)}", kind="text", selected=id(item) in self._selected_item_ids,
                label=label, icon_glyph="📝",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    def _collect_light_nodes(self) -> list[ExplorerNode]:
        nodes = []
        for item in self._scene_items_by_type("light"):
            nodes.append(ExplorerNode(
                id=f"light:{id(item)}", kind="light", selected=id(item) in self._selected_item_ids,
                label="Luz", icon_glyph="💡",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    def _collect_marker_nodes(self) -> list[ExplorerNode]:
        nodes = []
        for item in self._scene_items_by_type("marker"):
            nodes.append(ExplorerNode(
                id=f"marker:{id(item)}", kind="marker", selected=id(item) in self._selected_item_ids,
                label=item.props.name or "Marcador", icon_glyph=item.props.icon or "📍",
                payload={"scene_pos": item.scenePos(), "item": item},
            ))
        return nodes

    # ─── Clique num nó → foca no canvas ("Localizar") ─────────────────────

    def _on_node_activated(self, payload: dict):
        region_id = payload.get("region_id")
        if region_id:
            self._l._region_med.on_locate(region_id)
            item = self._l._region_med.zone_item(region_id)
            if item is not None:
                self._select_item(item)
            return
        scene_pos = payload.get("scene_pos")
        if scene_pos is not None:
            self._l.canvas.engine.viewport.center_on_point(scene_pos)
        item = payload.get("item")
        if item is not None:
            self._select_item(item, scene_pos)

    def _select_item(self, item, anchor_scene_pos=None):
        """Select `item` with the same on-canvas selection box a direct
        click gives it — mirrors ItemInteraction.select_and_begin_drag's
        select+anchor+notify sequence, minus the drag. `anchor_scene_pos`
        scopes the box to a single blob for shared multi-blob items
        (terrain/effect layers, see set_selection_anchor); a no-op for item
        types that don't support it."""
        engine = self._l.canvas.engine
        engine.selection.set([item])
        set_anchor = getattr(item, "set_selection_anchor", None)
        if set_anchor is not None and anchor_scene_pos is not None:
            set_anchor(item.mapFromScene(anchor_scene_pos))
            engine.selection.notify_changed()

    # ─── Hover num card → destaque no canvas ───────────────────────────────

    def _on_node_hovered(self, payload: dict, hovered: bool):
        """Mirrors the same glow an item shows on a real mouse hover (see
        item_utils.enable_hover_glow) — every item type it's wired for
        (terrain/effect/región layers, assets, npc/mob spawns, luz,
        marcador, texto) exposes it via a uniform set_explorer_highlight(
        bool) entry point, set by enable_hover_glow itself except where a
        type overrides its own native hoverEnterEvent (TextItem)."""
        region_id = payload.get("region_id")
        item = self._l._region_med.zone_item(region_id) if region_id else payload.get("item")
        if item is None:
            return
        highlight = getattr(item, "set_explorer_highlight", None)
        if highlight is not None:
            highlight(hovered)
