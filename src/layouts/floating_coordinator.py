"""FloatingCoordinator — shared obstacle-avoidance for floating UI chrome.

Every draggable/toggleable overlay (the canvas toolbar, the minimap, and any
future flyout a toolbar button opens — a color picker, an asset browser, a
sub-panel nested off Brush/Grid/Terrain, ...) needs the same two things:

  1. "Push myself clear of whatever I'm currently overlapping" — for when a
     hidden panel reappears (View dropdown) or my own size/position just
     changed (drag, resize, orientation flip) and now collides with someone.
  2. "Carve out a safe rect for myself before I even open" — for a panel
     about to show itself and wanting to land somewhere empty instead of
     directly on top of another floating panel.

Rather than every mediator hand-rolling its own obstacle list and push/carve
math (which is how the toolbar's version started, and which nothing else —
e.g. the minimap — got to share), anything that wants to participate just
registers here. A widget doesn't need to know what else exists; it only
needs to ask the coordinator.

Usage for a future sub-panel:
    coordinator.register("color_picker", picker_widget, movable=True)
    ...
    picker_widget.show()
    coordinator.push_clear("color_picker")   # nudge off whatever it opened on top of

Or, to place it in open space up front instead of moving it after showing:
    rect = coordinator.carve_around("color_picker", proposed_rect, min_w=200, min_h=150)
    picker_widget.setGeometry(rect)
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QRect


@dataclass
class _Entry:
    widget: QWidget
    movable: bool  # can be pushed clear by push_clear(); fixed chrome stays put


class FloatingCoordinator:
    """Registry + collision resolution for floating panels within one window."""

    def __init__(self, root: QWidget):
        self._root = root
        self._entries: dict[str, _Entry] = {}

    def register(self, name: str, widget: QWidget, *, movable: bool = False):
        self._entries[name] = _Entry(widget, movable)

    def unregister(self, name: str):
        self._entries.pop(name, None)

    # ─── Obstacles ───────────────────────────────────────────────────────

    def obstacles_for(self, name: str) -> list[QRect]:
        """Geometry of every visible *other* registered widget.

        Hidden ones aren't obstacles — that's the point of hiding something:
        freeing up its space for others to use.
        """
        return [
            e.widget.geometry() for n, e in self._entries.items()
            if n != name and e.widget.isVisible()
        ]

    # ─── Push clear (reactive: I already exist, get me off this obstacle) ─

    def push_clear(self, name: str, min_gap: int = 4, max_passes: int = 8):
        """Nudge `name`'s widget out from under anything it currently overlaps.

        Tries all 4 directions around whichever obstacle it's touching first,
        preferring one that clears *every* obstacle (not just that one) so
        two obstacles on opposite sides can't bounce it back and forth
        forever; falls back to the best partial move, and gives up rather
        than loop if it revisits a position it already tried.
        """
        entry = self._entries.get(name)
        if not entry or not entry.movable or not entry.widget.isVisible():
            return
        widget = entry.widget
        win = self._root.rect()
        seen: set[tuple[int, int]] = set()

        for _ in range(max_passes):
            cur = widget.geometry()
            obstacles = self.obstacles_for(name)
            hit = next((o for o in obstacles if cur.intersects(o)), None)
            if hit is None:
                return

            candidates = [
                QRect(hit.left() - cur.width() - min_gap, cur.y(), cur.width(), cur.height()),
                QRect(hit.right() + min_gap, cur.y(), cur.width(), cur.height()),
                QRect(cur.x(), hit.top() - cur.height() - min_gap, cur.width(), cur.height()),
                QRect(cur.x(), hit.bottom() + min_gap, cur.width(), cur.height()),
            ]
            candidates = [c for c in candidates if win.contains(c)]
            candidates.sort(key=lambda r: abs(r.x() - cur.x()) + abs(r.y() - cur.y()))

            fully_clear = [c for c in candidates if not any(c.intersects(o) for o in obstacles)]
            pick = fully_clear[0] if fully_clear else (candidates[0] if candidates else None)
            if pick is None:
                return  # nowhere valid on-screen — leave it rather than loop forever

            pos = (pick.x(), pick.y())
            if pos in seen:
                return  # already tried this spot — avoid bouncing forever
            seen.add(pos)
            widget.move(*pos)

    # ─── Carve (proactive: reserve me a rect that avoids everyone) ────────

    def carve_around(self, exclude: str, avail: QRect, min_w: int, min_h: int) -> QRect:
        """Shrink `avail` so it avoids every visible registered widget except
        `exclude`, picking whichever of the 4 side-exclusions leaves the most
        usable area for each obstacle in turn.

        Falls back to leaving `avail` overlapping a given obstacle if no side
        can clear it without dropping below (min_w, min_h) — a full-size
        panel that overlaps is still usable (callers should keep it raised
        above whatever it overlaps); a sliver-sized one to avoid overlap
        entirely is not.
        """
        result = QRect(avail)
        for name, entry in self._entries.items():
            if name == exclude or not entry.widget.isVisible():
                continue
            blocker = entry.widget.geometry()
            if not blocker.intersects(result):
                continue

            left = QRect(result); left.setRight(blocker.left() - 4)
            right = QRect(result); right.setLeft(blocker.right() + 4)
            top = QRect(result); top.setBottom(blocker.top() - 4)
            bottom = QRect(result); bottom.setTop(blocker.bottom() + 4)

            candidates = [c for c in (left, right, top, bottom) if c.width() >= min_w and c.height() >= min_h]
            if not candidates:
                continue  # can't avoid this one without degenerating — leave overlapping it
            candidates.sort(key=lambda r: r.width() * r.height(), reverse=True)
            result = candidates[0]
        return result
