"""MiniMap — minimapa com viewport indicator e zoom horizontal integrado."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QSlider, QGraphicsView,
)
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QColor, QPen, QBrush, QPainter

from src.styles.tokens import Colors, Typography


class _MiniMapView(QGraphicsView):
    """Secondary view that renders the scene in miniature."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet(f"background: {Colors.BG_TERTIARY}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;")
        self._view_rect: QRectF = QRectF()

    def set_viewport_rect(self, rect: QRectF):
        """Store viewport rect and trigger repaint (drawn in foreground, not in scene)."""
        self._view_rect = rect
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Draw viewport indicator on top without adding items to the shared scene."""
        if self._view_rect.isNull() or self._view_rect.isEmpty():
            return
        painter.setPen(QPen(QColor(79, 195, 247, 200), 0))  # cosmetic pen
        painter.setBrush(QBrush(QColor(79, 195, 247, 30)))
        painter.drawRect(self._view_rect)

    def wheelEvent(self, event):
        event.ignore()

    def mousePressEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()


class MiniMap(QFrame):
    """Minimapa com viewport indicator e zoom horizontal integrado."""

    zoom_changed = Signal(int)  # percent (5-500)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._full_size = (170, 140)
        self._collapsed_size = (170, 30)
        self._main_viewport = None
        self.setFixedSize(*self._full_size)
        self.setStyleSheet(f"""
            MiniMap {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("\U0001f5fa Minimap")
        header.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        header_row.addWidget(header)
        header_row.addStretch()

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("\u25bc")
        self._toggle_btn.setFixedSize(16, 16)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 8px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._toggle_btn.clicked.connect(self.toggle_visibility)
        header_row.addWidget(self._toggle_btn)
        layout.addLayout(header_row)

        # Mini view (renders the scene)
        self._mini_view = _MiniMapView()
        layout.addWidget(self._mini_view, 1)

        # Refresh timer (throttle updates to ~15fps)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(66)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

        # Zoom bar (horizontal, integrada)
        self._zoom_row = QFrame()
        self._zoom_row.setStyleSheet("background: transparent; border: none;")
        zoom_lay = QHBoxLayout(self._zoom_row)
        zoom_lay.setContentsMargins(0, 2, 0, 0)
        zoom_lay.setSpacing(4)

        btn_style = f"""
            QToolButton {{
                border: none; border-radius: 3px; font-size: 10px;
                color: {Colors.TEXT_MUTED}; background: transparent;
                padding: 0px;
            }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """

        self._btn_out = QToolButton()
        self._btn_out.setText("\u2212")
        self._btn_out.setFixedSize(14, 14)
        self._btn_out.setStyleSheet(btn_style)
        self._btn_out.clicked.connect(self._zoom_out)
        zoom_lay.addWidget(self._btn_out)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(1, 10000)
        self._slider.setValue(100)
        self._slider.setFixedHeight(12)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.wheelEvent = lambda e: e.ignore()
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 3px; background: {Colors.BORDER_SUBTLE}; border-radius: 1px;
            }}
            QSlider::handle:horizontal {{
                width: 8px; height: 8px; margin: -3px 0;
                background: {Colors.ACCENT}; border-radius: 4px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Colors.ACCENT_DIM}; border-radius: 1px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_slider)
        zoom_lay.addWidget(self._slider, 1)

        self._btn_in = QToolButton()
        self._btn_in.setText("+")
        self._btn_in.setFixedSize(14, 14)
        self._btn_in.setStyleSheet(btn_style)
        self._btn_in.clicked.connect(self._zoom_in)
        zoom_lay.addWidget(self._btn_in)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(30)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XXS}px;
            background: transparent; border: none;
        """)
        zoom_lay.addWidget(self.zoom_label)

        layout.addWidget(self._zoom_row)

        self._updating = False
        self._hidden_items: list = []

    # ─── Zoom API ────────────────────────────────────────────────────────

    def set_zoom(self, percent: int):
        """Update slider without emitting signal (called externally)."""
        self._updating = True
        self._slider.setValue(max(1, percent))
        self.zoom_label.setText(f"{percent}%")
        self._updating = False

    def _on_slider(self, value: int):
        self.zoom_label.setText(f"{value}%")
        if not self._updating:
            self.zoom_changed.emit(value)

    def _zoom_in(self):
        self._slider.setValue(self._slider.value() + 15)

    def _zoom_out(self):
        self._slider.setValue(max(1, self._slider.value() - 15))

    # ─── Viewport binding ────────────────────────────────────────────────

    def set_viewport(self, viewport):
        """Bind to the main Viewport to share its scene and track view changes."""
        self._main_viewport = viewport
        self._mini_view.setScene(viewport.scene())
        viewport.view_changed.connect(self._schedule_refresh)
        viewport.scene().changed.connect(self._schedule_refresh)
        self._refresh()

    def register_hidden_item(self, item):
        """Register a scene item that should not appear in the minimap."""
        self._hidden_items.append(item)

    def unregister_hidden_item(self, item):
        """Remove item from the minimap hidden list."""
        try:
            self._hidden_items.remove(item)
        except ValueError:
            pass

    def _schedule_refresh(self, *_args):
        """Ensure refresh happens on next timer tick (avoids redundant repaints)."""
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _refresh(self):
        """Fit the mini view to scene content and draw viewport indicator."""
        if not self._main_viewport or not self._expanded:
            return
        scene = self._main_viewport.scene()
        if not scene:
            return

        # Temporarily hide overlay items (brush cursor etc.)
        shown = [item for item in self._hidden_items if item.isVisible()]
        for item in shown:
            item.hide()

        # Fit to items bounding rect (with margin)
        items_rect = scene.itemsBoundingRect()
        if items_rect.isEmpty():
            items_rect = QRectF(-500, -500, 1000, 1000)
        margin = max(items_rect.width(), items_rect.height()) * 0.1
        fit_rect = items_rect.adjusted(-margin, -margin, margin, margin)
        self._mini_view.fitInView(fit_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._mini_view.viewport().update()

        # Viewport indicator
        vp = self._main_viewport
        top_left = vp.mapToScene(0, 0)
        bottom_right = vp.mapToScene(vp.viewport().width(), vp.viewport().height())
        view_rect = QRectF(top_left, bottom_right)
        self._mini_view.set_viewport_rect(view_rect)

        # Restore
        for item in shown:
            item.show()

    # ─── Toggle ──────────────────────────────────────────────────────────

    def toggle_visibility(self):
        self._expanded = not self._expanded
        self._mini_view.setVisible(self._expanded)
        self._zoom_row.setVisible(self._expanded)
        if self._expanded:
            self.setFixedSize(*self._full_size)
            self._toggle_btn.setText("\u25bc")
            self._refresh()
        else:
            self.setFixedSize(*self._collapsed_size)
            self._toggle_btn.setText("\u25b6")
