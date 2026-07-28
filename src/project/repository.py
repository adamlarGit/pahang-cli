"""Project repository module for Pahang CLI."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import Any, Sequence

import config
from src.project.models import CameraConfig, ProjectMetadata
from src.project.storage import LocalWorkspaceStorage



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

    @abstractmethod
    def get_camera_config(self) -> CameraConfig:
        """Retrieve camera photo pattern configuration."""

    @abstractmethod
    def save_camera_config(self, camera_config: CameraConfig) -> None:
        """Persist camera photo pattern configuration."""

    @abstractmethod
    def update(self, project: ProjectMetadata) -> None:
        """Update existing project metadata configuration."""

    @abstractmethod
    def update_base_path(self, key: str, new_path: str) -> None:
        """Update workspace root directory path for an existing project and bootstrap subfolders."""

    @abstractmethod
    def delete(self, key: str, session: Any | None = None) -> None:
        """Unregister a project from catalog configuration and reset active session if deleted."""



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

    def update(self, project: ProjectMetadata) -> None:
        """Update existing project metadata configuration."""
        _ = self.get(project.key)
        self.save(project)

    def update_base_path(self, key: str, new_path: str) -> None:
        """Update workspace root directory path for an existing project and bootstrap subfolders."""
        meta = self.get(key)
        updated_meta = ProjectMetadata(
            key=meta.key,
            name=meta.name,
            po_number=meta.po_number,
            state=meta.state,
            voltage_type=meta.voltage_type,
            year=meta.year,
            cycle=meta.cycle,
            technologies=meta.technologies,
            base_path=str(new_path),
        )
        self.save(updated_meta)
        storage = LocalWorkspaceStorage(new_path)
        storage._initialize_project_workspace()

    def delete(self, key: str, session: Any | None = None) -> None:
        """Unregister a project from catalog configuration and reset active session if deleted."""
        data: dict[str, Any] = {}
        if self.config_file.exists():
            try:
                loaded = json.loads(self.config_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                pass
        projects = data.get("projects", {})
        if isinstance(projects, dict) and key in projects:
            del projects[key]
            data["projects"] = projects
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        if session is not None and getattr(session, "active_project_key", None) == key:
            if hasattr(session, "deactivate_project"):
                session.deactivate_project()


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

    def _get_project_config_path(self) -> Path | None:
        try:
            meta = self.get_default()
            if meta and meta.base_path:
                return Path(meta.base_path) / "project_config.json"
        except (KeyError, ValueError, AttributeError):
            pass
        return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logging.warning("Could not read JSON configuration from %s: %s", path, exc)
            return {}

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except FileNotFoundError as exc:
            logging.warning("Could not write JSON configuration to %s: %s", path, exc)

    def get_camera_config(self) -> CameraConfig:
        target_path = self._get_project_config_path()
        if not target_path or not target_path.exists():
            target_path = self.config_file

        data = self._read_json(target_path)
        raw_cfg = data.get("camera_config", data if "ir_mode" in data else None)
        if raw_cfg and isinstance(raw_cfg, dict):
            return CameraConfig.from_dict(raw_cfg)
        return CameraConfig()

    def save_camera_config(self, camera_config: CameraConfig) -> None:
        target_path = self._get_project_config_path() or self.config_file
        data = self._read_json(target_path)
        data["camera_config"] = camera_config.to_dict()
        self._write_json(target_path, data)
