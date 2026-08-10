"""PanelLayoutEngine — owns MainLayout's resizeEvent-driven positioning:
where every panel/overlay sits once the window size (or which panels are
visible) changes. Pure geometry, reading/writing widgets MainLayout already
constructed — same `self._l = layout` convention the mediators use (see
e.g. LightMediator), just for layout instead of a feature domain. Extracted
verbatim from MainLayout.resizeEvent/_reposition_compass_hud (no behavior
change) since it was the single largest block of purely-positional code
sharing no state with anything else in that file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect

from src.layouts.panel_manager import PanelManager

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class PanelLayoutEngine:
    def __init__(self, layout: MainLayout):
        self._l = layout

    def reposition_compass_hud(self):
        """Anchors compass_hud to the compass's current spot — split out so
        Compass.position_changed (fired on every move, mid-drag included)
        can call just this instead of the full apply()/resizeEvent, and the
        HUD tracks the drag live instead of jumping once it ends."""
        l = self._l
        l.compass_hud.move(
            l.compass.x() + l.compass.width() - l.compass_hud.width(),
            l.compass.y() + l.compass.height() + 6,
        )
        l.compass_hud.raise_()

    def _size_to_content(self, panel, avail: QRect):
        """Resizes `panel` in place to its own content_height(), capped to
        the available work area — shared by every panel whose real height
        needs this override because PanelManager's generic _content_height()
        (which only measures the first QScrollArea it finds) undercounts it:
        a pinned header/button living outside the scroll area, or several
        nested QScrollAreas. Used for Brush, Região, Terrain, Background and
        Spawn — see each call site's own comment for why THAT panel needs
        the override."""
        geo = panel.geometry()
        panel_h = min(panel.content_height(), avail.height())
        panel.setGeometry(geo.x(), geo.y(), geo.width(), panel_h)

    def _dock_beside(self, host_rect: QRect, guest, avail: QRect, height: int):
        """Docks `guest` immediately to the right of `host_rect` (the host
        panel's already-computed geometry), width capped to the guest's own
        PANEL_WIDTH and the available work area — the shared x/width/raise
        plumbing behind every "sub-panel rides next to its host" pairing
        (Brush/AssetBrowser, Região/RegionEdit, Terrain/TerrainEdit, Spawn/
        MobSub, Texto/Personalizar). `height` is computed by the caller —
        each pairing derives it slightly differently (own content_height()
        vs PanelManager._content_height() vs the host's own height), see
        each call site's own comment."""
        x = host_rect.right() + 8
        w = min(guest.PANEL_WIDTH, max(0, avail.right() - x))
        guest.setGeometry(x, host_rect.y(), w, height)
        guest.raise_()

    def apply(self, w: int, h: int):
        l = self._l

        top_h = 72
        toolbar_h = 42
        status_h = 80
        prog_h = l.progression.height()

        body_top = top_h
        body_bottom = h - status_h
        body_h = body_bottom - body_top

        center_x = l.LEFT_W
        center_w = max(0, w - l.LEFT_W - l.RIGHT_W)

        l.canvas.setGeometry(0, 0, w, h)
        l.canvas.lower()
        l.top_bar.setGeometry(0, 0, w, top_h)
        l._left_container.setGeometry(0, body_top, l.LEFT_W, body_h)
        l._right_scroll.setGeometry(w - l.RIGHT_W, body_top, l.RIGHT_W, body_h)
        l._toolbar_med.layout(w, h, center_x, center_w, body_top, body_h)

        # Brush/Grid/Terrain panels normally sit right below the toolbar's
        # default top-docked slot — but the toolbar is now draggable, so
        # carve the panel area around wherever it actually is instead of
        # assuming that fixed slot.
        avail = QRect(center_x + 4, body_top + 4, max(0, center_w - 8), max(0, body_h - prog_h - 8))
        avail = l._toolbar_med.carve_panel_area(avail)
        l._panel_mgr.layout(avail.x(), avail.y(), avail.width(), avail.height())

        # Brush's header + Parâmetros/Assets tabs live outside its own
        # QScrollArea (added straight to `root`, same as Região's pinned
        # header) — PanelManager's generic sizing missed that entirely,
        # clipping the bottom sliders. Same content_height() override
        # pattern as Região/Terrain/Background, applied before the asset
        # browser below reads this panel's (now corrected) geometry.
        if l.brush_panel.isVisible():
            self._size_to_content(l.brush_panel, avail)

        # Asset browser rides next to Brush the same way RegionEditPanel
        # rides next to Região's CRUD list — sized to fill the full
        # available work area (not capped to brush_panel's own height,
        # which is now short since its sliders moved to a 2-column grid;
        # capping to it left the material grid showing only a couple
        # rows with tons of unused space below).
        if l.brush_panel.isVisible() and l.asset_browser_panel.isVisible():
            bp_rect = l.brush_panel.geometry()
            ab_h = min(l.asset_browser_panel.content_height(), max(0, avail.bottom() - bp_rect.y()))
            self._dock_beside(bp_rect, l.asset_browser_panel, avail, ab_h)

        # Região's CRUD list has a pinned header + "Nova Região" button
        # living OUTSIDE its card-list scroll area, so PanelManager's
        # generic _content_height() (which only measures the first
        # QScrollArea it finds) undercounts it — override with the panel's
        # own content_height(), which accounts for both.
        if l.region_panel.isVisible():
            self._size_to_content(l.region_panel, avail)

        # Terrain nests several QScrollAreas (whole-panel, terrain-card
        # list, background image browser) — same ambiguity as Região's
        # generic sizing, same override via its own content_height().
        if l.terrain_panel.isVisible():
            self._size_to_content(l.terrain_panel, avail)

        # Terreno's edit sub painel rides next to the CRUD list, same
        # convention as Região's edit panel below — sized to its own
        # content, capped to the available work area rather than Terreno's
        # own height, so one being shorter never squashes the other.
        if l.terrain_panel.isVisible() and l.terrain_edit_panel.isVisible():
            tp_rect = l.terrain_panel.geometry()
            max_h = max(0, avail.bottom() - tp_rect.y())
            te_h = min(PanelManager._content_height(l.terrain_edit_panel), max_h)
            self._dock_beside(tp_rect, l.terrain_edit_panel, avail, te_h)

        # Same nested-QScrollArea ambiguity as Terrain above (this panel
        # wraps BackgroundSection, which owns its own image-browser grid
        # scroll area) — same content_height() override.
        if l.background_panel.isVisible():
            self._size_to_content(l.background_panel, avail)

        # Spawn's header (outside its scroll area) has the same undercount
        # issue as Região's CRUD list — same content_height() override.
        if l.spawn_panel.isVisible():
            self._size_to_content(l.spawn_panel, avail)

        # Mob sub-panel rides next to Spawn's categories the same way
        # AssetBrowserPanel rides next to Brush.
        if l.spawn_panel.isVisible() and l.spawn_mob_sub_panel.isVisible():
            sp_rect = l.spawn_panel.geometry()
            ms_h = min(sp_rect.height(), max(0, avail.bottom() - sp_rect.y()))
            self._dock_beside(sp_rect, l.spawn_mob_sub_panel, avail, ms_h)

        # Personalizar rides next to Texto (not through PanelManager — see
        # where it's created), sized to its own content.
        if l.text_panel.isVisible() and l.color_customize_panel.isVisible():
            tp_rect = l.text_panel.geometry()
            cc_h = min(PanelManager._content_height(l.color_customize_panel), avail.height())
            self._dock_beside(tp_rect, l.color_customize_panel, avail, cc_h)

        # Região's edit panel rides next to the CRUD list the same way —
        # but sized to its OWN content (collapsible sections growing/
        # shrinking), same smart-height behavior Terrain's BackgroundSection
        # gets via PanelManager._content_height, not just copying Region's
        # height verbatim (which ignored its collapsed/expanded sections).
        if l.region_panel.isVisible() and l.region_edit_panel.isVisible():
            rp_rect = l.region_panel.geometry()
            # Capped to the available work area, NOT to Region's own height —
            # the two panels size independently to their own content now, so
            # one being shorter must never squash the other.
            max_h = max(0, avail.bottom() - rp_rect.y())
            re_h = min(PanelManager._content_height(l.region_edit_panel), max_h)
            self._dock_beside(rp_rect, l.region_edit_panel, avail, re_h)

        # Asset effects editor — not anchored to any tool/panel (opened from
        # the fullscreen Config view), so it floats centered over whatever's
        # currently showing by default, in-app like every other picker here
        # — unless the user has dragged it by its title bar (see
        # AssetEffectsPanel.has_custom_position), in which case that spot is
        # kept (just clamped to stay reachable on resize), same convention
        # as Compass/MiniMap.
        if l.asset_effects_panel.isVisible():
            ae_w = l.asset_effects_panel.width()
            ae_h = min(PanelManager._content_height(l.asset_effects_panel), h)
            l.asset_effects_panel.resize(ae_w, ae_h)
            if l.asset_effects_panel.has_custom_position():
                ae_x = min(max(l.asset_effects_panel.x(), 0), max(0, w - ae_w))
                ae_y = min(max(l.asset_effects_panel.y(), 0), max(0, h - ae_h))
                l.asset_effects_panel.move(ae_x, ae_y)
            else:
                l.asset_effects_panel.move((w - ae_w) // 2, (h - ae_h) // 2)
            l.asset_effects_panel.raise_()

        # Info modal — always centered over the canvas, no drag support
        # (it's a one-off dismiss-with-OK message, not a panel worth
        # remembering a position for).
        if l.info_modal.isVisible():
            im_w = l.info_modal.width()
            im_h = l.info_modal.sizeHint().height()
            l.info_modal.resize(im_w, im_h)
            l.info_modal.move((w - im_w) // 2, (h - im_h) // 2)
            l.info_modal.raise_()

        l.progression.setGeometry(center_x, body_bottom - prog_h, center_w, prog_h)
        l.status_bar.setGeometry(0, h - status_h, w, status_h)

        ov_top = body_top + toolbar_h
        ov_h = max(0, body_h - toolbar_h - prog_h)

        if l.compass.has_custom_position():
            # User dragged it via its own grip — keep their spot, just
            # clamp to stay reachable on resize (same pattern as minimap).
            cx = min(max(l.compass.x(), center_x), max(center_x, center_x + center_w - l.compass.width()))
            cy = min(max(l.compass.y(), ov_top), max(ov_top, ov_top + ov_h - l.compass.height()))
            l.compass.move(cx, cy)
        else:
            l.compass.move(center_x + center_w - l.compass.width() - 16, ov_top + 8)
        if l.minimap.has_custom_position():
            # User dragged it — keep their spot, just clamp to stay reachable on resize.
            mx = min(max(l.minimap.x(), center_x), max(center_x, center_x + center_w - l.minimap.width()))
            my = min(max(l.minimap.y(), ov_top), max(ov_top, ov_top + ov_h - l.minimap.height()))
            l.minimap.move(mx, my)
        else:
            l.minimap.move(
                center_x + center_w - l.minimap.width() - 16,
                ov_top + ov_h - l.minimap.height() - 8,
            )
        l.minimap.raise_()
        l.compass.raise_()
        # Raised last — compass_hud is a readout attached to the compass and
        # must stay legible even where its card overlaps the minimap (e.g. on
        # a short/narrow window), not get painted over by whichever of those
        # two happened to be raised most recently.
        self.reposition_compass_hud()
        # Both compass and compass_hud just landed at their default anchor
        # (top-right of the canvas), which on a short/narrow window can
        # collide with the minimap's own default anchor (bottom-right) —
        # nudge minimap clear of them here too, not just on the reactive
        # drag/visibility-toggle paths above, so this isn't left to whichever
        # of those happens to fire next.
        if not l.minimap.has_custom_position():
            l.floating.push_clear("minimap")

        menu_container = l._menu_med._menu_container
        if menu_container:
            menu_container.setGeometry(0, top_h, w, body_h)
            menu_container.raise_()
