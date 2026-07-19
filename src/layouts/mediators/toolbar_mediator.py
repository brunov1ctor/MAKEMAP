"""ToolbarMediator — owns the canvas toolbar: signal wiring, free-drag
placement, and collision-avoidance against every other floating panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class ToolbarMediator:
    """Owns the canvas toolbar: signal wiring, free-drag placement, and
    collision-avoidance against every other floating panel.

    Pulled out of MainLayout because the toolbar stopped being a fixed
    top-docked strip (it's draggable and can flip horizontal/vertical) —
    placing it, keeping the Brush/Grid/Terrain panel area out from under it,
    and keeping the toolbar itself off *reappearing* panels are one
    connected responsibility, not scattered resizeEvent bookkeeping.
    """

    # Below this, a "panel avoiding the toolbar" carve is worse than no carve
    # at all — PanelManager always raises panels above the toolbar in
    # z-order, so an overlapped-but-full-size panel is still fully usable;
    # a sliver-sized one (e.g. a vertical toolbar spanning most of the
    # available height) is not. This is what made Grid/Brush/Terrain seem to
    # not open at all when the toolbar was vertical — they *did* open, just
    # carved down to a few px.
    MIN_PANEL_W = 220
    MIN_PANEL_H = 160

    def __init__(self, layout: MainLayout):
        self._l = layout
        self._user_positioned = False

    def connect(self):
        tb = self._l.canvas_toolbar
        tb.tool_selected.connect(self._l.canvas.engine.tool_manager.activate)
        tb.tool_selected.connect(self._l._on_tool_selected)
        tb.action_triggered.connect(self._l._on_toolbar_action)
        tb.view_toggled.connect(self._l._on_view_toggled)
        tb.region_preset_selected.connect(self._l.canvas.engine.set_region_preset)
        tb.dragged.connect(self.on_dragged)
        tb.orientation_changed.connect(lambda _: self.on_orientation_changed())

    @property
    def user_positioned(self) -> bool:
        return self._user_positioned

    # ─── Placement ───────────────────────────────────────────────────────

    def layout(self, w: int, h: int, center_x: int, center_w: int, body_top: int, body_h: int):
        """Position the toolbar itself for this resize/reposition pass."""
        tb = self._l.canvas_toolbar
        hint = tb.sizeHint()
        if self._user_positioned:
            tb_w = min(hint.width(), w)
            tb_h = min(hint.height(), h)
            tb_x = min(max(tb.x(), 0), max(0, w - tb_w))
            tb_y = min(max(tb.y(), 0), max(0, h - tb_h))
        else:
            tb_w = min(hint.width(), center_w)
            tb_h = min(hint.height(), body_h)
            tb_x = center_x + (center_w - tb_w) // 2
            tb_y = body_top
        tb.setGeometry(tb_x, tb_y, tb_w, tb_h)

    def on_orientation_changed(self):
        """Re-anchor after a flip, then push clear of whatever it now overlaps.

        Flipping can swap a ~42px-wide vertical bar for a ~650px-wide
        horizontal one (or vice versa) while anchored at the same corner —
        that new footprint can land right under a neighboring panel, which
        then also blocks every click meant for the toolbar underneath it.
        `_reposition()` must run first so `resolve_collision()` sees the
        toolbar's actual post-flip geometry (sizeHint() already reflects the
        new orientation immediately, but the widget itself isn't resized to
        match until something calls setGeometry on it).
        """
        self._l._reposition()
        self.resolve_collision()

    def carve_panel_area(self, avail: QRect) -> QRect:
        """Shrink `avail` so the Brush/Grid/Terrain panel area never sits
        under the toolbar, wherever it's currently been dragged to.

        Only matters when the toolbar actually overlaps `avail` — its
        default top-docked slot is already reserved by the caller's starting
        rect and won't trigger this at all.

        Tries excluding the toolbar from all 4 sides (left/right/top/bottom
        of it) rather than guessing a single direction from which edge it's
        "hugging" — a vertical toolbar can span most of `avail`'s height
        without touching either the top or bottom edge, which made the old
        single-direction guess degenerate to nothing and fall back to
        letting the panel overlap it. Picking the largest still-usable
        candidate means panels stay clear of the toolbar in practically any
        position/orientation it's dragged into.
        """
        tb = self._l.canvas_toolbar
        if not tb.isVisible():
            return avail
        tb_rect = tb.geometry()
        overlap = tb_rect.intersected(avail)
        if overlap.isEmpty():
            return avail

        left = QRect(avail)
        left.setRight(tb_rect.left() - 4)
        right = QRect(avail)
        right.setLeft(tb_rect.right() + 4)
        top = QRect(avail)
        top.setBottom(tb_rect.top() - 4)
        bottom = QRect(avail)
        bottom.setTop(tb_rect.bottom() + 4)

        candidates = [
            c for c in (left, right, top, bottom)
            if c.width() >= self.MIN_PANEL_W and c.height() >= self.MIN_PANEL_H
        ]
        if not candidates:
            # No side has room for a usable panel at all (tiny window) —
            # overlapping is the least-bad option left, and PanelManager
            # always raises panels above the toolbar so it stays usable.
            return avail
        candidates.sort(key=lambda r: r.width() * r.height(), reverse=True)
        return candidates[0]

    # ─── Collision ───────────────────────────────────────────────────────

    def obstacles(self) -> list[QRect]:
        """Geometry of every currently-visible panel the toolbar must not overlap.

        Hidden panels (e.g. via the View dropdown) aren't obstacles — that's
        the whole point of hiding them: freeing up space for the toolbar.
        Sourced from the shared FloatingCoordinator registry so this list
        doesn't drift from what other floating panels (minimap, and future
        ones) see each other as.
        """
        return self._l.floating.obstacles_for("toolbar")

    def on_dragged(self, dx: int, dy: int):
        self._user_positioned = True
        tb = self._l.canvas_toolbar
        cur = tb.geometry()
        win = self._l.rect()
        obstacles = self.obstacles()

        def fits(rect: QRect) -> bool:
            if not win.contains(rect):
                return False
            return not any(rect.intersects(o) for o in obstacles)

        x, y, tw, th = cur.x(), cur.y(), cur.width(), cur.height()
        full = QRect(x + dx, y + dy, tw, th)
        if fits(full):
            x, y = x + dx, y + dy
        else:
            # Slide along whichever single axis is still free, so dragging
            # diagonally past an obstacle's corner keeps gliding instead of
            # sticking dead — like a simple AABB collision response.
            slide_x = QRect(x + dx, y, tw, th)
            slide_y = QRect(x, y + dy, tw, th)
            if fits(slide_x):
                x = x + dx
            elif fits(slide_y):
                y = y + dy

        tb.move(x, y)
        # Brush/Grid/Terrain panels need to re-carve their available area
        # around the toolbar's new spot, live, not just on the next resize.
        self._l._reposition()

    def resolve_collision(self):
        """Push the toolbar out from under any panel it currently overlaps.

        Dragging already avoids obstacles live (`on_dragged`), but a panel
        can also reappear later — e.g. re-enabled via the View dropdown
        while the toolbar was parked in its spot — in which case the toolbar
        itself never moved and needs its own nudge to get out of the way,
        rather than the newly-shown panel getting hidden behind it. Delegated
        to the shared FloatingCoordinator so every registered movable panel
        (not just the toolbar) gets this same push-clear behavior for free.
        """
        self._l.floating.push_clear("toolbar")
        self._l._reposition()
