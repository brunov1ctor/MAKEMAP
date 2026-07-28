"""Scene-space building blocks for the skill tree canvas — the card node
(_NodeItem), its connections (_EdgeItem), and the drag-in-progress preview
(_ConnectPreviewItem). None of these import SkillTreeCanvas: they reach back
into it only through the duck-typed `canvas` object passed at construction
(see each class's own `_canvas` attribute), which is how this module stays
free of a circular import against canvas.py.
"""

from __future__ import annotations

import json
import math
import uuid

from PySide6.QtWidgets import QGraphicsObject, QGraphicsPathItem
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QPainterPathStroker, QFont, QPixmap, QPolygonF,
)

from src.styles.tokens import Colors
from src.services.project_assets import resolve_asset_path


def _parse_json_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class _NodeItem(QGraphicsObject):
    """One rectangular skill-card node — shows the skill's own image when it
    has one (falls back to its emoji icon otherwise), matching the square
    tiles used elsewhere for catalog entries (see _CatalogTile in
    mobs/edit_widgets.py). Dragging the card body repositions it; dragging
    the small chain-link handle instead starts a connection to another node
    (see SkillTreeCanvas._begin_connect/_update_connect/_finish_connect)."""

    NODE_W = 64   # card width (image area)
    NODE_H = 64   # card height (image area)
    HANDLE_R = 9  # connect-handle radius (drawn size)
    HANDLE_HIT_R = 13  # bigger, invisible grab radius — the drawn circle alone is a fussy target
    CONNECT_ICON = "🔗"  # deliberately different from the "+" used to add nodes
    DELETE_BTN_R = 8  # radius of the "✕" button shown when selected (top-left corner)

    clicked = Signal(object, object)     # (self, Qt.KeyboardModifiers)
    moved = Signal(object)               # self (on drag release)

    def __init__(self, data: dict, canvas: "SkillTreeCanvas"):
        super().__init__()
        self._canvas = canvas
        self.node_id = data.get("id") or str(uuid.uuid4())
        self.name = data.get("name", "Nó")
        self.icon = data.get("icon", "✨")
        self.image_path = data.get("image_path") or ""
        self.rank_current = int(data.get("rank_current", 0))
        self.rank_max = int(data.get("rank_max", 1))
        self.color = data.get("color") or Colors.ACCENT
        self._pixmap_cache: QPixmap | None = None
        self.setPos(QPointF(float(data.get("x", 0)), float(data.get("y", 0))))
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(2)
        self._selected = False
        self._connecting = False
        self._rank_button_press = False
        self._hovering = False
        self._handle_hovering = False
        self.setAcceptHoverEvents(True)
        self.setToolTip("Arraste o card para mover • arraste o 🔗 para conectar • +/− ajusta o rank • selecione e clique no ✕ para remover")

    def boundingRect(self) -> QRectF:
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        # card + label strip below + enough margin on every side for the
        # hover halo / "alive" pulse ring / connect-handle circle, all of
        # which paint a few px past the card's own edge — too tight a
        # margin here means Qt only clears part of what paint() actually
        # draws each frame, leaving a smeared "ghost" trail behind exactly
        # like the old value (4px) did for the handle/hover glow.
        m = 14
        return QRectF(-hw - m, -hh - m, self.NODE_W + 2 * m, self.NODE_H + 48)

    def center(self) -> QPointF:
        return self.pos()

    def _card_rect(self) -> QRectF:
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        return QRectF(-hw, -hh, self.NODE_W, self.NODE_H)

    def _handle_center(self) -> QPointF:
        card = self._card_rect()
        return QPointF(card.right() - 3, card.bottom() - 3)

    def _handle_rect(self) -> QRectF:
        c = self._handle_center()
        hr = self.HANDLE_R
        return QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr)

    def _handle_hit_rect(self) -> QRectF:
        """Larger than the drawn circle (_handle_rect) — grabbing the tiny
        18px connect handle by its exact pixels was fussy; the extra margin
        is invisible (no bigger circle painted) but still counts as a hit
        in mousePressEvent/hoverMoveEvent below."""
        c = self._handle_center()
        hr = self.HANDLE_HIT_R
        return QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr)

    def _delete_button_rect(self) -> QRectF:
        """Top-left corner of the card — only meaningful (and only drawn/
        hit-tested) while the node is selected, so it doesn't compete with
        the connect handle (bottom-right) or the rank +/- buttons below."""
        card = self._card_rect()
        r = self.DELETE_BTN_R
        return QRectF(card.left() - r * 0.4, card.top() - r * 0.4, 2 * r, 2 * r)

    def _rank_button_rects(self) -> tuple[QRectF, QRectF]:
        """(minus_rect, plus_rect) — hit targets flanking the rank text
        ("X/Y") in the label strip below the card, so THIS card's rank can
        be adjusted directly without selecting it first or going through a
        separate panel (see SkillTreeCanvas._adjust_node_rank). Sized/
        spaced generously (15px, clear of the connect handle above) —
        too-tight hit targets here read as "the buttons don't work"."""
        hw = self.NODE_W / 2
        top = self._card_rect().bottom() + 14
        size = 15
        minus = QRectF(-hw - 9, top, size, size)
        plus = QRectF(hw - 6, top, size, size)
        return minus, plus

    def set_selected(self, value: bool):
        self._selected = value
        self.update()

    def set_image_path(self, image_path: str):
        self.image_path = image_path or ""
        self._pixmap_cache = None
        self.update()

    def _load_pixmap(self) -> QPixmap | None:
        if not self.image_path:
            return None
        if self._pixmap_cache is None:
            resolved = resolve_asset_path(self._canvas._project_dir, self.image_path)
            self._pixmap_cache = QPixmap(resolved) if resolved else QPixmap()
        return self._pixmap_cache if not self._pixmap_cache.isNull() else None

    def to_dict(self) -> dict:
        return {
            "id": self.node_id, "name": self.name, "icon": self.icon,
            "image_path": self.image_path,
            "rank_current": self.rank_current, "rank_max": self.rank_max,
            "color": self.color, "x": self.pos().x(), "y": self.pos().y(),
        }

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self._card_rect()
        color = QColor(self.color)
        theme_border = getattr(self._canvas, "_active_theme_color", "") if self._canvas else ""
        theme_text = getattr(self._canvas, "_active_text_color", "") if self._canvas else ""

        card_path = QPainterPath()
        card_path.addRoundedRect(card, 10, 10)

        # "Alive" breathing ring — a slow, continuous pulse (Copilot-prompt
        # style ambient glow) so the card reads as interactive even at rest,
        # not just on hover. Driven by the same shared _flow_phase the edge
        # flow-light already ticks (see SkillTreeCanvas._advance_flow).
        phase = getattr(self._canvas, "_flow_phase", None) if self._canvas else None
        if phase is not None:
            pulse = (math.sin(phase * 2 * math.pi) + 1) / 2  # 0..1..0
            pulse_color = QColor(theme_border) if theme_border else QColor(Colors.ACCENT)
            pulse_color.setAlpha(int(35 + pulse * 70))
            pulse_rect = card.adjusted(-3 - pulse * 2, -3 - pulse * 2, 3 + pulse * 2, 3 + pulse * 2)
            pulse_path = QPainterPath()
            pulse_path.addRoundedRect(pulse_rect, 13, 13)
            p.setPen(QPen(pulse_color, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(pulse_path)

        # Hover glow — a soft halo behind the card, drawn first so it reads
        # as a highlight rather than covering anything.
        if self._hovering:
            glow_rect = card.adjusted(-6, -6, 6, 6)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, 14, 14)
            glow_color = QColor(theme_border) if theme_border else QColor(Colors.ACCENT)
            glow_color.setAlpha(70)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow_color))
            p.drawPath(glow_path)

        # Selection / ring — a tab-level theme border color, when set,
        # overrides the skill-rarity color used by default.
        ring_base = QColor(theme_border) if theme_border else color
        if self._selected:
            p.setPen(QPen(QColor(Colors.ACCENT), 3))
        else:
            ring = QColor(ring_base)
            ring.setAlpha(220 if theme_border else 200)
            p.setPen(QPen(ring, 2.5 if theme_border else 2))
        grad = QColor(color)
        grad.setAlpha(60)
        p.setBrush(QBrush(grad))
        p.drawPath(card_path)

        pixmap = self._load_pixmap()
        if pixmap:
            p.save()
            p.setClipPath(card_path)
            scaled = pixmap.scaled(
                int(card.width()), int(card.height()),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            )
            x = card.left() + (card.width() - scaled.width()) / 2
            y = card.top() + (card.height() - scaled.height()) / 2
            p.drawPixmap(QPointF(x, y), scaled)
            p.restore()
        else:
            p.setPen(QColor("#FFFFFF"))
            icon_font = QFont("Segoe UI Emoji", 20)
            p.setFont(icon_font)
            p.drawText(card, Qt.AlignmentFlag.AlignCenter, self.icon)

        # Name — a tab-level theme text color, when set, overrides the
        # default primary/muted text colors.
        hw = self.NODE_W / 2
        if theme_text:
            name_color = QColor(theme_text)
            rank_color = QColor(theme_text)
            rank_color.setAlpha(160)
        else:
            name_color = QColor(Colors.TEXT_PRIMARY)
            rank_color = QColor(Colors.TEXT_MUTED)
        p.setPen(name_color)
        name_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(name_font)
        p.drawText(QRectF(-hw - 4, card.bottom() + 2, self.NODE_W + 8, 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.name)

        # Rank
        p.setPen(rank_color)
        rank_font = QFont("Segoe UI", 8)
        p.setFont(rank_font)
        p.drawText(QRectF(-hw - 4, card.bottom() + 16, self.NODE_W + 8, 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   f"{self.rank_current}/{self.rank_max}")

        # Rank +/- — right on the card, flanking the rank text, so this
        # node's rank can be nudged without selecting it first. Follows the
        # tab's theme color (like the ring above) when one is set.
        accent_color = QColor(theme_border) if theme_border else QColor(Colors.ACCENT)
        minus_rect, plus_rect = self._rank_button_rects()
        for rect, symbol, enabled in (
            (minus_rect, "−", self.rank_current > 0),
            (plus_rect, "+", self.rank_current < self.rank_max),
        ):
            if enabled:
                btn_color = accent_color
                fill = QColor(accent_color)
                fill.setAlpha(45)
            else:
                btn_color = QColor(Colors.BORDER_SUBTLE)
                fill = QColor(0, 0, 0, 0)
            p.setPen(QPen(btn_color, 1.2))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(btn_color)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)

        # Connect handle — a distinct chain-link icon, not the "+" used to
        # add nodes, so the two actions read as clearly different. Grows +
        # gets a glow ring while the cursor is over its (bigger, invisible)
        # hit area (see _handle_hit_rect/hoverMoveEvent) — confirms to the
        # user, before they even press, that this exact spot starts a drag.
        handle_rect = self._handle_rect()
        if self._handle_hovering:
            glow = handle_rect.adjusted(-4, -4, 4, 4)
            glow_color = QColor(Colors.ACCENT)
            glow_color.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow_color))
            p.drawEllipse(glow)
            handle_rect = handle_rect.adjusted(-1.5, -1.5, 1.5, 1.5)
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.setBrush(QBrush(QColor(20, 26, 40, 230)))
        p.drawEllipse(handle_rect)
        p.setFont(QFont("Segoe UI Emoji", 8))
        p.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, self.CONNECT_ICON)

        # Delete button — only while selected, so it doesn't clutter every
        # card at rest (see SkillTreeCanvas._delete_node, wired from
        # mousePressEvent below).
        if self._selected:
            del_rect = self._delete_button_rect()
            p.setPen(QPen(QColor("#F14C4C").darker(130), 1))
            p.setBrush(QBrush(QColor("#F14C4C")))
            p.drawEllipse(del_rect)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(del_rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged:
            self._canvas._on_node_moving(self)
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hovering = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovering = False
        if self._handle_hovering:
            self._handle_hovering = False
            self.update()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        # Distinguishes the connect-handle spot from the rest of the card
        # under the mouse *before* any click — a CrossCursor there signals
        # "drag from here to connect" instead of the plain OpenHandCursor
        # used for repositioning the card everywhere else.
        over_handle = self._handle_hit_rect().contains(event.pos())
        if over_handle != self._handle_hovering:
            self._handle_hovering = over_handle
            self.update()
        if over_handle:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._selected and self._delete_button_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            minus_rect, plus_rect = self._rank_button_rects()
            if minus_rect.contains(event.pos()) or plus_rect.contains(event.pos()):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self._selected and self._delete_button_rect().contains(event.pos()):
            self._canvas._delete_node(self)
            event.accept()
            return
        minus_rect, plus_rect = self._rank_button_rects()
        if minus_rect.contains(event.pos()) or plus_rect.contains(event.pos()):
            # Handled entirely on press — never calls the base class's
            # mousePressEvent, so mouseReleaseEvent must also skip its
            # super() call/moved signal below instead of treating this
            # like an (unstarted) card drag.
            self._rank_button_press = True
            self._canvas._adjust_node_rank(self, -1 if minus_rect.contains(event.pos()) else 1)
            event.accept()
            return
        if self._handle_hit_rect().contains(event.pos()):
            self._connecting = True
            self._canvas._begin_connect(self, self.mapToScene(event.pos()))
            event.accept()
            return
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.clicked.emit(self, event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._connecting:
            self._canvas._update_connect(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rank_button_press:
            self._rank_button_press = False
            event.accept()
            return
        if self._connecting:
            self._connecting = False
            self._canvas._finish_connect(self.mapToScene(event.pos()))
            event.accept()
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
        self.moved.emit(self)


def _arrow_head_polygon(tip: QPointF, angle: float, size: float, spread: float) -> QPolygonF:
    """A concave chevron (➤), not a plain filled triangle — reads much more
    clearly as a directional arrow at the small sizes an edge tip is drawn
    at. Shared by _EdgeItem (finished connections) and _ConnectPreviewItem
    (the drag-in-progress preview), so both look the same."""
    notch_depth = size * 0.45
    right = QPointF(tip.x() - math.cos(angle - spread) * size, tip.y() - math.sin(angle - spread) * size)
    left = QPointF(tip.x() - math.cos(angle + spread) * size, tip.y() - math.sin(angle + spread) * size)
    notch = QPointF(tip.x() - math.cos(angle) * notch_depth, tip.y() - math.sin(angle) * notch_depth)
    return QPolygonF([tip, right, notch, left])


class _EdgeItem(QGraphicsPathItem):
    """A connection between two nodes, drawn as a directional arrow (not
    just a line) with a bright pulse travelling along the stroke itself —
    confined to the line's own geometry, never a glow floating outside it
    — to read as "flow" from prerequisite to skill. Picks up the active
    tab's theme color (see SkillTreeCanvas._active_theme_color) instead of
    always using the flat app-wide accent. Selectable (click) so Del can
    remove it; redraws itself whenever either endpoint moves."""

    ARROW_SIZE = 14
    ARROW_SPREAD = math.radians(24)
    LINE_WIDTH = 2.4
    # How far (in scene px) the tip stops short of dst.center() — nodes are
    # drawn with a HIGHER zValue than edges (see _NodeItem.setZValue(2) vs
    # setZValue(1) below), so an arrow tip placed too close to the card's
    # center used to render fine but then vanish entirely underneath the
    # opaque node once the connection was no longer the live drag preview
    # (which sits above everything at zValue 5). Clearing the card's own
    # half-diagonal (√(32²+32²) ≈ 45px) keeps the tip visible outside the
    # card from any approach angle, corners included.
    NODE_CLEARANCE = 46
    ENDPOINT_GRAB_RADIUS = 16  # click-near-tip radius that starts a re-target drag
    HIT_WIDTH = 14             # width of the invisible click/hover strip around the thin drawn line
    DELETE_BTN_R = 9           # radius of the "✕" button shown when selected

    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "SkillTreeCanvas" = None):
        super().__init__()
        self.src = src
        self.dst = dst
        self._canvas = canvas
        self._redirect_end: str | None = None  # "src"/"dst" while a re-target drag is live
        self._hovering = False
        self._hover_end: str | None = None  # "src"/"dst" while hovering near that endpoint
        self.setZValue(1)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor(Colors.ACCENT), self.LINE_WIDTH))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_path()

    def shape(self):
        # The drawn stroke is only LINE_WIDTH (2.4px) wide — QGraphicsPath-
        # Item's default shape() hit-tests against that same pen, making
        # the curve a fussy sliver to click/hover precisely. Stroke a much
        # wider invisible band around the same path for hit-testing only
        # (paint() still draws the thin line); doesn't affect boundingRect,
        # which already has its own margin for the arrowhead/delete button.
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        return stroker.createStroke(self.path())

    def _theme_color(self) -> QColor:
        theme = getattr(self._canvas, "_active_theme_color", "") if self._canvas else ""
        return QColor(theme) if theme else QColor(Colors.ACCENT)

    def update_path(self):
        a = self.src.center()
        b = self.dst.center()
        path = QPainterPath(a)
        # slight vertical S-curve, like the reference's elbow connectors
        mid_y = (a.y() + b.y()) / 2
        path.cubicTo(QPointF(a.x(), mid_y), QPointF(b.x(), mid_y), b)
        self.prepareGeometryChange()
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        # QGraphicsPathItem's default boundingRect only covers path() itself
        # (+ pen width) — too tight once paint() also draws an arrowhead
        # past the plain curve. Qt only repaints/clears whatever
        # boundingRect() declares, so anything painted outside it never
        # gets erased on the next frame: exactly the smeared "ghost trail"
        # this margin fixes (most visible while update_path() runs every
        # frame during a connected node's drag).
        margin = self.ARROW_SIZE + 6 + self.DELETE_BTN_R
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def _delete_button_rect(self) -> QRectF:
        """Midpoint of the current curve — only meaningful (and only drawn/
        hit-tested) while the edge is selected, see paint()/mousePressEvent."""
        c = self.path().pointAtPercent(0.5)
        r = self.DELETE_BTN_R
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = self.path()
        base_color = self._theme_color()
        if self.isSelected():
            line_color = base_color.lighter(145)
            p.setPen(QPen(line_color, self.LINE_WIDTH + 0.6, Qt.PenStyle.DashLine))
        elif self._hovering:
            # Hover-only brighten (no dashing, that's reserved for
            # selection) — confirms the wider invisible shape() strip
            # actually caught the cursor before the user commits to a click.
            line_color = base_color.lighter(125)
            p.setPen(QPen(line_color, self.LINE_WIDTH + 0.8))
        else:
            line_color = base_color
            pen_color = QColor(line_color)
            pen_color.setAlpha(170)
            p.setPen(QPen(pen_color, self.LINE_WIDTH))
        p.drawPath(path)
        self._draw_arrowhead(p, path, line_color)
        self._draw_flow_light(p, path, line_color)
        if self._hover_end:
            self._draw_endpoint_hint(p, path, line_color)
        if self.isSelected():
            self._draw_delete_button(p)

    def _draw_endpoint_hint(self, p: QPainter, path: QPainterPath, color: QColor):
        """A soft ring around whichever endpoint the cursor is currently
        close enough to grab (see ENDPOINT_GRAB_RADIUS/hoverMoveEvent) —
        the redirect drag has no other visual cue before the user presses,
        so without this a wrong connection's fix is easy to miss entirely."""
        center = self.src.center() if self._hover_end == "src" else self.dst.center()
        r = self.ENDPOINT_GRAB_RADIUS
        ring = QColor(color)
        ring.setAlpha(140)
        p.setPen(QPen(ring, 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(center, r, r)

    def _draw_delete_button(self, p: QPainter):
        """A small "✕" at the curve's midpoint, shown only while selected —
        lets a wrong connection be removed with a click instead of having
        to select it and reach for the Delete key (see SkillTreeCanvas.
        _delete_selected_edges, wired from mousePressEvent below)."""
        rect = self._delete_button_rect()
        p.setPen(QPen(QColor("#F14C4C").darker(130), 1))
        p.setBrush(QBrush(QColor("#F14C4C")))
        p.drawEllipse(rect)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def _tip_percent(self, path: QPainterPath) -> float:
        """The path percentage that lands NODE_CLEARANCE px before the end
        — a fixed pixel distance from dst.center(), not a fixed percentage
        (a short edge's 96% point can still be deep inside the card while a
        long edge's would already clear it by a lot). Must go through
        percentAtLength() rather than a plain `1 - clearance/path.length()`:
        pointAtPercent()'s "percent" is NOT uniform arc length for a curved
        path (speed varies along a Bezier's own t parameter), so assuming
        it scales linearly with length landed the tip barely a third of
        NODE_CLEARANCE away from dst instead of the full distance —
        percentAtLength() is Qt's own (consistent) inverse of pointAtPercent
        in actual length terms."""
        total = path.length()
        if total <= 0:
            return 1.0
        target_len = max(total * 0.5, total - self.NODE_CLEARANCE)
        return path.percentAtLength(target_len)

    def _draw_arrowhead(self, p: QPainter, path: QPainterPath, color: QColor):
        """A filled chevron oriented along the path's own tangent, stopped
        short of dst's card (see _tip_percent) so it isn't drawn underneath
        the node and hidden by it — makes the connection read as directional
        (prerequisite → skill), not just an undirected line."""
        tip_t = self._tip_percent(path)
        tip = path.pointAtPercent(tip_t)
        back = path.pointAtPercent(max(0.0, tip_t - 0.08))
        dx, dy = tip.x() - back.x(), tip.y() - back.y()
        if dx == 0 and dy == 0:
            return
        angle = math.atan2(dy, dx)
        polygon = _arrow_head_polygon(tip, angle, self.ARROW_SIZE, self.ARROW_SPREAD)
        p.setPen(QPen(color.darker(130), 1))
        p.setBrush(QBrush(color))
        p.drawPolygon(polygon)

    def _draw_flow_light(self, p: QPainter, path: QPainterPath, color: QColor):
        """A bright pulse travelling src → just short of dst (same
        clearance as the arrowhead, so it doesn't disappear under the node
        either) on a loop, driven by SkillTreeCanvas._flow_timer — drawn by
        re-stroking a short arc of this SAME path around the current phase,
        so the highlight is part of the line's own geometry and can never
        spill out past its width (no separate glow blob floating beside/
        above the stroke)."""
        phase = getattr(self._canvas, "_flow_phase", None) if self._canvas else None
        if phase is None:
            return
        travel_end = self._tip_percent(path)
        span = 0.045
        t0, t1 = max(0.0, phase * travel_end - span), min(travel_end, phase * travel_end + span)
        if t1 <= t0:
            return
        segment = QPainterPath(path.pointAtPercent(t0))
        steps = 6
        for i in range(1, steps + 1):
            segment.lineTo(path.pointAtPercent(t0 + (t1 - t0) * i / steps))
        halo = QColor(color)
        halo.setAlpha(200)
        halo_pen = QPen(halo, self.LINE_WIDTH + 1.4)
        halo_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(halo_pen)
        p.drawPath(segment)
        core_pen = QPen(QColor(255, 255, 255, 235), self.LINE_WIDTH * 0.65)
        core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(core_pen)
        p.drawPath(segment)

    def _dist(self, a: QPointF, b: QPointF) -> float:
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    def _endpoint_near(self, pos: QPointF) -> str | None:
        dist_src = self._dist(pos, self.src.center())
        dist_dst = self._dist(pos, self.dst.center())
        if min(dist_src, dist_dst) <= self.ENDPOINT_GRAB_RADIUS:
            return "dst" if dist_dst <= dist_src else "src"
        return None

    def hoverEnterEvent(self, event):
        self._hovering = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        if self.isSelected() and self._delete_button_rect().contains(pos):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            near = self._endpoint_near(pos)
            if near != self._hover_end:
                self._hover_end = near
                self.update()
            self.setCursor(Qt.CursorShape.SizeAllCursor if near else Qt.CursorShape.PointingHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovering = False
        if self._hover_end:
            self._hover_end = None
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        pos = event.pos()
        if self.isSelected() and self._delete_button_rect().contains(pos):
            if self._canvas:
                self._canvas._delete_edge(self)
            event.accept()
            return
        near = self._endpoint_near(pos)
        if near:
            self._redirect_end = near
            self._hover_end = None
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._canvas:
                self._canvas._begin_redirect(self, self._redirect_end, self.mapToScene(pos))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._redirect_end and self._canvas:
            self._canvas._update_connect(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._redirect_end:
            end_pos = self.mapToScene(event.pos())
            self._redirect_end = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self._canvas:
                self._canvas._finish_redirect(end_pos)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _ConnectPreviewItem(QGraphicsPathItem):
    """The dashed preview shown while dragging a node's 🔗 handle toward a
    target — the same chevron-arrow shape and active-tab theme color as the
    real _EdgeItem connection it's about to create (see SkillTreeCanvas.
    _begin_connect/_update_connect), not just a plain line."""

    def __init__(self, start: QPointF, end: QPointF, canvas: "SkillTreeCanvas" = None):
        super().__init__()
        self.setZValue(5)
        self._start = start
        self._end = end
        self._canvas = canvas
        self._rebuild()

    def _theme_color(self) -> QColor:
        theme = getattr(self._canvas, "_active_theme_color", "") if self._canvas else ""
        return QColor(theme) if theme else QColor(Colors.ACCENT)

    def set_end(self, end: QPointF):
        self.prepareGeometryChange()
        self._end = end
        self._rebuild()

    def _rebuild(self):
        path = QPainterPath(self._start)
        path.lineTo(self._end)
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        # Same reasoning as _EdgeItem.boundingRect — paint() below draws an
        # arrowhead past the plain line, so the declared rect must cover it
        # too or repeated set_end() calls during the drag leave a ghost
        # trail behind the moving tip.
        margin = _EdgeItem.ARROW_SIZE + 6
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._theme_color()
        p.setPen(QPen(color, _EdgeItem.LINE_WIDTH, Qt.PenStyle.DashLine))
        p.drawPath(self.path())
        dx, dy = self._end.x() - self._start.x(), self._end.y() - self._start.y()
        if dx == 0 and dy == 0:
            return
        angle = math.atan2(dy, dx)
        polygon = _arrow_head_polygon(self._end, angle, _EdgeItem.ARROW_SIZE, _EdgeItem.ARROW_SPREAD)
        p.setPen(QPen(color.darker(130), 1))
        p.setBrush(QBrush(color))
        p.drawPolygon(polygon)
