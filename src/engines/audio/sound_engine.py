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
FADE_MS = 5000
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
    """Sounds triggered by brush actions + viewport-based ambient.

    - Painting sound: loops while actively painting (e.g. earth/dirt sound)
    - Ambient sound: plays based on visible terrain in viewport with crossfade

    Structure:
        sounds/brush/<asset_key>/
            paint_*.mp3    ← plays while painting
            ambient_*.mp3  ← plays when terrain is visible in viewport
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paint_sounds: dict[str, list[Path]] = {}
        self._ambient_sounds: dict[str, list[Path]] = {}
        self._active_paint: tuple[QMediaPlayer, QAudioOutput] | None = None
        self._current_key: str | None = None
        self._master = 0.7
        self._paint_vol_mult = 0.7

        # Viewport-based ambient: key -> (player, output, current_volume, target_volume)
        self._ambient_players: dict[str, tuple[QMediaPlayer, QAudioOutput]] = {}
        self._ambient_volumes: dict[str, float] = {}   # current volume per key
        self._ambient_targets: dict[str, float] = {}   # target volume per key
        self._ambient_files: dict[str, Path] = {}      # file per key for crossfade
        self._ambient_crossfading: dict[str, bool] = {}  # crossfade state per key

        # Fade timer for all ambient crossfades
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(FADE_STEP_MS)
        self._fade_timer.timeout.connect(self._fade_step)

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

    # ─── Paint Sound ─────────────────────────────────────────────────────

    def on_stroke_start(self, asset_key: str, master: float, paint_volume: float = 0.7):
        """Called when brush stroke begins."""
        self._master = master
        self._current_key = asset_key
        self._paint_vol_mult = paint_volume

        # Resolve which sound files to use for this asset
        paint_files = self._get_paint_files(asset_key)

        if paint_files:
            if self._active_paint:
                # Already playing (finishing previous stroke) — resume looping
                try:
                    self._active_paint[0].mediaStatusChanged.disconnect(self._on_paint_finished)
                except (RuntimeError, TypeError):
                    pass
                # Restart crossfade loop
                self._paint_looping = True
            else:
                f = random.choice(paint_files)
                self._paint_file = f
                output = QAudioOutput(self)
                output.setVolume(master * self._paint_vol_mult)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                player.setSource(_make_url(f))
                player.setLoops(1)
                player.positionChanged.connect(self._on_paint_position)
                player.mediaStatusChanged.connect(self._on_paint_loop_end)
                player.play()
                self._active_paint = (player, output)
                self._paint_looping = True
                self._paint_crossfading = False
                self._paint_next: tuple[QMediaPlayer, QAudioOutput] | None = None

    def _on_paint_position(self, position: int):
        """Start crossfade near end of current paint loop."""
        if not self._active_paint or not self._paint_looping or self._paint_crossfading:
            return
        player = self._active_paint[0]
        duration = player.duration()
        if duration <= 0:
            return
        # Start crossfade 1.5s before end
        crossfade_start = duration - 1500
        if position >= crossfade_start:
            self._start_paint_crossfade()

    def _start_paint_crossfade(self):
        """Spawn next player and fade between them."""
        if not self._paint_looping or not hasattr(self, '_paint_file'):
            return
        self._paint_crossfading = True
        vol = self._master * self._paint_vol_mult

        # Create next player starting at volume 0
        output = QAudioOutput(self)
        output.setVolume(0.0)
        player = QMediaPlayer(self)
        player.setAudioOutput(output)
        player.setSource(_make_url(self._paint_file))
        player.setLoops(1)
        player.play()
        self._paint_next = (player, output)

        # Fade: old out, new in over 1.5s
        self._paint_fade_steps = 30  # 30 steps * 50ms = 1.5s
        self._paint_fade_step = 0
        self._paint_fade_timer = QTimer(self)
        self._paint_fade_timer.setInterval(50)
        self._paint_fade_timer.timeout.connect(self._paint_fade_tick)
        self._paint_fade_timer.start()

    def _paint_fade_tick(self):
        """Crossfade tick between old and new paint player."""
        self._paint_fade_step += 1
        progress = self._paint_fade_step / self._paint_fade_steps
        vol = self._master * self._paint_vol_mult

        if self._active_paint:
            self._active_paint[1].setVolume(vol * (1.0 - progress))
        if self._paint_next:
            self._paint_next[1].setVolume(vol * progress)

        if self._paint_fade_step >= self._paint_fade_steps:
            self._paint_fade_timer.stop()
            if self._active_paint:
                self._active_paint[0].stop()
                try:
                    self._active_paint[0].positionChanged.disconnect(self._on_paint_position)
                except (RuntimeError, TypeError):
                    pass
            if self._paint_next:
                self._active_paint = self._paint_next
                self._active_paint[0].positionChanged.connect(self._on_paint_position)
                self._active_paint[0].mediaStatusChanged.connect(self._on_paint_loop_end)
            else:
                self._active_paint = None
            self._paint_next = None
            self._paint_crossfading = False

    def _on_paint_loop_end(self, status):
        """Handle end of a paint loop iteration."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._paint_looping and not self._paint_crossfading:
                # Crossfade didn't trigger (very short file), restart directly
                if self._active_paint:
                    self._active_paint[0].setPosition(0)
                    self._active_paint[0].play()

    def _get_paint_files(self, asset_key: str) -> list[Path]:
        return self._paint_sounds.get(asset_key, [])

    def _get_ambient_files(self, asset_key: str) -> list[Path]:
        return self._ambient_sounds.get(asset_key, [])

    def on_stroke_end(self):
        """Called when brush stroke ends. Let paint sound finish naturally."""
        self._paint_looping = False
        # Let current playback finish without spawning next crossfade
        if self._active_paint:
            self._active_paint[0].mediaStatusChanged.connect(self._on_paint_finished)

    def _on_paint_finished(self, status):
        """Clean up paint player after it finishes."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._paint_looping:
            if self._active_paint:
                try:
                    self._active_paint[0].positionChanged.disconnect(self._on_paint_position)
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._active_paint[0].mediaStatusChanged.disconnect(self._on_paint_finished)
                except (RuntimeError, TypeError):
                    pass
                self._active_paint[0].stop()
                self._active_paint = None

    # ─── Viewport Ambient Sound ──────────────────────────────────────────

    def update_visible_terrains(self, terrain_keys: dict[str, float], master: float):
        """Update ambient sounds based on visible terrains in viewport.

        Args:
            terrain_keys: dict of {terrain_key: coverage_ratio} where coverage
                          is 0.0-1.0 representing how much of the viewport
                          this terrain occupies.
            master: master volume (zoom-adjusted).
        """
        self._master = master

        # Set targets for visible terrains
        for key, coverage in terrain_keys.items():
            ambient_files = self._get_ambient_files(key)
            if not ambient_files:
                continue
            target = master * coverage
            self._ambient_targets[key] = target

            # Start player if not already active
            if key not in self._ambient_players:
                f = random.choice(ambient_files)
                output = QAudioOutput(self)
                output.setVolume(0.0)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                player.setSource(_make_url(f))
                player.setLoops(1)
                player.play()
                self._ambient_players[key] = (player, output)
                self._ambient_volumes[key] = 0.0
                self._ambient_files[key] = f
                self._ambient_crossfading[key] = False
                # Monitor position for crossfade
                player.positionChanged.connect(
                    lambda pos, k=key: self._on_ambient_position(k, pos)
                )
                player.mediaStatusChanged.connect(
                    lambda status, k=key: self._on_ambient_loop_end(k, status)
                )

        # Fade out terrains no longer visible
        for key in list(self._ambient_targets.keys()):
            if key not in terrain_keys:
                self._ambient_targets[key] = 0.0

        # Start fade timer if not running
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _on_ambient_position(self, key: str, position: int):
        """Start crossfade near end of ambient loop."""
        if key not in self._ambient_players or self._ambient_crossfading.get(key):
            return
        player = self._ambient_players[key][0]
        duration = player.duration()
        if duration <= 0:
            return
        if position >= duration - 2000:
            self._start_ambient_crossfade(key)

    def _start_ambient_crossfade(self, key: str):
        """Crossfade ambient loop: spawn next player and blend."""
        if key not in self._ambient_files:
            return
        self._ambient_crossfading[key] = True
        f = self._ambient_files[key]
        target_vol = self._ambient_volumes.get(key, 0.0)

        # New player
        output = QAudioOutput(self)
        output.setVolume(0.0)
        player = QMediaPlayer(self)
        player.setAudioOutput(output)
        player.setSource(_make_url(f))
        player.setLoops(1)
        player.play()

        old_player, old_output = self._ambient_players[key]

        # Crossfade over 2s (40 steps * 50ms)
        steps = 40
        step_count = [0]

        timer = QTimer(self)
        timer.setInterval(50)

        def tick():
            step_count[0] += 1
            progress = step_count[0] / steps
            old_output.setVolume(target_vol * (1.0 - progress))
            output.setVolume(target_vol * progress)
            if step_count[0] >= steps:
                timer.stop()
                old_player.stop()
                # Swap
                self._ambient_players[key] = (player, output)
                self._ambient_crossfading[key] = False
                player.positionChanged.connect(
                    lambda pos, k=key: self._on_ambient_position(k, pos)
                )
                player.mediaStatusChanged.connect(
                    lambda status, k=key: self._on_ambient_loop_end(k, status)
                )

        timer.timeout.connect(tick)
        timer.start()

    def _on_ambient_loop_end(self, key: str, status):
        """Handle end of ambient loop if crossfade didn't trigger."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if not self._ambient_crossfading.get(key) and key in self._ambient_players:
                # Very short file or crossfade missed, restart
                self._ambient_players[key][0].setPosition(0)
                self._ambient_players[key][0].play()

    def set_volume(self, vol: float):
        """Update all ambient volumes based on zoom/master changes."""
        old_master = self._master
        self._master = vol
        for key in list(self._ambient_targets.keys()):
            if self._ambient_targets[key] > 0 and old_master > 0.01:
                # Scale target proportionally to new master
                ratio = self._ambient_targets[key] / old_master
                self._ambient_targets[key] = vol * ratio
            elif self._ambient_targets[key] > 0:
                self._ambient_targets[key] = vol
        if not self._fade_timer.isActive() and self._ambient_players:
            self._fade_timer.start()

    def _fade_step(self):
        """Smooth crossfade all ambient channels toward their targets."""
        all_done = True
        to_remove = []

        for key in list(self._ambient_targets.keys()):
            current = self._ambient_volumes.get(key, 0.0)
            target = self._ambient_targets[key]
            step = max(0.005, abs(target - current) * (FADE_STEP_MS / FADE_MS) + 0.005)

            if current < target:
                current = min(current + step, target)
            elif current > target:
                current = max(current - step, target)

            self._ambient_volumes[key] = current

            if key in self._ambient_players:
                self._ambient_players[key][1].setVolume(current)

            if abs(current - target) > 0.005:
                all_done = False
            elif target == 0.0 and current <= 0.005:
                # Fully faded out — stop and remove
                to_remove.append(key)

        for key in to_remove:
            if key in self._ambient_players:
                self._ambient_players[key][0].stop()
                del self._ambient_players[key]
            self._ambient_volumes.pop(key, None)
            self._ambient_targets.pop(key, None)

        if all_done:
            self._fade_timer.stop()

    def stop(self):
        self._fade_timer.stop()
        self._paint_looping = False
        if hasattr(self, '_paint_fade_timer') and self._paint_fade_timer:
            self._paint_fade_timer.stop()
        if self._active_paint:
            self._active_paint[0].stop()
            self._active_paint = None
        if hasattr(self, '_paint_next') and self._paint_next:
            self._paint_next[0].stop()
            self._paint_next = None
        for player, output in self._ambient_players.values():
            player.stop()
        self._ambient_players.clear()
        self._ambient_volumes.clear()
        self._ambient_targets.clear()
        self._ambient_files.clear()
        self._ambient_crossfading.clear()


# ─── Main Engine ─────────────────────────────────────────────────────────────

class SoundEngine(QObject):
    """Orchestrates all 5 sound layers."""

    volume_changed = Signal(str, float)

    def __init__(self, parent=None, asset_settings=None):
        super().__init__(parent)
        self._asset_settings = asset_settings
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
        self.brush.set_volume(vol)
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
        paint_volume = 0.7
        if self._asset_settings:
            settings = self._asset_settings.get(asset_key)
            paint_volume = settings.get("sound_volume_paint", 0.7)
        self.brush.on_stroke_start(asset_key, vol, paint_volume)

    def on_brush_stroke_end(self):
        """Call when user stops painting."""
        self.brush.on_stroke_end()

    def on_visible_terrains_changed(self, terrain_keys: dict[str, float]):
        """Call with {terrain_key: coverage_ratio} for visible terrains."""
        vol = self._zoom_factor() * self._master_volume
        self.brush.update_visible_terrains(terrain_keys, vol)

    def _periodic_update(self):
        """Periodic volume sync."""
        self._update_zoom_volumes()

    def notify_asset_placed(self, asset_name: str):
        """Convenience: trigger sound context refresh on asset placement."""
        pass  # Handled by viewport scan in CanvasEngine
