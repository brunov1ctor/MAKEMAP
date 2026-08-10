"""Asset Engine — pixmap retrieval/caching/adjustments on top of the global
AssetLibrary (~/.makemap/library/), plus a per-pixmap brightness/contrast
adjustment service."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from src.engines.assets.cache import AssetCache
from src.engines.assets.library import AssetLibrary


class AssetEngine(QObject):
    """Manages assets — delegates to the global AssetLibrary."""

    asset_imported = Signal(str)  # asset_id
    asset_deleted = Signal(str)  # asset_id

    def __init__(self, parent=None):
        super().__init__(parent)

        # Adjustments service (singleton)
        from src.services.asset_adjustments import AssetAdjustmentsService
        if not hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance = AssetAdjustmentsService()
        self._adj_service = AssetAdjustmentsService._instance

        self.library = AssetLibrary(self)
        self.cache = AssetCache()

    # --- Retrieve ---

    def get_pixmap(self, asset_id: str) -> QPixmap | None:
        """Load asset pixmap from the library, applying brightness/contrast
        adjustments via the service if available."""
        cached = self.cache.get(asset_id)
        if cached:
            return self._apply_adjustment(cached, asset_id)
        pix = self.library.get_pixmap(asset_id)
        return self._apply_adjustment(pix, asset_id) if pix else None

    def _apply_adjustment(self, pixmap: QPixmap, asset_id: str) -> QPixmap:
        """Apply brightness/contrast via service if available."""
        if not self._adj_service:
            return pixmap
        path = self.library.get_path_by_id(asset_id) or ""
        return self._adj_service.get_adjusted_pixmap(path, pixmap)

    def get_pixmap_by_name(self, name: str) -> QPixmap | None:
        """Load pixmap by asset name — searches library."""
        return self.library.get_pixmap_by_name(name)

    def get_id_by_name(self, name: str) -> str | None:
        """Get asset ID by name — searches library."""
        return self.library.get_id_by_name(name)
