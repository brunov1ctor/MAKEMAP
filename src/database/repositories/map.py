"""Map/canvas repositories — every placed canvas item, painted zones/
terrain masks, and terrain boundaries. (MapRepository/LayerRepository —
multi-map-per-project and a Photoshop-style layers table — were removed:
every mediator here operates on a single hardcoded MAP_ID="default", and
the real Layers panel reads live scene items via LayersPanel.set_scene()
rather than the `layers` table, so neither ever had a UI writing to it.)"""

from src.database.repositories.base import BaseRepository, KeyedRepository


class CanvasItemRepository(BaseRepository):
    TABLE = "canvas_items"

    def get_by_map(self, map_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE map_id = ? ORDER BY z_index"
        return [dict(r) for r in self.db.fetchall(sql, (map_id,))]


class ZoneRepository(BaseRepository):
    TABLE = "painted_zones"

    def get_by_map(self, map_id: str) -> list[dict]:
        return self.get_all(map_id=map_id)


class TerrainPaintRepository(BaseRepository):
    """Brush-tool terrain material masks — one row per (map, asset_id)."""
    TABLE = "painted_terrain"

    def get_by_map(self, map_id: str) -> list[dict]:
        return self.get_all(map_id=map_id)


class TerrainRepository(BaseRepository):
    """Terrain panel's map boundaries (shape/size/position/visibility)."""
    TABLE = "terrains"

    def get_by_map(self, map_id: str) -> list[dict]:
        return self.get_all(map_id=map_id)


class ExplorerOverrideRepository(KeyedRepository):
    """Per-element icon/label-color overrides set from the Explorer panel's
    icon-click popup (see ExplorerSyncMediator._on_icon_edit). Keyed by a
    stable `node_key` string (not the map's own id — every mediator here
    already treats MAP_ID as the single constant "default", so no map
    scoping is needed)."""
    TABLE = "explorer_overrides"
    KEY_COLUMN = "node_key"

    def get_all(self) -> dict[str, dict]:
        rows = self.db.fetchall(f"SELECT * FROM {self.TABLE}")
        return {row["node_key"]: dict(row) for row in rows}

    def upsert(self, node_key: str, icon: str | None, label_color: str | None):
        self._upsert(node_key, icon=icon, label_color=label_color)

    def delete_key(self, node_key: str) -> bool:
        return self._delete_by_key(node_key)
