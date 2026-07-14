"""Asset Importer — validates, deduplicates, and copies assets into the project."""

from __future__ import annotations

import hashlib
import shutil
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger("MAKEMAP")

SUPPORTED_FORMATS = {".png", ".webp", ".svg", ".jpg", ".jpeg"}
MAX_DIMENSION = 8192


@dataclass
class ImportResult:
    success: bool
    asset_path: Path | None = None
    hash: str = ""
    error: str = ""


class AssetImporter:
    """Imports image files into the project asset directory."""

    def __init__(self, project_assets_dir: Path):
        self._dir = project_assets_dir / "imported"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._hashes: set[str] = set()
        self._scan_existing()

    def import_file(self, source: Path) -> ImportResult:
        """Import a single file with validation and dedup."""
        # Validate format
        if source.suffix.lower() not in SUPPORTED_FORMATS:
            return ImportResult(False, error=f"Formato não suportado: {source.suffix}")

        if not source.exists():
            return ImportResult(False, error="Arquivo não encontrado")

        # Validate size
        if source.stat().st_size > 50 * 1024 * 1024:  # 50MB
            return ImportResult(False, error="Arquivo excede 50MB")

        # Hash for dedup
        file_hash = self._compute_hash(source)
        if file_hash in self._hashes:
            # Find existing file with this hash
            existing = self._find_by_hash(file_hash)
            if existing:
                return ImportResult(True, asset_path=existing, hash=file_hash)

        # Copy to project
        dest = self._dir / source.name
        if dest.exists():
            stem = source.stem
            suffix = source.suffix
            counter = 1
            while dest.exists():
                dest = self._dir / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.copy2(source, dest)
        self._hashes.add(file_hash)
        logger.info("Asset importado: %s -> %s", source.name, dest.name)
        return ImportResult(True, asset_path=dest, hash=file_hash)

    def import_batch(self, sources: list[Path]) -> list[ImportResult]:
        """Import multiple files."""
        return [self.import_file(s) for s in sources]

    def _compute_hash(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _find_by_hash(self, file_hash: str) -> Path | None:
        for f in self._dir.iterdir():
            if f.is_file() and self._compute_hash(f) == file_hash:
                return f
        return None

    def _scan_existing(self):
        """Scan existing assets to populate hash set."""
        if not self._dir.exists():
            return
        for f in self._dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS:
                self._hashes.add(self._compute_hash(f))
