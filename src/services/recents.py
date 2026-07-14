"""Recent projects tracker — persists list of recently opened projects."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass

MAX_RECENTS = 10
RECENTS_FILE = Path.home() / ".makemap" / "recents.json"


@dataclass
class RecentEntry:
    name: str
    path: str


def load_recents() -> list[RecentEntry]:
    if not RECENTS_FILE.exists():
        return []
    try:
        data = json.loads(RECENTS_FILE.read_text(encoding="utf-8"))
        return [RecentEntry(**e) for e in data]
    except Exception:
        return []


def add_recent(name: str, path: str):
    recents = load_recents()
    # Remove duplicate
    recents = [r for r in recents if r.path != path]
    recents.insert(0, RecentEntry(name=name, path=path))
    recents = recents[:MAX_RECENTS]
    _save(recents)


def _save(recents: list[RecentEntry]):
    RECENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [{"name": r.name, "path": r.path} for r in recents]
    RECENTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
