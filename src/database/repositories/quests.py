"""Quests panel repositories — quests, their chains, and the quest/NPC
role join table (who gives/receives each quest)."""

from src.database.repositories.base import BaseRepository


class QuestRepository(BaseRepository):
    TABLE = "quests"

    def get_by_chain(self, chain_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE chain_id = ? ORDER BY chain_order"
        return [dict(r) for r in self.db.fetchall(sql, (chain_id,))]


class QuestChainRepository(BaseRepository):
    TABLE = "quest_chains"


class QuestNPCRepository:
    """quest_npcs — join table com PK composta (quest_id, npc_id), sem coluna
    `id` própria, então não dá pra herdar de BaseRepository (create() dele
    sempre tenta inserir um `id` que essa tabela não tem). `role` distingue
    quem entrega a quest ("giver") de quem a recebe de volta ("turn_in")."""

    TABLE = "quest_npcs"

    def __init__(self, db):
        self.db = db

    def get_by_quest(self, quest_id: str) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE} WHERE quest_id = ?"
        return [dict(r) for r in self.db.fetchall(sql, (quest_id,))]

    def distinct_npc_ids(self) -> list[str]:
        """Quantos NPCs distintos estão envolvidos em pelo menos uma quest
        (como giver ou turn_in) — usado pelo card "Resumo do Projeto"."""
        rows = self.db.fetchall(f"SELECT DISTINCT npc_id FROM {self.TABLE}")
        return [r["npc_id"] for r in rows]

    def set_role(self, quest_id: str, npc_id: str | None, role: str):
        """Substitui quem ocupa esse papel ("giver"/"turn_in") nesta quest —
        no máximo um NPC por papel, então tira o antigo antes de gravar o
        novo (ou só tira, se `npc_id` vier vazio)."""
        with self.db.transaction() as conn:
            conn.execute(f"DELETE FROM {self.TABLE} WHERE quest_id = ? AND role = ?", (quest_id, role))
            if npc_id:
                conn.execute(
                    f"INSERT INTO {self.TABLE} (quest_id, npc_id, role) VALUES (?, ?, ?)",
                    (quest_id, npc_id, role),
                )
