"""1. Barra Superior — glassmorphism, 72px, ícones, navegação completa."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QLineEdit,
    QComboBox, QSizePolicy, QWidget, QVBoxLayout,
)
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from src.styles.tokens import Colors, Metrics, Typography


class _NavButton(QToolButton):
    """Navigation button with icon + text."""

    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self.setText(f"{icon} {text}")
        self._name = text
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QToolButton {{
                color: {Colors.TEXT_MUTED};
                font-size: {Typography.SIZE_XS}px;
                padding: 6px 14px;
                border: none;
                border-radius: 8px;
                font-weight: {Typography.WEIGHT_MEDIUM};
                background: transparent;
            }}
            QToolButton:hover {{
                color: {Colors.TEXT_PRIMARY};
                background: {Colors.PANEL_HOVER};
            }}
            QToolButton:checked {{
                color: {Colors.ACCENT};
                background: {Colors.ACCENT_DIM};
                font-weight: {Typography.WEIGHT_BOLD};
            }}
        """)

    @property
    def nav_name(self):
        return self._name


class _IconButton(QToolButton):
    """Circular icon button for user area."""

    def __init__(self, icon: str, tooltip: str, size=36, parent=None):
        super().__init__(parent)
        self.setText(icon)
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QToolButton {{
                border: none;
                border-radius: {size // 2}px;
                font-size: 15px;
                color: {Colors.TEXT_MUTED};
                background: transparent;
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:pressed {{
                background: {Colors.PANEL_ACTIVE};
            }}
        """)


class TopBar(QFrame):
    """Barra superior 72px — glassmorphism, logo, projeto, navegação, busca, perfil."""

    module_changed = Signal(str)
    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("top_bar")
        self.setFixedHeight(Metrics.TOP_BAR_HEIGHT)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(0)

        # ── Grupo 1: Logo + Brand ──
        logo_frame = QFrame()
        logo_frame.setStyleSheet("background: transparent; border: none;")
        logo_layout = QHBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 0, 16, 0)
        logo_layout.setSpacing(10)

        logo = QLabel("◆")
        logo.setStyleSheet(f"""
            font-size: 22px; color: {Colors.ACCENT};
            background: transparent; border: none;
        """)
        logo_layout.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_name = QLabel("MAKE")
        brand_name.setStyleSheet(f"""
            font-size: 14px; font-weight: {Typography.WEIGHT_BLACK};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        brand_sub = QLabel("MAP")
        brand_sub.setStyleSheet(f"""
            font-size: 9px; font-weight: {Typography.WEIGHT_MEDIUM};
            color: {Colors.ACCENT}; background: transparent; border: none;
            letter-spacing: 2px;
        """)
        brand_col.addWidget(brand_name)
        brand_col.addWidget(brand_sub)
        logo_layout.addLayout(brand_col)

        layout.addWidget(logo_frame)
        layout.addWidget(self._sep())

        # ── Grupo 2: Projeto ──
        proj_frame = QFrame()
        proj_frame.setStyleSheet("background: transparent; border: none;")
        proj_layout = QHBoxLayout(proj_frame)
        proj_layout.setContentsMargins(12, 0, 12, 0)
        proj_layout.setSpacing(8)

        proj_icon = QLabel("📁")
        proj_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        proj_layout.addWidget(proj_icon)

        proj_col = QVBoxLayout()
        proj_col.setSpacing(0)
        proj_label = QLabel("PROJETO")
        proj_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 8px;
            font-weight: {Typography.WEIGHT_BOLD}; letter-spacing: 1px;
            background: transparent; border: none;
        """)
        proj_col.addWidget(proj_label)

        self.project_combo = QComboBox()
        self.project_combo.addItem("Sem Projeto")
        self.project_combo.setMinimumWidth(150)
        self.project_combo.setMaximumWidth(220)
        self.project_combo.setFixedHeight(28)
        self.project_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 6px;
                padding: 4px 10px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: {Typography.WEIGHT_BOLD};
            }}
            QComboBox:hover {{ border-color: {Colors.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_SECONDARY};
                border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_PRIMARY};
                border-radius: 6px;
            }}
        """)
        proj_col.addWidget(self.project_combo)
        proj_layout.addLayout(proj_col)

        layout.addWidget(proj_frame)
        layout.addWidget(self._sep())

        # ── Grupo 3: Navegação Principal ──
        nav_frame = QFrame()
        nav_frame.setStyleSheet("background: transparent; border: none;")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 0, 8, 0)
        nav_layout.setSpacing(2)

        self._nav_buttons = []
        modules = [
            ("🗺", "Mapa"), ("📜", "Quests"), ("🧙", "NPCs"),
            ("👹", "Mobs"), ("⚔", "Itens"), ("🏰", "Dungeons"),
            ("⚡", "Eventos"), ("📖", "Lore"), ("⚙", "Configurações"),
        ]
        for icon, name in modules:
            btn = _NavButton(icon, name)
            btn.clicked.connect(lambda checked, n=name: self._on_module(n))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        self._nav_buttons[0].setChecked(True)
        layout.addWidget(nav_frame)

        layout.addStretch()

        # ── Grupo 4: Busca Global ──
        search_frame = QFrame()
        search_frame.setStyleSheet("background: transparent; border: none;")
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Buscar... (Ctrl+K)")
        self.search.setMinimumWidth(180)
        self.search.setMaximumWidth(320)
        self.search.setFixedHeight(34)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 17px;
                padding: 0 16px;
                font-size: 11px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT};
                background: {Colors.GLASS_BG_STRONG};
            }}
        """)
        self.search.returnPressed.connect(lambda: self.search_requested.emit(self.search.text()))
        search_layout.addWidget(self.search)
        layout.addWidget(search_frame)

        layout.addStretch()

        # ── Grupo 5: Área do Usuário ──
        user_frame = QFrame()
        user_frame.setStyleSheet("background: transparent; border: none;")
        user_layout = QHBoxLayout(user_frame)
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.setSpacing(6)

        self.btn_notifications = _IconButton("🔔", "Notificações")
        self.btn_profile = _IconButton("👤", "Perfil")
        self.btn_settings = _IconButton("⚙", "Configurações Rápidas")

        user_layout.addWidget(self.btn_notifications)
        user_layout.addWidget(self.btn_profile)
        user_layout.addWidget(self.btn_settings)

        layout.addWidget(user_frame)

    def _on_module(self, name: str):
        for btn in self._nav_buttons:
            btn.setChecked(btn.nav_name == name)
        self.module_changed.emit(name)

    def _sep(self):
        s = QFrame()
        s.setFixedSize(1, 36)
        s.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return s

    def set_project_name(self, name: str):
        self.project_combo.setItemText(0, name)

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
