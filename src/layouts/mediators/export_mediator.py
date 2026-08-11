"""ExportMediator — wires the ExportPanel's export_requested signal to
map_exporter, running the actual render/save against the canvas engine and
reporting success/failure on the status bar. Also keeps the panel's live
preview thumbnail in sync with content_changed (area/frame/background
option changes)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap

from src.engines.export.map_exporter import export_map_image, render_preview

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")


class ExportMediator:
    def __init__(self, layout: MainLayout):
        self._l = layout
        self._l.export_panel.set_frame_options_fn(self._l.brush_panel.frame_options)
        self._l.export_panel.export_requested.connect(self._on_export_requested)
        self._l.export_panel.content_changed.connect(self.refresh_preview)
        self._pending = False

        # "Viewport atual" preview goes stale the moment the user pans/zooms
        # (WASD, scroll) with the panel open — view_changed fires up to 60x/
        # sec (see engine.py's own comment on it), so debounce with a timer
        # instead of re-rendering on every tick, same pattern MiniMap uses
        # for its own view_changed-driven refresh.
        self._viewport_refresh_timer = QTimer()
        self._viewport_refresh_timer.setSingleShot(True)
        self._viewport_refresh_timer.setInterval(120)
        self._viewport_refresh_timer.timeout.connect(self._do_refresh_preview)
        self._l.canvas.engine.viewport.view_changed.connect(self._on_viewport_view_changed)

    def _on_viewport_view_changed(self):
        panel = self._l.export_panel
        if not panel.isVisible() or panel.current_options().get("area") != "viewport":
            return
        self._viewport_refresh_timer.start()

    def _on_export_requested(self, options: dict):
        save_path = options.pop("save_path")
        try:
            export_map_image(self._l.canvas.engine, options, save_path)
        except Exception:
            logger.exception("Falha ao exportar mapa")
            self._l.status_bar.show_message("Falha ao exportar mapa.")
            return
        self._l.status_bar.show_message(f"Mapa exportado: {save_path}")

    def refresh_preview(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._do_refresh_preview)

    def _do_refresh_preview(self):
        options = self._l.export_panel.current_options()
        try:
            image = render_preview(self._l.canvas.engine, options)
        except Exception:
            logger.exception("Falha ao gerar pré-visualização de exportação")
            self._l.export_panel.set_preview_pixmap(None)
            return
        self._l.export_panel.set_preview_pixmap(QPixmap.fromImage(image))
