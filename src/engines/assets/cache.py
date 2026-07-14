"""Asset Cache — in-memory LRU cache for loaded asset pixmaps."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtGui import QPixmap


class AssetCache:
    """LRU cache for loaded QPixmaps."""

    DEFAULT_MAX = 200  # max cached items

    def __init__(self, max_items: int = DEFAULT_MAX):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max = max_items

    def get(self, asset_id: str) -> QPixmap | None:
        """Get a cached pixmap, moving it to most-recent."""
        if asset_id in self._cache:
            self._cache.move_to_end(asset_id)
            return self._cache[asset_id]
        return None

    def put(self, asset_id: str, pixmap: QPixmap):
        """Cache a pixmap."""
        if asset_id in self._cache:
            self._cache.move_to_end(asset_id)
        else:
            if len(self._cache) >= self._max:
                self._cache.popitem(last=False)
            self._cache[asset_id] = pixmap

    def load(self, asset_id: str, path: Path) -> QPixmap | None:
        """Load from disk into cache, or return cached."""
        cached = self.get(asset_id)
        if cached:
            return cached

        pix = QPixmap(str(path))
        if pix.isNull():
            return None

        self.put(asset_id, pix)
        return pix

    def invalidate(self, asset_id: str):
        """Remove from cache."""
        self._cache.pop(asset_id, None)

    def clear(self):
        """Clear entire cache."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
