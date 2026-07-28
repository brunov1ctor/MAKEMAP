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
        existing = self.db.fetchone(f"SELECT key FROM {self.TABLE} WHERE key = ?", (key,))
        with self.db.transaction():
            if existing:
                self.db.execute(f"UPDATE {self.TABLE} SET value = ? WHERE key = ?", (value, key))
            else:
                self.db.execute(f"INSERT INTO {self.TABLE} (key, value) VALUES (?, ?)", (key, value))
