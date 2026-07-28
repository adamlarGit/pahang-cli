from pathlib import Path
import pytest

import config
from src.project.models import ProjectMetadata
from src.project.repository import JsonFileProjectRepository
from src.cli_session import CliSession
from src.project.management import add_new_project_wizard, select_active_project_wizard
from src.project_settings_actions import (
    handle_view_project_info,
    handle_switch_project,
    handle_update_project_path,
    handle_unregister_project,
)


def test_add_new_project_wizard_programmatic(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    repo = JsonFileProjectRepository(config_file=config_file)
    session = CliSession(persistence_file=tmp_path / ".active_project.json")

    workspace = tmp_path / "kuantan_workspace"

    meta = add_new_project_wizard(
        name="Pahang Kuantan",
        po_number="42239999",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        base_path=str(workspace),
        repository=repo,
        session=session,
    )

    assert meta is not None
    assert meta.key == "pahang_kuantan_2026_cycle1"
    assert repo.get("pahang_kuantan_2026_cycle1").po_number == "42239999"
    assert session.active_project_key == "pahang_kuantan_2026_cycle1"
    assert (workspace / "PYTHON").exists()



def test_handle_view_project_info(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_file = tmp_path / ".cli_config.json"
    orig_config = config._CONFIG_FILE
    config._CONFIG_FILE = str(config_file)

    try:
        repo = JsonFileProjectRepository(config_file=config_file)
        session = CliSession(persistence_file=tmp_path / ".active_project.json")

        workspace = tmp_path / "view_workspace"
        workspace.mkdir()

        meta = ProjectMetadata(
            key="pahang_view_2026_cycle1",
            name="Pahang View Test",
            po_number="42231111",
            state="pahang",
            voltage_type="11kV",
            year="2026",
            cycle="Cycle 1",
            technologies=("IR", "US", "TEV"),
            base_path=str(workspace),
        )
        repo.save(meta)

        from src.project.environment import create_project_environment
        env = create_project_environment("pahang_view_2026_cycle1", repository=repo, validate=False)
        session.activate_project(env)

        handle_view_project_info(session, repository=repo, pause=False)


        captured = capsys.readouterr().out
        assert "ACTIVE PROJECT DETAILS" in captured
        assert "Pahang View Test" in captured
        assert "WORKSPACE FOLDER STATUS" in captured
    finally:
        config._CONFIG_FILE = orig_config


def test_handle_update_project_path_programmatic(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    repo = JsonFileProjectRepository(config_file=config_file)
    session = CliSession(persistence_file=tmp_path / ".active_project.json")

    old_path = tmp_path / "old_workspace"
    new_path = tmp_path / "new_workspace"

    meta = ProjectMetadata(
        key="pahang_update_2026_cycle1",
        name="Pahang Update Test",
        po_number="42232222",
        state="pahang",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(old_path),
    )
    repo.save(meta)

    handle_update_project_path(
        project_key="pahang_update_2026_cycle1",
        new_path=str(new_path),
        session=session,
        repository=repo,
    )

    updated = repo.get("pahang_update_2026_cycle1")
    assert updated.base_path == str(new_path)
    assert (new_path / "PYTHON").exists()


def test_handle_unregister_project_programmatic(tmp_path: Path) -> None:
    config_file = tmp_path / ".cli_config.json"
    orig_config = config._CONFIG_FILE
    config._CONFIG_FILE = str(config_file)

    try:
        repo = JsonFileProjectRepository(config_file=config_file)
        session = CliSession(persistence_file=tmp_path / ".active_project.json")

        meta = ProjectMetadata(
            key="pahang_del_2026_cycle1",
            name="Pahang Del Test",
            po_number="42233333",
            state="pahang",
            voltage_type="11kV",
            year="2026",
            cycle="Cycle 1",
            technologies=("IR", "US", "TEV"),
            base_path=str(tmp_path / "del_workspace"),
        )
        repo.save(meta)

        from src.project.environment import create_project_environment
        env = create_project_environment("pahang_del_2026_cycle1", repository=repo, validate=False)
        session.activate_project(env)

        handle_unregister_project(
            project_key="pahang_del_2026_cycle1",
            session=session,
            repository=repo,
        )

        assert len(repo.list_all()) == 0
        assert session.active_project_key is None
    finally:
        config._CONFIG_FILE = orig_config
