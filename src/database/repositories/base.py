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
