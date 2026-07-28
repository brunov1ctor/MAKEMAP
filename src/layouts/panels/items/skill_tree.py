"""SkillTreeCanvas — the ÁRVORE DE HABILIDADES right column of the
Habilidades row.

A node graph on a QGraphicsView: browser-style tabs across the top (one
chip per guia, a "✕" to fechar a ativa, um "+" no final), rectangular
card nodes — a square showing the skill's own image (ou o ícone, se não
tiver imagem) + name + rank (3/5), com um leve brilho ao passar o mouse —
conexões desenhadas como setas (com uma luz percorrendo a extensão delas,
pra dar ideia de fluxo src → dst) entre os cards, zoom controls bottom-right.

Interações que substituem o antigo combo "Evoluir de:" do Editor de
Habilidade:
  - "+" na barra de abas abre um painel de criação (troca de página com o
    canvas, mesmo padrão do CategoryEditPanel em mobs/) pedindo o nome da
    aba, a habilidade inicial (picker de catálogo, mesma UI de "informações
    extras de mobs": `_CatalogPickerDialog`) e opcionalmente uma cor de
    tema/borda e uma cor de texto (mesma UI de duas cores + um picker
    compartilhado da criação de categoria de mob) — viram o padrão do chip
    da aba, da borda e do texto dos nós dessa guia.
  - "+ Nó" no rodapé abre o mesmo picker de habilidade pra adicionar
    qualquer outra habilidade como nó solto na aba ativa.
  - Cada card tem uma alcinha 🔗 (ícone deliberadamente diferente do "+"
    usado pra adicionar nó) — arrastar dela até outro card cria a conexão
    entre os dois; selecionar uma conexão e apertar Delete a remove.
  - Arrastar o corpo do card (fora da alça) só reposiciona, como antes.
  - Cada card tem seus PRÓPRIOS botões +/− flanqueando o "rank_current/
    rank_max" (o "0/5" que antes não tinha nenhuma UI pra editar) — cada
    habilidade ajusta o rank dela direto no próprio card, sem precisar
    selecionar nada primeiro nem passar por um painel à parte.

`_TreeStatsPanel` é uma coluna fixa ao lado do canvas (espaço de layout de
verdade, não um card flutuante por cima) mostrando o agregado DA ÁRVORE
INTEIRA — mini radar (Dano/Alcance/Veloc./Custo/Utilidade) somando todo nó
com rank_current > 0 na aba ativa, e o total de "Pontos gastos" (soma do
rank_current de todo nó) — estilo árvore de talentos, não é por habilidade
individual. O teto de rank (rank_max) e o dano/escalonamento de cada rank
vêm do próprio Editor de Habilidade — aba Dano, campo "Rank Máximo" + a
tabela por rank (ver skill_editor.py) — não são mais fixos em 5/iguais pra
toda habilidade.

The whole graph for the active tab (nodes, edges, and the tab's theme
colors) is persisted as one JSON document per element in the skill_trees
table (see migration 12) — theme_color/text_color live inside that same
blob, no new DB columns. uow may be None (no project open) — then it
degrades to in-memory only.
"""

from __future__ import annotations

import json
import logging
import math
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QPushButton,
    QLineEdit, QGraphicsView, QGraphicsScene, QGraphicsObject,
    QGraphicsPathItem, QSizePolicy, QFrame, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QPixmap, QPolygonF,
)

from src.styles.tokens import Colors
from src.services.project_assets import resolve_asset_path
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.mobs.edit_widgets import _CatalogPickerDialog
from src.layouts.panels.mobs.category_edit_panel import _ColorSwatch, _SharedColorPicker
from src.layouts.panels.items.constants import panel_frame_style, sub_header, SKILL_FLAGS

logger = logging.getLogger("MAKEMAP")


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
    HANDLE_R = 9  # connect-handle radius
    CONNECT_ICON = "🔗"  # deliberately different from the "+" used to add nodes

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
        self.setAcceptHoverEvents(True)
        self.setToolTip("Arraste o card para mover • arraste o 🔗 para conectar • +/− ajusta o rank")

    def boundingRect(self) -> QRectF:
        hw, hh = self.NODE_W / 2, self.NODE_H / 2
        # card + label strip below + enough margin on every side for the
        # hover halo / "alive" pulse ring / connect-handle circle, all of
        # which paint a few px past the card's own edge — too tight a
        # margin here means Qt only clears part of what paint() actually
        # draws each frame, leaving a smeared "ghost" trail behind exactly
        # like the old value (4px) did for the handle/hover glow.
        m = 10
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
        # add nodes, so the two actions read as clearly different.
        handle_rect = self._handle_rect()
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.setBrush(QBrush(QColor(20, 26, 40, 230)))
        p.drawEllipse(handle_rect)
        p.setFont(QFont("Segoe UI Emoji", 8))
        p.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, self.CONNECT_ICON)

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
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
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
        if self._handle_rect().contains(event.pos()):
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

    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "SkillTreeCanvas" = None):
        super().__init__()
        self.src = src
        self.dst = dst
        self._canvas = canvas
        self.setZValue(1)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor(Colors.ACCENT), self.LINE_WIDTH))
        self.update_path()

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
        margin = self.ARROW_SIZE + 6
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = self.path()
        base_color = self._theme_color()
        if self.isSelected():
            line_color = base_color.lighter(145)
            p.setPen(QPen(line_color, self.LINE_WIDTH + 0.6, Qt.PenStyle.DashLine))
        else:
            line_color = base_color
            pen_color = QColor(line_color)
            pen_color.setAlpha(170)
            p.setPen(QPen(pen_color, self.LINE_WIDTH))
        p.drawPath(path)
        self._draw_arrowhead(p, path, line_color)
        self._draw_flow_light(p, path, line_color)

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


class _TreeView(QGraphicsView):
    """QGraphicsView with wheel-zoom and a Delete key that removes whatever
    connection is currently selected (nodes are dragged/connected directly
    via _NodeItem, not from here)."""

    def __init__(self, canvas: "SkillTreeCanvas"):
        super().__init__(canvas._scene)
        self._canvas = canvas
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._canvas.zoom_by(factor)

    def mousePressEvent(self, event):
        # Self-heals a stuck connect-preview from a previous drag whose
        # release never reached the node (e.g. released outside the
        # window) — the very next click anywhere in the canvas clears it
        # instead of leaving the ghost line stranded indefinitely.
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))
        self.setFocus()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Safety net: the node's own mouseReleaseEvent normally clears
        # _connecting_from already — this only fires if that release got
        # lost somewhere (e.g. the drag left the OS window before letting
        # go of the button), so the temp arrow doesn't linger as a ghost.
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._canvas._delete_selected_edges()
            return
        super().keyPressEvent(event)


class _TreeTabCreatePanel(QFrame):
    """Painel de criação de uma nova aba/árvore — troca de lugar com o
    canvas (ver SkillTreeCanvas._stack), o mesmo padrão do CategoryEditPanel
    (mobs/category_edit_panel.py): nome da aba + habilidade inicial,
    escolhida num picker de catálogo (mesma UI de "+ Vincular Habilidade"
    das informações extras de mobs). Sem QDialog, sem QMessageBox."""

    save_requested = Signal(str, dict, str, str)  # (tab_name, initial_skill, theme_color, text_color)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._catalog_provider = lambda: []
        self._picked_skill: dict | None = None
        self._color_target: str | None = None  # "theme" | "text" | None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("NOVA ABA")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(title)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        name_lbl = QLabel("Nome da aba")
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Ex.: Fogo, Terra, Água…")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px 6px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._name_edit.textEdited.connect(lambda _t: self._set_error(""))
        outer.addWidget(self._name_edit)

        skill_lbl = QLabel("Habilidade inicial")
        skill_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(skill_lbl)
        self._skill_btn = QPushButton("Escolher habilidade inicial")
        self._skill_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skill_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 6px 10px;
                font-size: 10px; text-align: left; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._skill_btn.clicked.connect(self._on_pick_skill)
        outer.addWidget(self._skill_btn)

        # Cor tema/borda — mesma UI (um _SharedColorPicker por baixo de dois
        # _ColorSwatch) da criação de categoria de mob (CategoryEditPanel).
        # Vira o padrão do chip da aba, da borda e do texto dos nós dessa
        # guia (ver SkillTreeCanvas._active_theme_color/_active_text_color).
        theme_lbl = QLabel("Cor do tema (opcional)")
        theme_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(theme_lbl)
        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        self._theme_swatch = _ColorSwatch("Tema / Borda")
        self._theme_swatch.clicked.connect(lambda: self._activate_color_target("theme"))
        self._theme_swatch.cleared.connect(lambda: self._on_swatch_cleared("theme"))
        swatches_row.addWidget(self._theme_swatch, 1)
        self._text_swatch = _ColorSwatch("Texto do Nó")
        self._text_swatch.clicked.connect(lambda: self._activate_color_target("text"))
        self._text_swatch.cleared.connect(lambda: self._on_swatch_cleared("text"))
        swatches_row.addWidget(self._text_swatch, 1)
        outer.addLayout(swatches_row)

        self._color_picker = _SharedColorPicker()
        self._color_picker.color_changed.connect(self._on_shared_color_changed)
        self._color_picker.hide()
        outer.addWidget(self._color_picker)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9px; background: transparent; border: none;")
        self._error_lbl.hide()
        outer.addWidget(self._error_lbl)

        outer.addStretch()

        self._save_btn = QToolButton()
        self._save_btn.setText("✓ Criar Aba")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setMinimumHeight(32)
        self._save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._save_btn.setStyleSheet(f"""
            QToolButton {{ background: {Colors.SUCCESS}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ background: #7bc97e; }}
        """)
        self._save_btn.clicked.connect(self._on_save_clicked)
        outer.addWidget(self._save_btn)

    def set_catalog_provider(self, provider):
        self._catalog_provider = provider

    def load(self):
        self._name_edit.clear()
        self._picked_skill = None
        self._skill_btn.setText("Escolher habilidade inicial")
        self._theme_swatch.set_color("")
        self._text_swatch.set_color("")
        self._color_picker.hide()
        self._color_target = None
        self._set_error("")
        self._name_edit.setFocus()

    def _set_error(self, message: str):
        self._error_lbl.setText(message)
        self._error_lbl.setVisible(bool(message))

    def _swatch_for_target(self, target: str) -> _ColorSwatch:
        return {"theme": self._theme_swatch, "text": self._text_swatch}[target]

    def _activate_color_target(self, target: str):
        """Clicar num swatch carrega a cor dele no único picker compartilhado
        e o mostra; clicar de novo no MESMO swatch (picker já aberto nele)
        só fecha — mesmo padrão de CategoryEditPanel._activate_color_target."""
        if self._color_target == target and self._color_picker.isVisible():
            self._color_picker.hide()
            self._color_target = None
            return
        self._color_target = target
        self._color_picker.set_color(self._swatch_for_target(target).color())
        self._color_picker.show()

    def _on_shared_color_changed(self, hex_color: str):
        if self._color_target:
            self._swatch_for_target(self._color_target).set_color(hex_color)

    def _on_swatch_cleared(self, target: str):
        if target == self._color_target:
            self._color_picker.hide()
            self._color_target = None

    def _on_pick_skill(self):
        dlg = _CatalogPickerDialog("Habilidade Inicial", "Buscar habilidade", self._catalog_provider(), parent=self)
        picked_id = dlg.exec()
        if not picked_id:
            return
        skill = next((sk for sk in self._catalog_provider() if sk.get("id") == picked_id), None)
        if not skill:
            return
        self._picked_skill = skill
        self._skill_btn.setText(f"{skill.get('icon') or '✨'}  {skill.get('name', '—')}")
        self._set_error("")

    def _on_save_clicked(self):
        name = self._name_edit.text().strip()
        if not name:
            self._set_error("Digite um nome para a aba.")
            self._name_edit.setFocus()
            return
        if not self._picked_skill:
            self._set_error("Escolha a habilidade inicial.")
            return
        self.save_requested.emit(name, self._picked_skill, self._theme_swatch.color(), self._text_swatch.color())


class _MiniRadar(QWidget):
    """A tiny 5-axis radar chart for the selected node's skill — same idea
    as the reference "Estatísticas Finais" mob panel (a filled polygon over
    a few axes + a big number in the middle), scaled down for one skill
    instead of a full character sheet."""

    AXES = ["Dano", "Alcance", "Veloc.", "Custo", "Utilid."]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedSize(104, 104)
        self._values = [0.0] * len(self.AXES)
        self._center_text = ""

    def set_values(self, values: list[float], center_text: str = ""):
        self._values = values
        self._center_text = center_text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self.AXES)
        cx, cy = self.width() / 2, self.height() / 2 - 4
        radius = min(cx, cy) - 18

        def axis_point(i: int, frac: float) -> QPointF:
            ang = 2 * math.pi * i / n - math.pi / 2
            return QPointF(cx + radius * frac * math.cos(ang), cy + radius * frac * math.sin(ang))

        # Rings
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for frac in (0.33, 0.66, 1.0):
            p.drawPolygon(QPolygonF([axis_point(i, frac) for i in range(n)]))
        # Spokes
        for i in range(n):
            p.drawLine(QPointF(cx, cy), axis_point(i, 1.0))

        # Axis labels
        p.setPen(QColor(Colors.TEXT_MUTED))
        p.setFont(QFont("Segoe UI", 6))
        for i, label in enumerate(self.AXES):
            pt = axis_point(i, 1.16)
            p.drawText(QRectF(pt.x() - 22, pt.y() - 6, 44, 12), Qt.AlignmentFlag.AlignCenter, label)

        # Value polygon — a small floor (0.05) so a 0-value axis still shows
        # a sliver instead of collapsing the whole shape onto the center.
        pts = [axis_point(i, max(0.05, min(1.0, v))) for i, v in enumerate(self._values)]
        fill = QColor(Colors.ACCENT)
        fill.setAlpha(90)
        p.setBrush(QBrush(fill))
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.drawPolygon(QPolygonF(pts))

        if self._center_text:
            p.setPen(QColor(Colors.TEXT_PRIMARY))
            p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 30, cy - 10, 60, 16), Qt.AlignmentFlag.AlignCenter, self._center_text)
            p.setPen(QColor(Colors.TEXT_MUTED))
            p.setFont(QFont("Segoe UI", 6))
            p.drawText(QRectF(cx - 30, cy + 5, 60, 10), Qt.AlignmentFlag.AlignCenter, "PODER")


class _TreeStatsPanel(QWidget):
    """Floats beside the canvas — NOT its own nested box and no divider
    line either: the whole SkillTreeCanvas (view + this) already sits
    inside one shared glass frame (see SkillTreeCanvas.__init__'s `frame`/
    panel_frame_style), so this stays fully borderless/transparent, sized
    to its own content and pinned to the bottom of its column (see
    SkillTreeCanvas._build_browse_page's `stats_col` — an addStretch()
    above this widget, not addWidget(alignment=AlignBottom), is what
    actually keeps it flush against the footer's zoom controls below,
    instead of stretched full-height or leaving a gap above the footer).
    Reads as stats floating in the same panel as the nodes, not a second
    panel stacked inside the first. Shows the ACTIVE TAB's aggregate stats
    — the combined mini radar + totals of every node with rank_current > 0
    (i.e. actually invested), plus "Pontos gastos" as the last line of that
    same text block (no separator — one continuous block, see set_stats).
    Per-node rank +/- lives on each card itself now (see _NodeItem.
    _rank_button_rects/mousePressEvent), not here — this panel is
    read-only, tree-wide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Plain QWidget + an unprefixed "background: transparent; border:
        # none;" — same exact recipe already working for other canvas
        # overlays in this app (see _ResizeGrip in canvas/overlays/
        # minimap.py). QFrame + an ID-selector rule (the previous attempt)
        # kept painting an opaque box despite the rule; this is the
        # established, verified-working pattern instead.
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedWidth(230)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 4, 8)
        lay.setSpacing(6)

        title = QLabel("ESTATÍSTICAS DA ÁRVORE")
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(title)

        # Radar ao lado do texto (não empilhado em cima dele).
        content_row = QHBoxLayout()
        content_row.setSpacing(10)
        self._radar = _MiniRadar()
        content_row.addWidget(self._radar, alignment=Qt.AlignmentFlag.AlignTop)

        # "Pontos gastos" é só mais uma linha do mesmo bloco — sem separador
        # nem label à parte (ver referência: as 5 linhas formam um bloco só).
        self._stats_lbl = QLabel("")
        self._stats_lbl.setWordWrap(True)
        self._stats_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        content_row.addWidget(self._stats_lbl, 1)
        lay.addLayout(content_row)

    def set_stats(self, dano_total: float, alcance: float, mana_total: float,
                  speed: float, util: float, points_spent: int, node_count: int):
        values = [
            min(1.0, dano_total / 400),
            min(1.0, alcance / 30),
            speed,
            min(1.0, mana_total / 400),
            util,
        ]
        self._radar.set_values(values, center_text=f"{dano_total:.0f}")
        self._stats_lbl.setText(
            f"Dano total: {dano_total:.0f}\nAlcance: {alcance:.0f}m\n"
            f"Custo total: {mana_total:.0f}\nNós ativos: {node_count}\n"
            f"Pontos gastos: {points_spent}"
        )

    def set_empty(self, points_spent: int = 0):
        self._radar.set_values([0, 0, 0, 0, 0], center_text="0")
        self._stats_lbl.setText(f"Nenhum nó com rank investido ainda.\nPontos gastos: {points_spent}")


class SkillTreeCanvas(QWidget):
    """The whole right column: browser-style tabs, the node view and zoom
    controls, plus the "+ Nova aba" create page swapped in over it."""

    def __init__(self, uow=None, skills_provider=None, catalog_provider=None, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._skills_provider = skills_provider or (lambda: [])
        self._catalog_provider = catalog_provider or (lambda: [])
        self._trees: list[dict] = []
        self._active_key: str = ""
        self._nodes: dict[str, _NodeItem] = {}
        self._edges: list[_EdgeItem] = []
        self._selected_node: _NodeItem | None = None
        self._connecting_from: _NodeItem | None = None
        self._temp_edge_line: "_ConnectPreviewItem | None" = None
        self._zoom = 1.0
        self._active_theme_color = ""  # active tree's node border/chip theme, if set
        self._active_text_color = ""   # active tree's node name/rank text color, if set

        # Drives the small light travelling along each edge (see
        # _EdgeItem._draw_flow_light) — only runs while the canvas is
        # actually visible (see showEvent/hideEvent below).
        self._flow_phase = 0.0
        self._flow_timer = QTimer(self)
        self._flow_timer.timeout.connect(self._advance_flow)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        outer_wrap = QVBoxLayout(self)
        outer_wrap.setContentsMargins(0, 0, 0, 0)
        outer_wrap.addWidget(frame)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 12)
        frame_layout.setSpacing(8)

        self._stack = QStackedWidget()
        frame_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_browse_page())

        self._tab_creator = _TreeTabCreatePanel()
        self._tab_creator.set_catalog_provider(lambda: self._catalog_provider())
        self._tab_creator.save_requested.connect(self._on_tab_creator_save)
        self._tab_creator.close_requested.connect(self._on_tab_creator_close)
        self._stack.addWidget(self._tab_creator)

    def showEvent(self, event):
        super().showEvent(event)
        self._flow_timer.start(40)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._flow_timer.stop()

    def _advance_flow(self):
        self._flow_phase = (self._flow_phase + 0.012) % 1.0
        for e in self._edges:
            e.update()
        for n in self._nodes.values():
            n.update()  # drives the card's "alive" breathing ring

    # ── UI: browse page (tabs + view + footer) ──

    def _build_browse_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        outer.addWidget(sub_header("Árvore de Habilidades"))

        # ── Browser-style tab row: one chip per guia + a trailing "+" ──
        self._tabs_row = QHBoxLayout()
        self._tabs_row.setSpacing(2)
        outer.addLayout(self._tabs_row)

        self._empty_hint = QLabel("Nenhuma guia ainda — clique em “+” para criar uma.")
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-style: italic; background: transparent; border: none;")
        outer.addWidget(self._empty_hint)

        # ── Graphics view ──
        view_row = QHBoxLayout()
        view_row.setSpacing(8)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-1000, -1000, 2000, 2000)
        self._view = _TreeView(self)
        view_row.addWidget(self._view, 1)

        # Fixed sidebar column, real layout space beside the canvas (not a
        # floating overlay on top of it) — the whole active tab's aggregate
        # stats. Per-node rank +/- lives on each card now (see _NodeItem).
        # An explicit addStretch() ABOVE the panel (rather than relying on
        # addWidget(..., alignment=AlignBottom), which left a gap) is what
        # actually pins it flush against the footer's zoom controls below,
        # sized to its own content instead of stretched full-height.
        self._tree_stats_panel = _TreeStatsPanel()
        stats_col = QVBoxLayout()
        stats_col.addStretch()
        stats_col.addWidget(self._tree_stats_panel)
        view_row.addLayout(stats_col)
        outer.addLayout(view_row, 1)

        # ── Footer: "+ Nó" (left) + hints + zoom (right) ──
        footer = QHBoxLayout()
        self._add_node_btn = QToolButton()
        self._add_node_btn.setText("+ Nó")
        self._add_node_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_node_btn.setToolTip("Adicionar outra habilidade como nó nesta guia")
        self._add_node_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT}; border-radius: 4px; padding: 2px 8px; font-size: 9px; font-weight: bold; }}
            QToolButton:hover {{ background: {Colors.ACCENT_DIM}; }}
            QToolButton:disabled {{ color: {Colors.TEXT_MUTED}; border-color: {Colors.BORDER_SUBTLE}; background: transparent; }}
        """)
        self._add_node_btn.clicked.connect(self._on_add_node_clicked)
        footer.addWidget(self._add_node_btn)

        hints = QLabel("Arraste o card pra mover • +/− ajusta o rank • alça 🔗 conecta • Del remove a conexão selecionada")
        hints.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        # Don't let this long line dictate the column's minimum width (it would
        # break the 2×3 grid alignment) — it can clip if the column is narrow.
        hints.setMinimumWidth(1)
        hints.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(hints)
        footer.addStretch()
        for text, cb in [("－", lambda: self.zoom_by(1 / 1.15)),
                         (None, None),
                         ("＋", lambda: self.zoom_by(1.15)),
                         ("⤢", self._reset_zoom)]:
            if text is None:
                self._zoom_lbl = QLabel("100%")
                self._zoom_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
                self._zoom_lbl.setFixedWidth(38)
                self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                footer.addWidget(self._zoom_lbl)
                continue
            b = QToolButton()
            b.setText(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; font-size: 11px;
                    min-width: 22px; min-height: 20px; }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            """)
            b.clicked.connect(cb)
            footer.addWidget(b)
        outer.addLayout(footer)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return page

    # ── public entry ──

    def reload(self):
        """(Re)load every guia + the active one's nodes from the DB."""
        self._trees = self._load_trees()
        if not self._active_key or self._active_key not in {t["tree_key"] for t in self._trees}:
            self._active_key = self._trees[0]["tree_key"] if self._trees else ""
        self._refresh_tab_bar()
        self._load_active_tree()

    def create_tab_for_skill(self, skill: dict, tab_name: str, theme_color: str = "", text_color: str = "") -> str:
        """Cria (ou reaproveita, se o nome já existir) uma aba com esse nome
        e a deixa ativa, com um nó raiz pra `skill` — chamado pelo painel de
        criação de aba ("+" na barra de abas) depois que o usuário escolhe a
        habilidade inicial no picker de catálogo. O ícone do nó vem do
        próprio ícone da habilidade. `theme_color`/`text_color` (escolhidos
        no mesmo painel, mesma UI de cor da criação de categoria de mob)
        viram o tema dessa aba — borda/chip e texto dos nós — guardados
        dentro do próprio blob `data` (não são coluna do banco)."""
        tab_name = tab_name.strip() or "Nova Guia"
        key = tab_name.lower().replace(" ", "_")
        if self._uow:
            existing = self._uow.skill_trees.get_all_ordered()
            if not any(t["tree_key"] == key for t in existing):
                initial_data = json.dumps(
                    {"nodes": [], "edges": [], "theme_color": theme_color, "text_color": text_color},
                    ensure_ascii=False,
                )
                self._uow.skill_trees.upsert(
                    key, name=tab_name, icon=skill.get("icon") or "✨",
                    sort_order=len(existing), data=initial_data)
        self._active_key = key
        self.reload()
        if self._active_tree():
            self._ensure_node(skill)
            self._persist()
        return key

    def show_tab_for_skill(self, skill_id: str):
        """Troca pra guia onde a habilidade já tem nó — chamado sempre que
        ela é selecionada na lista, pra árvore "seguir" o que está sendo
        editado em vez de exigir um clique numa aba pra ver."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            if any(n.get("id") == skill_id for n in data.get("nodes", [])):
                if tree["tree_key"] != self._active_key:
                    self._active_key = tree["tree_key"]
                    self.reload()
                return

    @staticmethod
    def _skill_rank_max(skill: dict) -> int:
        """Rank Máximo definido no Editor de Habilidade (aba Dano — ver
        skill_editor.py._rank_max_spin), lido de dentro do `stats` JSON.
        Falls back to 5 pra habilidades salvas antes desse campo existir."""
        stats = _parse_json_dict(skill.get("stats"))
        try:
            return max(1, min(10, int(stats.get("rank_max") or 5)))
        except (TypeError, ValueError):
            return 5

    def refresh_node_metadata(self, skill_id: str, skill: dict):
        """Atualiza nome/ícone/imagem/rank-máximo de um nó já existente pra
        essa habilidade, em qualquer aba onde ela exista — chamado ao salvar
        a habilidade no editor (mudar "Rank Máximo" lá se reflete aqui,
        inclusive baixando rank_current de nós que já tinham investido mais
        pontos do que o novo teto permite). Não cria nó nenhum (isso só
        acontece via "+ Nova aba"/"+ Nó"/arrastar a alça, direto no canvas)."""
        rank_max = self._skill_rank_max(skill)
        if not self._uow:
            node = self._nodes.get(skill_id)
            if node:
                node.name = skill.get("name", node.name)
                node.icon = skill.get("icon") or node.icon
                node.set_image_path(skill.get("image_path") or node.image_path)
                node.rank_max = rank_max
                node.rank_current = min(node.rank_current, rank_max)
                node.update()
            return
        touched_active = False
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            target = next((n for n in nodes if n.get("id") == skill_id), None)
            if not target:
                continue
            target["name"] = skill.get("name", target.get("name"))
            target["icon"] = skill.get("icon") or target.get("icon")
            target["image_path"] = skill.get("image_path") or target.get("image_path", "")
            target["rank_max"] = rank_max
            target["rank_current"] = min(int(target.get("rank_current", 0)), rank_max)
            self._uow.skill_trees.upsert(tree["tree_key"], data=json.dumps(data, ensure_ascii=False))
            if tree["tree_key"] == self._active_key:
                touched_active = True
        if touched_active:
            node = self._nodes.get(skill_id)
            if node:
                node.name = skill.get("name", node.name)
                node.icon = skill.get("icon") or node.icon
                node.set_image_path(skill.get("image_path") or node.image_path)
                node.rank_max = rank_max
                node.rank_current = min(node.rank_current, rank_max)
                node.update()
                self._refresh_tree_stats()

    def remove_skill_node(self, skill_id: str):
        """Chamado pelo painel ao excluir uma habilidade — tira o nó dela
        (e qualquer conexão que o referencie) de qualquer guia onde exista,
        pra não sobrar um nó órfão apontando pra um id que já era."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            if not any(n.get("id") == skill_id for n in nodes):
                continue
            data["nodes"] = [n for n in nodes if n.get("id") != skill_id]
            data["edges"] = [e for e in data.get("edges", []) if skill_id not in e]
            self._uow.skill_trees.upsert(tree["tree_key"], data=json.dumps(data, ensure_ascii=False))
            if tree["tree_key"] == self._active_key:
                self._load_active_tree()

    def _ensure_node(self, skill: dict) -> _NodeItem:
        """Nó existente pro id, ou um novo posicionado perto do centro da
        vista (deslocado a cada novo nó pra não empilhar em cima). O teto de
        rank vem do próprio "Rank Máximo" definido na habilidade (Editor de
        Habilidade, aba Dano) — não mais um 5 fixo pra toda habilidade."""
        existing = self._nodes.get(skill.get("id"))
        if existing:
            existing.name = skill.get("name", existing.name)
            existing.icon = skill.get("icon") or existing.icon
            existing.set_image_path(skill.get("image_path") or existing.image_path)
            return existing
        # `skill` aqui costuma ser uma row do catálogo (id/name/icon/rarity/
        # image_path) sem o `stats` JSON completo — resolve o registro cheio
        # pra ler o Rank Máximo real da habilidade.
        full = next((sk for sk in (self._skills_provider() or []) if sk.get("id") == skill.get("id")), None)
        rank_max = self._skill_rank_max(full or skill)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        offset = (len(self._nodes) % 5) * 24
        data = {
            "id": skill["id"],
            "name": skill.get("name", "Habilidade"),
            "icon": skill.get("icon") or "✨",
            "image_path": skill.get("image_path") or "",
            "color": item_rarity_color(skill.get("rarity", "common")),
            "x": center.x() + offset, "y": center.y() + offset,
            "rank_current": 0, "rank_max": rank_max,
        }
        return self._add_node_item(data)

    def _load_trees(self) -> list[dict]:
        if not self._uow:
            return []
        return self._uow.skill_trees.get_all_ordered()

    # ── tab bar ──

    def _refresh_tab_bar(self):
        while self._tabs_row.count():
            item = self._tabs_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tree in self._trees:
            self._tabs_row.addWidget(self._make_tab_chip(tree))
        self._tabs_row.addWidget(self._make_new_tab_chip())
        self._tabs_row.addStretch()
        self._empty_hint.setVisible(not self._trees)
        self._add_node_btn.setEnabled(self._active_tree() is not None)

    def _make_tab_chip(self, tree: dict) -> QWidget:
        chip = QWidget()
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        active = tree["tree_key"] == self._active_key
        # The tab's own theme color (chosen at creation, see
        # _TreeTabCreatePanel) drives the chip's active-state accent when
        # set — falls back to the app-wide accent otherwise.
        theme_color = self._parse_data(tree.get("data")).get("theme_color") or ""
        accent = theme_color or Colors.ACCENT
        btn = QToolButton()
        btn.setText(f"{tree.get('icon', '')} {tree['name']}".strip())
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.TEXT_MUTED};
                border: none; border-bottom: 2px solid transparent;
                padding: 4px 8px; font-size: 9px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.TEXT_SECONDARY}; }}
            QToolButton:checked {{ color: {accent}; border-bottom: 2px solid {accent}; }}
        """)
        btn.clicked.connect(lambda _c=False, key=tree["tree_key"]: self._switch_active_tab(key))
        lay.addWidget(btn)
        if active:
            close_btn = QToolButton()
            close_btn.setText("✕")
            close_btn.setFixedSize(14, 14)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setToolTip("Excluir esta guia")
            close_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 9px; }}
                QToolButton:hover {{ color: {Colors.ERROR}; }}
            """)
            close_btn.clicked.connect(lambda _c=False, key=tree["tree_key"]: self._delete_tab(key))
            lay.addWidget(close_btn)
        return chip

    def _make_new_tab_chip(self) -> QToolButton:
        btn = QToolButton()
        btn.setText("+")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Nova aba")
        btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.ACCENT}; border: none;
                padding: 4px 8px; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        btn.clicked.connect(self._open_tab_creator)
        return btn

    def _switch_active_tab(self, key: str):
        if key == self._active_key:
            return
        self._active_key = key
        self.reload()

    def _delete_tab(self, key: str):
        """Exclui a guia direto no clique do "✕" do chip — sem QMessageBox
        (isso abriria uma janela nativa fora do app; mesmo no-confirm
        precedent do "⋮" das categorias de mob, ver panel_category_mixin.py's
        _on_delete_category)."""
        tree = next((t for t in self._trees if t["tree_key"] == key), None)
        if not tree:
            return
        if self._uow:
            self._uow.skill_trees.delete_tree(key)
        if self._active_key == key:
            self._active_key = ""
        self.reload()
        logger.info("Guia da árvore de habilidades excluída: %s", key)

    # ── tab creator page ──

    def _open_tab_creator(self):
        self._tab_creator.load()
        self._stack.setCurrentIndex(1)

    def _on_tab_creator_save(self, name: str, skill: dict, theme_color: str, text_color: str):
        self.create_tab_for_skill(skill, name, theme_color=theme_color, text_color=text_color)
        self._stack.setCurrentIndex(0)

    def _on_tab_creator_close(self):
        self._stack.setCurrentIndex(0)

    # ── "+ Nó" ──

    def _on_add_node_clicked(self):
        if not self._active_tree():
            return
        dlg = _CatalogPickerDialog("Vincular Habilidade", "Buscar habilidade", self._catalog_provider(), parent=self._view)
        picked_id = dlg.exec()
        if not picked_id:
            return
        skill = next((sk for sk in self._catalog_provider() if sk.get("id") == picked_id), None)
        if not skill:
            return
        self._ensure_node(skill)
        self._persist()

    # ── scene <-> data ──

    def _active_tree(self) -> dict | None:
        for t in self._trees:
            if t["tree_key"] == self._active_key:
                return t
        return None

    def _load_active_tree(self):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._selected_node = None
        tree = self._active_tree()
        if not tree:
            self._active_theme_color = ""
            self._active_text_color = ""
            self._refresh_tree_stats()
            return
        data = self._parse_data(tree.get("data"))
        self._active_theme_color = data.get("theme_color") or ""
        self._active_text_color = data.get("text_color") or ""
        for nd in data.get("nodes", []):
            self._add_node_item(nd)
        for edge in data.get("edges", []):
            src = self._nodes.get(edge[0])
            dst = self._nodes.get(edge[1])
            if src and dst:
                self._add_edge_item(src, dst)
        self._refresh_tree_stats()

    def _add_node_item(self, data: dict) -> _NodeItem:
        node = _NodeItem(data, self)
        node.clicked.connect(self._on_node_clicked)
        node.moved.connect(lambda n: self._persist())
        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        return node

    def _add_edge_item(self, src: _NodeItem, dst: _NodeItem) -> _EdgeItem:
        edge = _EdgeItem(src, dst, self)
        self._scene.addItem(edge)
        self._edges.append(edge)
        return edge

    # ── connecting nodes by dragging a node's handle ──

    def _begin_connect(self, node: _NodeItem, scene_pos: QPointF):
        # Defensive: a stale preview from an unfinished previous drag (see
        # _TreeView.mousePressEvent/mouseReleaseEvent's cleanup) must not
        # leak when a fresh connect starts.
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        self._connecting_from = node
        preview = _ConnectPreviewItem(node.center(), scene_pos, self)
        self._scene.addItem(preview)
        self._temp_edge_line = preview

    def _update_connect(self, scene_pos: QPointF):
        if self._connecting_from and self._temp_edge_line:
            self._temp_edge_line.set_end(scene_pos)

    def _finish_connect(self, scene_pos: QPointF):
        src = self._connecting_from
        self._connecting_from = None
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        if not src:
            return
        dst = next(
            (n for n in self._nodes.values() if n is not src and n.sceneBoundingRect().contains(scene_pos)),
            None,
        )
        if dst and not self._edge_exists(src, dst):
            self._add_edge_item(src, dst)
            self._persist()

    def _delete_selected_edges(self):
        selected = [e for e in self._edges if e.isSelected()]
        if not selected:
            return
        for e in selected:
            self._scene.removeItem(e)
            self._edges.remove(e)
        self._persist()

    # ── interaction ──

    def _on_node_clicked(self, node: _NodeItem, modifiers):
        self._select_node(node)

    def _select_node(self, node: _NodeItem | None):
        for e in self._edges:
            e.setSelected(False)
        if self._selected_node and self._selected_node is not node:
            self._selected_node.set_selected(False)
        self._selected_node = node
        if node:
            node.set_selected(True)

    # ── tree-wide stats panel + per-node rank ──

    def _skill_metrics_for(self, node: _NodeItem) -> dict:
        """Resolves the full skill record behind a node (name/icon alone
        don't carry cooldown/mana_cost/rank_damage) and reads the ranked
        Dano Base/Escalonamento for the node's CURRENT rank (falls back to
        rank 1's row as a preview when rank_current is still 0)."""
        full = next((sk for sk in (self._skills_provider() or []) if sk.get("id") == node.node_id), None)
        if not full:
            return {}
        stats = _parse_json_dict(full.get("stats"))
        rank_damage = stats.get("rank_damage") or []
        idx = max(0, node.rank_current - 1)
        entry = rank_damage[idx] if idx < len(rank_damage) else {}
        flags_on = sum(1 for key, _label, default in SKILL_FLAGS if stats.get(key, default))
        return {
            "dano_base": entry.get("dano_base", 0),
            "escalonamento": entry.get("escalonamento", 0),
            "alcance": stats.get("alcance", 0),
            "cooldown": full.get("cooldown", 0),
            "mana_cost": full.get("mana_cost", 0),
            "flags_on": flags_on,
            "flags_total": len(SKILL_FLAGS),
        }

    def _refresh_tree_stats(self):
        """Aggregates every node with rank_current > 0 (actually invested)
        in the active tab into the sidebar panel — the whole build's
        totals, not any single node's. Called after anything that can
        change a node's rank/existence (see _persist()/_load_active_tree)."""
        points_spent = sum(n.rank_current for n in self._nodes.values())
        active_nodes = [n for n in self._nodes.values() if n.rank_current > 0]
        if not active_nodes:
            self._tree_stats_panel.set_empty(points_spent)
            return
        total_dano, max_alcance, total_mana = 0.0, 0.0, 0.0
        speed_scores, flag_fracs = [], []
        for node in active_nodes:
            m = self._skill_metrics_for(node)
            total_dano += float(m.get("dano_base", 0))
            max_alcance = max(max_alcance, float(m.get("alcance", 0)))
            total_mana += float(m.get("mana_cost", 0))
            cooldown = float(m.get("cooldown", 0))
            speed_scores.append(1.0 if cooldown <= 0 else max(0.0, 1 - min(cooldown, 10) / 10))
            flags_total = max(1, m.get("flags_total", 1))
            flag_fracs.append(m.get("flags_on", 0) / flags_total)
        self._tree_stats_panel.set_stats(
            dano_total=total_dano, alcance=max_alcance, mana_total=total_mana,
            speed=sum(speed_scores) / len(speed_scores), util=sum(flag_fracs) / len(flag_fracs),
            points_spent=points_spent, node_count=len(active_nodes),
        )

    def _adjust_node_rank(self, node: _NodeItem, delta: int):
        """Called by the +/- hit-targets drawn directly on the node's own
        card (see _NodeItem._rank_button_rects/mousePressEvent) — each card
        manages its own rank independently, no need to select it first."""
        new_rank = max(0, min(node.rank_max, node.rank_current + delta))
        if new_rank == node.rank_current:
            return
        node.rank_current = new_rank
        node.update()
        self._persist()
        self._refresh_tree_stats()

    def _edge_exists(self, a: _NodeItem, b: _NodeItem) -> bool:
        return any((e.src is a and e.dst is b) or (e.src is b and e.dst is a) for e in self._edges)

    def _on_node_moving(self, node: _NodeItem):
        for e in self._edges:
            if e.src is node or e.dst is node:
                e.update_path()

    # ── zoom ──

    def zoom_by(self, factor: float):
        new_zoom = self._zoom * factor
        if not (0.3 <= new_zoom <= 3.0):
            return
        self._zoom = new_zoom
        self._view.scale(factor, factor)
        self._zoom_lbl.setText(f"{int(self._zoom * 100)}%")

    def _reset_zoom(self):
        if self._zoom != 1.0:
            self._view.scale(1 / self._zoom, 1 / self._zoom)
            self._zoom = 1.0
            self._zoom_lbl.setText("100%")
        self._view.centerOn(0, 0)

    # ── persistence ──

    def _persist(self):
        tree = self._active_tree()
        if not tree:
            return
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [[e.src.node_id, e.dst.node_id] for e in self._edges],
            # Preserved as-is — this is the only writer of this tree's data
            # blob, and it must not clobber the theme chosen at tab
            # creation (see create_tab_for_skill) on every node move/connect.
            "theme_color": self._active_theme_color,
            "text_color": self._active_text_color,
        }
        tree["data"] = json.dumps(data, ensure_ascii=False)
        if self._uow:
            self._uow.skill_trees.upsert(self._active_key, data=tree["data"])

    @staticmethod
    def _parse_data(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {"nodes": [], "edges": []}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"nodes": [], "edges": []}
        except (json.JSONDecodeError, TypeError):
            return {"nodes": [], "edges": []}
