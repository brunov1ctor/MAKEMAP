"""Engine Integrator — status bar dashboard counts.

Used to also instantiate/wire a parallel set of in-memory "engines" (tool
routing, explorer/inspector, plugin hooks, view modes, validation,
performance, painting mode, MMORPG entities, workspace, rendering, polish,
road/river path drawing, smart-asset presets, map export) that nothing in
the app ever fed real data into or read from — the actual tool-changed
label, explorer tree, and inspector panel are wired directly in
main_layout.py/ExplorerPanel/ExplorerSyncMediator against real project
data. That whole dead layer (~1000+ lines across src/engines/map/painting.py,
road.py, river.py, path_engine.py, smart_asset.py, game/mmorpg.py,
io/workspace.py, io/export.py, view_modes.py, validation.py, performance.py,
explorer_inspector.py, plugin_sdk.py, polish.py, rendering.py, and the
TypographyEngine class) was removed. Only the status-bar dashboard counts
(set_uow/update_stats) and the canvas "fit to view" handler were ever
actually reachable, so that's all that's left here.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

_STATS_DEBOUNCE_MS = 30  # coalesces a burst of DB writes from one action (e.g. a save touching several tables) into a single re-count


class EngineIntegrator(QObject):
    """Status bar dashboard counts + canvas fit-to-view, wired to MainLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Status bar dashboard counts — see set_uow()/update_stats() below.
        self._uow = None
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.timeout.connect(self.update_stats)

    def connect_ui(self, layout):
        """Wire engines to MainLayout panels."""
        from src.layouts.main_layout import MainLayout
        ml: MainLayout = layout

        ml.status_bar.fit_clicked.connect(self._on_fit_clicked)

        # Store reference
        self._layout = ml

    # ─── Handlers ────────────────────────────────────────────────────────

    def _on_fit_clicked(self):
        """Fit canvas to view."""
        self._layout.canvas.engine.zoom_reset()

    # ─── Public API ──────────────────────────────────────────────────────

    def set_uow(self, uow):
        """Called once a project's database is open (see application.py's
        _on_project_loaded) — until then the dashboard has nothing real to
        count. Wires Database.on_write (see connection.py) so every
        committed write anywhere in the app — every repository's
        create/update/delete all go through Database.transaction(), the one
        choke point — schedules a re-count, instead of blindly re-counting
        on a fixed timer regardless of whether anything actually changed.
        The old previous uow's hook (if any) is cleared first so a closed
        project's Database can't keep firing into a stale integrator."""
        if self._uow is not None:
            self._uow.db.on_write = None
        self._uow = uow
        if uow is None:
            self._stats_timer.stop()
            return
        uow.db.on_write = self._on_data_written
        self.update_stats()

    def _on_data_written(self):
        self._stats_timer.start(_STATS_DEBOUNCE_MS)

    def update_stats(self):
        """Push real per-project counts to the status bar dashboard.

        `bosses` is `uow.mobs.count(category="boss")`, not a dedicated
        bosses table — the Mobs panel's "Boss" folder (mob_categories id
        "boss", seeded by migration 16) is where bosses actually get
        created; BossRepository has no UI writing to it anywhere."""
        if self._uow is None:
            return
        uow = self._uow
        self._layout.status_bar.update_stats(
            regions=uow.zones.count(),
            subregions=uow.canvas_items.count(item_type="marker"),
            npcs=uow.npcs.count(),
            mobs=uow.mobs.count(),
            items=uow.items.count(),
            quests=uow.quests.count(),
            bosses=uow.mobs.count(category="boss"),
            dungeons=uow.dungeons.count(),
        )
