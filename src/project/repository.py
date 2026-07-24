"""Project repository module for Pahang CLI."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any, Sequence

import config
from src.project.models import ProjectMetadata


class ProjectRepository(ABC):
    """Abstract base class for accessing and persisting project metadata."""

    @abstractmethod
    def get(self, key: str) -> ProjectMetadata:
        """Retrieve project metadata by key."""

    @abstractmethod
    def list_all(self) -> Sequence[ProjectMetadata]:
        """Return all configured projects."""

    @abstractmethod
    def save(self, project: ProjectMetadata) -> None:
        """Persist project metadata."""

    @abstractmethod
    def get_default(self, preferred_key: str | None = None) -> ProjectMetadata | None:
        """Return default project metadata or None if no projects registered."""


class JsonFileProjectRepository(ProjectRepository):
    """Project repository backed by a JSON configuration file."""

    def __init__(self, config_file: Path | None = None) -> None:
        if config_file is None:
            self.config_file = Path(config._CONFIG_FILE)
        else:
            self.config_file = Path(config_file)

    def _read_projects_dict(self) -> dict[str, dict[str, Any]]:
        if self.config_file.exists():
            try:
                text = self.config_file.read_text(encoding="utf-8")
                data = json.loads(text)
                projects = data.get("projects", {})
                if isinstance(projects, dict):
                    return projects
            except Exception:
                pass
        return {}

    def get(self, key: str) -> ProjectMetadata:
        projects = self._read_projects_dict()
        if key not in projects:
            raise KeyError(f"Unknown project key: {key}")
        return ProjectMetadata.from_dict(key, projects[key])

    def list_all(self) -> Sequence[ProjectMetadata]:
        projects = self._read_projects_dict()
        return [ProjectMetadata.from_dict(k, v) for k, v in projects.items()]

    def save(self, project: ProjectMetadata) -> None:
        data: dict[str, Any] = {}
        if self.config_file.exists():
            try:
                loaded = json.loads(self.config_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                pass
        projects = data.get("projects", {})
        if not isinstance(projects, dict):
            projects = {}
        projects[project.key] = project.to_dict()
        data["projects"] = projects
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_default(self, preferred_key: str | None = None) -> ProjectMetadata | None:
        if preferred_key:
            try:
                return self.get(preferred_key)
            except KeyError:
                pass
        all_projects = self.list_all()
        if not all_projects:
            return None
        return all_projects[0]
