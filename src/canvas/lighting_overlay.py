"""GlobalLightingOverlay — a single whole-scene QGraphicsItem with two
layers: an optional whole-map day/night darkening tint (see set_sky/
_paint_sky, driven by the single global "sky" setting — GLOBAL_TYPES in
src/engines/light.py), painted first, then every LightItem's glow on top
with CompositionMode_Plus (additive) so overlapping lights actually add up
into brighter light instead of stacking as separate translucent decals and
so placed lights visibly "cut through" the night tint. Each light's own
occluder shadow is subtracted from its glow before painting (see
lighting_compositor), so a stamped house still blocks light exactly like
before. LightMediator owns creating this and ticking its refresh in sync
with moving lights/occluders/the sky setting.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QImage, QPainter, QPainterPath, QTransform,
)
from PySide6.QtWidgets import QGraphicsItem

from src.canvas.contact_shadow import draw_contact_shadow
from src.canvas.item_utils import make_non_interactive
from src.canvas.light_item import LightItem
from src.canvas.z_order import ZOrder
from src.engines.fog_noise import paint_volume, volume_textures
from src.engines.light import LightProperties
from src.engines.lighting_compositor import (
    compute_lit_path, compute_shadows, cone_path, falloff_gamma, falloff_gradient, shadow_gradient,
)
from src.layouts.panels.spawn.portrait_compose import FRONT_TOKEN_SCALE

# Extra reach past each light's own radius so the overlay's bounding rect
# comfortably contains the soft falloff tail (falloff_gradient's alpha is
# already ~0 near the edge, but Qt still needs the geometry to cover it).
_MARGIN = 32.0

# A very faint always-on floor so a map with placed lights doesn't read as
# flat black outside each light's own falloff — real darkness is never
# pure black. Painted whenever there's at least one light, independent of
# the sky setting (see paint()); sky's own tint, when active, stacks on
# top as additional night darkening rather than replacing this floor —
# their alphas compose via normal SourceOver blending, which is bounded
# (not additive past 255), so stacking both never over-darkens badly even
# at full night.
_AMBIENT_COLOR = QColor(35, 32, 28)
_AMBIENT_ALPHA = 90

# Fraction of a spot cone's own angular width spent fading in/out at each
# straight edge (see _paint_spot_glow) — must stay < 0.5 or the two fade
# ramps would overlap/invert past the cone's center.
_CONE_EDGE_FADE = 0.16

# Top-level key under GlobalLightingOverlay._volume_cache (see
# _draw_volumetric) — volume_textures nests its own per-layer cache under
# this, mirroring the "cache_key" pattern used by brush_effects.
_VOLUMETRIC_CACHE_KEY = "light_volumetric"


def _paint_spot_glow(painter: QPainter, props: LightProperties, radius: float, lit_path: QPainterPath):
    """A spot cone filled with plain falloff_gradient cuts off dead
    straight at its two side edges — a radial gradient has no notion of
    angle, so there's nothing to soften them. Qt can't intersect a radial
    and an angular falloff in a single fillPath call, so this renders the
    glow to a small offscreen buffer, then multiplies in a
    QConicalGradient alpha mask (opaque through the middle of the cone,
    fading to 0 right at both edges) via CompositionMode_DestinationIn
    before compositing the result back onto the real painter. Module-level
    (not a GlobalLightingOverlay method) so LightGhostItem's placement
    preview gets the same edge fade as the real, placed light instead of
    the plain hard-edged version."""
    margin = 4
    size = int(radius * 2) + margin * 2
    buf = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    buf.fill(0)
    bp = QPainter(buf)
    bp.setRenderHint(QPainter.RenderHint.Antialiasing)
    bp.translate(size / 2, size / 2)
    bp.setClipPath(lit_path)
    gamma = falloff_gamma(props.falloff)
    bp.fillPath(lit_path, QBrush(falloff_gradient(QColor(props.color), props.intensity, radius, gamma)))

    # Matches cone_path's own arc start/sweep exactly, so the mask's
    # t=0/t=span stops land precisely on the cone's two straight edges.
    half = max(1.0, props.cone_angle_deg) / 2.0
    start_angle = -props.direction_deg - half
    span = props.cone_angle_deg / 360.0
    fade = _CONE_EDGE_FADE * span
    mask = QConicalGradient(0, 0, start_angle)
    mask.setColorAt(0.0, QColor(255, 255, 255, 0))
    mask.setColorAt(fade, QColor(255, 255, 255, 255))
    mask.setColorAt(span - fade, QColor(255, 255, 255, 255))
    mask.setColorAt(span, QColor(255, 255, 255, 0))
    mask.setColorAt(1.0, QColor(255, 255, 255, 0))
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    bp.fillRect(QRectF(-size / 2, -size / 2, size, size), QBrush(mask))
    bp.end()

    painter.drawImage(QRectF(-size / 2, -size / 2, size, size), buf)


class GlobalLightingOverlay(QGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Must sit above ZOrder.STAMPED_OBJECT (assets/mobs/npcs) or their
        # occluder shadows/contact smudges paint underneath the opaque stamp
        # and never show up on it at all — see z_order.py.
        self.setZValue(ZOrder.LIGHTING_OVERLAY)
        make_non_interactive(self)
        self._sky: LightProperties | None = None
        # Cached (fingerprint, lit_path, shadows) per light — id(light) ->
        # tuple, see _light_geometry(). compute_lit_path/compute_shadows
        # rebuild everything from scratch (including a scene.items() query
        # for occluders and per-occluder trig), and LightMediator's refresh
        # timer calls paint() every _REFRESH_TICK_MS unconditionally when any
        # light is volumetric (it has to, to drive the FBM haze's own
        # drift/breathing animation even when nothing moved) — without this
        # cache, that meant redoing the same occluder query and shadow math
        # for every light on every tick even while the map sat completely
        # still.
        self._light_cache: dict[int, tuple] = {}
        # Cached FBM haze textures per volumetric light — id(light) -> entry,
        # nested under _VOLUMETRIC_CACHE_KEY (see _draw_volumetric/
        # fog_noise.volume_textures). Regenerated only when a light's
        # radius/color actually change; pruned alongside _light_cache in
        # _prune_light_cache.
        self._volume_cache: dict = {}
        # Bumped whenever something that could occlude a light (an asset or
        # mob stamp) moves/rotates/resizes — see notify_light_moved()/
        # bump_occluder_generation() and LightMediator's transform signal
        # wiring. Folded into each light's fingerprint so a moved occluder
        # invalidates every light's cached shadow geometry without the
        # overlay needing to track which lights were actually near it.
        self._occluder_gen = 0
        # Cached list of visible LightItems — rescanning the whole scene
        # every _REFRESH_TICK_MS tick regardless of whether any light was
        # actually added/removed was a real cost at scale; see
        # mark_lights_dirty()/LightMediator for every point that
        # invalidates this.
        self._lights_cache: list[LightItem] | None = None

    def mark_lights_dirty(self):
        """Call whenever the set of visible lights (not just an existing
        light's own properties) may have changed — add/remove/load/visibility."""
        self._lights_cache = None
        self.prepareGeometryChange()

    def set_sky(self, props: LightProperties | None):
        """LightMediator calls this whenever the global sky setting loads or
        changes. day_amount >= 100 (full day) is treated as "off" so a fresh
        map with no sky configured yet costs nothing extra to paint."""
        self._sky = props

    def _sky_active(self) -> bool:
        return self._sky is not None and self._sky.day_amount < 100.0

    def notify_light_moved(self, light: LightItem):
        """LightItem.itemChange calls this on every position change (i.e.
        every mouse-move tick of a drag) — drops that light's cached
        geometry (its fingerprint's position no longer matches, so it'd
        miss anyway; this just saves the dict lookup) and repaints right
        away instead of waiting for the next periodic tick to notice."""
        self._light_cache.pop(id(light), None)
        self.prepareGeometryChange()
        self.update()

    def bump_occluder_generation(self):
        """Call whenever something that could occlude a light (an asset or
        mob stamp) finishes moving/rotating/resizing — invalidates every
        light's cached shadow geometry (via the fingerprint, see
        _light_geometry) so it's recomputed next paint. Cheaper than
        tracking exactly which lights were actually near the moved item."""
        self._occluder_gen += 1

    def _lights(self) -> list[LightItem]:
        if self._lights_cache is not None:
            return self._lights_cache
        if self.scene() is None:
            return []
        lights = [it for it in self.scene().items() if isinstance(it, LightItem) and it.isVisible()]
        self._lights_cache = lights
        return lights

    @staticmethod
    def _light_footprint(light: LightItem) -> QRectF:
        r = max(4.0, light.props.radius) + _MARGIN
        pos = light.scenePos()
        return QRectF(pos.x() - r, pos.y() - r, r * 2, r * 2)

    def animated_footprint(self) -> QRectF | None:
        """Union footprint of only the lights whose paint() output actually
        changes between periodic ticks — the volumetric haze's continuous
        FBM drift/breathing cross-fade, time.monotonic()-driven. A plain
        static point/spot light has nothing time-animated and is already
        repainted via
        notify_light_moved whenever it truly changes, so LightMediator's
        periodic tick doesn't need to touch it. None when nothing is
        animated, so the tick can skip entirely."""
        rect = None
        for light in self._lights():
            if light.props.volumetric:
                fr = self._light_footprint(light)
                rect = fr if rect is None else rect.united(fr)
        return rect

    def boundingRect(self) -> QRectF:
        lights = self._lights()
        sky_active = self._sky_active()
        if not lights and not sky_active:
            return QRectF()
        # The sky tint AND the ambient floor (_paint_ambient, painted
        # whenever any light exists — see paint()) both cover the whole map,
        # not just the square around each placed light: Qt clips paint()'s
        # exposedRect to boundingRect(), so leaving this as just the union
        # of light-radius squares made _paint_ambient's fillRect stop dead
        # at that square's edge — a visible dark vignette box around every
        # light instead of a uniform floor. The scene's own (fixed, huge)
        # sceneRect is the simplest stand-in for "the whole map" without
        # threading a MapBoundary reference through (Qt clips actual
        # painting to whatever's exposed on screen, so this costs nothing
        # extra either way).
        rect = self.scene().sceneRect() if (sky_active or lights) and self.scene() else None
        for light in lights:
            lr = self._light_footprint(light)
            rect = lr if rect is None else rect.united(lr)
        return rect if rect is not None else QRectF()

    def paint(self, painter: QPainter, option, widget=None):
        lights = self._lights()
        sky_active = self._sky_active()
        if not lights and not sky_active:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Ambient is the universal floor whenever lights exist — painted
        # first regardless of the sky setting, so a map with sky configured
        # near-day (day_amount close to 100, sky tint near-zero) still gets
        # a non-flat-black floor outside each light's falloff. Sky's own
        # tint (when active) stacks on top as ADDITIONAL night darkening,
        # not a replacement for it.
        if lights:
            self._paint_ambient(painter, option)
        if sky_active:
            self._paint_sky(painter, option)
        if lights:
            self._prune_light_cache(lights)
            self._paint_contact_shadows(painter, option)
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for light in lights:
                if not self._light_footprint(light).intersects(option.exposedRect):
                    continue
                self._paint_light(painter, light)
            painter.restore()

    def _prune_light_cache(self, lights: list[LightItem]):
        live_ids = {id(l) for l in lights}
        for stale_id in set(self._light_cache) - live_ids:
            del self._light_cache[stale_id]
        volume_sub = self._volume_cache.get(_VOLUMETRIC_CACHE_KEY)
        if volume_sub:
            for stale_id in set(volume_sub) - live_ids:
                del volume_sub[stale_id]

    def _paint_ambient(self, painter: QPainter, option):
        color = QColor(_AMBIENT_COLOR)
        color.setAlpha(_AMBIENT_ALPHA)
        painter.fillRect(option.exposedRect, color)

    def _paint_contact_shadows(self, painter: QPainter, option):
        """A small soft dark smudge at the base of every asset stamp (a
        house, a prop) AND every mob stamp in view — without it, sprites
        look like they're floating a few pixels above the ground instead
        of actually standing on it. Independent of any specific light
        (painted once, not per-light), so it holds even in fully
        ambient-lit areas."""
        if self.scene() is None:
            return
        for item in self.scene().items(option.exposedRect):
            data = item.data(0)
            if not isinstance(data, dict):
                continue
            item_type = data.get("item_type")
            # A brush-painted animated effect layer (Névoa, ...) is ALSO
            # tagged item_type "asset" (see BrushTool._get_or_create_
            # effect_layer) but it's a huge, mostly-transparent mask, not a
            # placed object — skip it here rather than drawing a smudge
            # under its (visually meaningless) bounding rect.
            if item_type == "asset" and not data.get("effect_key"):
                rect = item.sceneBoundingRect()
                if rect.isEmpty():
                    continue
                self._draw_contact_smudge(painter, rect.center().x(), rect.bottom(), rect.width() * 0.5)
            elif item_type == "mob_spawn":
                # Same visible-circle sizing as occluder_rects/the shadow
                # system (NOT sceneBoundingRect — that's the padded
                # composed-portrait canvas, see FRONT_TOKEN_SCALE) so the
                # smudge sits right under the actual token, not its
                # invisible bounding square.
                size = data.get("size") or 0
                if size <= 0:
                    continue
                token_radius = size * FRONT_TOKEN_SCALE / 2
                pos = item.scenePos()
                # Bottom edge of the circular token, same convention as the
                # asset branch's rect.bottom() — mob stamps sit at z=10 vs
                # this overlay's z=8 (SpawnTool.build_stamp_item), so most
                # of the smudge is naturally hidden under the opaque sprite
                # and only the base peeks out; anchoring higher (e.g. at
                # the token's own center) buried the whole thing with
                # nothing visible at all.
                self._draw_contact_smudge(painter, pos.x(), pos.y() + token_radius, token_radius * 1.1)

    @staticmethod
    def _draw_contact_smudge(painter: QPainter, cx: float, base_y: float, w: float):
        """One soft, squashed-elliptical dark smudge centered at (cx,
        base_y) — shared by both the asset and mob branches of
        _paint_contact_shadows."""
        h = max(6.0, w) * 0.32
        draw_contact_shadow(painter, cx, base_y - h * 0.25, w)

    def _paint_sky(self, painter: QPainter, option):
        t = max(0.0, min(100.0, self._sky.day_amount)) / 100.0  # 1 = day, 0 = night
        alpha = int(225 * (1.0 - t))
        if alpha <= 0:
            return
        color = QColor(self._sky.color)
        color.setAlpha(alpha)
        # Only the actually-exposed (on-screen) area needs filling — the
        # item's own boundingRect is the whole map, but Qt hands paint()
        # the real redraw region via option.exposedRect.
        painter.fillRect(option.exposedRect, color)

    def _light_geometry(self, light: LightItem, props: LightProperties, radius: float,
                         origin: QPointF) -> tuple[QPainterPath, list]:
        """lit_path + occluder shadows for this light, from cache when
        nothing relevant has changed since the last paint (see
        _light_cache/notify_light_moved/bump_occluder_generation) — the
        actual compute_lit_path/compute_shadows call (a scene spatial query
        plus per-occluder trig) only runs again when the fingerprint misses."""
        fingerprint = (
            round(origin.x(), 1), round(origin.y(), 1), radius,
            props.direction_deg, props.cone_angle_deg, props.light_type,
            props.shadows, self._occluder_gen,
        )
        cached = self._light_cache.get(id(light))
        if cached is not None and cached[0] == fingerprint:
            return cached[1], cached[2]

        lit_path = compute_lit_path(
            self.scene(), origin, radius, light_type=props.light_type,
            direction_deg=props.direction_deg, cone_angle_deg=props.cone_angle_deg,
            exclude=light,
        )
        shadows = compute_shadows(self.scene(), origin, radius, exclude=light) if props.shadows else []
        self._light_cache[id(light)] = (fingerprint, lit_path, shadows)
        return lit_path, shadows

    def _paint_light(self, painter: QPainter, light: LightItem):
        props = light.props
        radius = max(4.0, props.radius)
        origin = light.scenePos()
        lit_path, shadows = self._light_geometry(light, props, radius, origin)
        painter.save()
        painter.translate(origin)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setClipPath(lit_path)
        if props.light_type == "spot":
            _paint_spot_glow(painter, props, radius, lit_path)
        else:
            gamma = falloff_gamma(props.falloff)
            painter.fillPath(lit_path, QBrush(falloff_gradient(QColor(props.color), props.intensity, radius, gamma)))
        if props.volumetric:
            # The haze's own edge softness comes from its blurred silhouette
            # mask (see _draw_volumetric), not from this hard vector clip —
            # keeping lit_path clipped here would slice straight through the
            # middle of that fade and leave a visible ring right at the
            # light's radius, which is exactly the hard "cutoff" the mask
            # was built to avoid.
            painter.save()
            painter.setClipping(False)
            self._draw_volumetric(painter, light, radius, QColor(props.color), lit_path)
            painter.restore()

        # Shadows are painted as their own translucent layer ON TOP of the
        # glow (SourceOver, so they darken it) instead of being cut as a
        # hard hole out of lit_path — a shadowed patch now reads as "dimmer
        # here", with a near-occluder-to-far penumbra gradient (see
        # shadow_gradient), rather than "the light data just stops".
        if props.shadows:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setClipPath(lit_path)
            for shadow in shadows:
                self._paint_shadow(painter, shadow)
        painter.restore()

    # Occluder shadows near-double geometrically for scaling — see
    # _paint_shadow. Both scale FROM the light origin (0, 0), so the soft
    # layer bleeds further out along the same projection lines instead of
    # inflating uniformly in every direction (which would also puff it out
    # sideways past the occluder itself, looking wrong right at the base).
    _SHADOW_SOFT_SCALE = 1.22

    def _paint_shadow(self, painter: QPainter, shadow, alphas: tuple[int, int] = (55, 110)):
        """Two passes per occluder instead of one flat shape: a wider, dim
        "soft" layer first (scaled up from the light origin, so it bleeds
        past the crisp silhouette like real penumbra) then the normal
        "hard" shadow on top for a defined core — a single shadow shape at
        one opacity read as too clean/geometric, this layering is what
        actually reads as an organic soft-edged shadow. `alphas` is
        (soft, hard) peak alpha."""
        soft_alpha, hard_alpha = alphas
        k = self._SHADOW_SOFT_SCALE
        soft_path = QTransform().scale(k, k).map(shadow.path)
        soft_near = QPointF(shadow.near.x() * k, shadow.near.y() * k)
        soft_far = QPointF(shadow.far.x() * k, shadow.far.y() * k)
        painter.fillPath(soft_path, QBrush(shadow_gradient(soft_near, soft_far, max_alpha=soft_alpha)))
        painter.fillPath(shadow.path, QBrush(shadow_gradient(shadow.near, shadow.far, max_alpha=hard_alpha)))

    def _draw_volumetric(self, painter: QPainter, light: LightItem, radius: float,
                          color: QColor, lit_path: QPainterPath):
        """Continuous FBM haze filling the lit area (or cone, for spot
        lights) instead of discrete beams — same soft-edged density-field
        technique as brush_effects' fog/smoke (see fog_noise.volume_textures/
        paint_volume), reusing `lit_path` itself as the source shape for a
        blurred silhouette mask, so the haze naturally matches the light's
        own footprint with a soft, blurred boundary instead of a hard edge.
        The caller drops its hard vector clip before calling this (see
        _paint_light) — clipping to lit_path would slice straight through
        the middle of the mask's fade and reintroduce the hard ring this
        mask exists to avoid; the mask alone bounds the haze.
        Painted while the caller's CompositionMode_Plus is still active, so
        it adds into the glow like real volumetric scattering would; the
        shadow-darkening pass that runs right after this call (still within
        the same clip/local space) dims it under occluders exactly like the
        flat glow — no separate occlusion logic needed. Tuned lighter/
        thinner than fog/smoke's defaults (smaller texture, higher alpha
        gamma, lower alpha scale, near-zero drift) so it reads as a subtle
        drifting haze, not smoke, and nothing about the motion suggests
        rotation.

        Each density texture's own edge fade (see fog_noise._edge_fade_mask)
        is Chebyshev/square-shaped, not radial — invisible for brush_effects'
        fog/smoke because those shapes sit well inside their own bounding
        square, but a light's lit_path (a circle or cone) fills its bounding
        square edge-to-edge, so at a draw scale near 1.0 that square fade
        lands almost exactly on the light's own circular boundary and reads
        as a visible rectangle/facet instead of a smooth radial falloff. All
        three layers use the SAME oversized draw scale (~2x the light's
        diameter, well past where each texture's square fade even starts)
        so that square never becomes visible inside the light's radius —
        only the circular blurred mask (from lit_path) defines the visible
        boundary. Depth/movement still varies per layer via drift speed and
        alpha, just not apparent size."""
        bounds = QRectF(-radius, -radius, radius * 2, radius * 2)
        haze_color = QColor(color).lighter(115)
        blur_px = max(6, min(22, int(radius * 0.08)))
        entry = volume_textures(
            self._volume_cache, light, lit_path, bounds, haze_color,
            cache_key=_VOLUMETRIC_CACHE_KEY, tex_size=112, base_cells=3,
            alpha_gamma=2.1, alpha_scale=0.55, blur_px=blur_px, buf_margin=12,
            breathe_period=26.0,
        )
        paint_volume(
            painter, entry, bounds, time.monotonic(),
            layers=((2.0, 0.05, 0.45), (2.0, 0.09, 0.65), (2.0, 0.13, 0.85)),
            drift_fraction=0.035, breathe_period=26.0, swirl_speed=0.0,
            growth_period=0.0,
        )


class LightGhostItem(QGraphicsItem):
    """Cursor-following preview of the light about to be placed — while
    LightTool is armed (a type was picked in LightPanel but nothing's been
    clicked on the map yet), this follows the mouse showing just the glow
    (no icon, no occluder shadows — there's no real light/position yet) so
    the user can see roughly where/how big it'll land before committing.
    LightTool owns creating/moving/removing this; it's never persisted."""

    def __init__(self, props: LightProperties, parent=None):
        super().__init__(parent)
        self.props = props
        make_non_interactive(self)
        self.setZValue(ZOrder.CURSOR_GHOST)  # always on top so it reads clearly as a cursor-following ghost

    def boundingRect(self) -> QRectF:
        r = max(4.0, self.props.radius) + 4.0
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        radius = max(4.0, self.props.radius)
        is_spot = self.props.light_type == "spot"
        if is_spot:
            path = cone_path(radius, self.props.direction_deg, self.props.cone_angle_deg)
        else:
            path = QPainterPath()
            path.addEllipse(QPointF(0, 0), radius, radius)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setClipPath(path)
        # Same edge-fade treatment as the real, placed light (_paint_spot_glow)
        # — the preview used to show a hard-edged cone while the actual
        # placed light got a soft one, so it didn't preview honestly.
        if is_spot:
            _paint_spot_glow(painter, self.props, radius, path)
        else:
            gamma = falloff_gamma(self.props.falloff)
            painter.fillPath(path, QBrush(falloff_gradient(QColor(self.props.color), self.props.intensity, radius, gamma)))
        painter.restore()
