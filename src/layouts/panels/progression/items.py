"""Scene-space building blocks for the Progressão do Mundo canvas — the
biome/step card (_ProgressionNode), its connections (_ProgressionEdge), and
the drag-in-progress preview (_ProgressionConnectPreview). Mirrors
src/layouts/panels/items/skill_tree/items.py's node/edge mechanics (hover,
drag-to-connect, drag-the-tip-to-redirect, "✕" delete button) — kept as its
own copy rather than a shared import because the two node types diverge in
what a card needs to show (notes/map pin here vs. rank/image there).
"""

from __future__ import annotations

import math
import uuid

from PySide6.QtWidgets import QGraphicsObject, QGraphicsPathItem, QMenu
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QPainterPathStroker, QFont, QLinearGradient,
)

from src.styles.tokens import Colors

# ─── Biome Colors ──────────────────────────────────────────────────────────

BIOME_COLORS = {
    "Floresta": "#4CAF50", "Vale": "#8BC34A", "Pântano": "#689F38",
    "Montanhas": "#78909C", "Deserto": "#FFA726", "Vulcão": "#FF5722",
    "Sombras": "#AB47BC", "End Game": "#673AB7", "Tutorial": "#42A5F5",
    "Arena PvP": "#EF5350", "Crafting": "#26A69A", "Costa": "#29B6F6",
    "Abismo": "#5C6BC0",
}

def biome_color(name: str) -> str:
    return BIOME_COLORS.get(name, "#4FC3F7")


def _arrow_head_polygon(tip: QPointF, angle: float, size: float, spread: float):
    from PySide6.QtGui import QPolygonF
    notch_depth = size * 0.45
    right = QPointF(tip.x() - math.cos(angle - spread) * size, tip.y() - math.sin(angle - spread) * size)
    left = QPointF(tip.x() - math.cos(angle + spread) * size, tip.y() - math.sin(angle + spread) * size)
    notch = QPointF(tip.x() - math.cos(angle) * notch_depth, tip.y() - math.sin(angle) * notch_depth)
    return QPolygonF([tip, right, notch, left])


class _ProgressionNode(QGraphicsObject):
    """One rectangular biome/step card — icon/menu row, name, level, then a
    notes text field, with a pin corner control and a chain-link connect
    handle added below/around it. The card itself is
    read-only display — no click-to-rename/click-to-pick-icon affordances
    hidden on its face; every edit (icon/name/level/notes/border color)
    goes through the "⋮" menu button (Editar) or a double-click,
    both opening the same full ProgressionNodeDialog, plus "Remover" for
    deleting the card. Two ways to connect two cards: drag from the small
    🔗 handle (bottom-right) onto another card, or just drag the card body
    itself and drop it on top of another one — the dragged card snaps back
    to where it started either way (see ProgressionCanvas.request_connection)."""

    NODE_W = 110
    NODE_H = 82
    HANDLE_R = 9
    HANDLE_HIT_R = 13
    CONNECT_ICON = "🔗"
    DELETE_BTN_R = 8
    _DROP_CONNECT_TOLERANCE = 4  # min drag distance (px) before a body-drop-on-a-card counts as "connect"

    clicked = Signal(object, object)
    moved = Signal(object)
    edit_requested = Signal(object)
    pin_pick_requested = Signal(object)
    pin_locate_requested = Signal(object)
    pin_clear_requested = Signal(object)

    def __init__(self, data: dict, canvas: "ProgressionCanvas"):
        super().__init__()
        self._canvas = canvas
        self.node_id = data.get("id") or str(uuid.uuid4())
        self.icon = data.get("icon", "🗺")
        self.name = data.get("name", "Novo")
        self.levels = data.get("levels", "")
        self.notes = data.get("notes", "")
        self.pin = data.get("pin")  # {"x":.., "y":..} | None
        self.border_color = data.get("border_color") or None  # explicit override, else biome_color(name)
        self.setPos(QPointF(float(data.get("x", 0)), float(data.get("y", 0))))
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(2)
        self._selected = False
        self._hovering = False
        self._handle_hovering = False
        self._menu_hovering = False
        self._connecting = False
        self._drop_highlighted = False
        self._drag_start_pos: QPointF | None = None  # pre-drag pos, for drop-to-connect detection
        self.setAcceptHoverEvents(True)
        self._refresh_tooltip()

    # ── data ──

    @property
    def color(self) -> str:
        """Border/glow color — the explicit override the user picked (see
        set_border_color), else derived from the biome name as before."""
        return self.border_color or biome_color(self.name)

    def to_dict(self) -> dict:
        return {
            "id": self.node_id, "icon": self.icon, "name": self.name,
            "levels": self.levels, "notes": self.notes,
            "pin": self.pin, "border_color": self.border_color,
            "x": self.pos().x(), "y": self.pos().y(),
        }

    def set_data(self, icon: str, name: str, levels: str, notes: str):
        self.icon, self.name, self.levels, self.notes = icon, name, levels, notes
        self._refresh_tooltip()
        self.update()

    def set_icon(self, icon: str):
        if icon and icon != self.icon:
            self.icon = icon
            self.update()
            if self._canvas:
                self._canvas._persist()

    def set_border_color(self, color: str | None):
        if color != self.border_color:
            self.border_color = color
            self.update()
            if self._canvas:
                # Arrows derive their color from src.color at paint time
                # (see _ProgressionEdge._color) — they need their own
                # update() too, or a connected edge keeps showing the old
                # color until something else happens to repaint it.
                self._canvas._on_node_color_changed(self)
                self._canvas._persist()

    def set_pin(self, x: float, y: float):
        self.pin = {"x": x, "y": y}
        self._refresh_tooltip()
        self.update()

    def clear_pin(self):
        self.pin = None
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self):
        parts = ["Arraste o card para mover • arraste o 🔗 para conectar • ⋮ ou duplo-clique edita"]
        if self.notes:
            parts.append(f"📝 {self.notes}")
        self.setToolTip("\n".join(parts))

    # ── geometry ──

    def boundingRect(self) -> QRectF:
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        m = 14
        return QRectF(-hw - m, -hh - m, self.NODE_W + 2 * m, self.NODE_H + 2 * m)

    def center(self) -> QPointF:
        return self.pos()

    def edge_point(self, toward: QPointF) -> QPointF:
        """Point on this card's own rectangle border, along the ray from
        its center toward `toward` — so a connection leaves/arrives at the
        card's edge (whichever side actually faces the other card) instead
        of always a fixed side, and the drawn line starts exactly at the
        rectangle instead of floating from its center."""
        c = self.center()
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        if dx == 0 and dy == 0:
            return c
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        candidates = []
        if dx != 0:
            candidates.append(hw / abs(dx))
        if dy != 0:
            candidates.append(hh / abs(dy))
        scale = min(candidates)
        return QPointF(c.x() + dx * scale, c.y() + dy * scale)

    def _card_rect(self) -> QRectF:
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        return QRectF(-hw, -hh, self.NODE_W, self.NODE_H)

    def _icon_rect(self) -> QRectF:
        card = self._card_rect()
        return QRectF(card.left() + 4, card.top() + 2, 22, 18)

    def _handle_center(self) -> QPointF:
        card = self._card_rect()
        return QPointF(card.right() - 3, card.bottom() - 3)

    def _handle_rect(self) -> QRectF:
        c = self._handle_center()
        hr = self.HANDLE_R
        return QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr)

    def _handle_hit_rect(self) -> QRectF:
        c = self._handle_center()
        hr = self.HANDLE_HIT_R
        return QRectF(c.x() - hr, c.y() - hr, 2 * hr, 2 * hr)

    def _top_row_center_y(self) -> float:
        return self._card_rect().top() + self.DELETE_BTN_R * 1.3 + 2

    def _pin_button_rect(self) -> QRectF:
        """📍/🎯 — just left of the "⋮" menu, same top row."""
        card = self._card_rect()
        r = self.DELETE_BTN_R
        cx, cy = card.right() - r * 3.6, self._top_row_center_y()
        return QRectF(cx - r, cy - r, 2 * r, 2 * r)

    def _menu_button_rect(self) -> QRectF:
        """"⋮" — top-right corner, always visible. The single entry point
        for every edit (Editar opens the full dialog) and for Remover —
        same "top row, right-aligned controls" spot the old Block's delete
        button used."""
        card = self._card_rect()
        r = self.DELETE_BTN_R
        cx, cy = card.right() - r * 1.3, self._top_row_center_y()
        return QRectF(cx - r, cy - r, 2 * r, 2 * r)

    def _name_rect(self) -> QRectF:
        card = self._card_rect()
        return QRectF(card.left() + 6, card.top() + 20, card.width() - 12, 14)

    def _level_rect(self) -> QRectF:
        card = self._card_rect()
        return QRectF(card.left() + 6, card.top() + 35, card.width() - 12, 12)

    def _notes_rect(self) -> QRectF:
        """The card's own text field for notes — a live, always-visible
        preview line (not just an icon indicator) so a glance at the card
        shows whether/what it says, full text still available via the
        tooltip and the edit dialog's multi-line field."""
        card = self._card_rect()
        return QRectF(card.left() + 6, card.top() + 49, card.width() - 12, 14)

    def set_selected(self, value: bool):
        self._selected = value
        self.update()

    def set_drop_highlight(self, value: bool):
        if value != self._drop_highlighted:
            self._drop_highlighted = value
            self.update()

    # ── paint ──

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self._card_rect()
        color = QColor(self.color)

        card_path = QPainterPath()
        card_path.addRoundedRect(card, 8, 8)

        glow_color = QColor(color)
        glow_color.setAlpha(25)
        p.fillPath(card_path, glow_color)
        p.fillPath(card_path, QColor(8, 18, 32, 200))

        # Degradê de baixo pra cima — mais tingido da cor da borda perto do
        # rodapé, esmaecendo pro fundo escuro no topo, pra dar um pouco de
        # relevo/estilo à linha ao invés de um preenchimento chapado.
        grad = QLinearGradient(card.left(), card.bottom(), card.left(), card.top())
        base = QColor(color)
        base.setAlpha(90)
        fade = QColor(color)
        fade.setAlpha(0)
        grad.setColorAt(0.0, base)
        grad.setColorAt(1.0, fade)
        p.fillPath(card_path, QBrush(grad))

        if self._hovering:
            glow_rect = card.adjusted(-5, -5, 5, 5)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, 12, 12)
            hover_glow = QColor(color)
            hover_glow.setAlpha(60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(hover_glow))
            p.drawPath(glow_path)

        if self._selected:
            p.setPen(QPen(QColor(Colors.ACCENT), 2.5))
        else:
            pen_color = QColor(color)
            pen_color.setAlpha(180)
            p.setPen(QPen(pen_color, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(card_path)

        # Ícone (linha do topo, estilo antigo do Block) — só exibição, edite
        # pelo menu "⋮" (Editar).
        icon_rect = self._icon_rect()
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI Emoji", 13))
        p.drawText(icon_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.icon)

        # Nome
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        name_rect = self._name_rect()
        metrics = p.fontMetrics()
        elided_name = metrics.elidedText(self.name, Qt.TextElideMode.ElideRight, int(name_rect.width()))
        p.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_name)

        # Nível
        p.setPen(color)
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(self._level_rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.levels)

        # Campo de texto das notas — sempre visível (não só um ícone),
        # mostra um preview de uma linha; texto completo no tooltip/diálogo.
        notes_rect = self._notes_rect()
        notes_preview = " ".join(self.notes.split()) if self.notes else "sem notas"
        notes_font = QFont("Segoe UI", 7)
        notes_font.setItalic(not self.notes)
        p.setFont(notes_font)
        metrics = p.fontMetrics()
        elided_notes = metrics.elidedText(notes_preview, Qt.TextElideMode.ElideRight, int(notes_rect.width()))
        notes_color = QColor(Colors.TEXT_MUTED)
        if not self.notes:
            notes_color.setAlpha(120)
        p.setPen(notes_color)
        p.drawText(notes_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_notes)

        # Botão de marcador — 📍 sem pin, 🎯 com pin (destaque diferente)
        pin_rect = self._pin_button_rect()
        pin_color = QColor(Colors.ACCENT) if self.pin else QColor(Colors.TEXT_MUTED)
        p.setFont(QFont("Segoe UI Emoji", 8))
        p.setPen(pin_color)
        p.drawText(pin_rect, Qt.AlignmentFlag.AlignCenter, "🎯" if self.pin else "📍")

        # Alça de conexão — arraste daqui até outro card pra criar uma
        # seta (alternativa a simplesmente arrastar o corpo do card e
        # soltar em cima do alvo — ver mousePressEvent/_finish_connect).
        handle_rect = self._handle_rect()
        if self._handle_hovering:
            glow = handle_rect.adjusted(-4, -4, 4, 4)
            glow_color2 = QColor(Colors.ACCENT)
            glow_color2.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow_color2))
            p.drawEllipse(glow)
            handle_rect = handle_rect.adjusted(-1.5, -1.5, 1.5, 1.5)
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.setBrush(QBrush(QColor(20, 26, 40, 230)))
        p.drawEllipse(handle_rect)
        p.setFont(QFont("Segoe UI Emoji", 7))
        p.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, self.CONNECT_ICON)

        # Alvo de conexão — enquanto outro card está sendo arrastado por
        # cima deste, um contorno tracejado avisa "solte aqui para
        # conectar" (ver ProgressionCanvas._update_drop_highlight).
        if self._drop_highlighted:
            drop_rect = card.adjusted(-4, -4, 4, 4)
            drop_path = QPainterPath()
            drop_path.addRoundedRect(drop_rect, 11, 11)
            p.setPen(QPen(QColor(Colors.ACCENT), 2.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(drop_path)

        # Menu "⋮" — sempre visível, abre Editar/Remover (ver _show_menu).
        menu_rect = self._menu_button_rect()
        menu_color = QColor(Colors.ACCENT) if self._menu_hovering else QColor(Colors.TEXT_MUTED)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(menu_color)
        p.drawText(menu_rect, Qt.AlignmentFlag.AlignCenter, "⋮")

    # ── interaction ──

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged:
            self._canvas._on_node_moving(self)
            if self._drag_start_pos is not None:
                self._canvas._update_drop_highlight(self)
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hovering = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovering = False
        if self._handle_hovering:
            self._handle_hovering = False
        if self._menu_hovering:
            self._menu_hovering = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event):
        over_handle = self._handle_hit_rect().contains(event.pos())
        if over_handle != self._handle_hovering:
            self._handle_hovering = over_handle
            self.update()
        over_menu = self._menu_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos())
        if over_menu != self._menu_hovering:
            self._menu_hovering = over_menu
            self.update()
        if over_handle:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif over_menu:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._pin_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self._menu_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos()):
            self._show_menu()
            event.accept()
            return
        if self._pin_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos()):
            if event.button() == Qt.MouseButton.RightButton and self.pin:
                self.pin_clear_requested.emit(self)
            elif self.pin:
                self.pin_locate_requested.emit(self)
            else:
                self.pin_pick_requested.emit(self)
            event.accept()
            return
        if self._handle_hit_rect().contains(event.pos()):
            self._connecting = True
            self._canvas._begin_connect(self, self.mapToScene(event.pos()))
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Arrastar o corpo do card: se soltar em cima de outro card,
            # isso também vira uma conexão (ver mouseReleaseEvent) —
            # alternativa a usar a alça 🔗 acima.
            self._drag_start_pos = self.pos()
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
        if self._connecting:
            self._connecting = False
            self._canvas._finish_connect(self.mapToScene(event.pos()))
            event.accept()
            return
        start = self._drag_start_pos
        self._drag_start_pos = None
        self._canvas._clear_drop_highlight()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        moved_enough = start is not None and (self.pos() - start).manhattanLength() > self._DROP_CONNECT_TOLERANCE
        if moved_enough:
            target = self._canvas._node_at(self.pos(), exclude=self)
            if target is not None:
                self.setPos(start)  # gesto era "conectar", não "mover" — volta pro lugar
                super().mouseReleaseEvent(event)
                self._canvas.request_connection(self, target)
                return
        super().mouseReleaseEvent(event)
        if moved_enough:
            self.moved.emit(self)

    def mouseDoubleClickEvent(self, event):
        if self._pin_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos()):
            return
        if self._menu_button_rect().adjusted(-3, -3, 3, 3).contains(event.pos()):
            return
        self.edit_requested.emit(self)

    # ── menu "⋮" (Editar / Remover) ──

    def _show_menu(self):
        if not self._canvas:
            return
        view = self._canvas._view
        menu = QMenu(view)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER};
                     color: {Colors.TEXT_PRIMARY}; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.PANEL_HOVER}; }}
        """)
        edit_action = menu.addAction("✏ Editar")
        remove_action = menu.addAction("🗑 Remover")
        anchor_scene = self.mapToScene(self._menu_button_rect().center())
        global_pos = view.mapToGlobal(view.mapFromScene(anchor_scene))
        # menu.exec() must fully return (its own modal loop completely torn
        # down) BEFORE opening the edit dialog — triggering it from inside
        # an action's own callback would nest a second modal loop directly
        # inside the menu's. No extra delay needed beyond that: the dialog
        # is now its own top-level window (see node_dialog.py), so it
        # grabs focus the same reliable way any QDialog does, regardless
        # of exactly when after the menu closes it opens.
        chosen = menu.exec(global_pos)
        if chosen is edit_action:
            self.edit_requested.emit(self)
        elif chosen is remove_action:
            self._canvas._delete_node(self)


class _ProgressionEdge(QGraphicsPathItem):
    """A connection between two cards, drawn as a neon arrow with a bright
    pulse travelling along it (src → dst), leaving from src's own rectangle
    border and its arrowhead tip touching dst's border exactly — not
    floating between the two centers with a gap. Selectable (click) so
    Del/the "✕" button can remove it; dragging near either tip re-targets
    that end to a different card instead of having to delete and recreate
    the connection — same mechanic as items/skill_tree/items.py's
    _EdgeItem."""

    ARROW_SIZE = 12
    ARROW_SPREAD = math.radians(24)
    LINE_WIDTH = 2.2
    ENDPOINT_GRAB_RADIUS = 16
    HIT_WIDTH = 14
    DELETE_BTN_R = 9

    def __init__(self, src: _ProgressionNode, dst: _ProgressionNode, canvas: "ProgressionCanvas" = None):
        super().__init__()
        self.src = src
        self.dst = dst
        self._canvas = canvas
        self._redirect_end: str | None = None
        self._hovering = False
        self._hover_end: str | None = None
        self._pt_a = src.center()  # border point on src, refreshed by update_path
        self._pt_b = dst.center()  # border point on dst, refreshed by update_path
        self.setZValue(1)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_path()

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        return stroker.createStroke(self.path())

    def _color(self) -> QColor:
        return QColor(self.src.color)

    def update_path(self):
        a = self.src.edge_point(self.dst.center())
        b = self.dst.edge_point(self.src.center())
        self._pt_a, self._pt_b = a, b
        ctrl = max(abs(b.x() - a.x()) * 0.4, 40)
        path = QPainterPath(a)
        path.cubicTo(QPointF(a.x() + ctrl, a.y()), QPointF(b.x() - ctrl, b.y()), b)
        self.prepareGeometryChange()
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        margin = self.ARROW_SIZE + 8 + self.DELETE_BTN_R
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def _delete_button_rect(self) -> QRectF:
        c = self.path().pointAtPercent(0.5)
        r = self.DELETE_BTN_R
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = self.path()
        base_color = self._color()
        selected = self.isSelected()
        if selected:
            line_color = base_color.lighter(145)
        elif self._hovering:
            line_color = base_color.lighter(125)
        else:
            line_color = base_color

        if selected:
            p.setPen(QPen(line_color, self.LINE_WIDTH + 0.6, Qt.PenStyle.DashLine))
            p.drawPath(path)
        else:
            # Neon glow — layered strokes, wide+faint fading into
            # narrow+bright, same look as the old ChainCanvas connections.
            for alpha, width in [(40, self.LINE_WIDTH + 5), (110, self.LINE_WIDTH + 2.2), (220, self.LINE_WIDTH)]:
                c = QColor(line_color)
                c.setAlpha(alpha)
                p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(path)

        self._draw_arrowhead(p, path, line_color)
        self._draw_flow_light(p, path, line_color)
        if self._hover_end:
            self._draw_endpoint_hint(p, path, line_color)
        if selected:
            self._draw_delete_button(p)

    def _draw_endpoint_hint(self, p: QPainter, path: QPainterPath, color: QColor):
        center = self._pt_a if self._hover_end == "src" else self._pt_b
        r = self.ENDPOINT_GRAB_RADIUS
        ring = QColor(color)
        ring.setAlpha(140)
        p.setPen(QPen(ring, 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(center, r, r)

    def _draw_delete_button(self, p: QPainter):
        rect = self._delete_button_rect()
        p.setPen(QPen(QColor("#F14C4C").darker(130), 1))
        p.setBrush(QBrush(QColor("#F14C4C")))
        p.drawEllipse(rect)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✕")

    def _draw_arrowhead(self, p: QPainter, path: QPainterPath, color: QColor):
        """Tip sits exactly at the path's own end (dst's border point,
        _pt_b) — no clearance gap, so it visibly touches the next card."""
        tip = path.pointAtPercent(1.0)
        back = path.pointAtPercent(0.9)
        dx, dy = tip.x() - back.x(), tip.y() - back.y()
        if dx == 0 and dy == 0:
            return
        angle = math.atan2(dy, dx)
        polygon = _arrow_head_polygon(tip, angle, self.ARROW_SIZE, self.ARROW_SPREAD)
        p.setPen(QPen(color.darker(130), 1))
        p.setBrush(QBrush(color))
        p.drawPolygon(polygon)

    def _draw_flow_light(self, p: QPainter, path: QPainterPath, color: QColor):
        """A bright pulse travelling src → dst on a loop, driven by
        ProgressionCanvas._flow_phase (see canvas.py's _advance_flow) — the
        "neon lines in motion" effect, drawn by re-stroking a short arc of
        this same path so the highlight can never spill outside the line's
        own geometry."""
        phase = getattr(self._canvas, "_flow_phase", None) if self._canvas else None
        if phase is None:
            return
        span = 0.05
        t0, t1 = max(0.0, phase - span), min(1.0, phase + span)
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
        dist_src = self._dist(pos, self._pt_a)
        dist_dst = self._dist(pos, self._pt_b)
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
                self._canvas._begin_redirect(self, near, self.mapToScene(pos))
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


class _ProgressionConnectPreview(QGraphicsPathItem):
    """Dashed preview shown while dragging a card's 🔗 handle (or an
    existing edge's tip, during a redirect) toward a target — anchored to
    an actual node so its start point recomputes against that node's own
    border (via edge_point) as the cursor moves, same as the real
    _ProgressionEdge it's about to become instead of floating from a fixed
    center point. A small badge with the 🔗 icon rides right at the cursor
    tip the whole drag, reading as "carrying" the connect handle."""

    BADGE_R = 11

    def __init__(self, anchor: _ProgressionNode, end: QPointF, color: str = None):
        super().__init__()
        self.setZValue(5)
        self._anchor = anchor
        self._start = anchor.center()
        self._end = end
        self._color = QColor(color) if color else QColor(Colors.ACCENT)
        self._rebuild()

    def set_end(self, end: QPointF):
        self.prepareGeometryChange()
        self._end = end
        self._rebuild()

    def _rebuild(self):
        self._start = self._anchor.edge_point(self._end)
        path = QPainterPath(self._start)
        path.lineTo(self._end)
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        margin = max(_ProgressionEdge.ARROW_SIZE + 6, self.BADGE_R + 5)
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self._color, _ProgressionEdge.LINE_WIDTH, Qt.PenStyle.DashLine))
        p.drawPath(self.path())
        dx, dy = self._end.x() - self._start.x(), self._end.y() - self._start.y()
        if dx != 0 or dy != 0:
            angle = math.atan2(dy, dx)
            polygon = _arrow_head_polygon(self._end, angle, _ProgressionEdge.ARROW_SIZE, _ProgressionEdge.ARROW_SPREAD)
            p.setPen(QPen(self._color.darker(130), 1))
            p.setBrush(QBrush(self._color))
            p.drawPolygon(polygon)
        self._draw_badge(p)

    def _draw_badge(self, p: QPainter):
        """The cursor visibly "carries" the 🔗 handle for the length of the
        drag — a small round badge glued to the drag's current end point."""
        r = self.BADGE_R
        p.setPen(QPen(self._color, 1.6))
        p.setBrush(QBrush(QColor(20, 26, 40, 235)))
        p.drawEllipse(self._end, r, r)
        p.setPen(self._color)
        p.setFont(QFont("Segoe UI Emoji", 9))
        p.drawText(QRectF(self._end.x() - r, self._end.y() - r, 2 * r, 2 * r),
                   Qt.AlignmentFlag.AlignCenter, _ProgressionNode.CONNECT_ICON)
