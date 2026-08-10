"""Itens e Habilidades panel — items, skills, and the skill-tree node graph.
ProgressionRepository lives here too: same keyed-upsert shape as
SkillTreeRepository (one row per tab holding a whole node-graph JSON blob),
even though it belongs to the separate Progressão do Mundo panel."""

from src.database.repositories.base import BaseRepository, KeyedRepository


class ItemRepository(BaseRepository):
    TABLE = "items"


class SkillRepository(BaseRepository):
    """Habilidades — the Itens e Habilidades panel's skill catalog (see
    migration 12). Same shape/reasoning as ItemRepository: a few real
    columns, everything else in the `stats` JSON blob."""
    TABLE = "skills"


class SkillTreeRepository(KeyedRepository):
    """Árvore de Habilidades — one row per element tab, keyed by tree_key
    (NOT a uuid `id`), each holding the whole node graph as a JSON `data`
    blob. See KeyedRepository for the shared upsert/get/delete-by-key
    logic (same shape as ProgressionRepository below)."""
    TABLE = "skill_trees"
    KEY_COLUMN = "tree_key"

    def get_all_ordered(self) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} ORDER BY sort_order, name"
        return [dict(r) for r in self.db.fetchall(sql)]

    def upsert(self, tree_key: str, **fields):
        self._upsert(tree_key, **fields)

    def delete_tree(self, tree_key: str) -> bool:
        return self._delete_by_key(tree_key)


class ProgressionRepository(KeyedRepository):
    """Progressão do Mundo — one row per pipeline (aba), keyed by
    pipeline_key (NOT a uuid `id`), each holding the whole node graph as a
    JSON `data` blob. Same shape as SkillTreeRepository above."""
    TABLE = "progression_pipelines"
    KEY_COLUMN = "pipeline_key"

    def get_all_ordered(self) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} ORDER BY sort_order, name"
        return [dict(r) for r in self.db.fetchall(sql)]

    def get_pipeline(self, pipeline_key: str) -> dict | None:
        return self._get_by_key(pipeline_key)

    def upsert(self, pipeline_key: str, **fields):
        self._upsert(pipeline_key, **fields)
