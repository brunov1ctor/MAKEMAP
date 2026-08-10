"""Base repository — generic CRUD for all entities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.database.connection import Database


class BaseRepository:
    """Generic CRUD repository for a single table."""

    TABLE: str = ""

    def __init__(self, db: Database):
        self.db = db

    def create(self, **fields) -> str:
        if "id" not in fields:
            fields["id"] = str(uuid.uuid4())
        now = datetime.now().isoformat()
        fields.setdefault("created_at", now)
        fields.setdefault("updated_at", now)

        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        sql = f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

        with self.db.transaction():
            self.db.execute(sql, tuple(fields.values()))
        return fields["id"]

    def get(self, entity_id: str) -> dict | None:
        row = self.db.fetchone(f"SELECT * FROM {self.TABLE} WHERE id = ?", (entity_id,))
        return dict(row) if row else None

    def get_all(self, **filters) -> list[dict]:
        sql = f"SELECT * FROM {self.TABLE}"
        params = []
        if filters:
            clauses = []
            for k, v in filters.items():
                clauses.append(f"{k} = ?")
                params.append(v)
            sql += " WHERE " + " AND ".join(clauses)
        return [dict(r) for r in self.db.fetchall(sql, tuple(params))]

    def update(self, entity_id: str, **fields) -> bool:
        fields["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k} = ?" for k in fields)
        sql = f"UPDATE {self.TABLE} SET {sets} WHERE id = ?"
        params = tuple(fields.values()) + (entity_id,)

        with self.db.transaction():
            cursor = self.db.execute(sql, params)
        return cursor.rowcount > 0

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction():
            cursor = self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (entity_id,))
        return cursor.rowcount > 0

    def count(self, **filters) -> int:
        sql = f"SELECT COUNT(*) as c FROM {self.TABLE}"
        params = []
        if filters:
            clauses = [f"{k} = ?" for k in filters]
            params = list(filters.values())
            sql += " WHERE " + " AND ".join(clauses)
        row = self.db.fetchone(sql, tuple(params))
        return row["c"] if row else 0


class KeyedRepository(BaseRepository):
    """Shared insert-or-update-by-natural-key logic for tables whose PK is
    a stable key column, not a generated uuid `id` — e.g. SkillTreeRepository
    (tree_key) and ProgressionRepository (pipeline_key), which both hold one
    row per tab with the whole node graph as a JSON `data` blob and share
    this exact upsert/get/delete shape; only KEY_COLUMN differs."""

    KEY_COLUMN: str = ""

    def _get_by_key(self, key_value: str) -> dict | None:
        row = self.db.fetchone(f"SELECT * FROM {self.TABLE} WHERE {self.KEY_COLUMN} = ?", (key_value,))
        return dict(row) if row else None

    def _upsert(self, key_value: str, **fields):
        fields["updated_at"] = datetime.now().isoformat()
        fields.setdefault("created_at", datetime.now().isoformat())
        all_fields = {self.KEY_COLUMN: key_value, **fields}
        cols = ", ".join(all_fields.keys())
        placeholders = ", ".join("?" for _ in all_fields)
        # created_at is only meaningful on first insert — excluded() here is
        # the value that WOULD have been inserted, so leaving it out of the
        # update list keeps the original creation timestamp on conflict.
        sets = ", ".join(f"{k} = excluded.{k}" for k in fields if k != "created_at")
        with self.db.transaction():
            self.db.execute(
                f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT({self.KEY_COLUMN}) DO UPDATE SET {sets}",
                tuple(all_fields.values()),
            )

    def _delete_by_key(self, key_value: str) -> bool:
        with self.db.transaction():
            cursor = self.db.execute(f"DELETE FROM {self.TABLE} WHERE {self.KEY_COLUMN} = ?", (key_value,))
        return cursor.rowcount > 0


class CategoryTreeRepository(BaseRepository):
    """Shared parent_id-tree logic for directory-style category sidebars
    (Mobs/NPCs category trees, see migrations 5/27 in schema.py) — both
    tables share the same (id, parent_id, sort_order, name) shape, so
    get_children/get_path are identical; only TABLE differs per subclass."""

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
