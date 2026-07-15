"""Asset Engine — complete pipeline: import, metadata, thumbnail, cache, browse.

Uses the global AssetLibrary (~/.makemap/library/) as primary source.
Project-level assets are a secondary layer for project-specific overrides.
"""

from __future__ import annotations

import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QSize
from PySide6.QtGui import QPixmap, QImage

from src.engines.assets.importer import AssetImporter, ImportResult
from src.engines.assets.thumbnail import ThumbnailGenerator
from src.engines.assets.cache import AssetCache
from src.engines.assets.library import AssetLibrary

if TYPE_CHECKING:
    from src.database.unit_of_work import UnitOfWork

logger = logging.getLogger("MAKEMAP")


@dataclass
class AssetInfo:
    """Full asset metadata."""
    id: str
    name: str
    asset_type: str = "image"
    source_path: str = ""
    thumbnail_path: str = ""
    width: int = 0
    height: int = 0
    pivot_x: float = 0.5
    pivot_y: float = 0.5
    default_scale: float = 1.0
    category: str = ""
    pack_id: str = ""
    author: str = ""
    license: str = ""
    hash: str = ""
    tags: list[str] = field(default_factory=list)


class AssetEngine(QObject):
    """Manages assets — delegates to global library + project-level overrides."""

    asset_imported = Signal(str)  # asset_id
    asset_deleted = Signal(str)  # asset_id

    def __init__(self, project_path: Path = None, uow: UnitOfWork | None = None, parent=None):
        super().__init__(parent)
        self._project_path = project_path
        self._uow = uow

        # Adjustments service (singleton)
        from src.services.asset_adjustments import AssetAdjustmentsService
        if not hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance = AssetAdjustmentsService()
        self._adj_service = AssetAdjustmentsService._instance

        # Global library (always available)
        self.library = AssetLibrary(self)

        # Project-level (optional, for project-specific imports)
        if project_path:
            self.importer = AssetImporter(project_path / "assets")
            self.thumbnails = ThumbnailGenerator(project_path / "thumbnails")
        else:
            self.importer = None
            self.thumbnails = None

        self.cache = AssetCache()

    def set_uow(self, uow: UnitOfWork):
        self._uow = uow

    # --- Import ---

    def import_asset(self, source: Path, category: str = "", pack_id: str = "") -> AssetInfo | None:
        """Import a file and register in database."""
        result = self.importer.import_file(source)
        if not result.success:
            logger.error("Falha ao importar: %s", result.error)
            return None

        # Get image dimensions
        image = QImage(str(result.asset_path))
        width = image.width() if not image.isNull() else 0
        height = image.height() if not image.isNull() else 0

        asset_id = str(uuid.uuid4())

        # Generate thumbnails
        thumb_paths = self.thumbnails.generate(result.asset_path, asset_id)
        thumb_path = str(thumb_paths.get("medium", ""))

        # Create metadata
        info = AssetInfo(
            id=asset_id,
            name=source.stem,
            source_path=str(result.asset_path),
            thumbnail_path=thumb_path,
            width=width,
            height=height,
            hash=result.hash,
            category=category,
            pack_id=pack_id,
        )

        # Persist to database
        if self._uow:
            self._uow.assets.create(
                id=info.id,
                name=info.name,
                asset_type=info.asset_type,
                source_path=info.source_path,
                thumbnail_path=info.thumbnail_path,
                width=info.width,
                height=info.height,
                pivot_x=info.pivot_x,
                pivot_y=info.pivot_y,
                default_scale=info.default_scale,
                category=info.category,
                pack_id=info.pack_id or None,
                author=info.author,
                license=info.license,
                hash=info.hash,
                tags="[]",
            )

        self.asset_imported.emit(asset_id)
        logger.info("Asset registrado: %s (%s)", info.name, asset_id)
        return info

    def import_batch(self, sources: list[Path], category: str = "") -> list[AssetInfo]:
        """Import multiple assets."""
        results = []
        for source in sources:
            info = self.import_asset(source, category=category)
            if info:
                results.append(info)
        return results

    # --- Retrieve ---

    def get_asset(self, asset_id: str) -> AssetInfo | None:
        """Get asset metadata from database."""
        if not self._uow:
            return None
        data = self._uow.assets.get(asset_id)
        if not data:
            return None
        return AssetInfo(
            id=data["id"],
            name=data["name"],
            asset_type=data["asset_type"],
            source_path=data["source_path"],
            thumbnail_path=data["thumbnail_path"],
            width=data["width"],
            height=data["height"],
            pivot_x=data["pivot_x"],
            pivot_y=data["pivot_y"],
            default_scale=data["default_scale"],
            category=data["category"],
            pack_id=data.get("pack_id", ""),
            author=data["author"],
            license=data["license"],
            hash=data["hash"],
        )

    def get_pixmap(self, asset_id: str) -> QPixmap | None:
        """Load asset pixmap — checks project DB first, then global library.
        Applies brightness/contrast adjustments via service if available."""
        cached = self.cache.get(asset_id)
        if cached:
            return self._apply_adjustment(cached, asset_id)

        # Try project database
        if self._uow:
            info = self.get_asset(asset_id)
            if info:
                path = Path(info.source_path)
                if path.exists():
                    pix = self.cache.load(asset_id, path)
                    return self._apply_adjustment(pix, asset_id) if pix else None

        # Fallback to global library
        pix = self.library.get_pixmap(asset_id)
        return self._apply_adjustment(pix, asset_id) if pix else None

    def _apply_adjustment(self, pixmap: QPixmap, asset_id: str) -> QPixmap:
        """Apply brightness/contrast via service if available."""
        if not self._adj_service:
            return pixmap
        info = self.get_asset(asset_id) if self._uow else None
        path = info.source_path if info else (self.library.get_path_by_id(asset_id) or "")
        return self._adj_service.get_adjusted_pixmap(path, pixmap)

    def get_pixmap_by_name(self, name: str) -> QPixmap | None:
        """Load pixmap by asset name — searches library."""
        return self.library.get_pixmap_by_name(name)

    def get_id_by_name(self, name: str) -> str | None:
        """Get asset ID by name — searches library."""
        return self.library.get_id_by_name(name)

    def get_thumbnail(self, asset_id: str, size: str = "medium") -> QPixmap | None:
        """Get thumbnail pixmap."""
        return self.thumbnails.get_pixmap(asset_id, size)

    # --- Browse ---

    def list_all(self) -> list[AssetInfo]:
        """List all assets in the project."""
        if not self._uow:
            return []
        rows = self._uow.assets.get_all()
        return [self._row_to_info(r) for r in rows]

    def list_by_category(self, category: str) -> list[AssetInfo]:
        """List assets filtered by category."""
        if not self._uow:
            return []
        rows = self._uow.assets.get_all(category=category)
        return [self._row_to_info(r) for r in rows]

    def list_by_pack(self, pack_id: str) -> list[AssetInfo]:
        """List assets in a specific pack."""
        if not self._uow:
            return []
        rows = self._uow.assets.get_by_pack(pack_id)
        return [self._row_to_info(r) for r in rows]

    def search(self, query: str) -> list[AssetInfo]:
        """Search assets by name."""
        if not self._uow:
            return []
        all_assets = self._uow.assets.get_all()
        q = query.lower()
        return [self._row_to_info(r) for r in all_assets if q in r["name"].lower()]

    # --- Delete ---

    def delete_asset(self, asset_id: str):
        """Remove asset from project."""
        info = self.get_asset(asset_id)
        if info:
            # Remove file
            path = Path(info.source_path)
            if path.exists():
                path.unlink()

            # Remove thumbnails
            self.thumbnails.invalidate(asset_id)

            # Remove from cache
            self.cache.invalidate(asset_id)

            # Remove from database
            if self._uow:
                self._uow.assets.delete(asset_id)

            self.asset_deleted.emit(asset_id)

    # --- Packs ---

    def create_pack(self, name: str, description: str = "", author: str = "") -> str:
        """Create a new asset pack."""
        pack_id = str(uuid.uuid4())
        if self._uow:
            self._uow.asset_packs.create(
                id=pack_id, name=name, description=description, author=author
            )
        return pack_id

    def list_packs(self) -> list[dict]:
        """List all asset packs."""
        if not self._uow:
            return []
        return self._uow.asset_packs.get_all()

    # --- Helpers ---

    def _row_to_info(self, row: dict) -> AssetInfo:
        return AssetInfo(
            id=row["id"],
            name=row["name"],
            asset_type=row.get("asset_type", "image"),
            source_path=row.get("source_path", ""),
            thumbnail_path=row.get("thumbnail_path", ""),
            width=row.get("width", 0),
            height=row.get("height", 0),
            pivot_x=row.get("pivot_x", 0.5),
            pivot_y=row.get("pivot_y", 0.5),
            default_scale=row.get("default_scale", 1.0),
            category=row.get("category", ""),
            pack_id=row.get("pack_id", ""),
            author=row.get("author", ""),
            license=row.get("license", ""),
            hash=row.get("hash", ""),
        )
