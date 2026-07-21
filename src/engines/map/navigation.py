"""Navigation compass layer presets — a stack of transparent images, each
representing one part of the compass (background, degree ring, needle,
core, glow...) with its own continuous animation (fixed, spinning, pulsing,
blinking, or locked to the map's actual rotation). Replaces the old
hand-painted compass needle. Mirrors engines/map/parallax.py's persistence
pattern (own JSON file + copying imported layer images into
library/navigation/<key>/), plus a single "active" preset — the one Compass
actually plays.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIBRARY_DIR = _SOURCE_ROOT / "library"
NAVIGATION_DIR = LIBRARY_DIR / "navigation"
NAVIGATION_JSON = NAVIGATION_DIR / "navigation.json"

_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# (role key, label) — what part of the compass this layer represents.
ROLE_KINDS = [
    ("background_fx", "Efeitos de fundo"),
    ("ring_degrees", "Anel de rotação"),
    ("main_pointer", "Ponteiros principais"),
    ("secondary_pointer", "Ponteiros secundários"),
    ("core", "Miolo central"),
    ("outer_glow", "Brilho externo"),
]
_ROLE_KEYS = {k for k, _ in ROLE_KINDS}
DEFAULT_ROLE = "background_fx"

# (animation key, label) — how the layer behaves, continuously (no more
# frame-cycling). "locked_to_view" ignores `period` — driven directly by
# the attached Viewport's rotation instead of elapsed time.
ANIMATION_KINDS = [
    ("fixed", "Fixo na tela"),
    ("rotate_cw", "Rotação contínua"),
    ("rotate_ccw", "Rotação inversa"),
    ("locked_to_view", "Travado na direção do mapa"),
    ("pulse", "Pulso luminoso"),
    ("blink", "Piscar"),
    ("interaction", "Interação"),
]
_ANIMATION_KEYS = {k for k, _ in ANIMATION_KINDS}
DEFAULT_ANIMATION = "fixed"

# animations that actually use `period` — the rest ignore it.
TIMED_ANIMATIONS = {"rotate_cw", "rotate_ccw", "pulse", "blink"}


@dataclass
class NavigationLayer:
    image_path: str                    # absolute path, resolved at load time
    name: str = ""                     # user-editable label, independent of the filename
    role: str = DEFAULT_ROLE           # what part of the compass this represents
    animation: str = DEFAULT_ANIMATION  # how it behaves, continuously
    period: float = 6.0                # seconds per cycle — only used by TIMED_ANIMATIONS
    opacity: float = 1.0               # 0..1, same convention as ParallaxLayer.opacity — multiplies with any animation-driven opacity (pulse/blink)
    scale: float = 1.0                 # fraction of the role's baseline size (core diameter, or ring band for outer_glow/ring_degrees) — 1.0 = fills it, e.g. 0.25 for a small central núcleo


@dataclass
class NavigationPreset:
    key: str
    name: str
    layers: list[NavigationLayer] = field(default_factory=list)
    # Whether the HUD chip (terreno ativo / área do mapa / lat-lon —
    # CompassHUD) shows up alongside this preset when it's active and the
    # compass is expanded. Per-preset since a minimalist compass design
    # might not want that info cluttering it, while a detailed one might.
    show_info: bool = True


class NavigationLibrary(QObject):
    """Loads/saves navigation presets to library/navigation/navigation.json
    and manages copying imported layer images into library/navigation/<key>/."""

    # Emitted after every save() — Compass listens for this to reload the
    # active preset's layers, so editing them in the Config panel updates
    # the overlay immediately instead of leaving it on a stale stack.
    changed = Signal()

    def __init__(self, base_dir: Path | None = None):
        super().__init__()
        self._dir = base_dir or NAVIGATION_DIR
        self._json_path = self._dir / "navigation.json"
        self._presets: dict[str, NavigationPreset] = {}
        self._active_key: str | None = None
        self.load()

    def load(self):
        self._presets = {}
        self._active_key = None
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
                role = l.get("role", DEFAULT_ROLE)
                animation = l.get("animation", DEFAULT_ANIMATION)
                layers.append(NavigationLayer(
                    image_path=image_path,
                    name=l.get("name") or Path(image_path).stem,
                    # Normalize anything from an older/obsolete format (e.g.
                    # the "hover" role/frame-cycling model this replaced)
                    # back to a sane default instead of carrying it forward.
                    role=role if role in _ROLE_KEYS else DEFAULT_ROLE,
                    animation=animation if animation in _ANIMATION_KEYS else DEFAULT_ANIMATION,
                    period=l.get("period", 6.0),
                    opacity=l.get("opacity", 1.0),
                    scale=l.get("scale", 1.0),
                ))
            preset = NavigationPreset(
                key=entry["key"], name=entry["name"], layers=layers,
                show_info=entry.get("show_info", True),
            )
            self._presets[preset.key] = preset
        active_key = data.get("active_key")
        self._active_key = active_key if active_key in self._presets else None

    def save(self):
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "active_key": self._active_key,
            "presets": [
                {
                    "key": preset.key,
                    "name": preset.name,
                    "show_info": preset.show_info,
                    "layers": [
                        {
                            # stored relative to self._dir so the library stays portable
                            "image_path": str(Path(l.image_path).relative_to(self._dir))
                            if Path(l.image_path).is_relative_to(self._dir)
                            else l.image_path,
                            "name": l.name,
                            "role": l.role,
                            "animation": l.animation,
                            "period": l.period,
                            "opacity": l.opacity,
                            "scale": l.scale,
                        }
                        for l in preset.layers
                    ],
                }
                for preset in self._presets.values()
            ],
        }
        self._json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.changed.emit()

    def list_presets(self) -> list[NavigationPreset]:
        return list(self._presets.values())

    def get_preset(self, key: str) -> NavigationPreset | None:
        return self._presets.get(key)

    def active_key(self) -> str | None:
        return self._active_key

    def get_active_preset(self) -> NavigationPreset | None:
        return self._presets.get(self._active_key) if self._active_key else None

    def set_active(self, key: str | None):
        self._active_key = key if key in self._presets else None
        self.save()

    def add_preset(self, name: str) -> NavigationPreset:
        name = name.strip()
        base_key = name.lower().replace(" ", "_") or "preset"
        key = base_key
        n = 1
        while key in self._presets:
            n += 1
            key = f"{base_key}_{n}"
        preset = NavigationPreset(key=key, name=name)
        self._presets[key] = preset
        (self._dir / key).mkdir(parents=True, exist_ok=True)
        self.save()
        return preset

    def rename_preset(self, key: str, new_name: str):
        preset = self._presets.get(key)
        if preset:
            preset.name = new_name.strip() or preset.name
            self.save()

    def set_show_info(self, key: str, value: bool):
        preset = self._presets.get(key)
        if preset:
            preset.show_info = value
            self.save()

    def remove_preset(self, key: str):
        self._presets.pop(key, None)
        preset_dir = self._dir / key
        if preset_dir.exists():
            shutil.rmtree(preset_dir, ignore_errors=True)
        if self._active_key == key:
            self._active_key = None
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

    def add_layer(self, preset_key: str, source_path: str) -> NavigationLayer | None:
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
        layer = NavigationLayer(image_path=str(dest), name=src.stem)
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
        the Config panel. Order = stacking order (first = drawn first =
        further back), same convention as ParallaxLibrary.reorder_layer."""
        preset = self._presets.get(preset_key)
        if not preset:
            return
        n = len(preset.layers)
        if not (0 <= from_index < n) or not (0 <= to_index < n) or from_index == to_index:
            return
        layer = preset.layers.pop(from_index)
        preset.layers.insert(to_index, layer)
        self.save()


_shared: NavigationLibrary | None = None


def get_navigation_library() -> NavigationLibrary:
    global _shared
    if _shared is None:
        _shared = NavigationLibrary()
    return _shared
