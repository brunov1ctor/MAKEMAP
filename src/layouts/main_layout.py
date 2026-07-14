"""Main layout — mapa fullscreen com painéis glass flutuando por cima."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QSizePolicy
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.top_bar import TopBar
from src.layouts.panels.toolbar import CanvasToolbar
from src.layouts.panels.explorer import ExplorerPanel, FilterPanel
from src.layouts.panels.canvas_area import CanvasArea
from src.layouts.panels.inspector import InspectorPanel, QuestPanel, LayersPanel
from src.layouts.panels.progression import ProgressionBar
from src.layouts.panels.status_bar import StatusBar
from src.layouts.panels.logs_panel import LogsPanel
from src.canvas.overlays import HUDOverlay, Compass, ZoomControl, MiniMap
from src.engines.integrator import EngineIntegrator


class MainLayout(QWidget):
    """
    Canvas fullscreen + painéis como filhos diretos posicionados por cima.
    O canvas recebe mouse events nativamente nas áreas não cobertas.
    """

    LEFT_W = 280
    RIGHT_W = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {Colors.BG_SECONDARY};")

        # ═══ Canvas (sempre no fundo) ═══
        self.canvas = CanvasArea(self)

        # ═══ Painéis (filhos diretos, flutuam por cima) ═══
        self.top_bar = TopBar(self)

        self.canvas_toolbar = CanvasToolbar(self)
        self.canvas_toolbar.tool_selected.connect(self.canvas.engine.tool_manager.activate)

        # Explorer (esquerda)
        self._left_scroll = self._make_scroll()
        left_container = QWidget()
        left_container.setAttribute(Qt.WA_TranslucentBackground)
        left_container.setStyleSheet("background: transparent;")
        left_lay = QVBoxLayout(left_container)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left_lay.setSpacing(8)
        self.left_panel = ExplorerPanel()
        self.filters_panel = FilterPanel()
        left_lay.addWidget(self.left_panel, 1)
        left_lay.addWidget(self.filters_panel)
        left_lay.addStretch()
        self._left_scroll.setWidget(left_container)
        self.left_panel.collapsed_changed.connect(
            lambda collapsed: left_lay.setStretchFactor(self.left_panel, 0 if collapsed else 1)
        )

        # Inspector (direita)
        self._right_scroll = self._make_scroll()
        right_container = QWidget()
        right_container.setAttribute(Qt.WA_TranslucentBackground)
        right_container.setStyleSheet("background: transparent;")
        right_lay = QVBoxLayout(right_container)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right_lay.setSpacing(8)
        self.right_panel = InspectorPanel()
        self.quest_panel = QuestPanel()
        self.layers_panel = LayersPanel()
        right_lay.addWidget(self.right_panel, 1)
        right_lay.addWidget(self.quest_panel)
        right_lay.addWidget(self.layers_panel)
        self._right_scroll.setWidget(right_container)
        self.right_panel.collapsed_changed.connect(
            lambda collapsed: right_lay.setStretchFactor(self.right_panel, 0 if collapsed else 1)
        )

        # Logs (dentro do container direito)
        self.logs_panel = LogsPanel()
        right_lay.addWidget(self.logs_panel)
        right_lay.addStretch()

        # Progression + Status
        self.progression = ProgressionBar(self)
        self.progression.size_changed.connect(self._reposition)
        self.status_bar = StatusBar(self)

        # Overlays
        self.hud = HUDOverlay(self)
        self.compass = Compass(self)
        self.zoom_control = ZoomControl(self)
        self.minimap = MiniMap(self)

        # ═══ Conexões ═══
        self.canvas.engine.cursor_moved.connect(
            lambda x, y: self.status_bar.coords.setText(f"X: {x:.0f}  Y: {y:.0f}")
        )
        self.canvas.engine.zoom_changed.connect(self._on_zoom)
        self.canvas.engine.tool_changed.connect(
            lambda t: self.status_bar.tool_label.setText(f"🔧 {t}")
        )
        self.status_bar.zoom_in_clicked.connect(self.canvas.engine.zoom_in)
        self.status_bar.zoom_out_clicked.connect(self.canvas.engine.zoom_out)

        # ═══ Engine Integrator ═══
        self.engines = EngineIntegrator(self)
        self.engines.connect_ui(self)

    def _make_scroll(self) -> QScrollArea:
        s = QScrollArea(self)
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        s.setAttribute(Qt.WA_TranslucentBackground)
        s.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
        """)
        return s

    def _reposition(self):
        """Força recalcular posições quando um painel muda de tamanho."""
        self.resizeEvent(None)

    def resizeEvent(self, event):
        if event:
            super().resizeEvent(event)
        w, h = self.width(), self.height()

        top_h = 72
        toolbar_h = 42
        status_h = 80
        prog_h = self.progression.height()

        body_top = top_h
        body_bottom = h - status_h
        body_h = body_bottom - body_top

        center_x = self.LEFT_W
        center_w = max(0, w - self.LEFT_W - self.RIGHT_W)

        # Canvas: preenche tudo, fica embaixo
        self.canvas.setGeometry(0, 0, w, h)
        self.canvas.lower()

        # TopBar: topo, largura total
        self.top_bar.setGeometry(0, 0, w, top_h)

        # Explorer: esquerda, abaixo do top, até status
        self._left_scroll.setGeometry(0, body_top, self.LEFT_W, body_h)

        # Inspector: direita, abaixo do top, até status
        self._right_scroll.setGeometry(w - self.RIGHT_W, body_top, self.RIGHT_W, body_h)

        # Toolbar: abaixo do top, entre painéis laterais
        self.canvas_toolbar.setGeometry(center_x, body_top, center_w, toolbar_h)

        # Progression: centro-baixo, entre laterais, acima do status
        self.progression.setGeometry(center_x, body_bottom - prog_h, center_w, prog_h)

        # StatusBar: fundo, largura total
        self.status_bar.setGeometry(0, h - status_h, w, status_h)

        # Overlays na área central livre (abaixo da toolbar, acima da progression)
        ov_top = body_top + toolbar_h
        ov_h = max(0, body_h - toolbar_h - prog_h)

        self.hud.move(center_x + 16, ov_top + 8)
        self.compass.move(center_x + center_w - self.compass.width() - 16, ov_top + 8)
        self.zoom_control.move(
            center_x + center_w - self.zoom_control.width() - 16,
            ov_top + (ov_h - self.zoom_control.height()) // 2,
        )
        self.minimap.move(
            center_x + center_w - self.minimap.width() - 16,
            ov_top + ov_h - self.minimap.height() - 8,
        )

    def _on_zoom(self, percent: int):
        self.status_bar.zoom_label.setText(f"{percent}%")
        self.canvas_toolbar.zoom_label.setText(f"{percent}%")
        self.minimap.zoom_label.setText(f"{percent}%")
