"""Unit tests for PrpdConfig and ProjectRepository settings persistence."""

from pathlib import Path
import pytest

from src.project.models import ProjectMetadata, PrpdConfig, PrpdMode, VALID_PRPD_MODES
import src.project.models as project_models
from src.project.repository import JsonFileProjectRepository
from src.project.environment import ProjectEnvironment
from src.project.storage import LocalWorkspaceStorage


def test_prpd_mode_type_and_all_export():
    """Test PrpdMode is exported in __all__ and VALID_PRPD_MODES is immutable."""
    assert "PrpdMode" in project_models.__all__
    assert "VALID_PRPD_MODES" in project_models.__all__
    assert VALID_PRPD_MODES == ("option_c", "option_b")


def test_prpd_config_defaults():
    """Test PrpdConfig defaults to option_c."""
    cfg = PrpdConfig()
    assert cfg.mode == "option_c"
    assert cfg.to_dict() == {"mode": "option_c"}


def test_prpd_config_custom_and_fallback():
    """Test PrpdConfig accepts valid modes and falls back on invalid values."""
    cfg_b = PrpdConfig(mode="option_b")
    assert cfg_b.mode == "option_b"
    assert cfg_b.to_dict() == {"mode": "option_b"}

    # Invalid mode fallback in __post_init__
    cfg_invalid = PrpdConfig(mode="invalid_mode")
    assert cfg_invalid.mode == "option_c"

    # from_dict with valid data
    from_dict_b = PrpdConfig.from_dict({"mode": "option_b"})
    assert from_dict_b.mode == "option_b"

    # from_dict with invalid data
    from_dict_invalid = PrpdConfig.from_dict({"mode": "xyz"})
    assert from_dict_invalid.mode == "option_c"

    # from_dict with None or empty
    from_dict_none = PrpdConfig.from_dict(None)
    assert from_dict_none.mode == "option_c"


def test_repository_prpd_config_persistence(tmp_path: Path):
    """Test saving and retrieving PrpdConfig from JsonFileProjectRepository."""
    config_file = tmp_path / ".cli_config.json"
    repo = JsonFileProjectRepository(config_file=config_file)

    # Initial get should return default
    initial = repo.get_prpd_config()
    assert initial.mode == "option_c"

    # Save option_b
    repo.save_prpd_config(PrpdConfig(mode="option_b"))
    retrieved = repo.get_prpd_config()
    assert retrieved.mode == "option_b"

    # Save option_c
    repo.save_prpd_config(PrpdConfig(mode="option_c"))
    retrieved_c = repo.get_prpd_config()
    assert retrieved_c.mode == "option_c"


def test_environment_prpd_config_persistence(tmp_path: Path):
    """Test ProjectEnvironment get_prpd_config and save_prpd_config."""
    config_file = tmp_path / ".cli_config.json"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)

    repo = JsonFileProjectRepository(config_file=config_file)
    meta = ProjectMetadata(
        key="pahang_prpd_test",
        name="Pahang PRPD Test",
        po_number="42000000",
        state="pahang",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(workspace_dir),
    )
    repo.save(meta)

    storage = LocalWorkspaceStorage(workspace_dir)
    env = ProjectEnvironment(metadata=meta, storage=storage, repository=repo)

    # Initial default from environment
    assert env.get_prpd_config().mode == "option_c"

    # Update through environment
    env.save_prpd_config(PrpdConfig(mode="option_b"))
    assert env.get_prpd_config().mode == "option_b"
    # Verify persisted in project_config.json
    assert (workspace_dir / "project_config.json").exists()
