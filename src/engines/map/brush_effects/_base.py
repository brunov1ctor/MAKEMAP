"""Helpers compartilhados pelos módulos de efeitos do pincel."""

from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QTransform

from src.engines.fog_noise import density_to_qimage, fbm_density, path_to_blurred_mask

_FOG_TEX_SIZE = 160
_FOG_BREATHE_PERIOD = 40.0
_FOG_LAYERS = (
    (1.6, 0.14, 0.40),
    (1.15, 0.26, 0.60),
    (0.85, 0.50, 0.85),
)
_FOG_DRIFT_FRACTION = 0.06
_FOG_BLUR_PX = 10
_FOG_BUF_MARGIN = 24


def _center_path(path: QPainterPath, bounds: QRectF) -> QPainterPath:
    return QTransform().translate(-bounds.center().x(), -bounds.center().y()).map(path)


def _fog_textures(cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor) -> dict:
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
        "buf": None,
    }
    cache[id(layer)] = entry
    return entry


def _particle_seeds(cache: dict, layer, kind: str, count: int) -> dict:
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
        "clump": _clump_field(rng, count),
    }
    cache[id(layer)] = entry
    return entry


def _clump_field(rng: np.random.Generator, count: int) -> np.ndarray:
    """Static per-particle weight in [~0.15, 1.0] so a uniform scatter reads
    as loose clusters instead of an even spray, without any per-frame cost —
    computed once alongside the other seed arrays and just multiplied into
    alpha at draw time (see motion["clump"] in _paint_particles)."""
    n_centers = max(1, count // 6)
    centers_x = rng.random(n_centers).astype(np.float32)
    centers_y = rng.random(n_centers).astype(np.float32)
    x0 = rng.random(count).astype(np.float32)
    y0 = rng.random(count).astype(np.float32)
    d2 = np.min(
        (x0[:, None] - centers_x[None, :]) ** 2 + (y0[:, None] - centers_y[None, :]) ** 2, axis=1
    )
    weight = np.exp(-d2 * 18.0)
    return (0.15 + 0.85 * weight).astype(np.float32)


def _wind_sample(layer, t: float, *, period: float = 5.0, gust_period: float = 1.7,
                  salt: int = 0) -> float:
    """Signed value roughly in [-1, 1], spending most of its time near 0 and
    occasionally spiking into an occasional gust — a sway sin() alone is
    always moving; this reads as calm-with-gusts instead. Phase is derived
    from the layer identity so different strokes of the same effect don't
    all gust in lockstep."""
    phase = ((id(layer) ^ salt) & 0xFFFF) / 0xFFFF * 2 * math.pi
    base = math.sin(t * 2 * math.pi / period + phase)
    gust = math.sin(t * 2 * math.pi / gust_period + phase * 1.7)
    raw = base * 0.5 + gust * 0.5
    return math.copysign(abs(raw) ** 3, raw)


def _flicker_sample(layer, t: float, *, period: float = 3.0, salt: int = 0) -> float:
    """Value in [0, 1] for post-process scintillation/flicker — same phase
    trick as _wind_sample so it stays deterministic per layer without a
    cache entry."""
    phase = ((id(layer) ^ salt) & 0xFFFF) / 0xFFFF * 2 * math.pi
    return (math.sin(t * 2 * math.pi / period + phase) + 1) / 2


def _paint_particles(painter: QPainter, cache: dict, layer, path: QPainterPath,
                     bounds: QRectF, color: QColor, motion: dict):
    seeds = _particle_seeds(cache, layer, motion["kind"], motion["count"])
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    base_color = QColor(color)

    wind_cfg = motion.get("wind")
    gust = 0.0
    lateral_gust = 0.0
    if wind_cfg is not None:
        gust = _wind_sample(
            layer, t, period=wind_cfg.get("period", 5.0), gust_period=wind_cfg.get("gust_period", 1.7),
            salt=wind_cfg.get("salt", 0),
        )
        lateral_gust = gust * wind_cfg.get("lateral", 0.0)

    pulse_mult = 1.0
    pulse_cfg = motion.get("pulse")
    if pulse_cfg is not None:
        f = _flicker_sample(layer, t, period=pulse_cfg.get("period", 3.0), salt=pulse_cfg.get("salt", 0))
        lo, hi = pulse_cfg.get("range", (0.5, 1.0))
        pulse_mult = lo + (hi - lo) * f

    for i in range(motion["count"]):
        speed = motion["speed"] * seeds["speed_jitter"][i]
        if wind_cfg is not None:
            speed *= 1.0 + gust * wind_cfg.get("speed_mult", 0.0) * wind_cfg.get("wind_scale", 1.0)
        phase = seeds["phase"][i]
        if motion["style"] == "oscillate":
            nx = seeds["x0"][i] + math.sin(t * speed + phase) * motion["amount"] + lateral_gust
            ny = seeds["y0"][i] + math.cos(t * speed * 0.8 + phase) * motion["amount"]
            alpha = motion["alpha"]
        elif motion["style"] == "insect":
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
        else:
            if motion.get("axis", "vertical") == "vertical":
                ny = (seeds["y0"][i] + motion["dir"] * speed * t) % 1.0
                nx = (seeds["x0"][i] + math.sin(t * motion["sway_speed"] + phase) * motion["sway"] + lateral_gust) % 1.0
                edge = min(ny, 1.0 - ny) / motion["fade_band"]
            else:
                nx = (seeds["x0"][i] + motion["dir"] * speed * t) % 1.0
                ny = (seeds["y0"][i] + math.sin(t * motion["sway_speed"] + phase) * motion["sway"] + lateral_gust) % 1.0
                edge = min(nx, 1.0 - nx) / motion["fade_band"]
            alpha = motion["alpha"] * max(0.0, min(1.0, edge))

        if motion.get("clump"):
            alpha *= seeds["clump"][i]
        alpha *= pulse_mult

        alpha_i = int(alpha)
        if alpha_i <= 0:
            continue
        x = bounds.left() + max(0.0, min(1.0, nx)) * w
        y = bounds.top() + max(0.0, min(1.0, ny)) * h
        size = motion["size_min"] + seeds["size_jitter"][i] * (motion["size_max"] - motion["size_min"])

        particle_color = QColor(base_color)
        particle_color.setAlpha(alpha_i)
        if motion["kind"] in ("rain", "drizzle"):
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
            if motion["kind"] == "leaf" or motion.get("rotate"):
                aspect_x, aspect_y = motion.get("rotate_aspect", (1.0, 0.55))
                painter.save()
                painter.translate(x, y)
                spin = seeds["rot0"][i] + t * motion.get("rot_speed", 30.0) * seeds["spin_dir"][i]
                painter.rotate(spin)
                painter.drawEllipse(QRectF(-size * aspect_x, -size * aspect_y, size * 2 * aspect_x, size * 2 * aspect_y))
                painter.restore()
            elif motion.get("glow"):
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
    return cache.setdefault(name, {})


def _paint_particles_layered(painter: QPainter, cache: dict, layer, path: QPainterPath,
                              bounds: QRectF, color: QColor, base_motion: dict, depths: list[dict]):
    """Draws several independent particle passes (e.g. far/mid/near depth
    bands) from one base config, each with its own seeds and cache slot so
    they don't share phase/position — that's what reads as depth instead of
    one denser flat layer. Each `depths` entry may set `count`, `speed_mult`,
    `size_mult`, `alpha_mult`, `wind_scale`, or any raw motion key override."""
    base_kind = base_motion["kind"]
    for cfg in depths:
        name = cfg["name"]
        motion = dict(base_motion)
        motion["kind"] = f"{base_kind}_{name}"
        depth_color = cfg.get("color", color)
        if "count" in cfg:
            motion["count"] = cfg["count"]
        if "speed_mult" in cfg:
            motion["speed"] = motion["speed"] * cfg["speed_mult"]
        if "size_mult" in cfg:
            motion["size_min"] = motion["size_min"] * cfg["size_mult"]
            motion["size_max"] = motion["size_max"] * cfg["size_mult"]
        if "alpha_mult" in cfg:
            motion["alpha"] = motion["alpha"] * cfg["alpha_mult"]
        if "wind_scale" in cfg and motion.get("wind") is not None:
            motion["wind"] = {**motion["wind"], "wind_scale": cfg["wind_scale"]}
        _RESERVED_DEPTH_KEYS = ("name", "count", "speed_mult", "size_mult", "alpha_mult", "wind_scale", "color")
        for key, value in cfg.items():
            if key in _RESERVED_DEPTH_KEYS:
                continue
            motion[key] = value
        _paint_particles(painter, _subcache(cache, f"depth_{name}"), layer, path, bounds, depth_color, motion)


def _ground_seeds(cache: dict, layer, kind: str, count: int) -> dict:
    entry = cache.get(id(layer))
    if entry is not None and entry.get("kind") == kind and entry.get("count") == count:
        return entry
    rng = np.random.default_rng((id(layer) & 0xFFFFFFFF) ^ hash(kind) & 0xFFFFFFFF ^ 0x9E3779B9)
    entry = {
        "kind": kind,
        "count": count,
        "x0": rng.random(count).astype(np.float32),
        "phase": rng.random(count).astype(np.float32) * 2 * math.pi,
        "size_jitter": rng.random(count).astype(np.float32),
    }
    cache[id(layer)] = entry
    return entry


def _paint_ground_marks(painter: QPainter, cache: dict, layer, path: QPainterPath,
                         bounds: QRectF, color: QColor, config: dict):
    """Marks near the stroke's bottom edge — rain splashes (born, grow,
    vanish, cyclically) or snow/ash "pile" streaks (near-static, gently
    wind-shifted) — the closest thing to ground contact these effects have
    without reading the terrain layer underneath."""
    count = config["count"]
    kind = config["kind"]
    style = config["style"]
    period = config.get("period", 1.0)
    seeds = _ground_seeds(cache, layer, kind, count)
    t = time.monotonic()
    w, h = bounds.width(), bounds.height()
    size_min, size_max = config["size_min"], config["size_max"]
    base_alpha = config["alpha"]

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    base_color = QColor(color)

    for i in range(count):
        x0 = seeds["x0"][i]
        phase = seeds["phase"][i]
        y = bounds.top() + h * (0.94 + 0.05 * seeds["size_jitter"][i])
        x = bounds.left() + x0 * w

        if style == "splash":
            local_t = ((t / period) + phase / (2 * math.pi)) % 1.0
            if local_t > 0.6:
                continue
            grow = local_t / 0.6
            radius = (size_min + (size_max - size_min) * seeds["size_jitter"][i]) * grow
            alpha = int(base_alpha * (1.0 - grow))
            if alpha <= 0:
                continue
            splash_color = QColor(base_color)
            splash_color.setAlpha(alpha)
            painter.setPen(QPen(splash_color, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(x, y), radius, radius * 0.4)
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            drift = _wind_sample(layer, t, salt=i + 1) * w * 0.01
            radius = size_min + (size_max - size_min) * seeds["size_jitter"][i]
            pile_color = QColor(base_color)
            pile_color.setAlpha(base_alpha)
            painter.setBrush(pile_color)
            painter.drawEllipse(QRectF(x - radius + drift, y - radius * 0.35, radius * 2, radius * 0.7))

    painter.restore()


def _paint_wash(painter: QPainter, layer, path: QPainterPath, bounds: QRectF, color: QColor, *,
                 alpha: int, flicker: dict | None = None, t: float | None = None):
    """Shared version of the fillRect-under-clip wash pattern already used
    ad hoc (see tempestade_areia.py) — with an optional flicker/scintillation
    modulation on top of the flat alpha."""
    if t is None:
        t = time.monotonic()
    a = alpha
    if flicker is not None:
        f = _flicker_sample(layer, t, period=flicker.get("period", 3.0), salt=flicker.get("salt", 0))
        lo, hi = flicker.get("range", (0.6, 1.0))
        a = int(alpha * (lo + (hi - lo) * f))
    wash_color = QColor(color)
    wash_color.setAlpha(max(0, min(255, a)))
    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, wash_color)
    painter.restore()


def _volume_textures(cache: dict, layer, path: QPainterPath, bounds: QRectF, color: QColor, *,
                      cache_key: str, tex_size: int = 160, base_cells: int = 4,
                      alpha_gamma: float = 1.8, alpha_scale: float = 0.8, blur_px: int = 10,
                      buf_margin: int = 24, breathe_period: float = 40.0, seed_salt: int = 0) -> dict:
    """Generalized version of _fog_textures — same FBM/cross-fade/mask
    technique, but with tunable constants instead of fog's fixed ones, so a
    second effect (e.g. smoke) can reuse the machinery with its own look
    without touching _fog_textures/paint_nevoa."""
    sub = _subcache(cache, cache_key)
    key = (round(bounds.width() / 20) * 20, round(bounds.height() / 20) * 20, color.name())
    entry = sub.get(id(layer))
    if entry is not None and entry.get("key") == key:
        return entry

    seed = (id(layer) & 0xFFFFFFFF) ^ seed_salt
    near_color = color.lighter(140)
    far_color = color.darker(150)
    density_a = fbm_density(tex_size, tex_size, seed, base_cells=base_cells)
    density_b = fbm_density(tex_size, tex_size, seed ^ 0x5EED, base_cells=base_cells)
    max_scale = 1.6
    buf_size = int(max(bounds.width(), bounds.height()) * max_scale) + buf_margin * 2
    entry = {
        "key": key,
        "img_a": density_to_qimage(density_a, near_color, far_color, alpha_gamma=alpha_gamma, alpha_scale=alpha_scale),
        "img_b": density_to_qimage(density_b, near_color, far_color, alpha_gamma=alpha_gamma, alpha_scale=alpha_scale),
        "phase_offset": (seed % 1000) / 1000.0 * breathe_period,
        "buf_size": buf_size,
        "mask": path_to_blurred_mask(_center_path(path, bounds), buf_size, blur_px),
        "buf": None,
    }
    sub[id(layer)] = entry
    return entry


def _paint_volume(painter: QPainter, entry: dict, bounds: QRectF, t: float, *,
                   layers: tuple, drift_fraction: float = 0.06, breathe_period: float = 40.0,
                   swirl_speed: float = 0.0, growth_period: float = 0.0,
                   growth_range: tuple[float, float] = (0.85, 1.15)):
    """Paints an entry built by _volume_textures — parallax drift + breathing
    cross-fade like paint_nevoa, plus optional swirl (per-layer rotation)
    and growth/dissipation (slow scale+opacity envelope over the same two
    cached textures, so smoke can pulse without regenerating FBM)."""
    tt = t + entry["phase_offset"]
    mix = (math.sin(2 * math.pi * tt / breathe_period) + 1) / 2

    envelope = 1.0
    if growth_period > 0:
        cycle = (tt % growth_period) / growth_period
        tri = 1.0 - abs(cycle * 2 - 1)
        lo, hi = growth_range
        envelope = lo + (hi - lo) * tri

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
    for draw_scale, drift_speed, alpha_mult in layers:
        size = diag * draw_scale * envelope
        dx = math.sin(tt * drift_speed) * diag * drift_fraction
        dy = math.cos(tt * drift_speed * 0.8) * diag * drift_fraction
        bp.save()
        bp.translate(dx, dy)
        if swirl_speed:
            bp.rotate(tt * swirl_speed * 57.29577951308232 * drift_speed)
        target = QRectF(-size / 2, -size / 2, size, size)
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * (1 - mix) * envelope)))
        bp.drawImage(target, entry["img_a"])
        bp.setOpacity(max(0.0, min(1.0, alpha_mult * mix * envelope)))
        bp.drawImage(target, entry["img_b"])
        bp.restore()
    bp.setOpacity(1.0)
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    bp.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), entry["mask"])
    bp.end()

    painter.save()
    painter.translate(bounds.center())
    painter.drawImage(QRectF(-buf_size / 2, -buf_size / 2, buf_size, buf_size), buf)
    painter.restore()


def _paint_glow_edge(painter: QPainter, layer, path: QPainterPath, bounds: QRectF, color: QColor, *,
                      alpha: int, edge: str = "bottom", spread: float = 0.4,
                      flicker: dict | None = None, t: float | None = None):
    """Soft directional glow fading in from one side of the stroke (embers'
    glow from below, a curse's dim purple undertone) — a QLinearGradient
    clipped to the stroke path, cheaper than a radial volume pass and
    doesn't need its own FBM texture."""
    if t is None:
        t = time.monotonic()
    a = alpha
    if flicker is not None:
        f = _flicker_sample(layer, t, period=flicker.get("period", 3.0), salt=flicker.get("salt", 0))
        lo, hi = flicker.get("range", (0.6, 1.0))
        a = int(alpha * (lo + (hi - lo) * f))
    a = max(0, min(255, a))

    x0, y0 = bounds.left(), bounds.top()
    x1, y1 = bounds.right(), bounds.bottom()
    if edge == "bottom":
        grad = QLinearGradient(0, y0, 0, y1)
        near_stop = 1.0
    elif edge == "top":
        grad = QLinearGradient(0, y0, 0, y1)
        near_stop = 0.0
    elif edge == "right":
        grad = QLinearGradient(x0, 0, x1, 0)
        near_stop = 1.0
    else:
        grad = QLinearGradient(x0, 0, x1, 0)
        near_stop = 0.0

    far_stop = 1.0 - near_stop if near_stop in (0.0, 1.0) else 0.5
    stop_start = near_stop + (far_stop - near_stop) * (1.0 - spread)
    glow_color = QColor(color)
    glow_color.setAlpha(a)
    transparent = QColor(color)
    transparent.setAlpha(0)
    grad.setColorAt(near_stop, glow_color)
    grad.setColorAt(max(0.0, min(1.0, stop_start)), transparent)

    painter.save()
    painter.setClipPath(path)
    painter.fillRect(bounds, grad)
    painter.restore()


def _nearest_light_bias(cache: dict, bounds: QRectF) -> tuple[float, float] | None:
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
