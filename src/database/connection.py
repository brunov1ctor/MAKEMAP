"""Database connection manager — SQLite per project."""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger("MAKEMAP")


class Database:
    """Manages a single SQLite connection for a project."""

    def __init__(self, db_path: Path):
        self.path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        logger.info("DB conectado: %s", self.path)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            self.connect()
        return self._conn

    @contextmanager
    def transaction(self):
        """Context manager for atomic transactions."""
        conn = self.conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        return self.conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def table_columns(self, table: str) -> list[str]:
        """Column names for `table` via PRAGMA table_info — lets callers
        validate/filter a payload (e.g. an imported file) against the real
        schema without depending on any row already being loaded. `table`
        must be a trusted literal (e.g. a repository's own TABLE constant)
        since PRAGMA doesn't support parameter binding for identifiers."""
        return [row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()]
