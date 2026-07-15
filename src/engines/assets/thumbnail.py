"""Thumbnail Generator — creates and caches thumbnails at multiple resolutions."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger("MAKEMAP")

THUMBNAIL_SIZE = 128


class ThumbnailGenerator:
    """Generates and caches asset thumbnails (single size: 128px)."""

    def __init__(self, thumbnails_dir: Path):
        self._dir = thumbnails_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self, asset_path: Path, asset_id: str) -> dict[str, Path]:
        """Generate a single thumbnail. Returns {"medium": path}."""
        image = QImage(str(asset_path))
        if image.isNull():
            logger.warning("Não foi possível carregar imagem: %s", asset_path)
            return {}

        thumb_path = self._dir / f"{asset_id}.png"
        scaled = image.scaled(
            QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE),
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
        scaled.save(str(thumb_path), "PNG")
        return {"medium": thumb_path}

    def get(self, asset_id: str, size: str = "medium") -> Path | None:
        """Get cached thumbnail path."""
        thumb_path = self._dir / f"{asset_id}.png"
        return thumb_path if thumb_path.exists() else None

    def invalidate(self, asset_id: str):
        """Remove cached thumbnail."""
        path = self._dir / f"{asset_id}.png"
        if path.exists():
            path.unlink()

    def get_pixmap(self, asset_id: str, size: str = "medium") -> QPixmap | None:
        """Load thumbnail as QPixmap."""
        path = self.get(asset_id, size)
        if path:
            pix = QPixmap(str(path))
            if not pix.isNull():
                return pix
        return None
