"""Typography Engine — textos decorativos, labels, estilização avançada."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen, QBrush,
    QPainterPath, QLinearGradient, QRadialGradient, QTransform,
)


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
class TextShadow:
    enabled: bool = True
    color: str = "#000000"
    offset_x: float = 2.0
    offset_y: float = 2.0
    blur: float = 4.0
    opacity: float = 0.6


@dataclass
class TextOutline:
    enabled: bool = True
    color: str = "#000000"
    width: float = 2.0
    opacity: float = 1.0


@dataclass
class TextGlow:
    enabled: bool = True
    color: str = "#4FC3F7"
    radius: float = 8.0
    opacity: float = 0.5


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
    ribbon: TextRibbon = field(default_factory=TextRibbon)


# ─── Typography Renderer ───────────────────────────────────────────────────

class TypographyRenderer:
    """Renderiza texto com todos os efeitos aplicados."""

    @staticmethod
    def build_font(props: TextProperties) -> QFont:
        font = QFont(props.font_family)
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

        # 1. Ribbon (background decorativo)
        if props.ribbon.enabled:
            cls._render_ribbon(painter, text_path, props)

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
        color = QColor(props.color)
        painter.fillPath(text_path, QBrush(color))

        painter.restore()

    @staticmethod
    def _render_shadow(painter: QPainter, path: QPainterPath, shadow: TextShadow):
        color = QColor(shadow.color)
        color.setAlphaF(shadow.opacity)
        painter.save()
        painter.translate(shadow.offset_x, shadow.offset_y)
        painter.fillPath(path, QBrush(color))
        painter.restore()

    @staticmethod
    def _render_glow(painter: QPainter, path: QPainterPath, glow: TextGlow):
        color = QColor(glow.color)
        color.setAlphaF(glow.opacity * 0.3)
        pen = QPen(color, glow.radius)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)

    @staticmethod
    def _render_outline(painter: QPainter, path: QPainterPath, outline: TextOutline):
        color = QColor(outline.color)
        color.setAlphaF(outline.opacity)
        pen = QPen(color, outline.width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)

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
        if props.ribbon.enabled:
            expand = max(expand, max(props.ribbon.padding_x, props.ribbon.padding_y))

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
