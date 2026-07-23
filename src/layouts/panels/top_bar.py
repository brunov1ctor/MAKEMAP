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

    # Width every short single-word button already naturally lands on
    # ("Mapa"/"Mobs"/"NPCs"/"Lore"/"Logs") — a `wrap=True` button (see
    # below) is clamped to exactly this instead of its natural (much
    # wider) single-line width, so it reads as 2-3 lines rather than
    # visibly wider than the rest of the bar.
    _WRAPPED_WIDTH = 72

    def __init__(self, icon: str, text: str, menu_id: str = None, wrap: bool = False, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._label = text
        # Internal identifier used for activation/routing (menu_clicked,
        # set_active_menu, MENU_PANELS lookups) — kept distinct from the
        # displayed label so a button's on-screen text can be a longer,
        # friendlier name ("Itens e Habilidades") without also renaming
        # the panel/dict key everywhere else that still expects "Itens".
        self._menu_id = menu_id if menu_id is not None else text
        # Explicit per-button flag (set in TopBar's `modules` list) rather
        # than inferring "needs wrapping" from a measured pixel width
        # threshold — that measurement depends on whatever font actually
        # resolves at runtime (Typography.FAMILY may not be installed
        # everywhere), so a threshold tuned in one environment could sit
        # between two labels' real widths on another and wrap only one of
        # them. An explicit flag can't disagree with itself like that.
        self._wrap = wrap
        self.setCheckable(True)
        self.setToolTip(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)
        self.setMinimumWidth(72)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Remove all default styling — we paint everything ourselves
        self.setStyleSheet("QToolButton { background: transparent; border: none; }")

    def sizeHint(self):
        if self._wrap:
            return QSize(self._WRAPPED_WIDTH, 62)
        fm = QFontMetrics(QFont(Typography.FAMILY, 9, QFont.Weight.Bold))
        tw = fm.horizontalAdvance(self._label) + 20
        return QSize(max(tw, 72), 62)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Custom-painted, so Qt's own disabled-widget dimming (which only
        # applies to its built-in style/palette drawing) never kicks in on
        # its own — faded out explicitly here instead, e.g. while no
        # project is open (see TopBar.set_modules_enabled).
        if not self.isEnabled():
            p.setOpacity(0.30)

        w, h = self.width(), self.height()
        is_active = self.isChecked()
        is_hover = self.underMouse() and not is_active and self.isEnabled()
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

        # ── Icon (emoji) — posicionado na metade superior. Slightly
        # shorter than before (24px vs 28px) to free up room below for a
        # 2nd wrapped label line without growing the button's total
        # height. ──
        icon_font = QFont("Segoe UI Emoji", 16)
        p.setFont(icon_font)

        icon_rect = QRectF(0, 4, w, 24)
        if is_active:
            p.setPen(QColor(Colors.ACCENT))
        else:
            p.setPen(QColor("#ffffff"))
        p.drawText(icon_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter, self._icon)

        # ── Label — bold, posicionado na metade inferior. `wrap` buttons
        # (see __init__) word-wrap onto 2-3 lines within the same
        # _WRAPPED_WIDTH instead of the button growing wider for a longer
        # label, at a smaller point size so those lines actually fit the
        # available height instead of the last one clipping past the
        # button's edge. Every other (single-line) button is completely
        # unaffected. ──
        text_font = QFont(Typography.FAMILY, 7 if self._wrap else 9, QFont.Weight.Bold)
        p.setFont(text_font)

        text_rect = QRectF(2, 28, w - 4, 32)
        p.setPen(QColor("#ffffff"))
        p.drawText(
            text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            self._label,
        )

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
    logs_clicked = Signal()
    menu_clicked = Signal(str)  # emits menu name for exclusive panel management

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
        self._button_group.setExclusive(False)  # we manage exclusivity manually

        self._nav_buttons: list[TopNavigationButton] = []
        self._arquivo_btn: TopNavigationButton | None = None
        self._active_menu_btn: TopNavigationButton | None = None

        # (icon, menu_id, display_label, wrap) — menu_id is the internal
        # identifier routed through menu_clicked/set_active_menu/
        # MENU_PANELS and must stay exactly what those already expect;
        # display_label is only what's actually painted on the button, so
        # it can read friendlier/longer without renaming the panel itself.
        # wrap=True forces that button to wrap its label onto 2-3 lines at
        # the common 72px width instead of the button being visibly wider
        # than the rest of the bar.
        modules = [
            ("☰", "Projetos", "Projetos", False),
            ("🗺", "Mapa", "Mapa", False),
            ("📜", "Quests", "Quests", False),
            ("🧙", "NPCs", "NPCs", False),
            ("👹", "Mobs", "Mobs", False),
            ("⚔", "Itens", "Itens e Habilidades", True),
            ("🏰", "Dungeons", "Dungeons e Construções", True),
            ("📖", "Lore", "Lore", False),
            ("⚙", "Config", "Config", False),
            ("📋", "Logs", "Logs", False),
        ]

        for i, (icon, name, label, wrap) in enumerate(modules):
            btn = TopNavigationButton(icon, label, menu_id=name, wrap=wrap)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, n=name, b=btn: self._on_nav_clicked(n, b))
            self._button_group.addButton(btn, i)
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
            if name == "Projetos":
                self._arquivo_btn = btn

        # Default: Mapa ativo
        self._nav_buttons[1].setChecked(True)
        self._active_menu_btn = self._nav_buttons[1]
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

    def _on_nav_clicked(self, name: str, btn: TopNavigationButton):
        """Handle navigation button click with exclusive checked state."""
        # Uncheck all others
        for b in self._nav_buttons:
            if b is not btn:
                b.setChecked(False)
        btn.setChecked(True)
        self._active_menu_btn = btn

        # Emit signals
        self.menu_clicked.emit(name)
        if name == "Projetos":
            self.arquivo_clicked.emit()
        elif name == "Logs":
            self.logs_clicked.emit()
        else:
            self.module_changed.emit(name)

    def set_active_menu(self, name: str):
        """Programmatically set the active menu button."""
        for btn in self._nav_buttons:
            btn.setChecked(btn._menu_id == name)
            if btn._menu_id == name:
                self._active_menu_btn = btn

    # "Projetos" always stays reachable (it's the only way to ever get a
    # project in the first place) and "Logs" doesn't need one (see
    # MainLayout._on_menu_view) — every other module reads/writes through
    # window.uow, which is None until a project exists.
    _ALWAYS_ENABLED = {"Projetos", "Logs"}

    def set_modules_enabled(self, enabled: bool):
        """Fades out and disables every module button except Projetos/Logs
        while no project is open, so there's nothing to click into that
        would silently no-op every action — called from Application on
        startup (no project yet) and again once one loads/closes."""
        for btn in self._nav_buttons:
            btn.setEnabled(enabled or btn._menu_id in self._ALWAYS_ENABLED)

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
