"""Asset Settings repository — per-project brightness, contrast, sound volumes."""

from __future__ import annotations

from src.database.connection import Database


DEFAULT_SETTINGS = {
    "brightness": 0.0,
    "contrast": 0.0,
    "sound_volume_paint": 0.7,
    "sound_volume_ambient": 0.7,
}


class AssetSettingsRepository:
    """CRUD for asset_settings table (per-project overrides)."""

    TABLE = "asset_settings"

    def __init__(self, db: Database):
        self.db = db

    def get(self, asset_id: str) -> dict:
        """Get settings for an asset. Returns defaults if not set."""
        row = self.db.fetchone(
            f"SELECT * FROM {self.TABLE} WHERE asset_id = ?", (asset_id,)
        )
        if row:
            return dict(row)
        return {"asset_id": asset_id, **DEFAULT_SETTINGS}

    def set(self, asset_id: str, **fields):
        """Upsert settings for an asset."""
        existing = self.db.fetchone(
            f"SELECT asset_id FROM {self.TABLE} WHERE asset_id = ?", (asset_id,)
        )
        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            params = tuple(fields.values()) + (asset_id,)
            with self.db.transaction():
                self.db.execute(f"UPDATE {self.TABLE} SET {sets} WHERE asset_id = ?", params)
        else:
            all_fields = {**DEFAULT_SETTINGS, **fields, "asset_id": asset_id}
            cols = ", ".join(all_fields.keys())
            placeholders = ", ".join("?" for _ in all_fields)
            with self.db.transaction():
                self.db.execute(
                    f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})",
                    tuple(all_fields.values()),
                )

    def get_all(self) -> list[dict]:
        """Get all asset settings in this project."""
        return [dict(r) for r in self.db.fetchall(f"SELECT * FROM {self.TABLE}")]

    def delete(self, asset_id: str):
        """Remove settings (revert to defaults)."""
        with self.db.transaction():
            self.db.execute(f"DELETE FROM {self.TABLE} WHERE asset_id = ?", (asset_id,))
