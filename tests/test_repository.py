from pathlib import Path
import json
import pytest

import config
from src.project.models import ProjectMetadata, HealthCheckItem, WorkspaceHealth
from src.project.repository import JsonFileProjectRepository
from src.project.storage import LocalWorkspaceStorage
from src.cli_session import CliSession


def test_repository_update_base_path(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    repo = JsonFileProjectRepository(config_file=config_file)

    meta = ProjectMetadata(
        key="pahang_test_2026_cycle1",
        name="Pahang Test",
        po_number="42239999",
        state="pahang",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path / "old_path"),
    )
    repo.save(meta)

    new_path = tmp_path / "new_workspace_path"
    repo.update_base_path("pahang_test_2026_cycle1", str(new_path))

    updated = repo.get("pahang_test_2026_cycle1")
    assert updated.base_path == str(new_path)
    assert (new_path / "PYTHON").exists()
    assert (new_path / "RAW MATERIAL").exists()


def test_repository_update_project(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    repo = JsonFileProjectRepository(config_file=config_file)

    meta = ProjectMetadata(
        key="pahang_test_2026_cycle1",
        name="Pahang Test",
        po_number="42239999",
        state="pahang",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path / "workspace"),
    )
    repo.save(meta)

    updated_meta = ProjectMetadata(
        key="pahang_test_2026_cycle1",
        name="Pahang Test Updated",
        po_number="42238888",
        state="pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 2",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path / "workspace"),
    )
    repo.update(updated_meta)

    retrieved = repo.get("pahang_test_2026_cycle1")
    assert retrieved.name == "Pahang Test Updated"
    assert retrieved.po_number == "42238888"
    assert retrieved.voltage_type == "33kV"
    assert retrieved.cycle == "Cycle 2"


def test_repository_delete_resets_active_session(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    orig_config = config._CONFIG_FILE
    config._CONFIG_FILE = str(config_file)

    try:
        persistence_file = tmp_path / ".active_project.json"
        repo = JsonFileProjectRepository(config_file=config_file)
        session = CliSession(persistence_file=persistence_file)

        meta = ProjectMetadata(
            key="pahang_test_2026_cycle1",
            name="Pahang Test",
            po_number="42239999",
            state="pahang",
            voltage_type="11kV",
            year="2026",
            cycle="Cycle 1",
            technologies=("IR", "US", "TEV"),
            base_path=str(tmp_path / "workspace"),
        )
        repo.save(meta)

        # Activate project
        from src.project.environment import create_project_environment
        env = create_project_environment("pahang_test_2026_cycle1", repository=repo, validate=False)
        session.activate_project(env)
        assert session.load_last_project_key() == "pahang_test_2026_cycle1"

        # Delete project using repo.delete(key, session=session)
        repo.delete("pahang_test_2026_cycle1", session=session)

        assert len(repo.list_all()) == 0
        assert session.active_project_key is None
        assert session.load_last_project_key() is None
    finally:
        config._CONFIG_FILE = orig_config



def test_workspace_health_check(tmp_path: Path) -> None:
    workspace = tmp_path / "test_workspace"
    storage = LocalWorkspaceStorage(workspace)

    # Initially missing
    health_before = storage.check_workspace_health()
    assert health_before.is_healthy is False
    assert any(item.exists is False for item in health_before.items)

    # Create workspace subfolders & files
    (workspace / "PYTHON" / "ENGR FROM DRIVE").mkdir(parents=True)
    (workspace / "TESTSHEET").mkdir(parents=True)
    (workspace / "RAW MATERIAL").mkdir(parents=True)
    (workspace / "QUICK REPORT").mkdir(parents=True)
    (workspace / "PYTHON" / "TOTAL PE.xlsx").touch()
    (workspace / "PYTHON" / "DATA MSMS.xlsx").touch()

    health_after = storage.check_workspace_health()
    assert health_after.is_healthy is True
    assert all(item.exists for item in health_after.items if item.is_critical)
