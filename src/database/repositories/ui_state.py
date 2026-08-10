"""UI State repository — generic per-project key/value store for small
"remember the last X" preferences that don't warrant their own table
(e.g. the Brush panel's last-picked asset)."""

from __future__ import annotations

from src.database.connection import Database


class UIStateRepository:
    TABLE = "ui_state"

    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.fetchone(f"SELECT value FROM {self.TABLE} WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str):
        with self.db.transaction():
            self.db.execute(
                f"INSERT INTO {self.TABLE} (key, value) VALUES (?, ?) "
                f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
