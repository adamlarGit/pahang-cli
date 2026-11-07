"""Run Record behaviour, tested by running fake actions through the action-running layer.

No test here starts Word or Excel, and none touches a real project folder or the
real %LOCALAPPDATA%: every location used is under pytest's tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src import __version__
from src.cli_session import CliSession
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import ProjectWorkflowAction
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE
from src.utility_actions import UtilityAction
from src.workflow_cli import _run_project_workflow_menu, _run_utility_actions_menu


def make_environment(base_path: Path, key: str = "fake_project") -> ProjectEnvironment:
    metadata = ProjectMetadata(
        key=key,
        name="Fake Project",
        base_path=str(base_path),
        state="pahang",
        po_number="PO1",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
    )
    return ProjectEnvironment(metadata=metadata, storage=LocalWorkspaceStorage(base_path))


def run_project_action(behaviour, environment: ProjectEnvironment) -> None:
    """Choose one fake project workflow from the menu, then leave the menu."""
    action = ProjectWorkflowAction("Fake Workflow", runner_factory=lambda: behaviour)
    session = CliSession(
        persistence_file=Path(environment.base_path) / ".active_project.json",
        active_project=environment,
    )
    with patch("src.cli_menu.select_project_workflow_action", side_effect=[action, None]):
        _run_project_workflow_menu(session, [action])


def run_utility_action(behaviour) -> None:
    """Choose one fake utility action from the menu, then leave the menu."""
    action = UtilityAction("Fake Utility", lambda: behaviour)
    with patch("src.cli_menu.select_utility_action", side_effect=[action, None]):
        _run_utility_actions_menu([action])


def read_entries(folder: Path) -> list[dict]:
    """Read the single Run Record in a folder as a list of JSON entries."""
    records = list(folder.glob("*.jsonl"))
    assert len(records) == 1, f"expected one Run Record in {folder}, found {records}"
    return [json.loads(line) for line in records[0].read_text(encoding="utf-8").splitlines()]


def entries_of(entries: list[dict], entry_type: str) -> list[dict]:
    return [entry for entry in entries if entry["type"] == entry_type]


@pytest.fixture
def locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Production location rules, with the project and per-user folders under tmp_path."""
    project = tmp_path / "project"
    project.mkdir()
    local_app_data = tmp_path / "local_app_data"
    monkeypatch.delenv(RECORD_DIR_OVERRIDE_VARIABLE)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(
        project=project,
        project_logs=project / "logs",
        fallback_logs=local_app_data / "pahang-cli" / "logs",
        environment=make_environment(project),
    )


def test_project_workflow_saves_one_run_record_in_project_logs(locations) -> None:
    run_project_action(lambda environment: None, locations.environment)

    entries = read_entries(locations.project_logs)

    assert entries[0]["type"] == "run_start"
    assert entries[0]["label"] == "Fake Workflow"
    assert entries[0]["project_key"] == "fake_project"
    assert entries[-1]["type"] == "run_finish"
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["duration_seconds"] >= 0


def test_record_holds_app_git_python_word_and_excel_versions(locations) -> None:
    run_project_action(lambda environment: None, locations.environment)

    environment_entry = entries_of(read_entries(locations.project_logs), "environment")[0]

    assert environment_entry["app_version"] == __version__
    for field in ("git_sha", "python", "word", "excel"):
        assert isinstance(environment_entry[field], str) and environment_entry[field]


def test_failed_run_records_full_traceback_and_console_shows_path(locations, capsys) -> None:
    def inner_failure() -> None:
        raise RuntimeError("template is broken")

    def failing(environment) -> None:
        inner_failure()

    run_project_action(failing, locations.environment)

    entries = read_entries(locations.project_logs)
    error = entries_of(entries, "error")[0]
    assert "template is broken" in error["message"]
    assert "inner_failure" in error["traceback"]
    assert "Traceback (most recent call last)" in error["traceback"]
    assert entries[-1] == {**entries[-1], "type": "run_finish", "status": "failed"}

    console = capsys.readouterr().out
    assert "Action failed: template is broken" in console
    record_path = next(locations.project_logs.glob("*.jsonl"))
    assert str(record_path) in console


def test_successful_run_does_not_show_the_record_path(locations, capsys) -> None:
    run_project_action(lambda environment: None, locations.environment)

    record_path = next(locations.project_logs.glob("*.jsonl"))
    assert str(record_path) not in capsys.readouterr().out


def test_settings_style_action_is_not_recorded(locations) -> None:
    from src.workflow_cli import _run_settings_menu

    session = CliSession(persistence_file=locations.project / ".active_project.json")
    with (
        patch("src.cli_menu.select_settings_action", side_effect=["configure_cameras", None]),
        patch("src.settings_actions.run_configure_camera_patterns"),
    ):
        _run_settings_menu(session)

    assert not locations.project_logs.exists()
    assert not locations.fallback_logs.exists()
