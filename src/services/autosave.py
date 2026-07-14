"""Autosave service — periodic safe saves with recovery."""

from __future__ import annotations

import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QTimer, QObject, Signal

from src.services.project import Project

logger = logging.getLogger("MAKEMAP")


class AutosaveService(QObject):
    """Manages periodic autosave and crash recovery."""

    state_changed = Signal(str)  # "Salvo", "Salvando...", "Alterações pendentes"

    INTERVAL_MS = 60_000  # 1 minute default
    MAX_AUTOSAVES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._do_autosave)

    def start(self, project: Project, interval_ms: int | None = None):
        self._project = project
        self._timer.start(interval_ms or self.INTERVAL_MS)
        logger.info("Autosave iniciado (intervalo: %dms)", self._timer.interval())

    def stop(self):
        self._timer.stop()
        self._project = None

    def notify_change(self):
        """Called whenever the project is modified."""
        if self._project:
            self._project.mark_dirty()
            self.state_changed.emit("Alterações pendentes")

    def _do_autosave(self):
        if not self._project or not self._project.dirty:
            return

        self.state_changed.emit("Salvando...")
        try:
            autosave_dir = self._project.autosave_dir
            autosave_dir.mkdir(parents=True, exist_ok=True)

            # Rotate old autosaves
            existing = sorted(autosave_dir.glob("autosave_*.json"), reverse=True)
            for old in existing[self.MAX_AUTOSAVES - 1:]:
                old.unlink()

            # Write autosave
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = autosave_dir / f"autosave_{ts}.json"
            dest.write_text(
                json.dumps(self._project.meta.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            self._project.mark_clean()
            self.state_changed.emit("Salvo")
            logger.debug("Autosave concluído: %s", dest.name)
        except Exception as e:
            logger.error("Falha no autosave: %s", e)
            self.state_changed.emit("Erro no autosave")

    @staticmethod
    def has_recovery(project_dir: Path) -> bool:
        autosave_dir = project_dir / "autosave"
        if not autosave_dir.exists():
            return False
        return any(autosave_dir.glob("autosave_*.json"))

    @staticmethod
    def recover_latest(project_dir: Path) -> dict | None:
        autosave_dir = project_dir / "autosave"
        files = sorted(autosave_dir.glob("autosave_*.json"), reverse=True)
        if not files:
            return None
        return json.loads(files[0].read_text(encoding="utf-8"))
