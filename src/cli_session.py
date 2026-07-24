"""CLI session state and persistence helpers for Pahang CLI."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.project.environment import ProjectEnvironment, is_known_project_key


DEFAULT_PERSISTENCE_FILE = Path(".active_project.json")


def load_last_project_key(persistence_file: Path = DEFAULT_PERSISTENCE_FILE) -> str | None:
    """Load the last selected project key from disk, if present."""
    if not persistence_file.exists():
        return None

    try:
        data = json.loads(persistence_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    project_key = data.get("active_project")
    return str(project_key) if is_known_project_key(project_key) else None


def save_last_project_key(
    project_key: str,
    persistence_file: Path = DEFAULT_PERSISTENCE_FILE,
) -> None:
    """Persist the selected project key for the next CLI run."""
    try:
        persistence_file.write_text(json.dumps({"active_project": project_key}), encoding="utf-8")
    except Exception as exc:
        logging.warning("Failed to persist active project: %s", exc)


@dataclass
class CliSession:
    """Interactive CLI session state."""

    persistence_file: Path = field(default_factory=lambda: DEFAULT_PERSISTENCE_FILE)
    active_project: ProjectEnvironment | None = None

    def load_last_project_key(self) -> str | None:
        return load_last_project_key(self.persistence_file)

    def activate_project(self, environment: ProjectEnvironment) -> None:
        self.active_project = environment
        save_last_project_key(environment.project_key, self.persistence_file)
