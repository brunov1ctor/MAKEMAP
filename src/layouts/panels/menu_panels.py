"""Menu Panels — painéis glass fullscreen para cada módulo da topbar."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors, Typography


class MenuPanel(QWidget):
    """Painel glass genérico para módulos da topbar — estilo ProjectsPanel."""

    closed = Signal()

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._drag_pos = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 16)
        layout.setSpacing(0)

        # ── Header ──
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 6, 0, 8)
        hdr.setSpacing(8)

        if self._icon:
            icon_lbl = QLabel(self._icon)
            icon_lbl.setStyleSheet(
                f"font-size: 18px; background: transparent; border: none;"
            )
            hdr.addWidget(icon_lbl)

        title = QLabel(self._title.upper())
        title.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: none; font-size: 14px; border-radius: 14px; }}"
            f"QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.closed.emit)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        layout.addWidget(sep)

        # ── Content area (scroll) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
        )

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 12, 0, 12)
        self._content_layout.setSpacing(8)
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    @property
    def content_layout(self) -> QVBoxLayout:
        """Access the content layout to add widgets."""
        return self._content_layout

    def add_empty_state(self, message: str):
        """Show an empty state message with icon."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)

        icon = QLabel(self._icon or "📋")
        icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)

        msg = QLabel(message)
        msg.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11pt; background: transparent; border: none;"
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        lay.addWidget(msg)

        hint = QLabel("Em breve...")
        hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9pt; font-style: italic; "
            f"background: transparent; border: none;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        self._content_layout.addStretch()
        self._content_layout.addWidget(container)
        self._content_layout.addStretch()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(14, 22, 42, 230))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.drawPath(path)
        p.end()


# ─── Specific Menu Panels ────────────────────────────────────────────────────

class QuestsPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Quests", "📜", parent)
        self.add_empty_state("Crie missões e objetivos para seus jogadores.")


class NPCsPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("NPCs", "🧙", parent)
        self.add_empty_state("Gerencie personagens não-jogáveis do seu mundo.")


class ItensPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Itens", "⚔", parent)
        self.add_empty_state("Catalogue armas, armaduras e itens do mundo.")


class DungeonsPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Dungeons", "🏰", parent)
        self.add_empty_state("Projete masmorras e encontros de combate.")


class EventosPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Eventos", "⚡", parent)
        self.add_empty_state("Configure eventos e triggers do mundo.")


class LorePanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Lore", "📖", parent)
        self.add_empty_state("Escreva a história e lore do seu universo.")


class ConfigPanel(MenuPanel):
    def __init__(self, parent=None):
        super().__init__("Config", "⚙", parent)
        self.content_layout.setContentsMargins(0, 8, 0, 8)
        self.content_layout.setSpacing(0)
        from src.layouts.panels.assets.panel import AssetSoundManager
        manager = AssetSoundManager()
        self.content_layout.addWidget(manager)


# Registry for easy lookup
MENU_PANELS = {
    "Quests": QuestsPanel,
    "NPCs": NPCsPanel,
    "Itens": ItensPanel,
    "Dungeons": DungeonsPanel,
    "Eventos": EventosPanel,
    "Lore": LorePanel,
    "Config": ConfigPanel,
}
