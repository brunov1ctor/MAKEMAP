"""GridMediator — grid panel ↔ canvas engine wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout


class GridMediator:
    """Manages grid panel ↔ canvas engine connections."""

    def __init__(self, layout: MainLayout):
        self._l = layout

    def connect_panel(self):
        grid = self._l.canvas.engine.grid
        panel = self._l.grid_panel

        panel.size_slider.set_value(grid.cell_size)
        panel.subdivisions_slider.set_value(grid.subdivisions)
        panel.snap_check.setChecked(self._l.canvas.engine.snap.enabled)
        panel.measurements_check.setChecked(grid.show_measurements)
        self.sync_shape_combo()

        for sig in (panel.size_slider.value_changed, panel.subdivisions_slider.value_changed,
                    panel.opacity_slider.value_changed, panel.snap_toggled,
                    panel.measurements_toggled, panel.shape_changed):
            try:
                sig.disconnect()
            except (RuntimeError, TypeError, RuntimeWarning):
                pass

        def _update_size(v):
            grid.cell_size = v  # keep the decimal — the stepper allows half-meter steps now
            self._l.canvas.engine._update_grid()

        def _update_sub(v):
            grid.subdivisions = int(v)
            self._l.canvas.engine._update_grid()

        def _update_opacity(v):
            alpha_major = int(v * 2.55)
            alpha_minor = int(v * 1.0)
            grid.color_major = QColor(255, 255, 255, min(255, alpha_major))
            grid.color_minor = QColor(255, 255, 255, min(255, alpha_minor))
            self._l.canvas.engine._update_grid()

        def _update_shape(shape_name):
            grid.visible = shape_name != "Nenhum"
            if grid.visible:
                grid.shape = shape_name
            # Snap's meaning depends on the shape (it now fills whichever
            # cell you click, in that shape) — defaulting it off on every
            # shape change means turning it on is always a deliberate choice
            # for the shape you're currently looking at, not a leftover from
            # a previous one.
            if panel.snap_check.isChecked():
                panel.snap_check.setChecked(False)
            else:
                self._l.canvas.engine.snap.enabled = False
            self._l.canvas.engine._update_grid()

        def _update_measurements(on):
            grid.show_measurements = on
            self._l.canvas.engine._update_grid()

        panel.size_slider.value_changed.connect(_update_size)
        panel.subdivisions_slider.value_changed.connect(_update_sub)
        panel.opacity_slider.value_changed.connect(_update_opacity)
        panel.shape_changed.connect(_update_shape)
        panel.snap_toggled.connect(lambda on: self._l.canvas.engine.snap.toggle())
        panel.measurements_toggled.connect(_update_measurements)

    def sync_shape_combo(self):
        """Reflect the grid's actual visible/shape state in the dropdown."""
        grid = self._l.canvas.engine.grid
        panel = self._l.grid_panel
        panel.shape_combo.blockSignals(True)
        panel.shape_combo.setCurrentText(grid.shape if grid.visible else "Nenhum")
        panel.shape_combo.blockSignals(False)
        # blockSignals() above means the combo's own currentTextChanged ->
        # _sync_snap_visibility wiring didn't fire for this programmatic set.
        panel._sync_snap_visibility(panel.shape_combo.currentText())
