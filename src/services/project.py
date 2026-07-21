"""Project model — represents a MAKEMAP project on disk."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class ProjectMeta:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Novo Projeto"
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def touch(self):
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProjectMeta:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class Project:
    """Manages the .makemap project folder structure."""

    EXTENSION = ".makemap"
    META_FILE = "project.json"
    DB_FILE = "project.sqlite"
    DIRS = ["assets", "assets/imported", "assets/custom", "thumbnails", "maps", "autosave", "backups", "cache"]

    def __init__(self, path: Path, meta: ProjectMeta):
        self.path = path
        self.meta = meta
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self):
        self._dirty = True

    def mark_clean(self):
        self._dirty = False

    @property
    def meta_path(self) -> Path:
        return self.path / self.META_FILE

    @property
    def db_path(self) -> Path:
        return self.path / self.DB_FILE

    @property
    def autosave_dir(self) -> Path:
        return self.path / "autosave"

    @classmethod
    def create(cls, directory: Path, name: str) -> Project:
        """Create a new project folder with all subdirectories."""
        project_dir = cls._unique_dir(directory, name)
        project_dir.mkdir(parents=True, exist_ok=True)

        for d in cls.DIRS:
            (project_dir / d).mkdir(parents=True, exist_ok=True)

        meta = ProjectMeta(name=name)
        project = cls(project_dir, meta)
        project._write_meta()
        return project

    @classmethod
    def _unique_dir(cls, directory: Path, name: str) -> Path:
        """Pick a folder for `name` that doesn't collide with an existing project.

        Project folders are named after the project, so two creations with the
        same name (e.g. the auto-generated "Projeto_<timestamp>" when the new-project
        button is clicked twice within the same second) would otherwise both resolve
        to the same directory and silently merge into one project.
        """
        candidate = directory / f"{name}{cls.EXTENSION}"
        n = 2
        while candidate.exists():
            candidate = directory / f"{name} ({n}){cls.EXTENSION}"
            n += 1
        return candidate

    @classmethod
    def open(cls, project_dir: Path) -> Project:
        """Open an existing project from its folder."""
        meta_file = project_dir / cls.META_FILE
        if not meta_file.exists():
            raise FileNotFoundError(f"Arquivo {cls.META_FILE} não encontrado em {project_dir}")

        data = json.loads(meta_file.read_text(encoding="utf-8"))
        meta = ProjectMeta.from_dict(data)
        return cls(project_dir, meta)

    def save(self):
        """Safe write: write to temp, validate, then replace."""
        self.meta.touch()
        tmp = self.meta_path.with_suffix(".tmp")
        data = json.dumps(self.meta.to_dict(), indent=2, ensure_ascii=False)

        # Write to temp
        tmp.write_text(data, encoding="utf-8")

        # Validate temp
        json.loads(tmp.read_text(encoding="utf-8"))

        # Replace original
        if self.meta_path.exists():
            backup = self.meta_path.with_suffix(".bak")
            if backup.exists():
                backup.unlink()
            self.meta_path.rename(backup)

        tmp.rename(self.meta_path)
        self._dirty = False

    def delete(self):
        """Remove the entire project folder from disk."""
        import shutil
        if self.path.exists():
            shutil.rmtree(self.path)

    def _write_meta(self):
        data = json.dumps(self.meta.to_dict(), indent=2, ensure_ascii=False)
        self.meta_path.write_text(data, encoding="utf-8")
        self._dirty = False
