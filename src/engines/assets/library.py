"""Global Asset Library — app-wide asset storage alongside the source code.

Location: <project_root>/library/
Structure:
    MAKEMAP/
    └── library/
        ├── library.sqlite       ← metadata database
        ├── thumbnails/          ← generated thumbnails
        ├── terrain/             ← grass, sand, water, snow, lava
        ├── trees/               ← árvores, arbustos, vegetação
        ├── mountains/           ← montanhas, colinas
        ├── rocks/               ← pedras, rochas
        ├── buildings/           ← casas, torres, castelos, ruínas
        ├── effects/             ← nuvens, neblina, partículas
        └── misc/                ← outros

Usage:
    Drop any PNG/WEBP/JPG into the correct subfolder.
    The library auto-detects and registers it.
"""

from __future__ import annotations

import uuid
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal, QFileSystemWatcher, QTimer
from PySide6.QtGui import QPixmap, QImage

from src.engines.assets.thumbnail import ThumbnailGenerator
from src.engines.assets.cache import AssetCache

logger = logging.getLogger("MAKEMAP")

# Library lives alongside the source code
_SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIBRARY_DIR = _SOURCE_ROOT / "library"
LIBRARY_DB = LIBRARY_DIR / "library.sqlite"

SUPPORTED_FORMATS = {".png", ".webp", ".svg", ".jpg", ".jpeg"}

CATEGORY_FOLDERS = [
    "terrain",
    "trees",
    "mountains",
    "rocks",
    "buildings",
    "effects",
    "misc",
]


@dataclass
class LibraryAsset:
    """Asset metadata in the global library."""
    id: str
    name: str
    category: str = ""
    source_path: str = ""
    width: int = 0
    height: int = 0
    hash: str = ""
    tags: list[str] = field(default_factory=list)


class AssetLibrary(QObject):
    """Global asset library — independent of projects.

    Assets live in ~/.makemap/library/<category>/
    Drop files there and they get auto-registered.
    """

    asset_added = Signal(str)  # asset name
    asset_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Ensure directory structure
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        for folder in CATEGORY_FOLDERS:
            (LIBRARY_DIR / folder).mkdir(exist_ok=True)

        # Database
        self._db = self._init_db()

        # Thumbnails & cache
        self._thumb_dir = LIBRARY_DIR / "thumbnails"
        self._thumb_dir.mkdir(exist_ok=True)
        self.thumbnails = ThumbnailGenerator(self._thumb_dir)
        self.cache = AssetCache()

        # File watcher
        self._watcher = QFileSystemWatcher(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.sync)

        self._start_watching()

        # Initial sync
        self.sync()

    # ─── Database ────────────────────────────────────────────────────────

    def _init_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(LIBRARY_DB))
        db.row_factory = sqlite3.Row
        db.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                source_path TEXT NOT NULL UNIQUE,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                hash TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
        return db

    # ─── Watcher ─────────────────────────────────────────────────────────

    def _start_watching(self):
        dirs = [str(LIBRARY_DIR / f) for f in CATEGORY_FOLDERS]
        self._watcher.addPaths(dirs)
        self._watcher.directoryChanged.connect(lambda _: self._timer.start())

    def stop(self):
        paths = self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)

    # ─── Sync ────────────────────────────────────────────────────────────

    def sync(self):
        """Scan all category folders and register new files / fix missing thumbnails."""
        registered = self._get_registered_paths()

        # Detect orphan paths (file was renamed/moved/deleted)
        for path_str in registered:
            if not Path(path_str).exists():
                self._db.execute("DELETE FROM assets WHERE source_path = ?", (path_str,))
        self._db.commit()

        # Re-fetch after cleanup
        registered = self._get_registered_paths()

        for folder_name in CATEGORY_FOLDERS:
            folder = LIBRARY_DIR / folder_name
            if not folder.exists():
                continue

            for file in folder.iterdir():
                if not file.is_file():
                    continue
                if file.suffix.lower() not in SUPPORTED_FORMATS:
                    continue
                if str(file) in registered:
                    continue

                self._register(file, category=folder_name)

        # Ensure all registered assets have thumbnails
        self._ensure_thumbnails()

    def _ensure_thumbnails(self):
        """Regenerate missing thumbnails for all registered assets."""
        rows = self._db.execute("SELECT id, source_path FROM assets").fetchall()
        for row in rows:
            thumb_path = self._thumb_dir / f"{row['id']}.png"
            if not thumb_path.exists():
                src = Path(row["source_path"])
                if src.exists():
                    self.thumbnails.generate(src, row["id"])

    def _register(self, file: Path, category: str):
        """Register a single file into the library."""
        import hashlib

        # Hash
        h = hashlib.sha256()
        with open(file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        file_hash = h.hexdigest()[:16]

        # Check duplicate by hash — update name/path if file was renamed
        existing = self._db.execute(
            "SELECT id, source_path, name FROM assets WHERE hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            if existing["source_path"] != str(file) or existing["name"] != file.stem:
                self._db.execute(
                    "UPDATE assets SET source_path = ?, name = ?, category = ? WHERE id = ?",
                    (str(file), file.stem, category, existing["id"]),
                )
                self._db.commit()
                logger.info("Library: renomeado %s → %s", existing["name"], file.stem)
            # Ensure thumbnail exists
            thumb_path = self._thumb_dir / f"{existing['id']}.png"
            if not thumb_path.exists():
                self.thumbnails.generate(file, existing["id"])
            return

        # Image dimensions
        image = QImage(str(file))
        width = image.width() if not image.isNull() else 0
        height = image.height() if not image.isNull() else 0

        asset_id = str(uuid.uuid4())

        # Generate thumbnail
        self.thumbnails.generate(file, asset_id)

        # Insert into database
        self._db.execute(
            """INSERT INTO assets (id, name, category, source_path, width, height, hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, file.stem, category, str(file), width, height, file_hash),
        )
        self._db.commit()

        self.asset_added.emit(file.stem)
        logger.info("Library: registrado %s [%s] (%s)", file.stem, category, asset_id[:8])

    # ─── Retrieve ────────────────────────────────────────────────────────

    def get_pixmap(self, asset_id: str) -> QPixmap | None:
        """Load asset pixmap by ID."""
        cached = self.cache.get(asset_id)
        if cached:
            return cached

        row = self._db.execute(
            "SELECT source_path FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if not row:
            return None

        path = Path(row["source_path"])
        if not path.exists():
            return None

        return self.cache.load(asset_id, path)

    def get_pixmap_by_name(self, name: str) -> QPixmap | None:
        """Load asset pixmap by name (convenience for brush configs)."""
        row = self._db.execute(
            "SELECT id, source_path FROM assets WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None

        cached = self.cache.get(row["id"])
        if cached:
            return cached

        path = Path(row["source_path"])
        if not path.exists():
            return None

        return self.cache.load(row["id"], path)

    def get_id_by_name(self, name: str) -> str | None:
        """Get asset ID by filename (without extension)."""
        row = self._db.execute(
            "SELECT id FROM assets WHERE name = ?", (name,)
        ).fetchone()
        return row["id"] if row else None

    def get_thumbnail(self, asset_id: str, size: str = "medium") -> QPixmap | None:
        return self.thumbnails.get_pixmap(asset_id, size)

    # ─── Browse ──────────────────────────────────────────────────────────

    def list_all(self) -> list[LibraryAsset]:
        rows = self._db.execute("SELECT * FROM assets ORDER BY category, name").fetchall()
        return [self._row_to_asset(r) for r in rows]

    def list_by_category(self, category: str) -> list[LibraryAsset]:
        rows = self._db.execute(
            "SELECT * FROM assets WHERE category = ? ORDER BY name", (category,)
        ).fetchall()
        return [self._row_to_asset(r) for r in rows]

    def search(self, query: str) -> list[LibraryAsset]:
        rows = self._db.execute(
            "SELECT * FROM assets WHERE name LIKE ? ORDER BY name",
            (f"%{query}%",),
        ).fetchall()
        return [self._row_to_asset(r) for r in rows]

    @property
    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) as c FROM assets").fetchone()
        return row["c"] if row else 0

    # ─── Delete ──────────────────────────────────────────────────────────

    def delete_asset(self, asset_id: str):
        row = self._db.execute(
            "SELECT source_path FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if row:
            path = Path(row["source_path"])
            if path.exists():
                path.unlink()
            self.thumbnails.invalidate(asset_id)
            self.cache.invalidate(asset_id)
            self._db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            self._db.commit()
            self.asset_removed.emit(asset_id)

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _get_registered_paths(self) -> set[str]:
        rows = self._db.execute("SELECT source_path FROM assets").fetchall()
        return {row["source_path"] for row in rows}

    def _row_to_asset(self, row) -> LibraryAsset:
        return LibraryAsset(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            source_path=row["source_path"],
            width=row["width"],
            height=row["height"],
            hash=row["hash"],
        )

    @property
    def library_path(self) -> Path:
        return LIBRARY_DIR
