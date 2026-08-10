"""World-adjacent repositories still in real use — administrative regions
(read by the Quests panel's region dropdown) and lore entries. The rest of
the originally-planned world hierarchy (world > continent > kingdom, plus
biomes/cities/events/factions/tags) was never wired to any UI — no panel
ever creates/reads those tables — and was removed from here; the tables
themselves are left alone in schema.py rather than dropped."""

from src.database.repositories.base import BaseRepository


class RegionRepository(BaseRepository):
    TABLE = "regions"


class LoreRepository(BaseRepository):
    TABLE = "lore_entries"
