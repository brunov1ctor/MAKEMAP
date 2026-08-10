"""Unit of Work — single access point to all repositories for a project."""

from __future__ import annotations

from pathlib import Path

from src.database.connection import Database
from src.database.migrations.schema import run_migrations
from src.database.repositories.world import RegionRepository, LoreRepository
from src.database.repositories.creatures import (
    NPCRepository, NPCCategoryRepository, NPCAssetRepository,
    MobRepository, MobCategoryRepository, MobAssetRepository,
)
from src.database.repositories.items import (
    ItemRepository, SkillRepository, SkillTreeRepository, ProgressionRepository,
)
from src.database.repositories.quests import QuestRepository, QuestChainRepository, QuestNPCRepository
from src.database.repositories.dungeons import (
    DungeonRepository, BuildingRepository, BuildingCategoryRepository, DungeonTypeRepository,
)
from src.database.repositories.map import (
    CanvasItemRepository, ZoneRepository, TerrainPaintRepository, TerrainRepository,
    ExplorerOverrideRepository,
)
from src.database.repositories.asset_settings import AssetSettingsRepository
from src.database.repositories.ui_state import UIStateRepository


class UnitOfWork:
    """Provides transactional access to all repositories."""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.db.connect()
        run_migrations(self.db)

        # Repositories
        self.regions = RegionRepository(self.db)
        self.npcs = NPCRepository(self.db)
        self.npc_categories = NPCCategoryRepository(self.db)
        self.npc_assets = NPCAssetRepository(self.db)
        self.mobs = MobRepository(self.db)
        self.mob_categories = MobCategoryRepository(self.db)
        self.mob_assets = MobAssetRepository(self.db)
        self.items = ItemRepository(self.db)
        self.skills = SkillRepository(self.db)
        self.skill_trees = SkillTreeRepository(self.db)
        self.progression = ProgressionRepository(self.db)
        self.quests = QuestRepository(self.db)
        self.quest_chains = QuestChainRepository(self.db)
        self.quest_npcs = QuestNPCRepository(self.db)
        self.lore = LoreRepository(self.db)
        self.dungeons = DungeonRepository(self.db)
        self.buildings = BuildingRepository(self.db)
        self.building_categories = BuildingCategoryRepository(self.db)
        self.dungeon_types = DungeonTypeRepository(self.db)
        self.canvas_items = CanvasItemRepository(self.db)
        self.asset_settings = AssetSettingsRepository(self.db)
        self.zones = ZoneRepository(self.db)
        self.painted_terrain = TerrainPaintRepository(self.db)
        self.terrains = TerrainRepository(self.db)
        self.explorer_overrides = ExplorerOverrideRepository(self.db)
        self.ui_state = UIStateRepository(self.db)

    def close(self):
        self.db.close()
