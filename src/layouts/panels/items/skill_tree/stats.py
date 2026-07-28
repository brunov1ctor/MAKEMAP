"""Tree-wide aggregate stats — the mini radar + text block floated over the
canvas viewport's bottom-right corner (see _TreeView.set_stats_overlay in
view.py). No dependency on canvas.py: SkillTreeCanvas pushes numbers in via
set_stats/set_empty rather than this module reaching back into it.
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF

from src.styles.tokens import Colors


class _MiniRadar(QWidget):
    """A tiny 5-axis radar chart for the selected node's skill — same idea
    as the reference "Estatísticas Finais" mob panel (a filled polygon over
    a few axes + a big number in the middle), scaled down for one skill
    instead of a full character sheet."""

    AXES = ["Dano", "Alcance", "Veloc.", "Custo", "Utilid."]
    BASE_SIZE = 72

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedSize(self.BASE_SIZE, self.BASE_SIZE)
        self._values = [0.0] * len(self.AXES)
        self._center_text = ""
        self._scale = 1.0

    def set_values(self, values: list[float], center_text: str = ""):
        self._values = values
        self._center_text = center_text
        self.update()

    def set_scale(self, scale: float):
        """Grows/shrinks the whole chart (radius, spokes, every font) with
        the panel's own size (see _TreeStatsPanel.set_scale) — used to stay
        a fixed FRACTION of the view instead of a fixed pixel size, so it
        doesn't read as permanently tiny/compressed once the tree column is
        resized wider."""
        if abs(scale - self._scale) < 0.02:
            return
        self._scale = scale
        size = max(56, round(self.BASE_SIZE * scale))
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self.AXES)
        cx, cy = self.width() / 2, self.height() / 2 - 2
        radius = min(cx, cy) - 8

        def axis_point(i: int, frac: float) -> QPointF:
            ang = 2 * math.pi * i / n - math.pi / 2
            return QPointF(cx + radius * frac * math.cos(ang), cy + radius * frac * math.sin(ang))

        axis_font_px = max(5, round(5 * self._scale))
        center_font_px = max(7, round(8 * self._scale))

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
        p.setFont(QFont("Segoe UI", axis_font_px))
        for i, label in enumerate(self.AXES):
            pt = axis_point(i, 1.22)
            p.drawText(QRectF(pt.x() - 16, pt.y() - 5, 32, 10), Qt.AlignmentFlag.AlignCenter, label)

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
            p.setFont(QFont("Segoe UI", center_font_px, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 20, cy - 8, 40, 12), Qt.AlignmentFlag.AlignCenter, self._center_text)
            p.setPen(QColor(Colors.TEXT_MUTED))
            p.setFont(QFont("Segoe UI", axis_font_px))
            p.drawText(QRectF(cx - 20, cy + 3, 40, 8), Qt.AlignmentFlag.AlignCenter, "PODER")


class _TreeStatsPanel(QWidget):
    """Floats directly on top of the canvas viewport's bottom-right corner
    (see _TreeView.set_stats_overlay) — NOT a reserved layout column beside
    it, so the node graph keeps the view's full width and this costs it no
    space at all. Fully borderless/transparent (shows straight over the
    canvas background) and shrink-wrapped to its own content (see
    _resync_size). Shows the ACTIVE TAB's aggregate stats — the combined
    mini radar + totals of every node with rank_current > 0 (i.e. actually
    invested), plus "Pontos gastos" as the last line of that same text
    block (no separator — one continuous block, see set_stats). Per-node
    rank +/- lives on each card itself now (see _NodeItem.
    _rank_button_rects/mousePressEvent), not here — this panel is
    read-only, tree-wide."""

    BASE_MAX_WIDTH = 210
    BASE_LABEL_MIN_WIDTH = 110
    BASE_TITLE_FONT = 8
    BASE_STATS_FONT = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        # Plain QWidget + an unprefixed "background: transparent; border:
        # none;" — same exact recipe already working for other canvas
        # overlays in this app (see _ResizeGrip in canvas/overlays/
        # minimap.py). QFrame + an ID-selector rule (the previous attempt)
        # kept painting an opaque box despite the rule; this is the
        # established, verified-working pattern instead.
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self._owner_view: "_TreeView | None" = None
        self._scale = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self._title_lbl = QLabel("ESTATÍSTICAS DA ÁRVORE")
        self._title_lbl.setWordWrap(True)
        lay.addWidget(self._title_lbl)

        # Radar ao lado do texto (não empilhado em cima dele).
        content_row = QHBoxLayout()
        content_row.setSpacing(6)
        self._radar = _MiniRadar()
        content_row.addWidget(self._radar, alignment=Qt.AlignmentFlag.AlignTop)

        # "Pontos gastos" é só mais uma linha do mesmo bloco — sem separador
        # nem label à parte (ver referência: as 5 linhas formam um bloco só).
        self._stats_lbl = QLabel("")
        self._stats_lbl.setWordWrap(True)
        content_row.addWidget(self._stats_lbl, 1)
        lay.addLayout(content_row)

        self._apply_fonts_and_widths()  # sets the 1.0-scale baseline styling

    def _apply_fonts_and_widths(self):
        # Wide enough for the radar + its stats column at their own natural,
        # unwrapped width — too tight a cap here leaves the label only a
        # sliver to work with once the radar/spacing/margins are subtracted,
        # so every line ("Custo total: 0") wraps into 2-3 fragments and the
        # whole block reads as garbled/overlapping text (see set_scale for
        # why these also grow/shrink with the view instead of staying fixed).
        self.setMaximumWidth(round(self.BASE_MAX_WIDTH * self._scale))
        self._stats_lbl.setMinimumWidth(round(self.BASE_LABEL_MIN_WIDTH * self._scale))
        title_px = max(7, round(self.BASE_TITLE_FONT * self._scale))
        stats_px = max(7, round(self.BASE_STATS_FONT * self._scale))
        self._title_lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: {title_px}px; font-weight: bold; background: transparent; border: none;")
        self._stats_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {stats_px}px; background: transparent; border: none;")

    def set_scale(self, scale: float):
        """Called from _TreeView on every resize (see _reposition_stats_
        overlay/_stats_scale) so the whole panel is a fixed FRACTION of the
        view instead of a fixed pixel size — dragging the tree column wider
        used to leave this exact-same-size box looking permanently tiny/
        compressed in the corner instead of growing along with everything
        else."""
        if abs(scale - self._scale) < 0.02:
            return
        self._scale = scale
        self._radar.set_scale(scale)
        self._apply_fonts_and_widths()
        self._resync_size()

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
        self._resync_size()

    def set_empty(self, points_spent: int = 0):
        self._radar.set_values([0, 0, 0, 0, 0], center_text="0")
        self._stats_lbl.setText(f"Nenhum nó com rank investido ainda.\nPontos gastos: {points_spent}")
        self._resync_size()

    def _resync_size(self):
        """Text length changes the wrapped label's height — shrink-wrap to
        the new content and let the floating view (see _TreeView.
        set_stats_overlay) re-anchor it to the bottom-right corner."""
        self.adjustSize()
        if self._owner_view is not None:
            self._owner_view._reposition_stats_overlay()
