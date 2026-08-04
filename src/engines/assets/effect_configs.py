"""Effect Configs — persisted image + brilho/contraste per animated brush
effect key (see engines.map.brush_effects.ANIMATED_EFFECTS — Névoa, Poeira,
...). These aren't real library assets (no file the user drops in, no
per-style variants — the same fixed 21 keys exist regardless of which
style/project is active), so they get their own tiny table instead of
living in the `assets` table. Brush/ambient SOUND for an effect reuses the
existing `asset_sounds` table unchanged (see SoundColumn in
layouts/panels/assets/widgets.py), keyed by `f"{EFFECT_ASSET_PREFIX}{key}"`
— same asset_id shape BrushTool already uses to recognize an effect stamp
(see canvas/tools/brush_tool.py), so no new sound storage was needed here.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src.engines.assets.library import get_shared_db, LIBRARY_DIR

_THUMBS_DIR = LIBRARY_DIR / "effects_thumbs"
_SCHEMA_READY = False


def _ensure_schema():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    db = get_shared_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS effect_configs (
            key TEXT PRIMARY KEY,
            image_path TEXT DEFAULT '',
            brightness INTEGER DEFAULT 0,
            contrast INTEGER DEFAULT 0
        )
    """)
    db.commit()
    _SCHEMA_READY = True


def get_effect_config(key: str) -> dict:
    """{"image_path": str, "brightness": int, "contrast": int} — defaults
    (no image, 0/0) when this effect has never been configured."""
    _ensure_schema()
    db = get_shared_db()
    row = db.execute(
        "SELECT image_path, brightness, contrast FROM effect_configs WHERE key=?", (key,)
    ).fetchone()
    if row:
        return {"image_path": row["image_path"] or "", "brightness": row["brightness"] or 0,
                "contrast": row["contrast"] or 0}
    return {"image_path": "", "brightness": 0, "contrast": 0}


def set_effect_image(key: str, source_path: str) -> str:
    """Copies `source_path` into library/effects_thumbs/<key>.<ext> (a
    stable, library-owned location — same reasoning as ThumbnailGenerator's
    own cache dir, not the arbitrary path the user picked it from, which
    could move/vanish) and persists it as this effect's image. Returns the
    stored absolute path."""
    _ensure_schema()
    _THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(source_path).suffix.lower() or ".png"
    dest = _THUMBS_DIR / f"{key}{ext}"
    # Clear any previous image for this key under a different extension —
    # same "one file per stem" rule import_asset (project_assets.py) uses.
    for old in _THUMBS_DIR.glob(f"{key}.*"):
        if old != dest:
            old.unlink(missing_ok=True)
    if Path(source_path).resolve() != dest.resolve():
        shutil.copyfile(source_path, dest)
    stored = str(dest)
    db = get_shared_db()
    db.execute("""
        INSERT INTO effect_configs (key, image_path) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET image_path=excluded.image_path
    """, (key, stored))
    db.commit()
    return stored


def set_effect_adjustments(key: str, brightness: int, contrast: int):
    _ensure_schema()
    db = get_shared_db()
    db.execute("""
        INSERT INTO effect_configs (key, brightness, contrast) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET brightness=excluded.brightness, contrast=excluded.contrast
    """, (key, brightness, contrast))
    db.commit()
