"""Global Asset Library schema migrations — versioned (schema_version table +
ordered migration list), same approach src/database/migrations/schema.py
uses for a project's own database, instead of the "ALTER TABLE if column
missing" ad-hoc pattern AssetLibrary._init_db() used to run inline (no
version tracking, no guard against a script failing partway through).

Scoped to its own schema_version table inside library.sqlite (see
src/engines/assets/library.py) — entirely separate from any project's own
schema_version, since the library is one global app-wide database, not a
per-project file.
"""

from __future__ import annotations

import sqlite3
import logging

from src.database.connection import Database

logger = logging.getLogger("MAKEMAP")

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "Base assets/asset_sounds tables — the library's original shape", """
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            source_path TEXT NOT NULL UNIQUE,
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            hash TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            favorite INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS asset_sounds (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            prefix   TEXT NOT NULL,
            path     TEXT NOT NULL,
            volume   REAL DEFAULT 0.7,
            display_name TEXT DEFAULT '',
            UNIQUE(asset_id, prefix)
        );
    """),
    (2, "sort_order column — manual drag-reorder within a category", """
        ALTER TABLE assets ADD COLUMN sort_order INTEGER DEFAULT 0;
    """),
    (3, "style column — art-style dimension added on top of category", """
        ALTER TABLE assets ADD COLUMN style TEXT DEFAULT '';
    """),
    (4, "shore_foam column — per-asset shoreline foam toggle for water assets", """
        ALTER TABLE assets ADD COLUMN shore_foam INTEGER DEFAULT 1;
    """),
]


def run_library_migrations(db: Database):
    """Apply all pending migrations to the library DB. Same executescript +
    already-applied guard as schema.py's run_migrations (see its docstring
    for why: executescript() auto-commits DDL regardless of transaction(),
    so a script that failed partway must not be retried from scratch on
    next launch)."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.conn.commit()

    row = db.fetchone("SELECT MAX(version) as v FROM schema_version")
    current = row["v"] if row and row["v"] is not None else 0
    pending = [m for m in MIGRATIONS if m[0] > current]

    for version, desc, sql in pending:
        logger.info("Aplicando migration de library %d: %s", version, desc)
        try:
            db.conn.executescript(sql)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "already exists" in msg or "duplicate column" in msg:
                logger.warning(
                    "Migration de library %d parcialmente aplicada em execução anterior (%s) — marcando como concluída.",
                    version, e,
                )
            else:
                raise
        db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        db.conn.commit()
