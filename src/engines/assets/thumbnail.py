"""Thumbnail Generator — creates and caches thumbnails at multiple resolutions."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger("MAKEMAP")

THUMBNAIL_SIZES = {
    "small": 64,
    "medium": 128,
    "large": 256,
}


class ThumbnailGenerator:
    """Generates and caches asset thumbnails."""

    def __init__(self, thumbnails_dir: Path):
        self._dir = thumbnails_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self, asset_path: Path, asset_id: str) -> dict[str, Path]:
        """Generate thumbnails at all sizes. Returns {size_name: path}."""
        results = {}

        image = QImage(str(asset_path))
        if image.isNull():
            logger.warning("Não foi possível carregar imagem: %s", asset_path)
            return results

        for name, size in THUMBNAIL_SIZES.items():
            thumb_path = self._dir / f"{asset_id}_{name}.png"
            scaled = image.scaled(
                QSize(size, size),
                aspectMode=1,  # KeepAspectRatio
                mode=1,  # SmoothTransformation
            )
            scaled.save(str(thumb_path), "PNG")
            results[name] = thumb_path

        return results

    def get(self, asset_id: str, size: str = "medium") -> Path | None:
        """Get cached thumbnail path."""
        thumb_path = self._dir / f"{asset_id}_{size}.png"
        return thumb_path if thumb_path.exists() else None

    def invalidate(self, asset_id: str):
        """Remove all cached thumbnails for an asset."""
        for name in THUMBNAIL_SIZES:
            path = self._dir / f"{asset_id}_{name}.png"
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
