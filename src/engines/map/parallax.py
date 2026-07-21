"""Parallax background presets — free-form named sets of image layers, each
with its own speed/opacity/stacking-order, rendered by Viewport.drawBackground.

Presets persist across restarts (unlike terrains/zones, which don't persist
at all today) via a small JSON file, since there's no natural "it's just a
folder" identity for a preset the way asset styles have. Mirrors
engines/assets/library.py's get_shared_db() — one process-wide instance.
"""

from __future__ import annotations

import json
import random
import math
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIBRARY_DIR = _SOURCE_ROOT / "library"
PARALLAX_DIR = LIBRARY_DIR / "parallax"
PARALLAX_JSON = PARALLAX_DIR / "parallax.json"

_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@dataclass
class LayerEffect:
    """One lightweight, CPU-side "shader" applied to a layer's pixmap —
    tint/blur/chromatic are pre-baked once (static), wave is re-applied every
    frame in Viewport since it animates. See EFFECT_KINDS/EFFECT_DEFAULTS
    below for what params each kind expects."""
    kind: str                              # "tint" | "blur" | "chromatic" | "wave"
    enabled: bool = True
    params: dict = field(default_factory=dict)


# (kind, label) — order they appear in the "+ Efeito" picker. A generic,
# theme-agnostic catalog: a "desert" or "nebula" look is just different
# params on these same kinds, not a new kind per theme.
EFFECT_KINDS = [
    ("tint", "Tingir cor"),
    ("blur", "Desfoque"),
    ("chromatic", "Aberração cromática"),
    ("wave", "Onda / Distorção"),
]

EFFECT_DEFAULTS: dict[str, dict] = {
    "tint": {"color": "#4FC3F7", "strength": 0.3},
    "blur": {"radius": 4.0},
    "chromatic": {"offset_px": 2.0},
    "wave": {"amplitude": 6.0, "frequency": 0.05, "speed": 1.0},
}


@dataclass
class ParallaxLayer:
    image_path: str        # absolute path, resolved at load time
    name: str = ""         # user-editable label, independent of the filename
    speed_x: float = 0.5   # 0.0 = fixed to screen (skybox); negative = drifts opposite the pan
    speed_y: float = 0.0
    opacity: float = 1.0   # 0..1
    order: int = 0         # lower = drawn first (further back)

    # How side-by-side tile copies meet at the seam — only matters for
    # motion_mode="scroll" (an "orbit" layer isn't tiled at all).
    tile_mode: str = "repeat"        # "repeat" | "mirror" | "fade"

    # Motion mode
    motion_mode: str = "scroll"      # "scroll" (tiled, tied to pan) | "orbit" (short independent drift)
    orbit_radius: float = 20.0       # screen px
    orbit_period: float = 8.0        # seconds per full loop

    # Ambient time-driven pulsing — independent of pan, off by default so
    # existing layers keep behaving exactly as before.
    opacity_pulse: bool = False
    opacity_min: float = 0.6
    opacity_max: float = 1.0
    opacity_period: float = 4.0      # seconds per cycle

    scale_pulse: bool = False
    scale_min: float = 100.0         # %
    scale_max: float = 110.0
    scale_period: float = 6.0

    rotation_pulse: bool = False
    rotation_amplitude: float = 2.0  # degrees, oscillates -amp..+amp
    rotation_period: float = 10.0

    # Radians — randomized on creation (see add_layer) so multiple pulsing
    # layers don't all breathe in lockstep.
    phase_offset: float = 0.0

    # Lightweight CPU "shaders" — see LayerEffect above.
    effects: list[LayerEffect] = field(default_factory=list)


@dataclass
class ParallaxPreset:
    key: str
    name: str
    layers: list[ParallaxLayer] = field(default_factory=list)


class ParallaxLibrary(QObject):
    """Loads/saves parallax presets to library/parallax/parallax.json and
    manages copying imported layer images into library/parallax/<key>/."""

    # Emitted after every save() — whoever is showing a preset live (the
    # Viewport, via TerrainMediator) listens for this to re-apply it, so
    # editing an already-active preset's layers in the Config panel doesn't
    # leave the canvas showing a stale snapshot from before the edit.
    changed = Signal()

    def __init__(self, base_dir: Path | None = None):
        super().__init__()
        self._dir = base_dir or PARALLAX_DIR
        self._json_path = self._dir / "parallax.json"
        self._presets: dict[str, ParallaxPreset] = {}
        self.load()

    def load(self):
        self._presets = {}
        if not self._json_path.exists():
            return
        try:
            data = json.loads(self._json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for entry in data.get("presets", []):
            layers = []
            for l in entry.get("layers", []):
                image_path = str(self._dir / l["image_path"])
                # "speed" was the old single-axis field, kept readable for
                # presets saved before X/Y were split.
                speed_x = l.get("speed_x", l.get("speed", 0.5))
                layers.append(ParallaxLayer(
                    image_path=image_path,
                    name=l.get("name") or Path(image_path).stem,
                    speed_x=speed_x,
                    speed_y=l.get("speed_y", 0.0),
                    opacity=l.get("opacity", 1.0),
                    order=l.get("order", 0),
                    tile_mode=l.get("tile_mode", "repeat"),
                    motion_mode=l.get("motion_mode", "scroll"),
                    orbit_radius=l.get("orbit_radius", 20.0),
                    orbit_period=l.get("orbit_period", 8.0),
                    opacity_pulse=l.get("opacity_pulse", False),
                    opacity_min=l.get("opacity_min", 0.6),
                    opacity_max=l.get("opacity_max", 1.0),
                    opacity_period=l.get("opacity_period", 4.0),
                    scale_pulse=l.get("scale_pulse", False),
                    scale_min=l.get("scale_min", 100.0),
                    scale_max=l.get("scale_max", 110.0),
                    scale_period=l.get("scale_period", 6.0),
                    rotation_pulse=l.get("rotation_pulse", False),
                    rotation_amplitude=l.get("rotation_amplitude", 2.0),
                    rotation_period=l.get("rotation_period", 10.0),
                    phase_offset=l.get("phase_offset", 0.0),
                    effects=[
                        LayerEffect(kind=e.get("kind", ""), enabled=e.get("enabled", True), params=e.get("params", {}))
                        for e in l.get("effects", [])
                        if e.get("kind")
                    ],
                ))
            preset = ParallaxPreset(key=entry["key"], name=entry["name"], layers=layers)
            self._presets[preset.key] = preset

    def save(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "presets": [
                {
                    "key": preset.key,
                    "name": preset.name,
                    "layers": [
                        {
                            # stored relative to self._dir so the library stays portable
                            "image_path": str(Path(l.image_path).relative_to(self._dir))
                            if Path(l.image_path).is_relative_to(self._dir)
                            else l.image_path,
                            "name": l.name,
                            "speed_x": l.speed_x,
                            "speed_y": l.speed_y,
                            "opacity": l.opacity,
                            "order": l.order,
                            "tile_mode": l.tile_mode,
                            "motion_mode": l.motion_mode,
                            "orbit_radius": l.orbit_radius,
                            "orbit_period": l.orbit_period,
                            "opacity_pulse": l.opacity_pulse,
                            "opacity_min": l.opacity_min,
                            "opacity_max": l.opacity_max,
                            "opacity_period": l.opacity_period,
                            "scale_pulse": l.scale_pulse,
                            "scale_min": l.scale_min,
                            "scale_max": l.scale_max,
                            "scale_period": l.scale_period,
                            "rotation_pulse": l.rotation_pulse,
                            "rotation_amplitude": l.rotation_amplitude,
                            "rotation_period": l.rotation_period,
                            "phase_offset": l.phase_offset,
                            "effects": [
                                {"kind": e.kind, "enabled": e.enabled, "params": e.params}
                                for e in l.effects
                            ],
                        }
                        for l in preset.layers
                    ],
                }
                for preset in self._presets.values()
            ]
        }
        self._json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.changed.emit()

    def list_presets(self) -> list[ParallaxPreset]:
        return list(self._presets.values())

    def get_preset(self, key: str) -> ParallaxPreset | None:
        return self._presets.get(key)

    def add_preset(self, name: str) -> ParallaxPreset:
        name = name.strip()
        base_key = name.lower().replace(" ", "_") or "preset"
        key = base_key
        n = 1
        while key in self._presets:
            n += 1
            key = f"{base_key}_{n}"
        preset = ParallaxPreset(key=key, name=name)
        self._presets[key] = preset
        (self._dir / key).mkdir(parents=True, exist_ok=True)
        self.save()
        return preset

    def rename_preset(self, key: str, new_name: str):
        preset = self._presets.get(key)
        if preset:
            preset.name = new_name.strip() or preset.name
            self.save()

    def remove_preset(self, key: str):
        self._presets.pop(key, None)
        preset_dir = self._dir / key
        if preset_dir.exists():
            shutil.rmtree(preset_dir, ignore_errors=True)
        self.save()

    def reorder_preset(self, from_key: str, to_key: str):
        """Move a whole preset to sit where another one is — drag-and-drop
        in the Config panel, same idea as reorder_layer but one level up.
        Dict insertion order is what both list_presets() and save() iterate
        in, so rebuilding it in the new key order is enough to persist it."""
        if from_key == to_key or from_key not in self._presets or to_key not in self._presets:
            return
        keys = list(self._presets.keys())
        from_idx = keys.index(from_key)
        to_idx = keys.index(to_key)
        keys.pop(from_idx)
        keys.insert(to_idx, from_key)
        self._presets = {k: self._presets[k] for k in keys}
        self.save()

    def add_layer(self, preset_key: str, source_path: str) -> ParallaxLayer | None:
        preset = self._presets.get(preset_key)
        if preset is None:
            return None
        src = Path(source_path)
        if src.suffix.lower() not in _SUPPORTED_IMG:
            return None
        dest_dir = self._dir / preset_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            dest = dest_dir / f"{src.stem}_{uuid.uuid4().hex[:6]}{src.suffix}"
        shutil.copy2(src, dest)
        layer = ParallaxLayer(
            image_path=str(dest), name=src.stem,
            speed_x=0.5, speed_y=0.0, opacity=1.0, order=len(preset.layers),
            phase_offset=random.uniform(0, 2 * math.pi),
        )
        preset.layers.append(layer)
        self.save()
        return layer

    def remove_layer(self, preset_key: str, index: int):
        preset = self._presets.get(preset_key)
        if preset and 0 <= index < len(preset.layers):
            preset.layers.pop(index)
            self.save()

    def update_layer(self, preset_key: str, index: int, **kwargs):
        preset = self._presets.get(preset_key)
        if not preset or not (0 <= index < len(preset.layers)):
            return
        layer = preset.layers[index]
        for key, value in kwargs.items():
            if hasattr(layer, key):
                setattr(layer, key, value)
        self.save()

    def reorder_layer(self, preset_key: str, from_index: int, to_index: int):
        """Move a layer to a new position in the stack — drag-and-drop in
        the Config panel. `order` is kept in sync with list position (it's
        what Viewport actually sorts by when rendering), so moving a layer
        in the list changes its stacking order too, not just its on-screen
        row position."""
        preset = self._presets.get(preset_key)
        if not preset:
            return
        n = len(preset.layers)
        if not (0 <= from_index < n) or not (0 <= to_index < n) or from_index == to_index:
            return
        layer = preset.layers.pop(from_index)
        preset.layers.insert(to_index, layer)
        for i, l in enumerate(preset.layers):
            l.order = i
        self.save()

    def add_effect(self, preset_key: str, index: int, kind: str) -> LayerEffect | None:
        preset = self._presets.get(preset_key)
        if not preset or not (0 <= index < len(preset.layers)):
            return None
        effect = LayerEffect(kind=kind, params=dict(EFFECT_DEFAULTS.get(kind, {})))
        preset.layers[index].effects.append(effect)
        self.save()
        return effect

    def remove_effect(self, preset_key: str, index: int, effect_index: int):
        preset = self._presets.get(preset_key)
        if not preset or not (0 <= index < len(preset.layers)):
            return
        effects = preset.layers[index].effects
        if 0 <= effect_index < len(effects):
            effects.pop(effect_index)
            self.save()

    def update_effect(self, preset_key: str, index: int, effect_index: int, **kwargs):
        preset = self._presets.get(preset_key)
        if not preset or not (0 <= index < len(preset.layers)):
            return
        effects = preset.layers[index].effects
        if not (0 <= effect_index < len(effects)):
            return
        effect = effects[effect_index]
        if "enabled" in kwargs:
            effect.enabled = bool(kwargs["enabled"])
        if "params" in kwargs:
            effect.params.update(kwargs["params"])
        self.save()


_shared: ParallaxLibrary | None = None


def get_parallax_library() -> ParallaxLibrary:
    global _shared
    if _shared is None:
        _shared = ParallaxLibrary()
    return _shared
