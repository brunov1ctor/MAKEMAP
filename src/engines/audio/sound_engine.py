"""SoundEngine — 4-layer ambient audio system.

Layers:
1. Biomes   — continuous loops tied to terrain type (desert wind, forest birds, etc.)
2. Objects  — loops tied to specific assets in viewport (torch fire, mill creaking)
3. Occasional — random one-shots triggered by asset presence (crow caw, wolf howl)
4. Music    — region-based tracks with crossfade on camera enter/exit
"""

from __future__ import annotations

import random
import logging
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

logger = logging.getLogger("MAKEMAP")


SOUNDS_DIR = Path(__file__).resolve().parents[3] / "library" / "sounds"
FADE_MS = 3000
FADE_STEP_MS = 50


def _scan_audio_files(folder: Path) -> list[Path]:
    """Return all audio files in a folder."""
    if not folder.exists():
        return []
    return [f for f in folder.iterdir() if f.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac")]


def _make_url(path: Path) -> QUrl:
    return QUrl.fromLocalFile(str(path))


# ─── Layer 1: Biome Sounds ───────────────────────────────────────────────────

class BiomeLayer(QObject):
    """Continuous looping sounds per biome. Multiple files = layered."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._players: dict[str, list[tuple[QMediaPlayer, QAudioOutput]]] = {}
        self._active_biome: str | None = None
        self._volume = 0.0
        self._target_volume = 0.0
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)
        self._load_all()

    def _load_all(self):
        biomes_dir = SOUNDS_DIR / "biomes"
        if not biomes_dir.exists():
            return
        for biome_dir in biomes_dir.iterdir():
            if not biome_dir.is_dir():
                continue
            files = _scan_audio_files(biome_dir)
            if files:
                players = []
                for f in files:
                    output = QAudioOutput(self)
                    output.setVolume(0.0)
                    player = QMediaPlayer(self)
                    player.setAudioOutput(output)
                    player.setSource(_make_url(f))
                    player.setLoops(QMediaPlayer.Loops.Infinite)
                    players.append((player, output))
                self._players[biome_dir.name] = players

    def set_biome(self, biome: str | None, master: float):
        if biome == self._active_biome:
            return
        # Fade out current
        if self._active_biome and self._active_biome in self._players:
            for player, _ in self._players[self._active_biome]:
                player.stop()
        self._active_biome = biome
        self._volume = 0.0
        self._target_volume = master
        if biome and biome in self._players:
            for player, output in self._players[biome]:
                output.setVolume(0.0)
                player.play()
            self._fade_timer.start()

    def set_volume(self, vol: float):
        self._target_volume = vol
        if self._active_biome and not self._fade_timer.isActive():
            self._fade_timer.start()

    def _fade_step(self):
        step = self._target_volume * (FADE_STEP_MS / FADE_MS)
        if self._volume < self._target_volume:
            self._volume = min(self._volume + step, self._target_volume)
        elif self._volume > self._target_volume:
            self._volume = max(self._volume - step, self._target_volume)

        if self._active_biome and self._active_biome in self._players:
            for _, output in self._players[self._active_biome]:
                output.setVolume(self._volume)

        if abs(self._volume - self._target_volume) < 0.01:
            self._volume = self._target_volume
            self._fade_timer.stop()

    def stop(self):
        self._fade_timer.stop()
        for players in self._players.values():
            for player, output in players:
                player.stop()
                output.setVolume(0.0)
        self._active_biome = None
        self._volume = 0.0


# ─── Layer 2: Object Sounds ──────────────────────────────────────────────────

class ObjectLayer(QObject):
    """Looping sounds tied to specific asset types visible in viewport."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sounds: dict[str, list[Path]] = {}
        self._active: dict[str, tuple[QMediaPlayer, QAudioOutput]] = {}
        self._load_all()

    def _load_all(self):
        objects_dir = SOUNDS_DIR / "objects"
        if not objects_dir.exists():
            return
        for obj_dir in objects_dir.iterdir():
            if obj_dir.is_dir():
                files = _scan_audio_files(obj_dir)
                if files:
                    self._sounds[obj_dir.name] = files

    def update_visible(self, object_keys: set[str], master: float):
        """Activate/deactivate object sounds based on visible assets."""
        # Start new
        for key in object_keys:
            if key in self._sounds and key not in self._active:
                f = random.choice(self._sounds[key])
                output = QAudioOutput(self)
                output.setVolume(master)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                player.setSource(_make_url(f))
                player.setLoops(QMediaPlayer.Loops.Infinite)
                player.play()
                self._active[key] = (player, output)
            elif key in self._active:
                self._active[key][1].setVolume(master)

        # Stop removed
        to_remove = [k for k in self._active if k not in object_keys]
        for k in to_remove:
            player, output = self._active.pop(k)
            player.stop()

    def stop(self):
        for player, output in self._active.values():
            player.stop()
        self._active.clear()


# ─── Layer 3: Occasional Sounds ──────────────────────────────────────────────

class OccasionalLayer(QObject):
    """Random one-shot sounds triggered at random intervals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sounds: dict[str, list[Path]] = {}
        self._active_keys: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._trigger)
        self._timer.setInterval(self._random_interval())
        self._master = 0.5
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self._load_all()

    def _load_all(self):
        occ_dir = SOUNDS_DIR / "occasional"
        if not occ_dir.exists():
            return
        for sub in occ_dir.iterdir():
            if sub.is_dir():
                files = _scan_audio_files(sub)
                if files:
                    self._sounds[sub.name] = files

    def _random_interval(self) -> int:
        return random.randint(5000, 20000)

    def update_active(self, keys: set[str], master: float):
        self._active_keys = keys & set(self._sounds.keys())
        self._master = master
        if self._active_keys and not self._timer.isActive():
            self._timer.start()
        elif not self._active_keys:
            self._timer.stop()

    def _trigger(self):
        if not self._active_keys:
            return
        key = random.choice(list(self._active_keys))
        f = random.choice(self._sounds[key])

        # Play one-shot
        self._output = QAudioOutput(self)
        self._output.setVolume(self._master)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._player.setSource(_make_url(f))
        self._player.play()

        # Schedule next
        self._timer.setInterval(self._random_interval())

    def stop(self):
        self._timer.stop()
        if self._player:
            self._player.stop()
        self._active_keys.clear()


# ─── Layer 4: Music ──────────────────────────────────────────────────────────

class MusicLayer(QObject):
    """Region-based music with crossfade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: dict[str, Path] = {}
        self._current_region: str | None = None
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._output.setVolume(0.0)
        self._target_volume = 0.0
        self._volume = 0.0
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)
        self._load_all()

    def _load_all(self):
        music_dir = SOUNDS_DIR / "music"
        if not music_dir.exists():
            return
        for f in _scan_audio_files(music_dir):
            # filename without extension = region key
            self._tracks[f.stem] = f

    def set_region(self, region: str | None, master: float):
        """Switch music track with fade."""
        if region == self._current_region:
            return

        self._current_region = region
        if region and region in self._tracks:
            self._target_volume = master
            self._volume = 0.0
            self._output.setVolume(0.0)
            self._player.setSource(_make_url(self._tracks[region]))
            self._player.play()
            self._fade_timer.start()
        else:
            # Fade out
            self._target_volume = 0.0
            self._fade_timer.start()

    def set_volume(self, vol: float):
        self._target_volume = vol
        if not self._fade_timer.isActive():
            self._output.setVolume(vol)

    def _fade_step(self):
        step = FADE_STEP_MS / FADE_MS
        if self._volume < self._target_volume:
            self._volume = min(self._volume + step, self._target_volume)
        elif self._volume > self._target_volume:
            self._volume = max(self._volume - step, self._target_volume)

        self._output.setVolume(self._volume)

        if abs(self._volume - self._target_volume) < 0.01:
            self._volume = self._target_volume
            self._fade_timer.stop()
            if self._volume == 0.0 and not self._current_region:
                self._player.stop()

    def stop(self):
        self._fade_timer.stop()
        self._player.stop()
        self._output.setVolume(0.0)
        self._current_region = None


# ─── Layer 5: Brush Sounds ───────────────────────────────────────────────────

class BrushSoundLayer(QObject):
    """Sounds triggered by brush actions.

    - Painting sound: loops while actively painting (e.g. earth/dirt sound)
    - Ambient sound: fades in after painting stops (e.g. empty land breeze)

    Structure:
        sounds/brush/<asset_key>/
            paint_*.ogg    ← plays while painting
            ambient_*.ogg  ← plays after painting stops (idle terrain sound)
    """

    IDLE_DELAY_MS = 3000  # time after stroke ends before ambient kicks in

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paint_sounds: dict[str, list[Path]] = {}
        self._ambient_sounds: dict[str, list[Path]] = {}
        self._active_paint: tuple[QMediaPlayer, QAudioOutput] | None = None
        self._active_ambient: tuple[QMediaPlayer, QAudioOutput] | None = None
        self._current_key: str | None = None
        self._master = 0.7
        self._paint_vol_mult = 0.7
        self._ambient_vol_mult = 0.7

        # Timer to start ambient after idle
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._start_ambient)

        # Fade for ambient
        self._ambient_volume = 0.0
        self._ambient_target = 0.0
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_ambient_step)

        self._load_all()

    def _load_all(self):
        brush_dir = SOUNDS_DIR / "brush"
        if not brush_dir.exists():
            return
        for sub in brush_dir.iterdir():
            if not sub.is_dir():
                continue
            key = sub.name
            for f in _scan_audio_files(sub):
                name = f.stem.lower()
                if name.startswith("paint"):
                    self._paint_sounds.setdefault(key, []).append(f)
                elif name.startswith("ambient"):
                    self._ambient_sounds.setdefault(key, []).append(f)

    def on_stroke_start(self, asset_key: str, master: float):
        """Called when brush stroke begins."""
        self._master = master
        self._current_key = asset_key

        # Load per-asset volume from library DB
        paint_vol_mult, ambient_vol_mult = self._load_asset_volumes(asset_key)
        self._paint_vol_mult = paint_vol_mult
        self._ambient_vol_mult = ambient_vol_mult

        logger.info("BrushSound: stroke start key='%s', available paint=%s, ambient=%s",
                    asset_key, list(self._paint_sounds.keys()), list(self._ambient_sounds.keys()))

        # Stop ambient fade-in
        self._idle_timer.stop()
        self._stop_ambient()

        # Start paint sound
        if asset_key in self._paint_sounds and not self._active_paint:
            f = random.choice(self._paint_sounds[asset_key])
            logger.info("BrushSound: playing paint sound %s", f.name)
            output = QAudioOutput(self)
            output.setVolume(master * self._paint_vol_mult)
            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.setSource(_make_url(f))
            player.setLoops(QMediaPlayer.Loops.Infinite)
            player.play()
            self._active_paint = (player, output)
        elif asset_key not in self._paint_sounds:
            logger.warning("BrushSound: no paint sound for key='%s'", asset_key)

    def _load_asset_volumes(self, asset_key: str) -> tuple[float, float]:
        """Load per-asset sound volumes from project DB."""
        try:
            from PySide6.QtWidgets import QApplication
            window = QApplication.instance().activeWindow()
            if window and hasattr(window, 'uow') and window.uow:
                # Get first asset in this category to read its settings
                import sqlite3
                from src.engines.assets.library import LIBRARY_DB
                db = sqlite3.connect(str(LIBRARY_DB))
                db.row_factory = sqlite3.Row
                row = db.execute(
                    "SELECT id FROM assets WHERE category = ? LIMIT 1", (asset_key,)
                ).fetchone()
                db.close()
                if row:
                    settings = window.uow.asset_settings.get(row["id"])
                    vp = settings.get("sound_volume_paint", 0.7)
                    va = settings.get("sound_volume_ambient", 0.7)
                    return vp, va
        except Exception:
            pass
        return 0.7, 0.7

    def on_stroke_end(self):
        """Called when brush stroke ends."""
        # Stop paint sound
        if self._active_paint:
            self._active_paint[0].stop()
            self._active_paint = None

        # Schedule ambient start
        if self._current_key and self._current_key in self._ambient_sounds:
            self._idle_timer.start(self.IDLE_DELAY_MS)

    def _start_ambient(self):
        """Start ambient terrain sound with fade-in."""
        if not self._current_key or self._current_key not in self._ambient_sounds:
            return

        f = random.choice(self._ambient_sounds[self._current_key])
        output = QAudioOutput(self)
        output.setVolume(0.0)
        player = QMediaPlayer(self)
        player.setAudioOutput(output)
        player.setSource(_make_url(f))
        player.setLoops(QMediaPlayer.Loops.Infinite)
        player.play()
        self._active_ambient = (player, output)
        self._ambient_volume = 0.0
        self._ambient_target = self._master * 0.6 * self._ambient_vol_mult
        self._fade_timer.start()

    def _fade_ambient_step(self):
        step = self._ambient_target * (FADE_STEP_MS / FADE_MS)
        if self._ambient_volume < self._ambient_target:
            self._ambient_volume = min(self._ambient_volume + step, self._ambient_target)
        if self._active_ambient:
            self._active_ambient[1].setVolume(self._ambient_volume)
        if self._ambient_volume >= self._ambient_target:
            self._fade_timer.stop()

    def _stop_ambient(self):
        self._fade_timer.stop()
        if self._active_ambient:
            self._active_ambient[0].stop()
            self._active_ambient = None
        self._ambient_volume = 0.0

    def stop(self):
        self._idle_timer.stop()
        self._fade_timer.stop()
        if self._active_paint:
            self._active_paint[0].stop()
            self._active_paint = None
        self._stop_ambient()


# ─── Main Engine ─────────────────────────────────────────────────────────────

class SoundEngine(QObject):
    """Orchestrates all 5 sound layers."""

    volume_changed = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = True
        self._master_volume = 0.7
        self._zoom = 1.0

        self.biome = BiomeLayer(self)
        self.objects = ObjectLayer(self)
        self.occasional = OccasionalLayer(self)
        self.music = MusicLayer(self)
        self.brush = BrushSoundLayer(self)

        # Periodic context update
        self._context_timer = QTimer(self)
        self._context_timer.setInterval(1000)
        self._context_timer.timeout.connect(self._periodic_update)

    def start(self):
        if self._enabled:
            self._context_timer.start()

    def stop(self):
        self._context_timer.stop()
        self.biome.stop()
        self.objects.stop()
        self.occasional.stop()
        self.music.stop()
        self.brush.stop()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self.stop()

    def set_master_volume(self, vol: float):
        self._master_volume = max(0.0, min(1.0, vol))

    def on_zoom_changed(self, zoom_percent: int):
        self._zoom = zoom_percent / 100.0
        self._update_zoom_volumes()

    def _zoom_factor(self) -> float:
        """Closer = louder. Range 0..1."""
        return min(1.0, max(0.0, (self._zoom - 0.3) / 1.7))

    def _update_zoom_volumes(self):
        factor = self._zoom_factor()
        vol = factor * self._master_volume
        self.biome.set_volume(vol)
        self.music.set_volume(self._master_volume * 0.5)

    def on_biome_changed(self, biome: str | None):
        """Call when camera enters a new biome region."""
        self.biome.set_biome(biome, self._zoom_factor() * self._master_volume)

    def on_visible_objects_changed(self, object_keys: set[str]):
        """Call with set of object type keys visible in viewport."""
        vol = self._zoom_factor() * self._master_volume
        self.objects.update_visible(object_keys, vol)
        self.occasional.update_active(object_keys, vol * 0.6)

    def on_region_entered(self, region: str | None):
        """Call when camera enters a named region (for music)."""
        self.music.set_region(region, self._master_volume * 0.5)

    def on_brush_stroke_start(self, asset_key: str):
        """Call when user starts painting with brush."""
        vol = self._zoom_factor() * self._master_volume
        self.brush.on_stroke_start(asset_key, vol)

    def on_brush_stroke_end(self):
        """Call when user stops painting."""
        self.brush.on_stroke_end()

    def _periodic_update(self):
        """Periodic volume sync."""
        self._update_zoom_volumes()

    def notify_asset_placed(self, asset_name: str):
        """Convenience: trigger sound context refresh on asset placement."""
        pass  # Handled by viewport scan in CanvasEngine
