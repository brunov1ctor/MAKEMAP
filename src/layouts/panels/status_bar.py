"""6-7. Dashboard de Estatísticas + Barra de Status profissional."""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QWidget,
    QSizePolicy, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush

from src.styles.tokens import Colors, Metrics, Typography


# ─── Stat Card ─────────────────────────────────────────────────────────────

class _StatCard(QFrame):
    """Card de estatística individual — ícone, valor, label."""

    def __init__(self, icon: str, label: str, value: str = "0", color: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self._label_text = label
        self.setFixedHeight(44)
        self.setMinimumWidth(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            _StatCard {{
                background: {Colors.GLASS_BG};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 8px;
            }}
            _StatCard:hover {{
                background: {Colors.PANEL_HOVER};
                border-color: {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 14px; background: transparent; border: none;")
        layout.addWidget(icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(0)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BLACK};
            color: {color}; background: transparent; border: none;
        """)
        info_col.addWidget(self.value_label)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"""
            font-size: 8px; color: {Colors.TEXT_MUTED};
            font-weight: {Typography.WEIGHT_MEDIUM};
            background: transparent; border: none;
        """)
        info_col.addWidget(name_lbl)

        layout.addLayout(info_col)

    def set_value(self, value):
        self.value_label.setText(str(value))


# ─── Stats Dashboard (6) ──────────────────────────────────────────────────

class StatsDashboard(QFrame):
    """Dashboard de estatísticas — cards modernos com atualização automática."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            StatsDashboard {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)

        self.card_regions = _StatCard("🗺", "Regiões", "0", Colors.ACCENT)
        self.card_subregions = _StatCard("📍", "Sub-regiões", "0", Colors.TEAL)
        self.card_npcs = _StatCard("🧙", "NPCs", "0", Colors.SUCCESS)
        self.card_mobs = _StatCard("👹", "Mobs", "0", Colors.ERROR)
        self.card_items = _StatCard("⚔", "Itens", "0", Colors.WARNING)
        self.card_quests = _StatCard("📜", "Quests", "0", Colors.PURPLE)
        self.card_bosses = _StatCard("💀", "Bosses", "0", Colors.ORANGE)
        self.card_events = _StatCard("⚡", "Eventos", "0", Colors.INFO)
        self.card_dungeons = _StatCard("🏰", "Dungeons", "0", "#78909C")

        cards = [
            self.card_regions, self.card_subregions, self.card_npcs,
            self.card_mobs, self.card_items, self.card_quests,
            self.card_bosses, self.card_events, self.card_dungeons,
        ]
        for card in cards:
            layout.addWidget(card)

    def update_stats(self, **kwargs):
        mapping = {
            "regions": self.card_regions,
            "subregions": self.card_subregions,
            "npcs": self.card_npcs,
            "mobs": self.card_mobs,
            "items": self.card_items,
            "quests": self.card_quests,
            "bosses": self.card_bosses,
            "events": self.card_events,
            "dungeons": self.card_dungeons,
        }
        for key, value in kwargs.items():
            if key in mapping:
                mapping[key].set_value(f"{value:,}".replace(",", "."))


# ─── Status Bar (7) ───────────────────────────────────────────────────────

class StatusBar(QFrame):
    """Barra de status — coordenadas, zoom, FPS, ferramenta, camada, save."""

    zoom_in_clicked = Signal()
    zoom_out_clicked = Signal()
    fit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("status_bar")
        self.setFixedHeight(80)  # dashboard (52) + bar (28)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Stats dashboard
        self.dashboard = StatsDashboard()
        main_layout.addWidget(self.dashboard)

        # Status bar row
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {Colors.GLASS_BG_STRONG};
                border-top: 1px solid {Colors.BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(16)

        stat_style = f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            background: transparent; border: none;
        """

        # Coordinates
        self.coords = QLabel("X: 0  Y: 0")
        self.coords.setStyleSheet(stat_style)
        layout.addWidget(self.coords)

        layout.addWidget(self._sep())

        # Zoom
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        layout.addWidget(self.zoom_label)

        # Zoom controls
        btn_style = f"""
            QToolButton {{
                border: none; border-radius: 4px;
                font-size: 12px; color: {Colors.TEXT_MUTED};
                padding: 2px; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """

        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setFixedSize(20, 20)
        zoom_out.setStyleSheet(btn_style)
        zoom_out.clicked.connect(self.zoom_out_clicked.emit)
        layout.addWidget(zoom_out)

        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setFixedSize(20, 20)
        zoom_in.setStyleSheet(btn_style)
        zoom_in.clicked.connect(self.zoom_in_clicked.emit)
        layout.addWidget(zoom_in)

        fit_btn = QToolButton()
        fit_btn.setText("⊡")
        fit_btn.setToolTip("Encaixar na tela")
        fit_btn.setFixedSize(20, 20)
        fit_btn.setStyleSheet(btn_style)
        fit_btn.clicked.connect(self.fit_clicked.emit)
        layout.addWidget(fit_btn)

        layout.addWidget(self._sep())

        # FPS
        self.fps_label = QLabel("60 FPS")
        self.fps_label.setStyleSheet(f"""
            color: {Colors.SUCCESS}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        layout.addWidget(self.fps_label)

        layout.addWidget(self._sep())

        # Active tool
        self.tool_label = QLabel("🔧 Selecionar")
        self.tool_label.setStyleSheet(stat_style)
        layout.addWidget(self.tool_label)

        layout.addWidget(self._sep())

        # Active layer
        self.layer_label = QLabel("📐 Terreno")
        self.layer_label.setStyleSheet(stat_style)
        layout.addWidget(self.layer_label)

        layout.addStretch()

        # Messages
        self.message_label = QLabel("")
        self.message_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            background: transparent; border: none;
        """)
        layout.addWidget(self.message_label)

        layout.addWidget(self._sep())

        # Save indicator
        self.save_label = QLabel("● Salvo")
        self.save_label.setStyleSheet(f"""
            color: {Colors.SUCCESS}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        layout.addWidget(self.save_label)

        # Project state
        self.state_label = QLabel("Pronto")
        self.state_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            background: transparent; border: none;
        """)
        layout.addWidget(self.state_label)

        main_layout.addWidget(bar)

        # FPS timer
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)
        self._frame_count = 0

    def _sep(self):
        s = QFrame()
        s.setFixedSize(1, 14)
        s.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
        return s

    def _update_fps(self):
        # Placeholder — real FPS would come from canvas render loop
        pass

    def update_stats(self, **kwargs):
        """Delegate to dashboard."""
        self.dashboard.update_stats(**kwargs)

    def show_message(self, msg: str, duration_ms: int = 3000):
        self.message_label.setText(msg)
        QTimer.singleShot(duration_ms, lambda: self.message_label.setText(""))

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
