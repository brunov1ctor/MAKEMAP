"""5. Linha de Progressão — cards com thumbnail, nome, nível, status, conexões."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
    QScrollArea, QWidget, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Metrics, Typography


class _RegionCard(QFrame):
    """Card de região na linha de progressão."""

    def __init__(self, icon: str, name: str, levels: str, color: str, status: str = "✓", parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            _RegionCard {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 10px;
                border-bottom: 3px solid {color};
            }}
            _RegionCard:hover {{
                background: {Colors.PANEL_HOVER};
                border-color: {color};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Thumbnail + status row
        top_row = QHBoxLayout()
        thumb = QLabel(icon)
        thumb.setStyleSheet(f"font-size: 18px; background: transparent; border: none;")
        top_row.addWidget(thumb)
        top_row.addStretch()

        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(f"""
            font-size: 8px; color: {color};
            background: transparent; border: none;
        """)
        top_row.addWidget(status_lbl)
        layout.addLayout(top_row)

        # Name
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        # Level range
        level_lbl = QLabel(levels)
        level_lbl.setStyleSheet(f"""
            font-size: 8px; color: {color};
            font-weight: {Typography.WEIGHT_MEDIUM};
            background: transparent; border: none;
        """)
        layout.addWidget(level_lbl)


class _Connector(QFrame):
    """Linha conectora entre cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 72)
        self.setStyleSheet("background: transparent; border: none;")

        line = QLabel("─→")
        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        line.setStyleSheet(f"""
            font-size: 10px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line)


class ProgressionBar(QFrame):
    """Barra de progressão — scroll horizontal com cards de região."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(96)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 6, 12, 6)
        outer_layout.setSpacing(4)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("🗺 Progressão do Mundo")
        header.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_MUTED}; letter-spacing: 0.5px;
            background: transparent; border: none;
        """)
        header_row.addWidget(header)
        header_row.addStretch()
        outer_layout.addLayout(header_row)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setFixedHeight(76)

        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        segments = [
            ("🌲", "Floresta", "Lv 1–10", Colors.SUCCESS, "✓"),
            ("🏔", "Vale", "Lv 10–20", "#4CAF50", "✓"),
            ("🌿", "Pântano", "Lv 20–30", "#8BC34A", "◉"),
            ("⛰", "Montanhas", "Lv 30–40", "#CDDC39", "○"),
            ("🏜", "Deserto", "Lv 40–50", Colors.WARNING, "○"),
            ("🏖", "Costa", "Lv 50–60", "#FF9800", "○"),
            ("🌋", "Vulcão", "Lv 60–70", "#FF5722", "○"),
            ("🕳", "Abismo", "Lv 70–80", Colors.ERROR, "○"),
            ("🌑", "Sombras", "Lv 80–90", Colors.PURPLE, "○"),
            ("⚔", "End Game", "Lv 90–100", "#673AB7", "○"),
        ]

        for i, (icon, name, levels, color, status) in enumerate(segments):
            card = _RegionCard(icon, name, levels, color, status)
            content_layout.addWidget(card)

            if i < len(segments) - 1:
                connector = _Connector()
                content_layout.addWidget(connector)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(r, 0, 0)
        p.fillPath(path, QColor(11, 25, 41, 210))
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.drawLine(0, 0, w, 0)
        p.end()
