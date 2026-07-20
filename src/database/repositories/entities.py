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


class BossRepository(BaseRepository):
    TABLE = "bosses"

    def get_by_dungeon(self, dungeon_id: str) -> list[dict]:
        return self.get_all(dungeon_id=dungeon_id)


class ItemRepository(BaseRepository):
    TABLE = "items"

    def get_by_rarity(self, rarity: str) -> list[dict]:
        return self.get_all(rarity=rarity)


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


class AssetRepository(BaseRepository):
    TABLE = "assets"

    def get_by_pack(self, pack_id: str) -> list[dict]:
        return self.get_all(pack_id=pack_id)


class AssetPackRepository(BaseRepository):
    TABLE = "asset_packs"
