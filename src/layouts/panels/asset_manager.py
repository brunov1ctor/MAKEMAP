"""Backward-compatible re-exports from assets package."""

from src.layouts.panels.assets.panel import AssetSoundManager
from src.layouts.panels.assets.card import AssetRowCard, CategorySection
from src.layouts.panels.assets.widgets import MiniSlider, SoundColumn, DropZone
from src.layouts.panels.assets.audio_processing import process_sound_file

# Legacy aliases
_MiniSlider = MiniSlider
_SoundColumn = SoundColumn
_process_sound_file = process_sound_file

__all__ = ["AssetSoundManager", "AssetRowCard", "CategorySection", "DropZone"]
