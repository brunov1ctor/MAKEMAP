"""Brush-painted effects that animate over time (Névoa, Poeira, Cinzas,
Folhas, ...) — painted directly with the Brush tool (category "effects" in
AssetBrowserPanel), into a TerrainLayer mask (mask_only, no visible
texture — see BrushTool's effects routing) rather than a static pixmap,
since they need to keep moving after the stroke is painted. Rendered
instead by BrushEffectsOverlay, a separate whole-scene QGraphicsItem
repainted on BrushMediator's own refresh timer, clipped per-stroke to
TerrainLayer.effect_geometry()'s traced silhouette.

Style-agnostic on purpose: the same effect looks identical regardless of
which asset style (realistic/cartoon/rabiscos/...) is active — unlike
terrain, there's no separate texture per style to pick, just one shared
procedural look per effect key.

To add a new animated effect: write a paint function with the signature
`(painter, cache, layer, path, bounds, color) -> None`, register it in
ANIMATED_EFFECTS, and add a default tint to EFFECT_COLORS below.
"""

from __future__ import annotations

import math
import time
from typing import Callable

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from src.engines.fog_noise import density_to_qimage, fbm_density, path_to_blurred_mask

# Internal FBM generation resolution — independent of the região's actual
# painted size, same reasoning as lighting_overlay._FOG_TEX_SIZE: it's
# soft, blurry noise to begin with, so scaling a modest texture up via
# QPainter costs nothing extra and keeps generation cost constant
# regardless of how big the região is.
_FOG_TEX_SIZE = 160
_FOG_BREATHE_PERIOD = 40.0  # seconds for one full crossfade "breathe" cycle
# (draw_scale, drift_speed, alpha_mult) per parallax layer, same idea as
# lighting_overlay._FOG_LAYERS — reuses the SAME cached/crossfaded noise
# texture at different sizes/drift/opacity instead of tripling generation
# cost.
_FOG_LAYERS = (
    (1.6, 0.14, 0.40),
    (1.15, 0.26, 0.60),
    (0.85, 0.50, 0.85),
)
_FOG_DRIFT_FRACTION = 0.06  # max drift as a fraction of the shape's own size
_FOG_BLUR_PX = 10
_FOG_BUF_MARGIN = 24


def _center_path(path: QPainterPath, bounds: QRectF) -> QPainterPath:
    """path_to_blurred_mask expects coordinates roughly centered on the
    image it rasterizes into (-size/2..size/2) — a região's traced
    silhouette instead sits wherever it was painted on the (up to
    4096x4096) mask, so this re-centers it on its own bounds first."""
    return QTransform().translate(-bounds.center().x(), -bounds.center().y()).map(path)


def _fog_textures(cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor) -> dict:
    """Cached (seed, size-bucket, color) -> two FBM density QImages plus a
    blurred silhouette mask (see path_to_blurred_mask) — regenerated only
    when the shape's own size bucket or tint actually changes, not every
    repaint tick (RegionMediator's refresh timer fires continuously to
    drive the breathing/drift animation even when nothing else changed)."""
    key = (round(bounds.width() / 20) * 20, round(bounds.height() / 20) * 20, color.name())
    entry = cache.get(id(layer))
    if entry is not None and entry.get("key") == key:
        return entry

    seed = id(layer) & 0xFFFFFFFF
    near_color = color.lighter(140)
    far_color = color.darker(150)
    density_a = fbm_density(_FOG_TEX_SIZE, _FOG_TEX_SIZE, seed, base_cells=4)
    density_b = fbm_density(_FOG_TEX_SIZE, _FOG_TEX_SIZE, seed ^ 0x5EED, base_cells=4)
    max_layer_scale = max(scale for scale, _, _ in _FOG_LAYERS)
    buf_size = int(max(bounds.width(), bounds.height()) * max_layer_scale) + _FOG_BUF_MARGIN * 2
    entry = {
        "key": key,
        "img_a": density_to_qimage(density_a, near_color, far_color, alpha_gamma=1.8, alpha_scale=0.8),
        "img_b": density_to_qimage(density_b, near_color, far_color, alpha_gamma=1.8, alpha_scale=0.8),
        "phase_offset": (seed % 1000) / 1000.0 * _FOG_BREATHE_PERIOD,
        "buf_size": buf_size,
        "mask": path_to_blurred_mask(_center_path(path, bounds), buf_size, _FOG_BLUR_PX),
        "buf": None,  # composite scratch buffer, allocated lazily and reused across ticks — see paint_nevoa
    }
    cache[id(layer)] = entry
    return entry


def paint_nevoa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Low-lying mist confined to the região's own painted shape — same
    parallax-FBM technique as GlobalLightingOverlay's light-type "fog"
    (see lighting_overlay._paint_fog), just clipped to an arbitrary traced
    silhouette instead of a light's circular/cone lit_path."""
    entry = _fog_textures(cache, layer, path, bounds, color)
    t = time.monotonic() + entry["phase_offset"]
    mix = (math.sin(2 * math.pi * t / _FOG_BREATHE_PERIOD) + 1) / 2  # 0..1, slow crossfade

    buf_size = entry["buf_size"]
    buf = entry["buf"]
    if buf is None or buf.width() != buf_size:
        buf = QImage(buf_size, buf_size, QImage.Format.Format_ARGB32_Premultiplied)
        entry["buf"] = buf
    buf.fill(0)
    bp = QPainter(buf)
    bp.setRenderHint(QPainter.RenderHint.Antialiasing)
    bp.translate(buf_size / 2, buf_size / 2)
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    diag = max(bounds.width(), bounds.height())
    for draw_scale, drift_speed, alpha_mult in _FOG_LAYERS:
        size = diag * draw_scale
        dx = math.sin(t * drift_speed) * diag * _FOG_DRIFT_FRACTION
        dy = math.cos(t * drift_speed * 0.8) * diag * _FOG_DRIFT_FRACTION
        target = QRectF(-size / 2 + dx, -size / 2 + dy, size, size)
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * (1 - mix))))
        bp.drawImage(target, entry["img_a"])
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * mix)))
        bp.drawImage(target, entry["img_b"])
    bp.setOpacity(1.0)
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    bp.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), entry["mask"])
    bp.end()

    painter.save()
    painter.translate(bounds.center())
    painter.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), buf)
    painter.restore()


# ─── Simple drifting-particle effects (Poeira, Cinzas, Folhas) ────────────
# All three are the same underlying idea — a fixed set of particles, each
# following its own deterministic, purely time-driven path (no per-frame
# physics/state to update, same "stateless, driven by time.monotonic()"
# approach lighting_overlay._draw_volumetric already uses) — just with
# different vertical drift/sway/size/shape constants, passed as `motion`.
# Positions are computed in the shape's own [0,1]x[0,1] bounds-normalized
# space and only clipped to the traced silhouette at draw time (via
# painter.setClipPath), not confined to the actual painted area itself —
# for a very non-rectangular região this wastes a few particles clipped
# away entirely, which reads as "a bit sparser" rather than as a bug, and
# is far cheaper than sampling the actual mask per-particle.

def _particle_seeds(cache: dict, layer, kind: str, count: int) -> dict:
    """Per-região, per-effect-kind random particle attributes (initial
    position/phase/size/speed jitter/rotation) — regenerated only when the
    kind or count changes (i.e. the Estilo was switched to a different
    particle effect), not every repaint tick."""
    entry = cache.get(id(layer))
    if entry is not None and entry.get("kind") == kind and entry.get("count") == count:
        return entry
    rng = np.random.default_rng((id(layer) & 0xFFFFFFFF) ^ hash(kind) & 0xFFFFFFFF)
    entry = {
        "kind": kind,
        "count": count,
        "x0": rng.random(count).astype(np.float32),
        "y0": rng.random(count).astype(np.float32),
        "phase": rng.random(count).astype(np.float32) * 2 * math.pi,
        "speed_jitter": 0.7 + rng.random(count).astype(np.float32) * 0.6,
        "size_jitter": rng.random(count).astype(np.float32),
        "rot0": rng.random(count).astype(np.float32) * 360.0,
        "spin_dir": np.where(rng.random(count) < 0.5, -1.0, 1.0).astype(np.float32),
    }
    cache[id(layer)] = entry
    return entry


def _paint_particles(painter: QPainter, cache: dict, layer, path: QPainterPath,
                      bounds: QRectF, color: QColor, motion: dict):
    """Shared draw loop for Poeira/Cinzas/Folhas — `motion` selects the
    physics: "oscillate" particles wobble in place around their seed point
    (dust drifting in the air, never leaving the shape); "drift" particles
    move steadily along one axis and wrap back around when they leave the
    shape's bounds (ash rising, leaves falling), fading out near the wrap
    edge (`fade_band`) so the wrap-around doesn't read as a visible pop."""
    seeds = _particle_seeds(cache, layer, motion["kind"], motion["count"])
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    base_color = QColor(color)

    for i in range(motion["count"]):
        speed = motion["speed"] * seeds["speed_jitter"][i]
        phase = seeds["phase"][i]
        if motion["style"] == "oscillate":
            nx = seeds["x0"][i] + math.sin(t * speed + phase) * motion["amount"]
            ny = seeds["y0"][i] + math.cos(t * speed * 0.8 + phase) * motion["amount"]
            alpha = motion["alpha"]
        elif motion["style"] == "insect":
            # Buzzes around its own seed point same as "oscillate", but the
            # oscillation CENTER is pulled toward `_bias` (the nearest
            # light's own position, normalized into this shape's bounds —
            # see _nearest_light_bias) when one exists nearby — "as
            # partículas podem ser atraídas pela luz". No bias found (no
            # light nearby) just leaves it buzzing around its own seed.
            ox = math.sin(t * speed + phase) * motion["amount"]
            oy = math.cos(t * speed * 0.8 + phase) * motion["amount"]
            bias = motion.get("_bias")
            if bias is not None:
                pull = motion["attract"]
                nx = seeds["x0"][i] * (1 - pull) + bias[0] * pull + ox
                ny = seeds["y0"][i] * (1 - pull) + bias[1] * pull + oy
            else:
                nx = seeds["x0"][i] + ox
                ny = seeds["y0"][i] + oy
            alpha = motion["alpha"]
        else:  # "drift" — moves steadily along one axis, wrapping around
            # when it leaves the shape's bounds; the OTHER axis just sways.
            # Vertical (rain/snow/ash/leaves falling or rising) is the
            # common case; horizontal (sandstorm blowing sideways) swaps
            # which axis drifts vs. sways.
            if motion.get("axis", "vertical") == "vertical":
                ny = (seeds["y0"][i] + motion["dir"] * speed * t) % 1.0
                nx = (seeds["x0"][i] + math.sin(t * motion["sway_speed"] + phase) * motion["sway"]) % 1.0
                edge = min(ny, 1.0 - ny) / motion["fade_band"]
            else:
                nx = (seeds["x0"][i] + motion["dir"] * speed * t) % 1.0
                ny = (seeds["y0"][i] + math.sin(t * motion["sway_speed"] + phase) * motion["sway"]) % 1.0
                edge = min(nx, 1.0 - nx) / motion["fade_band"]
            alpha = motion["alpha"] * max(0.0, min(1.0, edge))

        alpha_i = int(alpha)
        if alpha_i <= 0:
            continue
        x = bounds.left() + max(0.0, min(1.0, nx)) * w
        y = bounds.top() + max(0.0, min(1.0, ny)) * h
        size = motion["size_min"] + seeds["size_jitter"][i] * (motion["size_max"] - motion["size_min"])

        particle_color = QColor(base_color)
        particle_color.setAlpha(alpha_i)
        if motion["kind"] in ("rain", "drizzle"):
            # A short streak along the fall direction reads as motion-
            # blurred rain/drizzle far better than a round drop would at
            # this scale — length itself follows `size` so drizzle (small
            # size_min/max) draws as barely-there hairline scratches, per
            # "sem gotas visíveis, só pequenos riscos transparentes".
            angle = math.radians(motion.get("angle_deg", 10.0))
            dx = math.sin(angle) * size
            dy = math.cos(angle) * size
            pen = painter.pen()
            pen.setColor(particle_color)
            pen.setWidthF(motion["width"])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(x - dx / 2, y - dy / 2), QPointF(x + dx / 2, y + dy / 2))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(particle_color)
            if motion["kind"] == "leaf":
                painter.save()
                painter.translate(x, y)
                spin = seeds["rot0"][i] + t * motion["rot_speed"] * seeds["spin_dir"][i]
                painter.rotate(spin)
                painter.drawEllipse(QRectF(-size, -size * 0.55, size * 2, size * 1.1))
                painter.restore()
            elif motion.get("glow"):
                # A soft, wide, low-alpha halo behind a small full-alpha
                # core — a plain flat dot at this size just read as a
                # speck, not "brilhante" (pólen/esporos/vaga-lumes are all
                # described as glowing, not merely small).
                halo = QColor(particle_color)
                halo.setAlpha(max(0, alpha_i // 3))
                painter.setBrush(halo)
                painter.drawEllipse(QPointF(x, y), size * 2.4, size * 2.4)
                painter.setBrush(particle_color)
                painter.drawEllipse(QPointF(x, y), size, size)
            else:
                painter.drawEllipse(QPointF(x, y), size, size)

    painter.restore()


def _subcache(cache: dict, name: str) -> dict:
    """A namespaced sub-dict of the overlay's per-layer `cache` — for
    composite effects (e.g. Região Fria = tinted Névoa + ice motes) that
    need to call two independent cached sub-effects for the SAME layer.
    Both `_fog_textures` and `_particle_seeds` key their own cache purely
    by id(layer), so handing them the very same top-level `cache` dict
    from two different sub-effects on one layer would have them
    overwrite each other's entry every frame (mismatched shape -> cache
    miss -> full regen -> every tick, defeating the cache rather than
    crashing). Giving each sub-effect its own namespaced dict avoids that
    without changing either helper."""
    return cache.setdefault(name, {})


def _nearest_light_bias(cache: dict, bounds: QRectF) -> tuple[float, float] | None:
    """Nearest visible LightItem to this stroke's own center, normalized
    into `bounds`' [0,1]x[0,1] space (clamped) — what paint_insetos pulls
    its particles toward ("as partículas podem ser atraídas pela luz").
    `bounds` is already in SCENE coords by the time an effect painter runs
    (see BrushEffectsOverlay.paint), so this compares directly against
    LightItem.scenePos() with no extra transform. `cache["_lights"]` is the
    list of visible LightItems the overlay already collected once for this
    whole paint pass (see BrushEffectsOverlay.paint) — reusing it avoids
    this doing its own separate full-scene scan per stroke per tick. None
    if there's no visible light at all — not just none nearby, since a
    single light anywhere still reads as "the" light to drift toward
    rather than leaving insects with nothing to react to."""
    lights = cache.get("_lights", ())
    center = bounds.center()
    best_pos, best_d2 = None, None
    for item in lights:
        pos = item.scenePos()
        d2 = (pos.x() - center.x()) ** 2 + (pos.y() - center.y()) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2, best_pos = d2, pos
    if best_pos is None:
        return None
    w, h = max(1.0, bounds.width()), max(1.0, bounds.height())
    bx = max(0.0, min(1.0, (best_pos.x() - bounds.left()) / w))
    by = max(0.0, min(1.0, (best_pos.y() - bounds.top()) / h))
    return bx, by


def paint_poeira(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Fine dust motes floating in place — small, numerous, gently
    wobbling instead of steadily drifting in one direction."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "dust", "style": "oscillate", "count": 46,
        "speed": 0.35, "amount": 0.05,
        "size_min": 1.0, "size_max": 2.6, "alpha": 130,
    })


def paint_polen(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Pollen — fixed golden tint regardless of the região's own color
    ("partículas douradas"), nearly invisible at rest (very low alpha) but
    glowing (see `_paint_particles`' "glow" halo), same idea as "muito
    bonito contra a luz" — reads best silhouetted against a bright light
    or sky, which the halo helps sell even without real backlighting."""
    gold = QColor(235, 200, 90)
    _paint_particles(painter, cache, layer, path, bounds, gold, {
        "kind": "pollen", "style": "oscillate", "count": 40,
        "speed": 0.2, "amount": 0.04,
        "size_min": 0.8, "size_max": 1.6, "alpha": 55, "glow": True,
    })


def paint_insetos(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Fireflies/moths/mosquitoes — small glowing motes that buzz around
    their own spot but drift toward the nearest light in the scene, if
    any (see _nearest_light_bias)."""
    motion = {
        "kind": "insect", "style": "insect", "count": 18,
        "speed": 0.6, "amount": 0.03, "attract": 0.55,
        "size_min": 1.0, "size_max": 2.0, "alpha": 200, "glow": True,
        "_bias": _nearest_light_bias(cache, bounds),
    }
    _paint_particles(painter, cache, layer, path, bounds, color, motion)


def paint_cinzas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Charred flecks rising slowly and steadily, swaying a little on the
    way up — fewer and slightly larger than dust, dimmer than leaves."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "ash", "style": "drift", "count": 30, "dir": -1.0,
        "speed": 0.028, "sway_speed": 0.4, "sway": 0.03,
        "size_min": 1.2, "size_max": 2.6, "alpha": 150, "fade_band": 0.18,
    })


def paint_folhas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Leaves falling with a lazy side-to-side sway, each spinning at its
    own rate/direction (see _particle_seeds' spin_dir) — bigger, sparser
    and more opaque than dust/ash so individual leaves read clearly."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "leaf", "style": "drift", "count": 20, "dir": 1.0,
        "speed": 0.045, "sway_speed": 0.5, "sway": 0.07,
        "size_min": 3.5, "size_max": 6.0, "alpha": 190, "fade_band": 0.15,
        "rot_speed": 70.0,
    })


# ─── Weather effects (Chuva localizada, Garoa, Neve, Tempestade de areia) ──
# Same particle engine as above — rain/drizzle just draw a short streak
# along the fall direction instead of a dot/ellipse (see _paint_particles'
# "rain"/"drizzle" kind branch), and reuse `size_min`/`size_max` to mean
# streak LENGTH instead of radius.

def paint_chuva(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Localized rain — fast, steep streaks confined to the região itself
    (unlike Névoa's wide drifting mist). Reads best with a pale blue-grey
    região color, but — same convention as every other effect here —
    always uses whatever color the região was actually given."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "rain", "style": "drift", "count": 55, "dir": 1.0, "axis": "vertical",
        "speed": 1.1, "sway_speed": 0.2, "sway": 0.01,
        "size_min": 14.0, "size_max": 26.0, "alpha": 170, "fade_band": 0.10,
        "width": 1.6, "angle_deg": 8.0,
    })


def paint_garoa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Drizzle — same falling-streak idea as Chuva, but much fainter,
    thinner and slower, with no distinct visible "drops" — "sem gotas
    visíveis, só pequenos riscos transparentes"."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "drizzle", "style": "drift", "count": 70, "dir": 1.0, "axis": "vertical",
        "speed": 0.55, "sway_speed": 0.15, "sway": 0.008,
        "size_min": 6.0, "size_max": 12.0, "alpha": 55, "fade_band": 0.12,
        "width": 0.8, "angle_deg": 6.0,
    })


def paint_neve(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Snow — falls slowly with a wide, lazy side-to-side sway (wind). No
    ground accumulation: this is a stateless per-frame overlay effect, not
    a persistent layer that could build up over time — accumulating snow
    would need its own painted mask that grows, closer to how RegionLayer
    itself paints, which is a much bigger feature than this overlay."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "snow", "style": "drift", "count": 40, "dir": 1.0, "axis": "vertical",
        "speed": 0.05, "sway_speed": 0.35, "sway": 0.09,
        "size_min": 2.0, "size_max": 4.0, "alpha": 210, "fade_band": 0.15,
    })


def paint_tempestade_areia(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Sandstorm — dense particles blowing sideways plus a translucent
    haze wash over the whole shape, standing in for "aumenta a fog, reduz
    visão" WITHIN the região itself. Does NOT reach into the lighting
    system to actually dim nearby lights ("diminui intensidade das
    luzes") — that would need RegionMediator to notify LightMediator
    about which lights currently sit inside an active sandstorm região,
    cross-module wiring that doesn't exist yet."""
    haze = QColor(color)
    haze.setAlpha(70)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, haze)
    painter.restore()
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "sand", "style": "drift", "count": 60, "dir": 1.0, "axis": "horizontal",
        "speed": 0.12, "sway_speed": 0.6, "sway": 0.04,
        "size_min": 1.0, "size_max": 2.4, "alpha": 150, "fade_band": 0.12,
    })


# ─── Fumaça, Gás tóxico, Esporos, Cinzas vulcânicas ────────────────────────

def paint_fumaca(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Smoke — big, soft, low-alpha puffs rising slowly with a gentle
    sway; fábricas/incêndios/acampamentos all just need a different
    região color (grey for factories, orange-grey for fires, ...) —
    same "usa a cor da região" convention as Poeira/Cinzas/Folhas."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "smoke", "style": "drift", "count": 16, "dir": -1.0, "axis": "vertical",
        "speed": 0.02, "sway_speed": 0.25, "sway": 0.05,
        "size_min": 10.0, "size_max": 22.0, "alpha": 55, "fade_band": 0.2,
    })


def paint_gas_toxico(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Toxic gas — fixed sickly-green tint regardless of the região's own
    color ("neblina verde", "luz esverdeada" — the green IS the effect's
    identity, unlike every other effect here that tints by the região's
    own color): a translucent green haze wash plus small floating motes.
    No real pixel distortion ("distorção leve") — that needs warping the
    scene behind the effect, which this QPainter-level overlay can't do
    without rendering the map itself to an offscreen buffer first; skipped
    rather than faked badly."""
    toxic = QColor(70, 190, 90)
    haze = QColor(toxic)
    haze.setAlpha(60)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, haze)
    painter.restore()
    _paint_particles(painter, cache, layer, path, bounds, toxic, {
        "kind": "toxic", "style": "oscillate", "count": 26,
        "speed": 0.3, "amount": 0.06,
        "size_min": 1.5, "size_max": 3.0, "alpha": 120,
    })


def paint_esporos(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Spores — small glowing motes drifting extremely slowly, for alien
    forests. Same glow treatment as Pólen/Insetos but uses the região's
    own color (no fixed tint mandated by the brief, unlike Pólen's gold
    or Gás tóxico's green)."""
    _paint_particles(painter, cache, layer, path, bounds, color, {
        "kind": "spore", "style": "oscillate", "count": 24,
        "speed": 0.08, "amount": 0.03,
        "size_min": 1.2, "size_max": 2.2, "alpha": 170, "glow": True,
    })


def paint_cinzas_vulcanicas(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Volcanic ash — fixed black particles ("partículas pretas",
    unrelated to the região's own color) drifting down, plus a modest
    dark haze wash standing in for "redução gradual da iluminação"
    LOCALLY within the região. Doesn't actually dim the map's real
    lights outside it — same cross-module limitation noted on
    paint_tempestade_areia; "gradual" is also not literal here since this
    overlay has no notion of "time since entering the região" to ramp
    against, just a fixed wash."""
    black = QColor(15, 15, 15)
    haze = QColor(black)
    haze.setAlpha(50)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, haze)
    painter.restore()
    _paint_particles(painter, cache, layer, path, bounds, black, {
        "kind": "vash", "style": "drift", "count": 34, "dir": -1.0, "axis": "vertical",
        "speed": 0.03, "sway_speed": 0.3, "sway": 0.03,
        "size_min": 1.2, "size_max": 2.4, "alpha": 170, "fade_band": 0.18,
    })


# ─── Thematic regions — compose the primitives above (fog, particles, a
# tint wash) into a single richer look per the brief. None of these touch
# pixels OUTSIDE their own painted shape or reach into other systems (real
# blur/distortion of the map itself, actual light flicker/dimming, longer
# occluder shadows, character breath) — those would need either an
# offscreen re-render of the map to post-process, or cross-module wiring
# into TransformEngine/GlobalLightingOverlay that doesn't exist. Each
# docstring below says exactly what's skipped and why.

def paint_regiao_fria(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Cold região — icy-blue-tinted Névoa (see _subcache for why this
    needs its own fog cache namespace, separate from the ice motes'
    particle cache) plus small glowing ice motes. No visible-breath puff
    system — this editor has no character/mob "breathing" concept to
    attach one to."""
    ice_tint = QColor(190, 220, 255)
    paint_nevoa(painter, _subcache(cache, "fog"), layer, path, bounds, ice_tint)
    _paint_particles(painter, _subcache(cache, "particles"), layer, path, bounds, QColor(230, 245, 255), {
        "kind": "ice", "style": "oscillate", "count": 22,
        "speed": 0.15, "amount": 0.02,
        "size_min": 1.0, "size_max": 2.0, "alpha": 190, "glow": True,
    })


def paint_regiao_quente(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Hot região — animated heat-shimmer bands (additive, wavering
    horizontal streaks — the moving counterpart to the static Vapor
    bake's ripple) plus glowing ember motes for "brilho forte". Can't
    reduce the underlying fill's own saturation from here ("saturação
    menor") — that's Vapor's job (a static bake with real pixel access to
    the fill), this overlay only ever paints ON TOP of it."""
    painter.save()
    painter.setClipPath(path)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setPen(Qt.PenStyle.NoPen)
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    bands = 5
    for i in range(bands):
        phase = i * 1.3
        wobble = math.sin(t * 1.4 + phase) * h * 0.02
        y = bounds.top() + (i + 0.5) / bands * h + wobble
        band_color = QColor(255, 200, 120, 32)
        painter.setBrush(band_color)
        painter.drawRect(QRectF(bounds.left(), y - h * 0.03, w, h * 0.06))
    painter.restore()
    _paint_particles(painter, _subcache(cache, "particles"), layer, path, bounds, QColor(255, 170, 80), {
        "kind": "ember", "style": "oscillate", "count": 14,
        "speed": 0.5, "amount": 0.04,
        "size_min": 1.0, "size_max": 2.2, "alpha": 170, "glow": True,
    })


def paint_regiao_magica(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Magic região — small blue/purple/gold particles spiraling around
    the shape's own center. A dedicated draw loop rather than another
    _paint_particles "style", since spiral motion is angle+radius, not
    the nx/ny drift/oscillate/insect styles that helper already covers —
    one-off geometry isn't worth generalizing the shared helper for."""
    entry = cache.get(id(layer))
    count = 30
    if entry is None or entry.get("kind") != "magic":
        rng = np.random.default_rng(id(layer) & 0xFFFFFFFF)
        entry = {
            "kind": "magic", "count": count,
            "radius0": rng.random(count).astype(np.float32),
            "angle0": rng.random(count).astype(np.float32) * 2 * math.pi,
            "speed_jitter": 0.6 + rng.random(count).astype(np.float32) * 0.8,
            "size_jitter": rng.random(count).astype(np.float32),
            "color_pick": rng.integers(0, 3, count),
        }
        cache[id(layer)] = entry

    palette = (QColor(120, 160, 255), QColor(190, 120, 255), QColor(255, 215, 110))
    t = time.monotonic()
    cx, cy = bounds.center().x(), bounds.center().y()
    max_r = min(bounds.width(), bounds.height()) * 0.45

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(entry["count"]):
        spin_speed = 0.4 * entry["speed_jitter"][i]
        angle = entry["angle0"][i] + t * spin_speed
        radius = entry["radius0"][i] * max_r * (0.6 + 0.4 * math.sin(t * 0.3 + entry["angle0"][i]))
        x = cx + math.cos(angle) * radius
        y = cy + math.sin(angle) * radius
        size = 1.2 + entry["size_jitter"][i] * 1.8

        particle_color = QColor(palette[int(entry["color_pick"][i])])
        particle_color.setAlpha(190)
        halo = QColor(particle_color)
        halo.setAlpha(60)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(x, y), size * 2.2, size * 2.2)
        painter.setBrush(particle_color)
        painter.drawEllipse(QPointF(x, y), size, size)
    painter.restore()


def paint_regiao_radioativa(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Radioactive região — green haze wash plus small sharp flashes (each
    particle only becomes visible near the peak of its own sine cycle,
    ramping in/out over the last 10% instead of a hard on/off pop). No
    "ruído na iluminação" — that would mean perturbing GlobalLighting
    Overlay's actual light rendering, cross-module wiring this doesn't
    have."""
    green = QColor(140, 230, 90)
    haze = QColor(green)
    haze.setAlpha(55)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, haze)
    painter.restore()

    entry = cache.get(id(layer))
    count = 12
    if entry is None or entry.get("kind") != "radioactive":
        rng = np.random.default_rng(id(layer) & 0xFFFFFFFF)
        entry = {
            "kind": "radioactive", "count": count,
            "x0": rng.random(count).astype(np.float32),
            "y0": rng.random(count).astype(np.float32),
            "phase": rng.random(count).astype(np.float32) * 2 * math.pi,
            "flash_speed": 0.6 + rng.random(count).astype(np.float32) * 1.2,
        }
        cache[id(layer)] = entry

    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(entry["count"]):
        flash = math.sin(t * entry["flash_speed"][i] + entry["phase"][i])
        if flash < 0.9:
            continue
        strength = (flash - 0.9) / 0.1
        x = bounds.left() + entry["x0"][i] * w
        y = bounds.top() + entry["y0"][i] * h
        flash_color = QColor(230, 255, 190)
        flash_color.setAlpha(int(200 * strength))
        painter.setBrush(flash_color)
        painter.drawEllipse(QPointF(x, y), 2.0 + 3.0 * strength, 2.0 + 3.0 * strength)
    painter.restore()


def paint_regiao_sonho(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Dream região — lightened, slow-breathing Névoa plus small glowing
    motes in four different colors (four separate _paint_particles calls,
    each with its own namespaced sub-cache and fixed color, rather than
    teaching the shared particle helper to vary color per-particle for
    this one effect). No real "desfoque leve" (slight blur) of the map
    underneath — that needs re-rendering the region to an offscreen
    buffer and Gaussian-blurring it, which this paint-on-top overlay
    can't do; the glow halos stand in for "bloom" instead."""
    dreamy = QColor(color).lighter(130)
    paint_nevoa(painter, _subcache(cache, "fog"), layer, path, bounds, dreamy)
    palette = (QColor(255, 140, 220), QColor(140, 200, 255), QColor(255, 230, 140), QColor(180, 140, 255))
    for idx, particle_color in enumerate(palette):
        _paint_particles(painter, _subcache(cache, f"particles_{idx}"), layer, path, bounds, particle_color, {
            "kind": f"dream{idx}", "style": "oscillate", "count": 8,
            "speed": 0.15, "amount": 0.05,
            "size_min": 1.5, "size_max": 2.8, "alpha": 150, "glow": True,
        })


def paint_regiao_amaldicoada(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Cursed região — a dark wash plus a denser, dark-tinted Névoa. Does
    NOT lengthen actual asset/mob shadow geometry (TransformEngine/
    lighting_compositor own that) or flicker real placed lights
    (GlobalLightingOverlay) — both would need cross-module wiring this
    doesn't have."""
    dark = QColor(20, 15, 25)
    wash = QColor(dark)
    wash.setAlpha(90)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, wash)
    painter.restore()
    paint_nevoa(painter, _subcache(cache, "fog"), layer, path, bounds, QColor(40, 30, 45))


def paint_regiao_subaquatica(painter: QPainter, cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor):
    """Underwater región — blue-green tint wash, a handful of wavy bright
    streaks drifting across the shape (a cheap stand-in for caustics —
    real caustics are a projected light pattern, out of reach for a
    QPainter overlay with no light-projection model) plus small slow
    suspended-silt motes."""
    water = QColor(70, 170, 170)
    wash = QColor(water)
    wash.setAlpha(70)
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, wash)
    painter.restore()

    painter.save()
    painter.setClipPath(path)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    lines = 6
    steps = 10
    for i in range(lines):
        phase = i * 0.9
        base_y = bounds.top() + (i + 0.5) / lines * h
        pen = QPen(QColor(200, 255, 240, 40), 2.5)
        painter.setPen(pen)
        caustic_path = QPainterPath()
        for s in range(steps + 1):
            fx = bounds.left() + s / steps * w
            fy = base_y + math.sin(t * 0.5 + fx * 0.02 + phase) * h * 0.02
            if s == 0:
                caustic_path.moveTo(fx, fy)
            else:
                caustic_path.lineTo(fx, fy)
        painter.drawPath(caustic_path)
    painter.restore()

    _paint_particles(painter, _subcache(cache, "particles"), layer, path, bounds, QColor(220, 240, 235), {
        "kind": "silt", "style": "oscillate", "count": 22,
        "speed": 0.12, "amount": 0.05,
        "size_min": 0.8, "size_max": 1.8, "alpha": 110,
    })


# effect key (asset name in the "Effects" brush category) -> animated
# per-frame painter, same signature as paint_nevoa. BrushEffectsOverlay
# owns the per-layer cache dict passed into each call.
ANIMATED_EFFECTS: dict[str, Callable] = {
    "Névoa": paint_nevoa,
    "Poeira": paint_poeira,
    "Pólen": paint_polen,
    "Insetos": paint_insetos,
    "Cinzas": paint_cinzas,
    "Folhas": paint_folhas,
    "Chuva localizada": paint_chuva,
    "Garoa": paint_garoa,
    "Neve": paint_neve,
    "Tempestade de areia": paint_tempestade_areia,
    "Fumaça": paint_fumaca,
    "Gás tóxico": paint_gas_toxico,
    "Esporos": paint_esporos,
    "Cinzas vulcânicas": paint_cinzas_vulcanicas,
    "Região fria": paint_regiao_fria,
    "Região quente": paint_regiao_quente,
    "Região mágica": paint_regiao_magica,
    "Região radioativa": paint_regiao_radioativa,
    "Região de sonho": paint_regiao_sonho,
    "Região amaldiçoada": paint_regiao_amaldicoada,
    "Região subaquática": paint_regiao_subaquatica,
}

# Default tint per effect key — a região used to supply its own assigned
# color (RegionLayer.color); a brush-painted stroke has no such per-instance
# color of its own, so each effect gets one fixed, sensible default instead
# (same spirit as assets/effects_panel.py's _PREVIEW_COLORS). Most paint_*
# functions above already override this with a fixed tint internally when
# the effect's identity depends on a specific color (Pólen's gold, Gás
# tóxico's green, ...) — this dict only matters for the ones that actually
# use the color they're passed (Névoa, Poeira, Cinzas, Folhas, Chuva,
# Garoa, Neve, Tempestade de areia, Fumaça, Esporos, Região quente/
# subaquática/amaldiçoada).
EFFECT_COLORS: dict[str, QColor] = {
    "Névoa": QColor(210, 220, 230),
    "Poeira": QColor(200, 190, 160),
    "Insetos": QColor(255, 240, 180),
    "Cinzas": QColor(120, 110, 110),
    "Folhas": QColor(110, 150, 70),
    "Chuva localizada": QColor(150, 180, 210),
    "Garoa": QColor(170, 190, 210),
    "Neve": QColor(240, 245, 255),
    "Tempestade de areia": QColor(200, 170, 110),
    "Fumaça": QColor(120, 120, 120),
    "Esporos": QColor(150, 210, 160),
    "Cinzas vulcânicas": QColor(60, 55, 55),
    "Região fria": QColor(190, 220, 255),
    "Região quente": QColor(255, 150, 90),
    "Região mágica": QColor(160, 140, 255),
    "Região radioativa": QColor(160, 230, 90),
    "Região de sonho": QColor(230, 180, 255),
    "Região amaldiçoada": QColor(80, 60, 90),
    "Região subaquática": QColor(70, 170, 170),
}


def effect_color(key: str) -> QColor:
    return QColor(EFFECT_COLORS.get(key, QColor(200, 200, 200)))
