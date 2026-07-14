"""1. Barra Superior — glassmorphism, 72px, navegação com QButtonGroup."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton,
    QSizePolicy, QWidget, QVBoxLayout, QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath,
    QLinearGradient, QPen, QBrush,
)

from src.styles.tokens import Colors, Metrics, Typography


# ─────────────────────────────────────────────────────────────────────────────
# TopNavigationButton — componente reutilizável para cada opção do menu
# ─────────────────────────────────────────────────────────────────────────────

class TopNavigationButton(QToolButton):
    """
    Botão de navegação da topbar.
    - Ícone (emoji) acima do texto (ToolButtonTextUnderIcon style via paintEvent)
    - Estados: normal, hover, pressed, ativo (checked)
    - Linha inferior azul quando ativo
    - Tamanho consistente: 62px altura, min 72px largura
    """

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._label = text
        self.setCheckable(True)
        self.setToolTip(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        self.setMinimumWidth(72)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Remove all default styling — we paint everything ourselves
        self.setStyleSheet("QToolButton { background: transparent; border: none; }")

    def sizeHint(self):
        fm = QFontMetrics(QFont(Typography.FAMILY, 9, QFont.Weight.Bold))
        tw = fm.horizontalAdvance(self._label) + 20
        return QSize(max(tw, 72), 62)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        is_active = self.isChecked()
        is_hover = self.underMouse() and not is_active
        is_pressed = self.isDown()

        # ── Background ──
        bg_rect = QRectF(2, 2, w - 4, h - 4)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(bg_rect, 10, 10)

        if is_active:
            # Fundo azul escuro
            p.fillPath(bg_path, QColor(15, 40, 70, 200))
        elif is_pressed:
            p.fillPath(bg_path, QColor(20, 50, 85, 180))
        elif is_hover:
            # Fundo azul semitransparente
            p.fillPath(bg_path, QColor(30, 60, 100, 100))

        # ── Icon (emoji) — 28px, posicionado na metade superior ──
        icon_font = QFont("Segoe UI Emoji", 16)
        p.setFont(icon_font)

        icon_rect = QRectF(0, 6, w, 28)
        if is_active:
            p.setPen(QColor(Colors.ACCENT))
        elif is_hover:
            p.setPen(QColor(Colors.TEXT_PRIMARY))
        else:
            p.setPen(QColor(Colors.TEXT_MUTED))
        p.drawText(icon_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter, self._icon)

        # ── Label — 9pt bold, posicionado na metade inferior ──
        text_font = QFont(Typography.FAMILY, 9, QFont.Weight.Bold)
        p.setFont(text_font)

        text_rect = QRectF(2, 34, w - 4, 20)
        if is_active:
            p.setPen(QColor(Colors.TEXT_PRIMARY))
        elif is_hover:
            p.setPen(QColor(Colors.TEXT_PRIMARY))
        else:
            p.setPen(QColor(Colors.TEXT_MUTED))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._label)

        # ── Linha inferior azul quando ativo ──
        if is_active:
            line_w = min(w - 16, 40)
            line_x = (w - line_w) / 2
            line_y = h - 4
            p.setPen(QPen(QColor(Colors.ACCENT), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(int(line_x), int(line_y), int(line_x + line_w), int(line_y))

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# _ProjectBadge — badge do projeto ativo no canto direito
# ─────────────────────────────────────────────────────────────────────────────

class _ProjectBadge(QWidget):
    """Badge do projeto ativo."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._text = text
        self.setFixedHeight(30)
        self.setMinimumWidth(80)

    def set_text(self, text: str):
        self._text = text or ""
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(Typography.FAMILY, 11, QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self._text) + 20
        self.setFixedWidth(max(tw, 80))
        p.setPen(QColor(Colors.ACCENT))
        p.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# TopBar — barra superior completa
# ─────────────────────────────────────────────────────────────────────────────

class TopBar(QFrame):
    """Barra superior 72px — glassmorphism, logo, navegação, busca, badge."""

    module_changed = Signal(str)
    search_requested = Signal(str)
    arquivo_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("top_bar")
        self.setFixedHeight(Metrics.TOP_BAR_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # ── Logo + Brand ──
        logo_frame = QFrame()
        logo_frame.setStyleSheet("background: transparent; border: none;")
        logo_layout = QHBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 0, 12, 0)
        logo_layout.setSpacing(8)

        logo = QLabel("◆")
        logo.setStyleSheet(f"""
            font-size: 20px; color: {Colors.ACCENT};
            background: transparent; border: none;
        """)
        logo_layout.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_name = QLabel("MAKE")
        brand_name.setStyleSheet(f"""
            font-size: 13px; font-weight: {Typography.WEIGHT_BLACK};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        brand_sub = QLabel("MAP")
        brand_sub.setStyleSheet(f"""
            font-size: 8px; font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.ACCENT}; background: transparent; border: none;
            letter-spacing: 2px;
        """)
        brand_col.addWidget(brand_name)
        brand_col.addWidget(brand_sub)
        logo_layout.addLayout(brand_col)

        layout.addWidget(logo_frame)
        layout.addWidget(self._sep())

        # ── Navegação ──
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background: transparent; border: none;")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(4, 0, 4, 0)
        nav_layout.setSpacing(4)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._nav_buttons: list[TopNavigationButton] = []
        self._arquivo_btn: TopNavigationButton | None = None

        modules = [
            ("📁", "Arquivo"),
            ("🗺", "Mapa"),
            ("📜", "Quests"),
            ("🧙", "NPCs"),
            ("👹", "Mobs"),
            ("⚔", "Itens"),
            ("🏰", "Dungeons"),
            ("⚡", "Eventos"),
            ("📖", "Lore"),
            ("⚙", "Config"),
            ("📋", "Logs"),
        ]

        for i, (icon, name) in enumerate(modules):
            btn = TopNavigationButton(icon, name)
            if name == "Arquivo":
                # Arquivo não participa do grupo exclusivo
                btn.setCheckable(False)
                btn.clicked.connect(self._on_arquivo)
                self._arquivo_btn = btn
            else:
                self._button_group.addButton(btn, i)
                btn.clicked.connect(lambda checked, n=name: self._on_module(n))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Default: Mapa ativo
        self._nav_buttons[1].setChecked(True)
        layout.addWidget(nav_frame)

        layout.addStretch()

        # ── Busca Global ──
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Buscar... (Ctrl+K)")
        self.search.setMinimumWidth(160)
        self.search.setMaximumWidth(280)
        self.search.setFixedHeight(32)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 16px;
                padding: 0 14px;
                font-size: 11px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT};
                background: {Colors.GLASS_BG_STRONG};
            }}
        """)
        self.search.returnPressed.connect(lambda: self.search_requested.emit(self.search.text()))
        layout.addWidget(self.search)

        layout.addStretch()

        # ── Badge do Projeto ──
        self._project_badge = _ProjectBadge("")
        layout.addWidget(self._project_badge)

    # ── Slots ──

    def _on_arquivo(self):
        self.arquivo_clicked.emit()

    def _on_module(self, name: str):
        self.module_changed.emit(name)

    # ── API ──

    def set_project_name(self, name: str):
        self._project_badge.set_text(name)

    # ── Helpers ──

    def _sep(self):
        s = QFrame()
        s.setFixedSize(1, 36)
        s.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return s

    # ── Paint ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(r, 0, 0)
        # Glass tint
        p.fillPath(path, QColor(11, 25, 41, 200))
        # Top highlight
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(255, 255, 255, 8))
        grad.setColorAt(0.3, QColor(255, 255, 255, 2))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillPath(path, QBrush(grad))
        # Bottom border
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawLine(0, h - 1, w, h - 1)
        p.end()
