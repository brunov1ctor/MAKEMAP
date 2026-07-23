"""Entity repositories — one per domain entity."""

from src.database.repositories.base import BaseRepository


class WorldRepository(BaseRepository):
    TABLE = "worlds"


class ContinentRepository(BaseRepository):
    TABLE = "continents"

    def get_by_world(self, world_id: str) -> list[dict]:
        return self.get_all(world_id=world_id)


class KingdomRepository(BaseRepository):
    TABLE = "kingdoms"

    def get_by_continent(self, continent_id: str) -> list[dict]:
        return self.get_all(continent_id=continent_id)


class RegionRepository(BaseRepository):
    TABLE = "regions"

    def get_by_kingdom(self, kingdom_id: str) -> list[dict]:
        return self.get_all(kingdom_id=kingdom_id)

    def get_by_level_range(self, level: int) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE level_min <= ? AND level_max >= ?"
        return [dict(r) for r in self.db.fetchall(sql, (level, level))]


class BiomeRepository(BaseRepository):
    TABLE = "biomes"


class CityRepository(BaseRepository):
    TABLE = "cities"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)


class NPCRepository(BaseRepository):
    TABLE = "npcs"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)

    def get_by_city(self, city_id: str) -> list[dict]:
        return self.get_all(city_id=city_id)


class MobRepository(BaseRepository):
    TABLE = "mobs"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)


class MobCategoryRepository(BaseRepository):
    """Directory-style tree for the Mobs panel's category sidebar — see
    migration 5 in schema.py. parent_id NULL means a root-level folder."""
    TABLE = "mob_categories"

    def get_children(self, parent_id: str | None) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE parent_id IS ? ORDER BY sort_order, name"
        return [dict(r) for r in self.db.fetchall(sql, (parent_id,))]

    def get_path(self, category_id: str | None) -> list[dict]:
        """Root-to-leaf breadcrumb chain for `category_id` — empty list at
        the root or if the id no longer exists (folder was deleted)."""
        path = []
        current = self.get(category_id) if category_id else None
        while current:
            path.append(current)
            current = self.get(current["parent_id"]) if current.get("parent_id") else None
        return list(reversed(path))


class MobAssetRepository(BaseRepository):
    """Stamp assets attached to a mob (see migration 8) — the eventual
    canvas "Mobs" placement tool will place one of these, same idea as
    BrushTool's object-stamp mode but tied to a specific mob record."""
    TABLE = "mob_assets"

    def get_by_mob(self, mob_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE mob_id = ? ORDER BY sort_order, created_at"
        return [dict(r) for r in self.db.fetchall(sql, (mob_id,))]


class BossRepository(BaseRepository):
    TABLE = "bosses"

    def get_by_dungeon(self, dungeon_id: str) -> list[dict]:
        return self.get_all(dungeon_id=dungeon_id)


class ItemRepository(BaseRepository):
    TABLE = "items"

    def get_by_rarity(self, rarity: str) -> list[dict]:
        return self.get_all(rarity=rarity)


class SkillRepository(BaseRepository):
    """Habilidades — the Itens e Habilidades panel's skill catalog (see
    migration 12). Same shape/reasoning as ItemRepository: a few real
    columns, everything else in the `stats` JSON blob."""
    TABLE = "skills"

    def get_by_category(self, category: str) -> list[dict]:
        return self.get_all(category=category)


class SkillTreeRepository(BaseRepository):
    """Árvore de Habilidades — one row per element tab, keyed by tree_key
    (NOT a uuid `id`), each holding the whole node graph as a JSON `data`
    blob. Overrides the base CRUD's uuid/id assumptions accordingly."""
    TABLE = "skill_trees"

    def get_all_ordered(self) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} ORDER BY sort_order, name"
        return [dict(r) for r in self.db.fetchall(sql)]

    def get_tree(self, tree_key: str) -> dict | None:
        row = self.db.fetchone(f"SELECT * FROM {self.TABLE} WHERE tree_key = ?", (tree_key,))
        return dict(row) if row else None

    def upsert(self, tree_key: str, **fields):
        """Insert-or-update by tree_key — the table's PK is the tab key, not
        a generated uuid, so the base create()/update() (which assume an
        `id` column) don't apply here."""
        from datetime import datetime
        fields["updated_at"] = datetime.now().isoformat()
        existing = self.get_tree(tree_key)
        with self.db.transaction():
            if existing:
                sets = ", ".join(f"{k} = ?" for k in fields)
                self.db.execute(
                    f"UPDATE {self.TABLE} SET {sets} WHERE tree_key = ?",
                    tuple(fields.values()) + (tree_key,),
                )
            else:
                fields["tree_key"] = tree_key
                fields.setdefault("created_at", datetime.now().isoformat())
                cols = ", ".join(fields.keys())
                placeholders = ", ".join("?" for _ in fields)
                self.db.execute(
                    f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})",
                    tuple(fields.values()),
                )

    def delete_tree(self, tree_key: str) -> bool:
        with self.db.transaction():
            cursor = self.db.execute(f"DELETE FROM {self.TABLE} WHERE tree_key = ?", (tree_key,))
        return cursor.rowcount > 0


class ResourceRepository(BaseRepository):
    TABLE = "resources"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)


class QuestRepository(BaseRepository):
    TABLE = "quests"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)

    def get_by_chain(self, chain_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE chain_id = ? ORDER BY chain_order"
        return [dict(r) for r in self.db.fetchall(sql, (chain_id,))]


class QuestChainRepository(BaseRepository):
    TABLE = "quest_chains"


class DungeonRepository(BaseRepository):
    TABLE = "dungeons"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)


class BuildingRepository(BaseRepository):
    TABLE = "buildings"

    def get_children(self, parent_id: str) -> list[dict]:
        return self.get_all(parent_id=parent_id)


class BuildingCategoryRepository(BaseRepository):
    TABLE = "building_categories"


class DungeonTypeRepository(BaseRepository):
    TABLE = "dungeon_types"


class EventRepository(BaseRepository):
    TABLE = "events"

    def get_by_region(self, region_id: str) -> list[dict]:
        return self.get_all(region_id=region_id)


class FactionRepository(BaseRepository):
    TABLE = "factions"

    def get_by_world(self, world_id: str) -> list[dict]:
        return self.get_all(world_id=world_id)


class TagRepository(BaseRepository):
    TABLE = "tags"


class MapRepository(BaseRepository):
    TABLE = "maps"

    def get_by_world(self, world_id: str) -> list[dict]:
        return self.get_all(world_id=world_id)


class LayerRepository(BaseRepository):
    TABLE = "layers"

    def get_by_map(self, map_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE map_id = ? ORDER BY layer_order"
        return [dict(r) for r in self.db.fetchall(sql, (map_id,))]


class CanvasItemRepository(BaseRepository):
    TABLE = "canvas_items"

    def get_by_layer(self, layer_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE layer_id = ? ORDER BY z_index"
        return [dict(r) for r in self.db.fetchall(sql, (layer_id,))]

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


class AssetRepository(BaseRepository):
    TABLE = "assets"

    def get_by_pack(self, pack_id: str) -> list[dict]:
        return self.get_all(pack_id=pack_id)


class AssetPackRepository(BaseRepository):
    TABLE = "asset_packs"
