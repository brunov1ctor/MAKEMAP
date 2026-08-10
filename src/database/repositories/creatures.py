"""NPCs and Mobs repositories — the two entity-panel trees (see
src/layouts/panels/npcs/, src/layouts/panels/mobs/), their category
sidebars, and stamp assets. Bosses are a Mobs sub-concept tracked via the
"Boss" mob_categories folder — the separate `bosses` table/BossRepository
had no UI writing to it anywhere in the app and was removed from here."""

from src.database.repositories.base import BaseRepository, CategoryTreeRepository


class NPCRepository(BaseRepository):
    TABLE = "npcs"


class NPCCategoryRepository(CategoryTreeRepository):
    """Directory-style tree for the NPCs panel's category sidebar — mirrors
    MobCategoryRepository (see migration 27 in schema.py)."""
    TABLE = "npc_categories"


class NPCAssetRepository(BaseRepository):
    """Stamp assets attached to an NPC (see migration 27) — mirrors
    MobAssetRepository; the Spawn tool's NPCs mode places one of these."""
    TABLE = "npc_assets"

    def get_by_npc(self, npc_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE npc_id = ? ORDER BY sort_order, created_at"
        return [dict(r) for r in self.db.fetchall(sql, (npc_id,))]


class MobRepository(BaseRepository):
    TABLE = "mobs"


class MobCategoryRepository(CategoryTreeRepository):
    """Directory-style tree for the Mobs panel's category sidebar — see
    migration 5 in schema.py. parent_id NULL means a root-level folder."""
    TABLE = "mob_categories"


class MobAssetRepository(BaseRepository):
    """Stamp assets attached to a mob (see migration 8) — the eventual
    canvas "Mobs" placement tool will place one of these, same idea as
    BrushTool's object-stamp mode but tied to a specific mob record."""
    TABLE = "mob_assets"

    def get_by_mob(self, mob_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE mob_id = ? ORDER BY sort_order, created_at"
        return [dict(r) for r in self.db.fetchall(sql, (mob_id,))]
