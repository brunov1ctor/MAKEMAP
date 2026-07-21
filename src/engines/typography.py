"""Typography Engine — textos decorativos, labels, estilização avançada."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen, QBrush,
    QPainterPath, QLinearGradient, QRadialGradient, QTransform,
    QImage, QPixmap,
)

# Resolution of the freehand-painted color grid (the "Personalizar" picker's
# paintable preview) — small enough to paint comfortably, big enough that
# stretching it over a text object's bounding box doesn't look blocky.
PAINT_GRID_COLS = 12
PAINT_GRID_ROWS = 6


# ─── Enums ──────────────────────────────────────────────────────────────────

class TextAlign(Enum):
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()
    JUSTIFY = auto()


class TextStyle(Enum):
    NORMAL = auto()
    OUTLINE = auto()
    SHADOW = auto()
    GLOW = auto()
    CURVED = auto()
    RIBBON = auto()


# ─── Data Models ────────────────────────────────────────────────────────────

@dataclass
class PaintGrid:
    """A small freehand-painted color grid — the alternate fill a fill/
    shadow/outline/glow color can take on when the user paints more than
    one color into the Personalizar picker's preview (e.g. a striped
    "Napolitano" look) instead of picking a single solid color. Empty
    (never painted) means "just use the plain color string instead"."""
    cells: list[str] = field(default_factory=list)

    def ensure(self, base_color: str):
        """Lazily fill to a uniform grid of base_color the first time this
        target is painted on, without touching an already-painted grid."""
        n = PAINT_GRID_COLS * PAINT_GRID_ROWS
        if len(self.cells) != n:
            self.cells = [base_color] * n

    def fill(self, color: str):
        """Reset to a uniform grid of `color` — used when a quick solid
        pick (native color dialog) should override any painted stripes."""
        self.cells = [color] * (PAINT_GRID_COLS * PAINT_GRID_ROWS)

    def is_uniform(self) -> bool:
        return len(set(self.cells)) <= 1

    def dominant(self, fallback: str) -> str:
        return self.cells[0] if self.cells else fallback


@dataclass
class TextShadow:
    enabled: bool = True
    color: str = "#000000"
    offset_x: float = 2.0
    offset_y: float = 2.0
    blur: float = 4.0
    opacity: float = 0.6
    pattern: PaintGrid = field(default_factory=PaintGrid)


@dataclass
class TextOutline:
    enabled: bool = True
    color: str = "#000000"
    width: float = 2.0
    opacity: float = 1.0
    pattern: PaintGrid = field(default_factory=PaintGrid)


@dataclass
class TextGlow:
    enabled: bool = True
    color: str = "#4FC3F7"
    radius: float = 8.0
    opacity: float = 0.5
    pattern: PaintGrid = field(default_factory=PaintGrid)


@dataclass
class TextCurve:
    enabled: bool = False
    radius: float = 200.0
    start_angle: float = 180.0
    clockwise: bool = True


@dataclass
class TextRibbon:
    enabled: bool = False
    color: str = "#2C3E50"
    padding_x: float = 16.0
    padding_y: float = 6.0
    radius: float = 4.0
    opacity: float = 0.85


@dataclass
class TextSpacing:
    letter_spacing: float = 0.0
    word_spacing: float = 0.0
    line_height: float = 1.2


@dataclass
class TextProperties:
    """Propriedades completas de um texto no canvas."""
    text: str = ""
    font_family: str = "Segoe UI"
    font_size: float = 14.0
    font_weight: int = 400  # 100-900
    italic: bool = False
    color: str = "#FFFFFF"
    background_color: str = ""
    opacity: float = 1.0
    align: TextAlign = TextAlign.CENTER
    spacing: TextSpacing = field(default_factory=TextSpacing)
    outline: TextOutline = field(default_factory=lambda: TextOutline(enabled=False))
    shadow: TextShadow = field(default_factory=lambda: TextShadow(enabled=False))
    glow: TextGlow = field(default_factory=lambda: TextGlow(enabled=False))
    curve: TextCurve = field(default_factory=TextCurve)
    pattern: PaintGrid = field(default_factory=PaintGrid)
    ribbon: TextRibbon = field(default_factory=TextRibbon)

    # Efeitos (quick-toggle decorations) — Contorno/Caixa reuse the
    # outline/ribbon fields above; these are the ones with no other home.
    strikethrough: bool = False
    overline: bool = False
    underline: bool = False
    double_underline: bool = False
    cloud: bool = False
    serif: bool = False


# ─── Typography Renderer ───────────────────────────────────────────────────

class TypographyRenderer:
    """Renderiza texto com todos os efeitos aplicados."""

    SERIF_FALLBACK = "Georgia"

    @classmethod
    def build_font(cls, props: TextProperties) -> QFont:
        font = QFont(cls.SERIF_FALLBACK if props.serif else props.font_family)
        font.setPointSizeF(max(1.0, props.font_size))
        font.setWeight(QFont.Weight(props.font_weight))
        font.setItalic(props.italic)
        if props.spacing.letter_spacing != 0:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, props.spacing.letter_spacing)
        if props.spacing.word_spacing != 0:
            font.setWordSpacing(props.spacing.word_spacing)
        return font

    @staticmethod
    def build_path(props: TextProperties, font: QFont) -> QPainterPath:
        """Constrói o path do texto (reto ou curvo)."""
        path = QPainterPath()

        if props.curve.enabled:
            TypographyRenderer._build_curved_path(path, props, font)
        else:
            path.addText(0, QFontMetrics(font).ascent(), font, props.text)

        return path

    @staticmethod
    def _build_curved_path(path: QPainterPath, props: TextProperties, font: QFont):
        """Texto em arco."""
        fm = QFontMetrics(font)
        radius = props.curve.radius
        angle = props.curve.start_angle
        direction = 1 if props.curve.clockwise else -1

        for char in props.text:
            char_width = fm.horizontalAdvance(char)
            angle_step = (char_width / (2 * 3.14159 * radius)) * 360 * direction

            import math
            rad = math.radians(angle)
            x = radius * math.cos(rad)
            y = radius * math.sin(rad)

            transform = QTransform()
            transform.translate(x + radius, y + radius)
            transform.rotate(angle + 90 * direction)

            char_path = QPainterPath()
            char_path.addText(0, 0, font, char)
            path.addPath(transform.map(char_path))

            angle += angle_step

    @classmethod
    def render(cls, painter: QPainter, pos: QPointF, props: TextProperties):
        """Renderiza texto completo com todos os efeitos."""
        if not props.text:
            return

        painter.save()
        painter.translate(pos)
        painter.setOpacity(props.opacity)

        font = cls.build_font(props)
        text_path = cls.build_path(props, font)

        # 1. Ribbon / Cloud (background decorativo)
        if props.ribbon.enabled:
            cls._render_ribbon(painter, text_path, props)
        if props.cloud:
            cls._render_cloud(painter, text_path, props)

        # 2. Shadow
        if props.shadow.enabled:
            cls._render_shadow(painter, text_path, props.shadow)

        # 3. Glow
        if props.glow.enabled:
            cls._render_glow(painter, text_path, props.glow)

        # 4. Outline
        if props.outline.enabled:
            cls._render_outline(painter, text_path, props.outline)

        # 5. Fill
        brush = cls._pattern_brush(props.pattern, props.color, text_path.boundingRect())
        painter.fillPath(text_path, brush)

        # 6. Line decorations (skipped on curved text — a straight line
        # under an arced baseline doesn't read as an underline/strikeout)
        if not props.curve.enabled:
            cls._render_decorations(painter, font, props)

        painter.restore()

    @staticmethod
    def _pattern_brush(pattern: PaintGrid, base_color: str, rect: QRectF) -> QBrush:
        """A flat QBrush(color) unless the user has freehand-painted more
        than one color into this target's grid — then a QBrush built from
        the painted pixels, stretched to cover `rect` (the fill area)."""
        pattern.ensure(base_color)
        if pattern.is_uniform():
            return QBrush(QColor(pattern.dominant(base_color)))

        img = QImage(PAINT_GRID_COLS, PAINT_GRID_ROWS, QImage.Format.Format_ARGB32)
        for y in range(PAINT_GRID_ROWS):
            for x in range(PAINT_GRID_COLS):
                img.setPixelColor(x, y, QColor(pattern.cells[y * PAINT_GRID_COLS + x]))
        brush = QBrush(QPixmap.fromImage(img))
        if rect.width() > 0 and rect.height() > 0:
            t = QTransform()
            t.translate(rect.left(), rect.top())
            t.scale(rect.width() / PAINT_GRID_COLS, rect.height() / PAINT_GRID_ROWS)
            brush.setTransform(t)
        return brush

    @classmethod
    def _render_shadow(cls, painter: QPainter, path: QPainterPath, shadow: TextShadow):
        brush = cls._pattern_brush(shadow.pattern, shadow.color, path.boundingRect())
        painter.save()
        painter.translate(shadow.offset_x, shadow.offset_y)
        painter.setOpacity(shadow.opacity)
        painter.fillPath(path, brush)
        painter.restore()

    @classmethod
    def _render_glow(cls, painter: QPainter, path: QPainterPath, glow: TextGlow):
        brush = cls._pattern_brush(glow.pattern, glow.color, path.boundingRect())
        pen = QPen(brush, glow.radius)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.save()
        painter.setOpacity(glow.opacity * 0.3)
        painter.strokePath(path, pen)
        painter.restore()

    @classmethod
    def _render_outline(cls, painter: QPainter, path: QPainterPath, outline: TextOutline):
        brush = cls._pattern_brush(outline.pattern, outline.color, path.boundingRect())
        pen = QPen(brush, outline.width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.save()
        painter.setOpacity(outline.opacity)
        painter.strokePath(path, pen)
        painter.restore()

    @staticmethod
    def _render_ribbon(painter: QPainter, path: QPainterPath, props: TextProperties):
        ribbon = props.ribbon
        color = QColor(ribbon.color)
        color.setAlphaF(ribbon.opacity)
        bounds = path.boundingRect()
        ribbon_rect = bounds.adjusted(
            -ribbon.padding_x, -ribbon.padding_y,
            ribbon.padding_x, ribbon.padding_y,
        )
        ribbon_path = QPainterPath()
        ribbon_path.addRoundedRect(ribbon_rect, ribbon.radius, ribbon.radius)
        painter.fillPath(ribbon_path, QBrush(color))

    @staticmethod
    def _render_cloud(painter: QPainter, path: QPainterPath, props: TextProperties):
        """A speech-bubble/cloud backdrop — same styling knobs as Ribbon
        (color/opacity/padding), but a bumpy comic-cloud outline instead of
        a plain rounded rect."""
        ribbon = props.ribbon
        color = QColor(ribbon.color)
        color.setAlphaF(ribbon.opacity)
        rect = path.boundingRect().adjusted(
            -ribbon.padding_x, -ribbon.padding_y,
            ribbon.padding_x, ribbon.padding_y,
        )
        if rect.width() <= 0 or rect.height() <= 0:
            return

        bumps_x = max(3, round(rect.width() / 22))
        bumps_y = max(2, round(rect.height() / 22))
        rx = rect.width() / bumps_x * 0.62
        ry = rect.height() / bumps_y * 0.62

        cloud_path = QPainterPath()
        cloud_path.addRoundedRect(rect.adjusted(rx * 0.5, ry * 0.5, -rx * 0.5, -ry * 0.5), rx * 0.4, ry * 0.4)
        for i in range(bumps_x):
            t = i / max(1, bumps_x - 1)
            cx = rect.left() + t * rect.width()
            bump = QPainterPath()
            bump.addEllipse(QPointF(cx, rect.top()), rx, ry)
            cloud_path = cloud_path.united(bump)
            bump = QPainterPath()
            bump.addEllipse(QPointF(cx, rect.bottom()), rx, ry)
            cloud_path = cloud_path.united(bump)
        for j in range(bumps_y):
            t = j / max(1, bumps_y - 1)
            cy = rect.top() + t * rect.height()
            bump = QPainterPath()
            bump.addEllipse(QPointF(rect.left(), cy), rx, ry)
            cloud_path = cloud_path.united(bump)
            bump = QPainterPath()
            bump.addEllipse(QPointF(rect.right(), cy), rx, ry)
            cloud_path = cloud_path.united(bump)

        painter.fillPath(cloud_path.simplified(), QBrush(color))

    @classmethod
    def _render_decorations(cls, painter: QPainter, font: QFont, props: TextProperties):
        """Underline / double underline / overline / strikethrough — drawn
        from font metrics rather than baked into the glyph path, since they
        span the full text width as simple straight lines."""
        if not (props.underline or props.double_underline or props.overline or props.strikethrough):
            return

        fm = QFontMetrics(font)
        width = fm.horizontalAdvance(props.text)
        if width <= 0:
            return
        baseline = fm.ascent()
        brush = cls._pattern_brush(props.pattern, props.color, QRectF(0, 0, width, fm.height()))
        pen = QPen(brush, max(1.0, fm.lineWidth()))

        painter.save()
        painter.setPen(pen)
        if props.underline:
            y = baseline + fm.underlinePos()
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        if props.double_underline:
            y1 = baseline + fm.underlinePos()
            y2 = y1 + pen.widthF() * 2.5
            painter.drawLine(QPointF(0, y1), QPointF(width, y1))
            painter.drawLine(QPointF(0, y2), QPointF(width, y2))
        if props.overline:
            y = 0.0
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        if props.strikethrough:
            y = baseline - fm.strikeOutPos()
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        painter.restore()

    @staticmethod
    def bounding_rect(props: TextProperties) -> QRectF:
        """Calcula o bounding rect do texto com efeitos."""
        font = TypographyRenderer.build_font(props)
        path = TypographyRenderer.build_path(props, font)
        rect = path.boundingRect()

        # Expand for effects
        expand = 0.0
        if props.shadow.enabled:
            expand = max(expand, props.shadow.blur + abs(props.shadow.offset_x) + abs(props.shadow.offset_y))
        if props.glow.enabled:
            expand = max(expand, props.glow.radius)
        if props.outline.enabled:
            expand = max(expand, props.outline.width)
        if props.ribbon.enabled or props.cloud:
            # Cloud's bumps extend a bit further than Ribbon's plain edge.
            bump_extra = 1.6 if props.cloud else 1.0
            expand = max(expand, max(props.ribbon.padding_x, props.ribbon.padding_y) * bump_extra)
        if props.double_underline:
            expand = max(expand, 6.0)

        return rect.adjusted(-expand, -expand, expand, expand)


# ─── Typography Engine ─────────────────────────────────────────────────────

class TypographyEngine:
    """Engine principal — gerencia textos no canvas."""

    def __init__(self):
        self._texts: dict[str, TextProperties] = {}
        self._renderer = TypographyRenderer()

    @property
    def renderer(self) -> TypographyRenderer:
        return self._renderer

    def create_text(self, text_id: str, text: str = "", **kwargs) -> TextProperties:
        props = TextProperties(text=text, **kwargs)
        self._texts[text_id] = props
        return props

    def get_text(self, text_id: str) -> Optional[TextProperties]:
        return self._texts.get(text_id)

    def update_text(self, text_id: str, **kwargs):
        props = self._texts.get(text_id)
        if not props:
            return
        for key, value in kwargs.items():
            if hasattr(props, key):
                setattr(props, key, value)

    def remove_text(self, text_id: str):
        self._texts.pop(text_id, None)

    def render_text(self, painter: QPainter, text_id: str, pos: QPointF):
        props = self._texts.get(text_id)
        if props:
            self._renderer.render(painter, pos, props)

    @property
    def count(self) -> int:
        return len(self._texts)

    # ── Presets ──

    @staticmethod
    def preset_city_label() -> TextProperties:
        return TextProperties(
            font_family="Segoe UI",
            font_size=16,
            font_weight=700,
            color="#FFFFFF",
            outline=TextOutline(enabled=True, color="#000000", width=2.5),
            shadow=TextShadow(enabled=True, offset_x=1, offset_y=2, blur=3),
        )

    @staticmethod
    def preset_region_title() -> TextProperties:
        return TextProperties(
            font_family="Segoe UI",
            font_size=24,
            font_weight=600,
            color="#E8D5A3",
            spacing=TextSpacing(letter_spacing=3.0),
            outline=TextOutline(enabled=True, color="#2C1810", width=3),
            shadow=TextShadow(enabled=True, offset_x=2, offset_y=3, blur=6, opacity=0.7),
        )

    @staticmethod
    def preset_ocean_label() -> TextProperties:
        return TextProperties(
            font_family="Segoe UI",
            font_size=20,
            font_weight=400,
            italic=True,
            color="#87CEEB",
            spacing=TextSpacing(letter_spacing=8.0),
            glow=TextGlow(enabled=True, color="#4FC3F7", radius=6, opacity=0.4),
        )

    @staticmethod
    def preset_banner() -> TextProperties:
        return TextProperties(
            font_family="Segoe UI",
            font_size=18,
            font_weight=700,
            color="#FFFFFF",
            ribbon=TextRibbon(enabled=True, color="#8B4513", padding_x=20, padding_y=8, radius=6),
            shadow=TextShadow(enabled=True, offset_x=0, offset_y=3, blur=5),
        )
