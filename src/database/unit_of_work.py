"""Unit of Work — single access point to all repositories for a project."""

from __future__ import annotations

from pathlib import Path

from src.database.connection import Database
from src.database.migrations.schema import run_migrations
from src.database.repositories.entities import (
    WorldRepository, ContinentRepository, KingdomRepository,
    RegionRepository, BiomeRepository, CityRepository,
    NPCRepository, MobRepository, BossRepository,
    ItemRepository, ResourceRepository, QuestRepository,
    QuestChainRepository, DungeonRepository, EventRepository,
    FactionRepository, TagRepository, MapRepository,
    LayerRepository, CanvasItemRepository, AssetRepository,
    AssetPackRepository,
)


class UnitOfWork:
    """Provides transactional access to all repositories."""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.db.connect()
        run_migrations(self.db)

        # Repositories
        self.worlds = WorldRepository(self.db)
        self.continents = ContinentRepository(self.db)
        self.kingdoms = KingdomRepository(self.db)
        self.regions = RegionRepository(self.db)
        self.biomes = BiomeRepository(self.db)
        self.cities = CityRepository(self.db)
        self.npcs = NPCRepository(self.db)
        self.mobs = MobRepository(self.db)
        self.bosses = BossRepository(self.db)
        self.items = ItemRepository(self.db)
        self.resources = ResourceRepository(self.db)
        self.quests = QuestRepository(self.db)
        self.quest_chains = QuestChainRepository(self.db)
        self.dungeons = DungeonRepository(self.db)
        self.events = EventRepository(self.db)
        self.factions = FactionRepository(self.db)
        self.tags = TagRepository(self.db)
        self.maps = MapRepository(self.db)
        self.layers = LayerRepository(self.db)
        self.canvas_items = CanvasItemRepository(self.db)
        self.assets = AssetRepository(self.db)
        self.asset_packs = AssetPackRepository(self.db)

    def close(self):
        self.db.close()
