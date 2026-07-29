"""FBM (fractal Brownian motion) value-noise generation for fog rendering
(see GlobalLightingOverlay._paint_fog). True per-pixel Perlin/Simplex noise
in pure Python would be far too slow to regenerate every repaint tick, so
this leans on numpy for the octave math and Qt's own SmoothTransformation
image scaling as the (bilinear-equivalent) interpolation between each
octave's small random grid — no hand-written interpolation code, and it's
fast enough to run interactively. Callers are expected to cache the result
per light (see GlobalLightingOverlay._fog_cache) rather than regenerate it
every frame.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath


def fbm_density(width: int, height: int, seed: int, octaves: int = 4,
                 base_cells: int = 5, persistence: float = 0.55) -> np.ndarray:
    """(height, width) float32 array, values in [0, 1] — a fractal sum of
    `octaves` layers of value noise, each doubling frequency (grid
    resolution) and shrinking amplitude by `persistence`. This is what
    gives organic, continuous "masses" of density instead of a handful of
    separate circular puffs stamped next to each other."""
    width = max(2, int(width))
    height = max(2, int(height))
    rng = np.random.default_rng(seed)
    acc = np.zeros((height, width), dtype=np.float32)
    amp = 1.0
    total = 0.0
    cells = max(2, base_cells)
    for _ in range(max(1, octaves)):
        gw = gh = max(2, int(cells))
        grid = (rng.random((gh, gw)) * 255).astype(np.uint8)
        grid = np.ascontiguousarray(grid)
        small_img = QImage(grid.data, gw, gh, gw, QImage.Format.Format_Grayscale8)
        scaled = small_img.scaled(
            width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ).convertToFormat(QImage.Format.Format_Grayscale8)
        layer = np.frombuffer(scaled.bits(), dtype=np.uint8, count=width * height)
        layer = layer.reshape(height, width).astype(np.float32) / 255.0
        acc += layer * amp
        total += amp
        amp *= persistence
        cells *= 2
    acc /= max(1e-6, total)
    return acc


def _edge_fade_mask(width: int, height: int, start: float = 0.55, power: float = 2.2) -> np.ndarray:
    """Falloff from the image center, 1.0 out to `start` (fraction of the
    distance to the NEAREST edge) then curving down to 0.0 right at every
    edge — multiplied into alpha so the texture's own square boundary
    always fades to fully transparent before it's reached, no matter how
    high density/intensity/alpha_scale push everything else. Uses
    Chebyshev (max-of-axes) distance rather than Euclidean/radial — a
    radial falloff normalized by the CORNER distance only fully fades the
    corners, leaving the flat edge midpoints still clearly visible (still
    a hard rectangle, just with rounded corners); Chebyshev distance
    reaches 1.0 uniformly along all four edges, not just the corners."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    nx = np.abs(xx - cx) / max(1e-6, cx)
    ny = np.abs(yy - cy) / max(1e-6, cy)
    dist = np.maximum(nx, ny)
    t = np.clip((dist - start) / max(1e-6, 1.0 - start), 0.0, 1.0)
    return (1.0 - t ** power).astype(np.float32)


def density_to_qimage(density: np.ndarray, near_color: QColor, far_color: QColor,
                       alpha_gamma: float = 2.0, alpha_scale: float = 1.0) -> QImage:
    """Turns a raw density field into a premultiplied ARGB32 image — alpha
    follows density**alpha_gamma (thin wisps stay translucent, dense
    clumps read solid, instead of one flat opacity everywhere) times a
    radial edge-fade mask (see _edge_fade_mask, always fully transparent
    at the image's own boundary), and color interpolates per-pixel between
    `far_color` (low density — reads as a "shadowed"/cooler patch) and
    `near_color` (high density — catches more of the ambient/light tint)."""
    h, w = density.shape
    d = np.clip(density, 0.0, 1.0)
    alpha = np.clip((d ** alpha_gamma) * alpha_scale, 0.0, 1.0) * _edge_fade_mask(w, h)

    near = np.array([near_color.red(), near_color.green(), near_color.blue()], dtype=np.float32)
    far = np.array([far_color.red(), far_color.green(), far_color.blue()], dtype=np.float32)
    t = d[..., None]
    rgb = far * (1 - t) + near * t

    out = np.empty((h, w, 4), dtype=np.uint8)
    a = alpha[..., None]
    premult = np.clip(rgb * a, 0, 255).astype(np.uint8)
    out[..., 0] = premult[..., 2]  # B
    out[..., 1] = premult[..., 1]  # G
    out[..., 2] = premult[..., 0]  # R
    out[..., 3] = (alpha * 255).astype(np.uint8)
    out = np.ascontiguousarray(out)
    img = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied)
    return img.copy()  # detach from `out` before it's garbage-collected


def _box_blur_1d(arr: np.ndarray, radius_px: int, axis: int) -> np.ndarray:
    """Box blur along one axis via a cumulative-sum sliding window — O(n)
    per row/column regardless of `radius_px`, unlike a naive convolution.
    Edge-padded (not wrapped), so it doesn't darken/lighten near the
    array's own boundary."""
    if radius_px <= 0:
        return arr
    pad = [(0, 0)] * arr.ndim
    pad[axis] = (radius_px, radius_px)
    padded = np.pad(arr, pad, mode="edge")
    cs = np.cumsum(padded, axis=axis, dtype=np.float32)
    cs = np.insert(cs, 0, 0, axis=axis)
    n = arr.shape[axis]
    hi = np.take(cs, np.arange(n) + 2 * radius_px + 1, axis=axis)
    lo = np.take(cs, np.arange(n), axis=axis)
    return (hi - lo) / (2 * radius_px + 1)


def _box_blur(arr: np.ndarray, radius_px: int, passes: int = 3) -> np.ndarray:
    """Three box-blur passes approximate a Gaussian blur closely enough
    for a soft edge mask, and are much cheaper than a true Gaussian kernel
    convolution at the radii fog needs (10-20px)."""
    for _ in range(max(1, passes)):
        arr = _box_blur_1d(arr, radius_px, axis=0)
        arr = _box_blur_1d(arr, radius_px, axis=1)
    return arr


def path_to_blurred_mask(path: QPainterPath, size: int, blur_px: int) -> QImage:
    """Rasterizes `path` (in a coordinate system centered on the image,
    i.e. path coordinates run roughly -size/2..size/2) as opaque white,
    then blurs the result — used to turn a fog blob's own hard vector
    outline into a soft-edged alpha mask (see GlobalLightingOverlay.
    _paint_fog), applied via CompositionMode_DestinationIn instead of a
    crisp QPainter clip. A vector clip's edge is anti-aliased over ~1px;
    this fades it over `blur_px` instead, which is what actually reads as
    "the fog thins out" rather than "the fog has a boundary line"."""
    raster = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    raster.fill(0)
    p = QPainter(raster)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(size / 2, size / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 255))
    p.drawPath(path)
    p.end()

    alpha = np.frombuffer(raster.bits(), dtype=np.uint8, count=size * size * 4)
    alpha = alpha.reshape(size, size, 4)[..., 3].astype(np.float32)
    blurred = np.clip(_box_blur(alpha, blur_px), 0, 255).astype(np.uint8)

    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., 0] = 255
    out[..., 1] = 255
    out[..., 2] = 255
    out[..., 3] = blurred
    out = np.ascontiguousarray(out)
    img = QImage(out.data, size, size, size * 4, QImage.Format.Format_ARGB32)
    return img.copy()
