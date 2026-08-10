"""Dungeons e Construções panel repositories — dungeons and buildings share
one panel (see src/layouts/panels/dungeons/), each with its own type/
category vocabulary table."""

from src.database.repositories.base import BaseRepository


class DungeonRepository(BaseRepository):
    TABLE = "dungeons"


class BuildingRepository(BaseRepository):
    TABLE = "buildings"


class BuildingCategoryRepository(BaseRepository):
    TABLE = "building_categories"


class DungeonTypeRepository(BaseRepository):
    TABLE = "dungeon_types"
