"""Tree-wide aggregate stats — the mini radar + text block floated over the
canvas viewport's bottom-right corner (see _TreeView.set_stats_overlay in
view.py). No dependency on canvas.py: SkillTreeCanvas pushes numbers in via
set_stats/set_empty rather than this module reaching back into it.
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPolygonF

from src.styles.tokens import Colors


class _MiniRadar(QWidget):
    """A tiny 5-axis radar chart for the tree's aggregate stats — just the
    filled polygon over its axes, no center number/caption (removed at the
    user's request: with a single tree-wide radar instead of one number per
    skill, "PODER" in the middle didn't map to anything specific, it just
    duplicated "Dano total" already spelled out in the text column)."""

    AXES = ["Dano", "Alcance", "Veloc.", "Custo", "Utilid."]
    BASE_SIZE = 88

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedSize(self.BASE_SIZE, self.BASE_SIZE)
        self._values = [0.0] * len(self.AXES)
        self._scale = 1.0

    def set_values(self, values: list[float]):
        self._values = values
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

        axis_font_px = max(6, round(6 * self._scale))
        axis_font = QFont("Segoe UI", axis_font_px)
        metrics = QFontMetrics(axis_font)

        # The plot radius reserves room for the axis labels outside the
        # outer ring — an *approximate* margin here, not a guarantee; the
        # label placement below clamps each label's actual measured
        # rect to the widget bounds as the real guarantee against clipping
        # (this alone isn't enough at small scales, where min(cx,cy) can be
        # too small to fit both the ring and the margin).
        label_margin = metrics.height() + 6
        radius = max(10.0, min(cx, cy) - label_margin)

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

        # Axis labels — placed a small fixed gap past the outer ring, then
        # each label's *actual measured* width/height (via QFontMetrics,
        # not a guessed multiplier) is clamped to stay fully inside the
        # widget rect. That clamp is what actually prevents clipping
        # ("Alcance"/"Utilid."/"Veloc." reading as cut off) at every scale,
        # including small ones where there isn't room for a full margin.
        p.setPen(QColor(Colors.TEXT_MUTED))
        p.setFont(axis_font)
        for i, label in enumerate(self.AXES):
            ang = 2 * math.pi * i / n - math.pi / 2
            lx = cx + (radius + label_margin * 0.6) * math.cos(ang)
            ly = cy + (radius + label_margin * 0.6) * math.sin(ang)
            tw = metrics.horizontalAdvance(label) + 4
            th = metrics.height()
            rx = min(max(lx - tw / 2, 0.0), self.width() - tw)
            ry = min(max(ly - th / 2, 0.0), self.height() - th)
            p.drawText(QRectF(rx, ry, tw, th), Qt.AlignmentFlag.AlignCenter, label)

        # Value polygon — a small floor (0.05) so a 0-value axis still shows
        # a sliver instead of collapsing the whole shape onto the center.
        pts = [axis_point(i, max(0.05, min(1.0, v))) for i, v in enumerate(self._values)]
        fill = QColor(Colors.ACCENT)
        fill.setAlpha(90)
        p.setBrush(QBrush(fill))
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.drawPolygon(QPolygonF(pts))


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

    BASE_MAX_WIDTH = 226
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
                  speed: float, util: float, points_spent: int, node_count: int,
                  dano_max: float = 0.0, alcance_max: float = 0.0, mana_max: float = 0.0):
        """dano_max/alcance_max/mana_max are the highest totals among ALL
        guias that exist (see SkillTreeCanvas._max_totals_across_trees) —
        Dano/Alcance/Custo are plotted relative to that real ceiling
        (this guia's total ÷ the biggest guia's total) instead of a fixed
        constant, so a guia at half the top guia's dano_total reads as
        half the axis, full when it IS the top guia, and so on as other
        guias change. speed/util already come in pre-normalized to 0..1."""
        def ratio(value: float, maximum: float) -> float:
            return 0.0 if maximum <= 0 else min(1.0, value / maximum)

        values = [
            ratio(dano_total, dano_max),
            ratio(alcance, alcance_max),
            speed,
            ratio(mana_total, mana_max),
            util,
        ]
        self._radar.set_values(values)
        self._stats_lbl.setText(
            f"Dano total: {dano_total:.0f}\nAlcance: {alcance:.0f}m\n"
            f"Custo total: {mana_total:.0f}\nNós ativos: {node_count}\n"
            f"Pontos gastos: {points_spent}"
        )
        self._resync_size()

    def set_empty(self, points_spent: int = 0):
        self._radar.set_values([0, 0, 0, 0, 0])
        self._stats_lbl.setText(f"Nenhum nó com rank investido ainda.\nPontos gastos: {points_spent}")
        self._resync_size()

    def _resync_size(self):
        """Text length changes the wrapped label's height — shrink-wrap to
        the new content and let the floating view (see _TreeView.
        set_stats_overlay) re-anchor it to the bottom-right corner."""
        self.adjustSize()
        if self._owner_view is not None:
            self._owner_view._reposition_stats_overlay()
