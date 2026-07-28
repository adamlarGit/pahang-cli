import os
from pathlib import Path

import config
from src.project.storage import LocalWorkspaceStorage

def test_local_workspace_storage_template_resolution(tmp_path: Path) -> None:
    # Setup global template mock
    original_global_templates = config.GLOBAL_TEMPLATES_DIR
    original_templates = config.TEMPLATES
    original_seed_files = getattr(config, "SEED_FILES", {})

    mock_global_templates = tmp_path / "global_templates"
    mock_global_templates.mkdir()
    config.GLOBAL_TEMPLATES_DIR = mock_global_templates
    
    mock_template_rel = "QUICK REPORT/template.docx"
    config.TEMPLATES = {"test_template": mock_template_rel}
    
    mock_seed_rel = "PYTHON/SEED.xlsx"
    config.SEED_FILES = {mock_seed_rel: mock_seed_rel}

    (mock_global_templates / "QUICK REPORT").mkdir(parents=True)
    (mock_global_templates / mock_template_rel).touch()

    (mock_global_templates / "PYTHON").mkdir(parents=True)
    (mock_global_templates / mock_seed_rel).touch()

    try:
        project_root = tmp_path / "project_root"
        project_root.mkdir()

        # Initialize storage and trigger bootstrap
        storage = LocalWorkspaceStorage(project_root)
        storage._initialize_project_workspace()

        # Verify templates dir defaults to <base_path>/templates
        assert storage._templates_dir == project_root / "templates"

        # Verify template resolution from project workspace templates
        resolved_path = storage.resolve_template_path("test_template")
        assert resolved_path == project_root / "templates" / mock_template_rel
        assert resolved_path.exists()

        # Verify seed file copied to correct path
        seed_target = project_root / mock_seed_rel
        assert seed_target.exists()

    finally:
        # Restore original config
        config.GLOBAL_TEMPLATES_DIR = original_global_templates
        config.TEMPLATES = original_templates
        config.SEED_FILES = original_seed_files
