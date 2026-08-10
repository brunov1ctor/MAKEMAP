"""Shared lighting math — occluder shadow projection, spot-cone shape, and
falloff-gradient computation. Extracted from the old LightItem.paint() so
both the on-canvas light gizmo (light_item.py, just draws a selection
outline hint) and the whole-map GlobalLightingOverlay (lighting_overlay.py,
does the actual illumination) compute identical shadows/falloff instead of
duplicating the math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPolygonF, QRadialGradient

from src.layouts.panels.spawn.portrait_compose import FRONT_TOKEN_SCALE


def shadow_quad(corners: list[QPointF], radius: float, length_scale: float = 1.0) -> QPolygonF | None:
    """corners: an occluder's 4 corners in the light's local space (light at
    origin). Returns the quad silhouette-shadow polygon cast away from the
    origin out to `radius` — the closer the occluder sits to the origin, the
    more of `radius` is left to project across, so the shadow is naturally
    longer for occluders near the light and shorter for occluders near the
    edge of its reach ("proximity" shadow length). Returns None if the
    corners are degenerate (occluder sits exactly on the light).

    `length_scale` (0..1) shortens how much of that remaining distance the
    shadow actually covers — 1.0 (assets) reaches all the way to `radius`
    same as before; a mob stamp scales this by its altura (see
    occluder_rects) so a taller mob casts a longer shadow than a short one
    instead of every mob throwing the same full-length shadow regardless
    of size."""
    angles = [math.atan2(c.y(), c.x()) for c in corners]
    # Circular mean avoids picking the wrong "extremes" when the occluder
    # straddles the atan2 +-pi discontinuity.
    mean_ang = math.atan2(
        sum(math.sin(a) for a in angles) / len(angles),
        sum(math.cos(a) for a in angles) / len(angles),
    )

    def rel(a: float) -> float:
        d = a - mean_ang
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        return d

    rels = [rel(a) for a in angles]
    c1 = corners[rels.index(min(rels))]
    c2 = corners[rels.index(max(rels))]

    def extend(c: QPointF) -> QPointF | None:
        d = math.hypot(c.x(), c.y())
        if d < 1e-6:
            return None
        target_d = d + (radius - d) * length_scale
        scale = target_d / d
        return QPointF(c.x() * scale, c.y() * scale)

    f1, f2 = extend(c1), extend(c2)
    if f1 is None or f2 is None:
        return None
    return QPolygonF([c1, f1, f2, c2])


def shadow_from_circle(center: QPointF, occluder_radius: float, light_radius: float,
                        length_scale: float = 1.0) -> tuple[QPainterPath, QPointF, QPointF] | None:
    """Shadow cast by a CIRCULAR occluder (a mob stamp — see occluder_rects)
    in the light's local space (light at origin). Unlike shadow_quad (built
    for a rectangular occluder's 4 corners), this traces the actual tangent
    lines from the light to the circle plus the circle's own disc, so the
    shadow's near edge follows the mob's round silhouette instead of
    showing the flat corner of its (invisible) bounding square — that
    mismatch was the whole complaint driving this function's existence.

    Returns (path, near, far) — `near`/`far` are the shadow's own start/end
    points along the light's axis (the tangent chord's midpoint and the far
    arc's midpoint), used to build the near-opaque-to-far-transparent
    penumbra gradient (see GlobalLightingOverlay._paint_shadows) instead of
    treating the whole shadow as one flat opacity. Returns None if the
    light sits inside/on the circle (degenerate)."""
    d = math.hypot(center.x(), center.y())
    if d <= occluder_radius:
        return None

    theta = math.atan2(center.y(), center.x())
    alpha = math.asin(min(1.0, occluder_radius / d))
    tangent_dist = math.sqrt(d * d - occluder_radius * occluder_radius)
    t1 = QPointF(tangent_dist * math.cos(theta + alpha), tangent_dist * math.sin(theta + alpha))
    t2 = QPointF(tangent_dist * math.cos(theta - alpha), tangent_dist * math.sin(theta - alpha))

    target_dist = tangent_dist + (light_radius - tangent_dist) * length_scale

    def extend(t: QPointF) -> QPointF:
        scale = target_dist / tangent_dist
        return QPointF(t.x() * scale, t.y() * scale)

    f1, f2 = extend(t1), extend(t2)

    # f1 -> f2 is capped with an ARC (same radius as the light's own outer
    # boundary at this depth) instead of a straight line — a flat chord
    # there read as an odd flat/rectangular tip pasted onto an otherwise
    # round-occluder shadow, especially at short length_scale where the
    # cap ends up wide relative to how far it's reached.
    wedge = QPainterPath()
    wedge.moveTo(t1)
    wedge.lineTo(f1)
    start_deg = -math.degrees(theta + alpha)
    sweep_deg = 2 * math.degrees(alpha)
    wedge.arcTo(QRectF(-target_dist, -target_dist, target_dist * 2, target_dist * 2), start_deg, sweep_deg)
    wedge.lineTo(t2)
    wedge.closeSubpath()

    # The wedge alone only covers the outward-facing half of the disc (the
    # tangent chord cuts across it) — union with the full disc so the mob's
    # own footprint is included too, not just the umbra beyond it.
    disc = QPainterPath()
    disc.addEllipse(center, occluder_radius, occluder_radius)
    near = (t1 + t2) / 2
    far = (f1 + f2) / 2
    return disc.united(wedge), near, far


# A mob/npc stamp reaches this altura (meters, see MobEditPanel/NPCEditPanel's
# Altura field) before its shadow gets the same full "to the edge of the
# light" reach a large-enough asset can also have — shorter tokens cast
# proportionally shorter shadows, 0 altura casts none at all (see
# occluder_rects/shadow_quad's length_scale).
_MOB_SHADOW_REFERENCE_HEIGHT = 3.0

# An asset stamp (house, rock, tree — anything BrushTool.place_stamp_item
# tagged item_type == 'asset') reaches this scene-px size (its longest
# sceneBoundingRect side — matches how the brush's own "Size" slider is
# already used as a scene-px diameter elsewhere, see BrushTool.size/
# ObjectStamper.on_stamp) before its shadow gets the same full "to the edge
# of the light" reach a big prop always had — a pebble stamped small casts
# a proportionally short shadow instead of the same full-length wedge a
# house gets, same idea as _MOB_SHADOW_REFERENCE_HEIGHT.
_ASSET_SHADOW_REFERENCE_SIZE = 256.0


def occluder_rects(scene, origin: QPointF, radius: float, exclude=None):
    """Every occluder within `radius` of `origin`, as ("rect"|"circle",
    geometry, length_scale) — an asset stamp yields a scene-space QRectF
    (shaped by shadow_quad), a mob or npc stamp (item_type ==
    'mob_spawn'/'npc_spawn') yields a (center, radius) circle instead —
    round tokens, not boxes, so their shadow is built by shadow_from_circle
    to hug the actual silhouette instead of an invisible bounding square's
    flat corner. An asset's length_scale is derived from its bounding
    rect's longest side (see _ASSET_SHADOW_REFERENCE_SIZE); a mob/npc's
    from its altura (see _MOB_SHADOW_REFERENCE_HEIGHT) — altura == 0 (the
    default) yields nothing, matching how mobs/npcs cast no shadow at all
    before this existed."""
    if scene is None:
        return
    search = QRectF(origin.x() - radius, origin.y() - radius, radius * 2, radius * 2)
    for other in scene.items(search):
        if other is exclude:
            continue
        data = other.data(0)
        if not isinstance(data, dict):
            continue
        item_type = data.get("item_type")
        # A brush-painted animated effect layer (Névoa, ...) is ALSO
        # tagged item_type "asset" (see BrushTool._get_or_create_
        # effect_layer) but it's a huge, mostly-transparent mask, not a
        # real placed object — casting a shadow the size of its whole
        # (2048px+) bounding rect would black out every light near it.
        if item_type == "asset" and not data.get("effect_key"):
            srect = other.sceneBoundingRect()
            length_scale = min(1.0, max(srect.width(), srect.height()) / _ASSET_SHADOW_REFERENCE_SIZE)
            yield "rect", srect, length_scale
        elif item_type in ("mob_spawn", "npc_spawn"):
            height = data.get("height") or 0
            if height <= 0:
                continue
            length_scale = min(1.0, height / _MOB_SHADOW_REFERENCE_HEIGHT)
            # Visible circle diameter, NOT other.sceneBoundingRect() — that's
            # the full composed-portrait canvas (item_type == 'mob_spawn's
            # "size"), padded well past the actual token (see
            # portrait_compose.FRONT_TOKEN_SCALE: only 60% of it is drawn,
            # room for the dimmed group-fan behind it).
            size = data.get("size") or 0
            if size <= 0:
                continue
            occluder_radius = size * FRONT_TOKEN_SCALE / 2
            yield "circle", (other.scenePos(), occluder_radius), length_scale


def cone_path(radius: float, direction_deg: float, cone_angle_deg: float) -> QPainterPath:
    """Pie-slice in LOCAL coordinates (apex at (0, 0)) aimed at
    `direction_deg`, `cone_angle_deg` wide — the lit shape of a spot light."""
    path = QPainterPath()
    path.moveTo(0, 0)
    half = max(1.0, cone_angle_deg) / 2.0
    path.arcTo(QRectF(-radius, -radius, radius * 2, radius * 2), -direction_deg - half, cone_angle_deg)
    path.closeSubpath()
    return path




def compute_lit_path(
    scene, origin: QPointF, radius: float, *, light_type: str = "point",
    direction_deg: float = 0.0, cone_angle_deg: float = 45.0,
    exclude=None,
) -> QPainterPath:
    """Base lit-area path in LOCAL coordinates (light at (0, 0)) — a cone
    for spot, or a full disc for point/sky.

    Does NOT cut occluder shadows into this anymore — shadows are painted
    as their own translucent penumbra layer on top instead of a hard hole
    punched out of the light (see compute_shadows +
    GlobalLightingOverlay._paint_shadows), so a shadowed patch still reads
    as "in shadow", not "no light data ever reached here". `scene`/
    `exclude` are unused now (shadows moved to compute_shadows) but kept so
    existing call sites don't need updating."""
    if light_type == "spot":
        return cone_path(radius, direction_deg, cone_angle_deg)
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), radius, radius)
    return path


@dataclass
class ShadowShape:
    """One occluder's shadow, in the light's local coordinates (light at
    origin) — `near`/`far` are points along the shadow's own length axis
    (not necessarily through the origin) used to build the near-opaque-to-
    far-transparent penumbra gradient in
    GlobalLightingOverlay._paint_shadows."""
    path: QPainterPath
    near: QPointF
    far: QPointF


def compute_shadows(scene, origin: QPointF, radius: float, exclude=None) -> list[ShadowShape]:
    """Every occluder shadow (asset or mob) within `radius` of `origin`, in
    the light's local coordinates — paired with compute_lit_path's base
    shape (via a shared clip) by the caller, not merged into it here."""
    shadows: list[ShadowShape] = []
    for kind, geometry, length_scale in occluder_rects(scene, origin, radius, exclude=exclude):
        if kind == "circle":
            center, occluder_radius = geometry
            local_center = QPointF(center.x() - origin.x(), center.y() - origin.y())
            if math.hypot(local_center.x(), local_center.y()) - occluder_radius > radius:
                continue
            result = shadow_from_circle(local_center, occluder_radius, radius, length_scale)
            if result is None:
                continue
            shadow_path, near, far = result
        else:
            srect = geometry
            corners = [
                QPointF(srect.left() - origin.x(), srect.top() - origin.y()),
                QPointF(srect.right() - origin.x(), srect.top() - origin.y()),
                QPointF(srect.right() - origin.x(), srect.bottom() - origin.y()),
                QPointF(srect.left() - origin.x(), srect.bottom() - origin.y()),
            ]
            if min(math.hypot(c.x(), c.y()) for c in corners) > radius:
                continue
            quad = shadow_quad(corners, radius, length_scale)
            if quad is None:
                continue
            shadow_path = QPainterPath()
            shadow_path.addPolygon(quad)
            shadow_path.closeSubpath()
            near = (quad[0] + quad[3]) / 2  # c1, c2 — the occluder-facing edge
            far = (quad[1] + quad[2]) / 2  # f1, f2 — the far, radius-facing edge
        shadows.append(ShadowShape(shadow_path, near, far))
    return shadows


# Falloff/penumbra alpha profiles are built from these (t=0 near/center,
# t=1 far/edge) instead of a handful of linear-interpolated stops — Qt
# gradients only interpolate LINEARLY between adjacent stops, so a visibly
# curved (not just piecewise-linear) falloff needs enough stops to
# approximate the curve, not a smarter interpolation mode.
_GRADIENT_STOPS = 16

# gamma range mapped from LightProperties.falloff's 0-100 UI slider (see
# falloff_gamma) — 4.0 (falloff=0) is the old hardcoded exponent's harsher
# cousin (alpha ~ (1-t)^4 stays near-peak for most of the radius, then
# drops steeply right at the edge — a small, hot-looking core); 0.8
# (falloff=100) is close to a straight linear ramp, no hot core at all.
_FALLOFF_GAMMA_MAX = 4.0  # falloff=0 (concentrated)
_FALLOFF_GAMMA_MIN = 0.8  # falloff=100 (diffuse)


def falloff_gamma(falloff: float) -> float:
    """Maps LightProperties.falloff (0=concentrated..100=diffuse) to the
    gamma exponent falloff_gradient's power-curve alpha ramp uses."""
    t = max(0.0, min(100.0, falloff)) / 100.0
    return _FALLOFF_GAMMA_MAX - t * (_FALLOFF_GAMMA_MAX - _FALLOFF_GAMMA_MIN)


def falloff_gradient(color: QColor, intensity: float, radius: float, gamma: float = 2.4) -> QRadialGradient:
    """Power-curve falloff (alpha ~ (1-t)^gamma) instead of the old 4-stop
    linear ramp — a light's edge used to cut off in a visibly straight
    taper; this keeps alpha near-peak through the middle of the radius and
    only drops steeply near the very edge, reading as a much softer,
    natural glow."""
    alpha_peak = max(0, min(255, int(230 * intensity)))
    grad = QRadialGradient(0, 0, radius)
    for i in range(_GRADIENT_STOPS + 1):
        t = i / _GRADIENT_STOPS
        c = QColor(color)
        c.setAlpha(int(alpha_peak * (1.0 - t) ** gamma))
        grad.setColorAt(t, c)
    return grad


def shadow_gradient(near: QPointF, far: QPointF, max_alpha: int = 140,
                     shadow_color: QColor | None = None) -> QRadialGradient:
    """Penumbra gradient along a shadow's near->far axis — opaque-ish right
    at the occluder, fading to fully transparent by the far end, instead of
    one flat alpha for the whole shape. A QRadialGradient centered on
    `near` with its radius reaching `far` approximates the linear "distance
    from the occluder" falloff without needing the gradient's own axis to
    be reprojected per shadow (QLinearGradient would need its perpendicular
    extent handled separately to avoid banding across the shadow's width)."""
    length = math.hypot(far.x() - near.x(), far.y() - near.y())
    grad = QRadialGradient(near, max(1.0, length))
    color = shadow_color or QColor(8, 10, 16)
    for stop, factor in ((0.0, 0.90), (0.2, 0.80), (0.4, 0.65), (0.6, 0.45), (0.8, 0.20), (1.0, 0.0)):
        c = QColor(color)
        c.setAlpha(int(max_alpha * factor))
        grad.setColorAt(stop, c)
    return grad
